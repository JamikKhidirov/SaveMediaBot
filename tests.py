import sys
import os
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

from bot.handlers.download import URL_PATTERN, _extract_urls, _is_shorts, _link_store
from bot.services.downloader import _get_available_heights
from bot.services.subscription import (
    add_channel, remove_channel, get_required_channels,
    save_required_channels, CHANNELS_FILE
)


class TestURLPattern(unittest.TestCase):

    def setUp(self):
        _link_store.clear()

    def test_youtube_url(self):
        urls = _extract_urls("https://youtube.com/watch?v=abc123")
        self.assertEqual(len(urls), 1)
        self.assertIn("youtube.com/watch?v=abc123", urls[0])

    def test_youtu_be(self):
        urls = _extract_urls("https://youtu.be/abc123")
        self.assertEqual(len(urls), 1)
        self.assertIn("youtu.be/abc123", urls[0])

    def test_instagram(self):
        urls = _extract_urls("https://instagram.com/p/ABC123/")
        self.assertEqual(len(urls), 1)

    def test_tiktok(self):
        urls = _extract_urls("https://tiktok.com/@user/video/123456")
        self.assertEqual(len(urls), 1)

    def test_vk(self):
        urls = _extract_urls("https://vk.com/video-123456_789012")
        self.assertEqual(len(urls), 1)

    def test_twitter(self):
        urls = _extract_urls("https://twitter.com/user/status/123456")
        self.assertEqual(len(urls), 1)

    def test_x_com(self):
        urls = _extract_urls("https://x.com/user/status/123456")
        self.assertEqual(len(urls), 1)

    def test_no_url(self):
        urls = _extract_urls("просто текст без ссылок")
        self.assertEqual(len(urls), 0)

    def test_multiple_urls(self):
        text = (
            "https://youtube.com/watch?v=abc\n"
            "https://instagram.com/p/xyz/\n"
            "https://tiktok.com/@user/video/123"
        )
        urls = _extract_urls(text)
        self.assertEqual(len(urls), 3)

    def test_duplicate_urls(self):
        text = "https://youtube.com/watch?v=abc https://youtube.com/watch?v=abc"
        urls = _extract_urls(text)
        self.assertEqual(len(urls), 1)


class TestShortsDetection(unittest.TestCase):

    def test_youtube_shorts(self):
        self.assertTrue(_is_shorts("https://youtube.com/shorts/abc123"))
        self.assertTrue(_is_shorts("https://youtu.be/shorts/abc123"))

    def test_not_shorts(self):
        self.assertFalse(_is_shorts("https://youtube.com/watch?v=abc123"))
        self.assertFalse(_is_shorts("https://instagram.com/p/abc123/"))
        self.assertFalse(_is_shorts("https://tiktok.com/@user/video/123"))


class TestDownloader(unittest.TestCase):

    def test_get_available_heights(self):
        info = {
            "formats": [
                {"height": 2160, "vcodec": "avc1"},
                {"height": 1080, "vcodec": "avc1"},
                {"height": 720, "vcodec": "avc1"},
                {"height": 480, "vcodec": "avc1"},
                {"height": 360, "vcodec": "avc1"},
                {"height": 144, "vcodec": "avc1"},
                {"height": None, "vcodec": "avc1"},
                {"height": 720, "vcodec": "none"},
            ]
        }
        heights = _get_available_heights(info)
        self.assertEqual(heights, [2160, 1080, 720, 480, 360, 144])

    def test_empty_formats(self):
        heights = _get_available_heights({"formats": []})
        self.assertEqual(heights, [])

    def test_no_formats_key(self):
        heights = _get_available_heights({})
        self.assertEqual(heights, [])


class TestSubscriptionService(unittest.TestCase):

    def setUp(self):
        self.backup = None
        if os.path.exists(CHANNELS_FILE):
            with open(CHANNELS_FILE, encoding="utf-8") as f:
                self.backup = f.read()
        save_required_channels([])

    def tearDown(self):
        if self.backup is not None:
            with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
                f.write(self.backup)
        else:
            if os.path.exists(CHANNELS_FILE):
                os.remove(CHANNELS_FILE)

    def test_empty_channels(self):
        self.assertEqual(get_required_channels(), [])

    def test_add_channel(self):
        self.assertTrue(add_channel("channel1"))
        self.assertEqual(get_required_channels(), ["channel1"])

    def test_add_duplicate(self):
        add_channel("channel1")
        self.assertFalse(add_channel("channel1"))
        self.assertEqual(get_required_channels(), ["channel1"])

    def test_add_multiple(self):
        add_channel("channel1")
        add_channel("channel2")
        add_channel("channel3")
        self.assertEqual(get_required_channels(), ["channel1", "channel2", "channel3"])

    def test_remove_channel(self):
        add_channel("channel1")
        self.assertTrue(remove_channel("channel1"))
        self.assertEqual(get_required_channels(), [])

    def test_remove_not_found(self):
        self.assertFalse(remove_channel("nonexistent"))

    def test_remove_from_middle(self):
        add_channel("ch1")
        add_channel("ch2")
        add_channel("ch3")
        self.assertTrue(remove_channel("ch2"))
        self.assertEqual(get_required_channels(), ["ch1", "ch3"])

    def test_persistence(self):
        add_channel("persist_channel")
        channels1 = get_required_channels()

        channels2 = get_required_channels()
        self.assertEqual(channels1, channels2)
        self.assertIn("persist_channel", channels2)


class TestLinkStore(unittest.TestCase):

    def setUp(self):
        _link_store.clear()

    def test_store_and_retrieve(self):
        _link_store[1] = {"urls": ["https://youtube.com/watch?v=abc"], "is_shorts": False}
        entry = _link_store.get(1)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["urls"], ["https://youtube.com/watch?v=abc"])
        self.assertFalse(entry["is_shorts"])

    def test_store_shorts(self):
        _link_store[2] = {"urls": ["https://youtube.com/shorts/xyz"], "is_shorts": True}
        entry = _link_store.get(2)
        self.assertTrue(entry["is_shorts"])

    def test_delete_after_use(self):
        _link_store[3] = {"urls": ["https://example.com/video"], "is_shorts": False}
        del _link_store[3]
        self.assertIsNone(_link_store.get(3))

    def test_multiple_urls_in_store(self):
        urls = ["url1", "url2", "url3"]
        _link_store[4] = {"urls": urls, "is_shorts": False}
        entry = _link_store.get(4)
        self.assertEqual(len(entry["urls"]), 3)


class TestCallbackDataParsing(unittest.TestCase):

    def test_format_video_parse(self):
        data = "fmt:video:42"
        parts = data.split(":")
        self.assertEqual(parts[0], "fmt")
        self.assertEqual(parts[1], "video")
        self.assertEqual(int(parts[2]), 42)

    def test_format_audio_parse(self):
        data = "fmt:audio:99"
        parts = data.split(":")
        self.assertEqual(parts[1], "audio")
        self.assertEqual(int(parts[2]), 99)

    def test_quality_parse_best(self):
        data = "q:best:42"
        parts = data.split(":")
        height_str = parts[1]
        self.assertEqual(height_str, "best")

    def test_quality_parse_number(self):
        data = "q:720:42"
        parts = data.split(":")
        height = int(parts[1])
        self.assertEqual(height, 720)

    def test_batch_video_parse(self):
        data = "batch:video:7"
        parts = data.split(":")
        self.assertEqual(parts[1], "video")
        self.assertEqual(int(parts[2]), 7)

    def test_batch_audio_parse(self):
        data = "batch:audio:3"
        parts = data.split(":")
        self.assertEqual(parts[1], "audio")

    def test_back_parse(self):
        data = "back:15"
        parts = data.split(":")
        self.assertEqual(parts[0], "back")
        self.assertEqual(int(parts[1]), 15)


class TestAdminCommands(unittest.TestCase):

    def test_admin_check(self):
        from bot.config import ADMIN_IDS
        self.assertIsInstance(ADMIN_IDS, list)
        for a in ADMIN_IDS:
            self.assertIsInstance(a, int)

    def test_channel_format_strip_at(self):
        channel = "@testchannel".strip().lstrip("@")
        self.assertEqual(channel, "testchannel")

    def test_channel_format_no_at(self):
        channel = "testchannel".strip().lstrip("@")
        self.assertEqual(channel, "testchannel")


if __name__ == "__main__":
    unittest.main(verbosity=2)
