---
name: x-bookmarks
description: Fetches X/Twitter bookmarks via cookie auth and saves each as a Markdown file optimized for Obsidian. Use when user says "fetch bookmarks", "sync x bookmarks", "import twitter bookmarks", "x bookmarks to markdown", or invokes /x-bookmarks.
---

# X Bookmarks → Markdown

Fetches all X/Twitter bookmarks and writes one `.md` file per tweet.

## Required env vars

```
X_CT0=<ct0 cookie value>
X_AUTH_TOKEN=<auth_token cookie value>
```

Optional:
- `X_BOOKMARKS_OUTPUT_DIR` (default: `~/.x-bookmarks/`)
- `XAI_API_KEY` — xAI Grok API key. When set, fetches **full X article body** instead of preview. Get at https://console.x.ai

## How to get credentials

1. Open x.com in browser, log in
2. DevTools (F12) → Application → Cookies → `https://x.com`
3. Copy `ct0` value → set as `X_CT0`
4. Copy `auth_token` value → set as `X_AUTH_TOKEN`

Export in shell before running:
```bash
export X_CT0=your_ct0_value
export X_AUTH_TOKEN=your_auth_token_value
```

## Run

First time — create venv and install deps:
```bash
python3 -m venv /tmp/xbm-venv
/tmp/xbm-venv/bin/pip install requests -q

# For full X Article body with rich formatting (optional, ~130 MB one-time download):
/tmp/xbm-venv/bin/pip install playwright markdownify -q
/tmp/xbm-venv/bin/playwright install chromium
```

Then run (Claude uses Bash tool, or user runs in terminal):
```bash
/tmp/xbm-venv/bin/python ~/.claude/skills/x-bookmarks/fetch.py
```

Note: `/tmp/xbm-venv` is ephemeral. Re-create after reboot. Alternatively install permanently:
```bash
pip3 install --user requests  # if allowed by system
```

## Output format

Filename: `{tweet_id}_{username}.md`

```markdown
---
author: "@username"
date: 2024-01-15
url: https://x.com/username/status/1234567890
tags: ["tweet", "bookmark", "ai", "python"]
---

Tweet text here.

![](https://pbs.twimg.com/media/example.jpg)
```

## Behavior

- **Incremental**: stops pagination when first existing file found — safe to re-run anytime
- **Dedup**: skips write if `{tweet_id}_{username}.md` already exists
- **Rate limit**: 1s sleep between pages; exits with clear message on 429
- **Media**: photos embed inline (`![](url)`); videos link to highest-bitrate mp4
- **Tags**: static `tweet`/`bookmark` + hashtags extracted from tweet text

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Missing env vars` | Export `X_CT0` and `X_AUTH_TOKEN` |
| `401` or empty results | Cookies expired — re-copy from browser |
| `429 Rate limited` | Wait 15 min, re-run |
| `queryId error` / empty data | X changed GraphQL queryId — update `BOOKMARKS_QUERY_ID` in `fetch.py` by inspecting network tab on x.com/bookmarks |
