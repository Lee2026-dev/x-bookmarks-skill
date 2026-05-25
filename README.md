# x-bookmarks

Fetches X/Twitter bookmarks and saves each as a Markdown file optimized for Obsidian.

## Setup

### 1. Choose a Backend

**Hermes Tweet / Xquik** (recommended, no browser cookies):

1. Sign in at [dashboard.xquik.com](https://dashboard.xquik.com/).
2. Open [Account > API Keys](https://dashboard.xquik.com/en/account?tab=api-keys).
3. Create an API key for this skill and copy it once.
4. Set it as `XQUIK_API_KEY` or `HERMES_TWEET_API_KEY`.

```bash
export XQUIK_API_KEY=your_xquik_key
```

Leave `XQUIK_BASE_URL` unset for the default hosted API. Set it only if you use
a compatible self-hosted endpoint. To sync one bookmark folder, set
`X_BOOKMARKS_FOLDER_ID`.

**X Cookie Credentials** (fallback):

1. Open [x.com](https://x.com) in your browser and log in
2. Open DevTools (F12) → Application → Cookies → `https://x.com`
3. Copy the `ct0` value → set as `X_CT0`
4. Copy the `auth_token` value → set as `X_AUTH_TOKEN`

### 2. Set Environment Variables

```bash
export X_CT0=your_ct0_value
export X_AUTH_TOKEN=your_auth_token_value
```

**Optional:**
- `X_BOOKMARKS_OUTPUT_DIR` — output directory (default: `~/.x-bookmarks/`)
- `X_BOOKMARKS_FOLDER_ID` — Hermes Tweet / Xquik bookmark folder ID
- `XQUIK_BASE_URL` — compatible API base URL (default: `https://xquik.com`)
- `XAI_API_KEY` — xAI Grok API key for fetching full article bodies. Get at [console.x.ai](https://console.x.ai)

### 3. Install Dependencies

```bash
python3 -m venv /tmp/xbm-venv
/tmp/xbm-venv/bin/pip install requests -q

# Optional: for full X Article body extraction (~130 MB one-time download)
/tmp/xbm-venv/bin/pip install playwright -q
/tmp/xbm-venv/bin/playwright install chromium
```

> **Note:** `/tmp/xbm-venv` is ephemeral. Re-create after reboot. Alternatively install permanently with `pip3 install --user requests`.

## Usage

```bash
/tmp/xbm-venv/bin/python ~/.claude/skills/x-bookmarks/fetch.py
```

Or if installed permanently:
```bash
python3 ~/.claude/skills/x-bookmarks/fetch.py
```

## Output

Files are saved to `~/.x-bookmarks/` (or your custom `X_BOOKMARKS_OUTPUT_DIR`).

**Filename format:** `{tweet_id}_{username}.md`

**Example:**
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

## Features

- **Incremental sync** — stops pagination when first existing file found; safe to re-run anytime
- **Deduplication** — skips write if file already exists
- **Backend selection** — uses Hermes Tweet / Xquik when an API key is set,
  otherwise uses X cookie credentials
- **Rate limiting** — 1s sleep between pages; exits with clear message on 429
- **Media support** — photos embed inline (`![](url)`); videos link to highest-bitrate mp4
- **Hashtag extraction** — static tags + hashtags from tweet text
- **X Article support** — fetches full article body via Playwright if `XAI_API_KEY` not set, otherwise uses preview

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Missing env vars` | Export `X_CT0` and `X_AUTH_TOKEN` |
| `401` or empty results | Cookies expired — re-copy from browser |
| `429 Rate limited` | Wait 15 min, then re-run |
| `queryId error` / empty data | X changed GraphQL queryId — update `BOOKMARKS_QUERY_ID` in `fetch.py` by inspecting network tab on x.com/bookmarks |

## Files

- `SKILL.md` — skill definition for Claude
- `fetch.py` — main script
