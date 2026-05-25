import os
import unittest
from unittest.mock import patch

import fetch


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "response text"

    def json(self):
        return self._payload


class XquikBackendTest(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ.clear()
        os.environ["XQUIK_API_KEY"] = "xq_test"
        fetch.XQUIK_BASE_URL = "https://example.test"
        fetch.XQUIK_FOLDER_ID = "folder-1"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        fetch.XQUIK_BASE_URL = os.environ.get("XQUIK_BASE_URL", "https://xquik.com").rstrip("/")
        fetch.XQUIK_FOLDER_ID = os.environ.get("X_BOOKMARKS_FOLDER_ID")

    def test_fetch_xquik_bookmarks_page_uses_api_key_and_cursor(self):
        calls = []

        def fake_get(url, headers, params, timeout):
            calls.append((url, headers, params, timeout))
            return FakeResponse({
                "bookmarks": [
                    {
                        "id": "123",
                        "text": "Saved thread",
                        "author": {"username": "alice"},
                        "createdAt": "2026-05-25T08:00:00Z",
                    }
                ],
                "nextCursor": "next-1",
            })

        with patch("fetch.requests.get", fake_get):
            data = fetch.fetch_xquik_bookmarks_page(cursor="cursor-1")

        tweets, cursor = fetch.parse_xquik_page(data)
        self.assertEqual(calls[0][0], "https://example.test/api/v1/x/bookmarks")
        self.assertEqual(calls[0][1]["x-api-key"], "xq_test")
        self.assertEqual(calls[0][2], {"cursor": "cursor-1", "folderId": "folder-1"})
        self.assertEqual(calls[0][3], 30)
        self.assertEqual(cursor, "next-1")
        self.assertEqual(tweets[0]["id"], "123")
        self.assertEqual(tweets[0]["username"], "alice")
        self.assertEqual(tweets[0]["url"], "https://x.com/alice/status/123")

    def test_normalize_xquik_tweet_accepts_media_and_article_fields(self):
        tweet = fetch.normalize_xquik_tweet({
            "tweet_id": 456,
            "full_text": "Article bookmark",
            "user": "@bob",
            "created_at": "Mon May 25 09:00:00 +0000 2026",
            "hashtags": ["AI", "#Agents"],
            "media": [{"media_url_https": "https://pbs.twimg.com/media/test.jpg"}],
            "article": {
                "title": "Longform note",
                "preview_text": "Preview",
                "cover_image_url": "https://example.test/cover.jpg",
                "rest_id": "456",
            },
        })

        self.assertEqual(tweet["id"], "456")
        self.assertEqual(tweet["username"], "bob")
        self.assertEqual(tweet["date"], "2026-05-25")
        self.assertEqual(tweet["hashtags"], ["ai", "agents"])
        self.assertEqual(tweet["media"], ["https://pbs.twimg.com/media/test.jpg"])
        self.assertEqual(tweet["article_title"], "Longform note")
        self.assertEqual(tweet["article_rest_id"], "456")


if __name__ == "__main__":
    unittest.main()
