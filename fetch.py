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


_ENGAGEMENT_RE = re.compile(r'^\d+(?:[.,]\d+)?[KMBkmb]?$')


def _strip_article_header(text, article_title):
    """Remove X article page chrome (duplicate title, author, nav stats) from main inner_text."""
    lines = text.split('\n')
    i = 0
    # Skip duplicate title line
    if lines and lines[i].strip() == article_title:
        i += 1
    # Skip short nav lines (author name, @handle, ·, date, Subscribe, numeric stats)
    while i < len(lines):
        line = lines[i].strip()
        if line and len(line) > 30:
            break
        i += 1
    return '\n'.join(lines[i:]).strip()


_ARTICLE_PAGE_FOOTER = "Want to publish your own Article?"


def _strip_article_footer(text):
    """Strip X article page footer and trailing engagement-number lines."""
    # Cut at the standard X article page footer marker
    idx = text.find(_ARTICLE_PAGE_FOOTER)
    if idx != -1:
        text = text[:idx].rstrip()
    # Walk backwards: also drop blank lines and standalone engagement-stat lines at tail
    lines = text.split('\n')
    cut = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if not line or _ENGAGEMENT_RE.match(line):
            cut = i
        else:
            break
    return '\n'.join(lines[:cut]).rstrip()


def fetch_article_body(tweet_url, article_title, article_rest_id=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ! playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    # /i/article/{rest_id} when available; else derive from tweet URL (/status/ → /article/)
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
            # Initial wait for JS hydration; X.com never reaches networkidle (websockets)
            page.wait_for_timeout(5000)
            # Scroll to trigger lazy-loaded article content below the fold
            for _ in range(6):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)

            for selector in [
                "[data-testid='article-content']",
                "[data-testid='articleContent']",
                "article",
                "main",
            ]:
                el = page.query_selector(selector)
                if el:
                    raw = el.inner_text().strip()
                    text = _strip_article_header(raw, article_title)
                    text = _strip_article_footer(text)
                    if len(text) > 500:
                        browser.close()
                        return text
            browser.close()
            return None
    except Exception as e:
        print(f"  ! Playwright fetch failed: {e}")
        return None


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
            body = f"# {tweet['article_title']}\n\n{full_body}{cover_line}"
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


def main():
    if not CT0 or not AUTH_TOKEN:
        print("Missing env vars. Export before running:")
        print("  export X_CT0=<ct0 cookie value>")
        print("  export X_AUTH_TOKEN=<auth_token cookie value>")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
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
