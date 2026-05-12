#!/usr/bin/env python3
import os
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests")
    sys.exit(1)

CT0 = os.environ.get("X_CT0")
AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN")
OUTPUT_DIR = Path(os.environ.get("X_BOOKMARKS_OUTPUT_DIR", "~/.x-bookmarks/")).expanduser()
XAI_API_KEY = os.environ.get("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/responses"
XAI_MODEL = "grok-3-mini"

BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

# If X changes this, inspect network tab on x.com/bookmarks to find new queryId
BOOKMARKS_QUERY_ID = "ojgFx9G-r0OkXCFVN9k5oA"
BOOKMARKS_URL = f"https://x.com/i/api/graphql/{BOOKMARKS_QUERY_ID}/Bookmarks"

FEATURES = {
    "graphql_timeline_v2_bookmark_timeline": True,
    "rweb_lists_timeline_redesign_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "articles_preview_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_the_sky_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


def headers():
    return {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "X-Csrf-Token": CT0,
        "Cookie": f"auth_token={AUTH_TOKEN}; ct0={CT0}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Twitter-Active-User": "yes",
        "X-Twitter-Auth-Type": "OAuth2Session",
        "X-Twitter-Client-Language": "en",
    }


def fetch_page(cursor=None):
    variables = {"count": 20, "includePromotedContent": False}
    if cursor:
        variables["cursor"] = cursor

    params = {
        "variables": json.dumps(variables),
        "features": json.dumps(FEATURES),
    }

    r = requests.get(BOOKMARKS_URL, headers=headers(), params=params, timeout=30)

    if r.status_code == 429:
        print("Rate limited (429). Wait ~15 min then re-run.")
        sys.exit(1)
    if r.status_code in (401, 403):
        print(f"Auth error ({r.status_code}). Re-copy ct0 and auth_token from browser.")
        sys.exit(1)
    if r.status_code != 200:
        print(f"Error {r.status_code}: {r.text[:300]}")
        sys.exit(1)

    return r.json()


def parse_page(data):
    tweets = []
    next_cursor = None

    try:
        instructions = data["data"]["bookmark_timeline_v2"]["timeline"]["instructions"]
    except KeyError:
        print("Unexpected API response structure. X may have changed their API.")
        print("Raw response keys:", list(data.keys()))
        return tweets, next_cursor

    entries = []
    for instruction in instructions:
        if instruction.get("type") == "TimelineAddEntries":
            entries = instruction.get("entries", [])
            break

    for entry in entries:
        entry_id = entry.get("entryId", "")

        if "cursor-bottom" in entry_id:
            try:
                next_cursor = entry["content"]["value"]
            except KeyError:
                pass
            continue

        try:
            item_content = entry["content"]["itemContent"]
            result = item_content["tweet_results"]["result"]
            tweet_obj = result.get("tweet", result)

            legacy = tweet_obj["legacy"]
            user_result = tweet_obj["core"]["user_results"]["result"]
            user_core = user_result.get("core") or user_result.get("legacy", {})

            tweet_id = legacy["id_str"]
            username = user_core["screen_name"]
            full_text = legacy["full_text"]
            created_at = legacy["created_at"]

            dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S +0000 %Y")
            date_str = dt.strftime("%Y-%m-%d")

            media_urls = []
            extended = legacy.get("extended_entities", {})
            for m in extended.get("media", []):
                if m["type"] == "photo":
                    media_urls.append(m["media_url_https"])
                elif m["type"] in ("video", "animated_gif"):
                    variants = m.get("video_info", {}).get("variants", [])
                    mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
                    if mp4s:
                        best = max(mp4s, key=lambda v: v.get("bitrate", 0))
                        media_urls.append(best["url"])

            hashtags = [
                h["text"].lower()
                for h in legacy.get("entities", {}).get("hashtags", [])
            ]

            # Detect X Article
            article_data = tweet_obj.get("article", {}).get("article_results", {}).get("result", {})
            article_title = article_data.get("title")
            article_preview = article_data.get("preview_text")
            article_cover = (
                article_data.get("cover_media", {})
                .get("media_info", {})
                .get("original_img_url")
            )
            article_rest_id = article_data.get("rest_id")

            tweets.append({
                "id": tweet_id,
                "username": username,
                "date": date_str,
                "text": full_text,
                "url": f"https://x.com/{username}/status/{tweet_id}",
                "media": media_urls,
                "hashtags": hashtags,
                "article_title": article_title,
                "article_preview": article_preview,
                "article_cover": article_cover,
                "article_rest_id": article_rest_id,
            })
        except (KeyError, TypeError):
            continue

    return tweets, next_cursor


def html_to_article_markdown(html: str) -> str:
    from markdownify import markdownify as _md
    return _md(html, heading_style="ATX", code_language="", newline_style="backslash").strip()


def clean_article_markdown(text: str, article_title: str = None) -> str:
    lines = text.split("\n")

    # Remove duplicate title at top (markdownify often repeats it)
    if article_title:
        cleaned_start = []
        title_removed = False
        for line in lines:
            stripped = line.strip()
            if not title_removed and stripped and stripped == article_title:
                title_removed = True
                continue
            cleaned_start.append(line)
        lines = cleaned_start

    # Remove orphan profile image links: [![](twimg profile pic)](/user)
    lines = [l for l in lines if not re.match(
        r'^\s*\[?\!?\[.*?\]\(https?://pbs\.twimg\.com/profile_images/.*?\)\]?\(?/.*?\)?\s*$', l
    )]

    # Strip chrome/engagement lines
    chrome_patterns = [
        r'^\s*·\s*$',
        r'^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+\s*$',
        r'^\s*·\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+\s*$',
        r'^\s*Subscribe\s*$',
        r'^\s*Click to (Subscribe|Unfollow).*$',
        r'^\s*Following\s*$',
        r'^\s*Want to publish your own Article\?\s*$',
        r'^\s*\[Upgrade to Premium\].*$',
        r'^\s*\d+(\.\d+)?[KMB]?\s*$',
        r'^\s*\[\d+(\.\d+)?[KMB]?\]\(.*?/analytics\)\s*$',
        r'^\s*\[@\w+\]\(/\w+\)\s*$',
        r'^\s*!\[\]\(https?://pbs\.twimg\.com/profile_images/.*?\)\s*$',
    ]
    chrome_re = re.compile("|".join(f"({p})" for p in chrome_patterns))
    lines = [l for l in lines if not chrome_re.match(l)]

    # Remove multi-line author name blocks: "[Name\n...\n](/user)"
    # Also remove orphan "[Name" lines left after profile image removal
    cleaned = []
    i = 0
    while i < len(lines):
        if re.match(r'^\s*\[[\w\s]+$', lines[i]) and not lines[i].strip().startswith('[http'):
            found_close = False
            for j in range(i + 1, min(i + 6, len(lines))):
                if re.match(r'^\s*\]\(/\w+\)\s*$', lines[j]):
                    found_close = True
                    i = j + 1
                    break
            if found_close:
                continue
            # Orphan open bracket with just a name — skip it too
            if re.match(r'^\s*\[\w[\w\s]*$', lines[i].rstrip()):
                i += 1
                continue
        cleaned.append(lines[i])
        i += 1
    lines = cleaned

    # Remove trailing author bio card
    cut_idx = None
    for i in range(len(lines) - 1, max(len(lines) - 40, -1), -1):
        if re.match(r'^\s*-\s*\[?\!?\[.*?\]\(https?://pbs\.twimg\.com/profile_images/', lines[i]):
            cut_idx = i
            break
        # Also match: "- [@username](/username)" pattern
        if re.match(r'^\s*-\s*\[@\w+\]\(/\w+\)', lines[i]):
            cut_idx = i
            break
    if cut_idx is not None:
        lines = lines[:cut_idx]

    # Collapse 3+ consecutive blank lines to 2
    result = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)

    # Rejoin broken inline links: markdownify splits "[text](url)" onto separate lines
    # when the original HTML had block-level <a> tags.
    joined = []
    i = 0
    while i < len(result):
        line = result[i]
        if line.strip() and i + 1 < len(result):
            buf = line.rstrip()
            j = i + 1
            has_link = bool(re.search(r'\[.+?\]\(.+?\)', buf))
            while j < len(result):
                if result[j].strip() == "" and j + 1 < len(result) and result[j + 1].strip():
                    peek = result[j + 1].strip()
                    if re.match(r'^\[.+?\]\(.+?\)', peek) or re.match(r'^[,;.]', peek):
                        j += 1
                        continue
                    elif has_link and re.match(r'^[a-z]', peek):
                        j += 1
                        continue
                    else:
                        break
                elif result[j].strip() == "":
                    break
                else:
                    stripped = result[j].strip()
                    if re.match(r'^\[.+?\]\(.+?\)\s*[,;.]?\s*$', stripped) or re.match(r'^[,;.]\s*', stripped):
                        if re.match(r'^[,;.]', stripped):
                            buf = buf + stripped
                        else:
                            buf = buf + " " + stripped
                        has_link = True
                        j += 1
                        continue
                    # Lowercase continuation directly after a link line
                    elif has_link and re.match(r'^[a-z]', stripped):
                        buf = buf + " " + stripped
                        j += 1
                        while j < len(result) and result[j].strip() and not re.match(r'^#{1,6}\s', result[j].strip()):
                            nxt = result[j].strip()
                            if re.match(r'^\[.+?\]\(.+?\)', nxt):
                                buf = buf + " " + nxt
                                has_link = True
                                j += 1
                                continue
                            elif re.match(r'^[,;.]', nxt):
                                buf = buf + nxt
                                j += 1
                                continue
                            else:
                                buf = buf + " " + nxt
                                j += 1
                        break
                    else:
                        if has_link and buf != line.rstrip():
                            buf = buf + " " + stripped
                            j += 1
                            while j < len(result) and result[j].strip() and not re.match(r'^#{1,6}\s', result[j].strip()):
                                buf = buf + " " + result[j].strip()
                                j += 1
                        break
                j += 1
            if j > i + 1:
                joined.append(buf)
                i = j
                continue
        joined.append(line)
        i += 1

    # Second pass: merge paragraphs split by blank lines when next starts with [link](url)
    # followed by continuation text (same paragraph broken by markdownify)
    # Run iteratively until no more merges happen
    changed = True
    while changed:
        changed = False
        merged = []
        i = 0
        while i < len(joined):
            line = joined[i]
            if (line.strip()
                and not re.match(r'^#{1,6}\s', line.strip())
                and not re.match(r'^\s*[-*\d]', line.strip())
                and i + 2 < len(joined)
                and joined[i + 1].strip() == ""
                and re.match(r'^\[.+?\]\(.+?\)\s', joined[i + 2].strip())):
                merged.append(line.rstrip() + " " + joined[i + 2].strip())
                i += 3
                changed = True
                continue
            merged.append(line)
            i += 1
        joined = merged

    return "\n".join(merged).strip()


def fetch_article_body(tweet_url, article_title, article_rest_id=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ! playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    try:
        from markdownify import markdownify  # noqa: F401 — verify dep before launching browser
    except ImportError:
        print("  ! markdownify not installed. Run: pip install markdownify")
        return None

    article_url = f"https://x.com/i/article/{article_rest_id}" if article_rest_id else tweet_url.replace("/status/", "/article/")
    print(f"  [playwright] fetching {article_url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ))
            ctx.add_cookies([
                {"name": "auth_token", "value": AUTH_TOKEN, "domain": ".x.com", "path": "/"},
                {"name": "ct0", "value": CT0, "domain": ".x.com", "path": "/"},
            ])
            page = ctx.new_page()
            page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            for _ in range(6):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)

            # Remove chrome: header/nav/footer/byline/stats before extracting content
            page.evaluate("""() => {
                const noise = [
                    'header', 'nav', 'footer',
                    '[data-testid="article-header"]',
                    '[data-testid="article-footer"]',
                    '[data-testid="articleHeader"]',
                    '[data-testid="articleFooter"]',
                    '[data-testid="sheetDialog"]',
                    '[data-testid="User-Name"]',
                    '[data-testid="caret"]',
                    '[data-testid="app-text-transition-container"]',
                    '[role="group"]',
                    '[aria-label="Subscribe"]',
                    '[aria-label*="Subscribe to"]',
                    '[aria-label*="Unfollow"]',
                    'a[href*="/i/premium_sign_up"]',
                ];
                noise.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
                // Remove small profile avatar images in byline area
                document.querySelectorAll('img[src*="/profile_images/"]').forEach(el => {
                    const w = el.width || el.naturalWidth || 0;
                    if (w <= 48) el.closest('a')?.remove() || el.remove();
                });
            }""")

            for selector in [
                "[data-testid='article-content']",
                "[data-testid='articleContent']",
                "article",
                "main",
            ]:
                el = page.query_selector(selector)
                if el:
                    html = el.inner_html()
                    text = clean_article_markdown(
                        html_to_article_markdown(html), article_title
                    )
                    if len(text) > 500:
                        browser.close()
                        return text
            browser.close()
            return None
    except Exception as e:
        print(f"  ! Playwright fetch failed: {e}")
        return None


TWEET_DETAIL_QUERY_ID = "xOhkmRac04YFZmOzU9PJHg"
TWEET_DETAIL_URL = f"https://x.com/i/api/graphql/{TWEET_DETAIL_QUERY_ID}/TweetDetail"


def fetch_single_tweet_data(tweet_id):
    variables = {
        "focalTweetId": tweet_id,
        "with_rux_injections": False,
        "rankingMode": "Relevance",
        "includePromotedContent": True,
        "withCommunity": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withBirdwatchNotes": True,
        "withVoice": True,
    }
    tweet_features = {
        **FEATURES,
        "rweb_tipjar_consumption_enabled": True,
        "creator_subscriptions_quote_tweet_preview_enabled": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "articles_preview_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
    }
    params = {
        "variables": json.dumps(variables),
        "features": json.dumps(tweet_features),
    }
    r = requests.get(TWEET_DETAIL_URL, headers=headers(), params=params, timeout=30)
    if r.status_code != 200:
        print(f"Error {r.status_code}: {r.text[:300]}")
        sys.exit(1)

    data = r.json()
    tweet_obj = None
    # TweetDetail may return either key depending on query version
    conv = (
        data.get("data", {}).get("threaded_conversation_with_injections_v2")
        or data.get("data", {}).get("threaded_conversation_with_injections")
    )
    try:
        entries = conv["instructions"][0]["entries"]
        for entry in entries:
            if entry.get("entryId", "").startswith(f"tweet-{tweet_id}"):
                item = entry["content"]["itemContent"]["tweet_results"]["result"]
                tweet_obj = item.get("tweet", item)
                break
    except (KeyError, TypeError, IndexError):
        pass

    if tweet_obj is None:
        # Fallback: tweetResult path
        try:
            result = data["data"]["tweetResult"]["result"]
            tweet_obj = result.get("tweet", result)
        except (KeyError, TypeError):
            print("Tweet not found in response.")
            sys.exit(1)

    legacy = tweet_obj["legacy"]
    user_result = tweet_obj["core"]["user_results"]["result"]
    user_core = user_result.get("core") or user_result.get("legacy", {})

    username = user_core["screen_name"]
    full_text = legacy["full_text"]
    created_at = legacy["created_at"]
    dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S +0000 %Y")
    date_str = dt.strftime("%Y-%m-%d")

    media_urls = []
    extended = legacy.get("extended_entities", {})
    for m in extended.get("media", []):
        if m["type"] == "photo":
            media_urls.append(m["media_url_https"])
        elif m["type"] in ("video", "animated_gif"):
            variants = m.get("video_info", {}).get("variants", [])
            mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
            if mp4s:
                best = max(mp4s, key=lambda v: v.get("bitrate", 0))
                media_urls.append(best["url"])

    hashtags = [h["text"].lower() for h in legacy.get("entities", {}).get("hashtags", [])]

    # Article data lives at different paths depending on API endpoint
    article_raw = tweet_obj.get("article", {})
    article_data = (
        article_raw.get("article_results", {}).get("result")
        or article_raw.get("article")
        or {}
    )
    article_title = article_data.get("title")
    article_preview = article_data.get("preview_text")
    article_cover = (
        article_data.get("cover_media", {})
        .get("media_info", {})
        .get("original_img_url")
    )
    article_rest_id = article_data.get("rest_id")

    return {
        "id": tweet_id,
        "username": username,
        "date": date_str,
        "text": full_text,
        "url": f"https://x.com/{username}/status/{tweet_id}",
        "media": media_urls,
        "hashtags": hashtags,
        "article_title": article_title,
        "article_preview": article_preview,
        "article_cover": article_cover,
        "article_rest_id": article_rest_id,
    }




def safe_username(username):
    return re.sub(r"[^\w\-]", "_", username)


def write_tweet(tweet):
    filename = f"{tweet['id']}_{safe_username(tweet['username'])}.md"
    filepath = OUTPUT_DIR / filename

    if filepath.exists():
        return False

    is_article = bool(tweet.get("article_title"))
    base_tags = ["tweet", "bookmark"] + (["article"] if is_article else [])
    tags = base_tags + tweet["hashtags"]
    tags_yaml = json.dumps(tags)

    if is_article:
        cover_line = f"\n\n![]({tweet['article_cover']})" if tweet.get("article_cover") else ""
        full_body = fetch_article_body(tweet["url"], tweet["article_title"], tweet.get("article_rest_id"))
        if full_body:
            body = f"# {tweet['article_title']}\n\n{full_body}"
        else:
            preview = tweet.get("article_preview") or ""
            body = f"# {tweet['article_title']}\n\n{preview}…{cover_line}\n\n> [Read full article]({tweet['url']})"
    else:
        media_lines = ""
        if tweet["media"]:
            media_lines = "\n\n" + "\n".join(f"![]({url})" for url in tweet["media"])
        body = f"{tweet['text']}{media_lines}"

    content = f"""---
author: "@{tweet['username']}"
date: {tweet['date']}
url: {tweet['url']}
tags: {tags_yaml}
---

{body}
"""

    filepath.write_text(content, encoding="utf-8")
    return True


def parse_tweet_url(url):
    m = re.match(r'https?://(?:x|twitter)\.com/\w+/status/(\d+)', url)
    if m:
        return m.group(1)
    return None


def main():
    if not CT0 or not AUTH_TOKEN:
        print("Missing env vars. Export before running:")
        print("  export X_CT0=<ct0 cookie value>")
        print("  export X_AUTH_TOKEN=<auth_token cookie value>")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Single URL mode
    if len(sys.argv) > 1:
        url = sys.argv[1]
        tweet_id = parse_tweet_url(url)
        if not tweet_id:
            print(f"Invalid tweet URL: {url}")
            sys.exit(1)

        print(f"Fetching single tweet {tweet_id}...")
        tweet = fetch_single_tweet_data(tweet_id)
        written = write_tweet(tweet)
        if written:
            filename = f"{tweet['id']}_{safe_username(tweet['username'])}.md"
            print(f"  + {OUTPUT_DIR / filename}")
        else:
            filename = f"{tweet['id']}_{safe_username(tweet['username'])}.md"
            print(f"  = {filename} already exists")
        return

    # Bulk bookmarks mode
    print(f"Output: {OUTPUT_DIR}")

    cursor = None
    total_new = 0
    page = 0

    while True:
        page += 1
        print(f"Fetching page {page}...", end=" ", flush=True)

        data = fetch_page(cursor)
        tweets, next_cursor = parse_page(data)

        if not tweets:
            print(f"\nDone. {total_new} new bookmarks saved.")
            break

        print(f"{len(tweets)} tweets")

        stop = False
        for tweet in tweets:
            written = write_tweet(tweet)
            if written:
                total_new += 1
                print(f"  + {tweet['id']}_{safe_username(tweet['username'])}.md")
            else:
                print(f"  = {tweet['id']} exists — stopping (incremental sync complete)")
                stop = True
                break

        if stop or not next_cursor:
            print(f"Done. {total_new} new bookmarks saved.")
            break

        cursor = next_cursor
        time.sleep(1)


if __name__ == "__main__":
    main()
