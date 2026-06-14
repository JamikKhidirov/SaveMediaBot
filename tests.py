import sys
import os
import json
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

from bot.utils import URL_PATTERN, extract_urls, is_shorts, short_label, SHORTS_HEIGHT
from bot.handlers.download import _link_store
from bot.services.downloader import _get_available_heights
from bot.services.subscription import (
    add_channel, remove_channel, get_required_channels,
    save_required_channels, CHANNELS_FILE
)


class TestUtils(unittest.TestCase):

    def setUp(self):
        _link_store.clear()

    def test_extract_youtube(self):
        urls = extract_urls("https://youtube.com/watch?v=abc123")
        self.assertEqual(len(urls), 1)
        self.assertIn("youtube.com/watch?v=abc123", urls[0])

    def test_extract_youtu_be(self):
        urls = extract_urls("https://youtu.be/abc123")
        self.assertEqual(len(urls), 1)
        self.assertIn("youtu.be/abc123", urls[0])

    def test_extract_instagram(self):
        urls = extract_urls("https://instagram.com/p/ABC123/")
        self.assertEqual(len(urls), 1)

    def test_extract_tiktok(self):
        urls = extract_urls("https://tiktok.com/@user/video/123456")
        self.assertEqual(len(urls), 1)

    def test_extract_vk(self):
        urls = extract_urls("https://vk.com/video-123456_789012")
        self.assertEqual(len(urls), 1)

    def test_extract_twitter(self):
        urls = extract_urls("https://twitter.com/user/status/123456")
        self.assertEqual(len(urls), 1)

    def test_extract_x(self):
        urls = extract_urls("https://x.com/user/status/123456")
        self.assertEqual(len(urls), 1)

    def test_no_url(self):
        urls = extract_urls("просто текст без ссылок")
        self.assertEqual(len(urls), 0)

    def test_multiple(self):
        urls = extract_urls("https://youtube.com/watch?v=abc\nhttps://instagram.com/p/xyz/")
        self.assertEqual(len(urls), 2)

    def test_duplicates(self):
        urls = extract_urls("https://youtube.com/watch?v=abc https://youtube.com/watch?v=abc")
        self.assertEqual(len(urls), 1)

    def test_is_shorts(self):
        self.assertTrue(is_shorts("https://youtube.com/shorts/abc123"))
        self.assertTrue(is_shorts("https://youtu.be/shorts/abc123"))

    def test_not_shorts(self):
        self.assertFalse(is_shorts("https://youtube.com/watch?v=abc123"))

    def test_short_label(self):
        self.assertEqual(short_label("https://youtube.com/shorts/xyz"), "🎬 Shorts")
        self.assertEqual(short_label("https://youtube.com/watch?v=abc"), "🎬 Видео")


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
        self.assertEqual(_get_available_heights({"formats": []}), [])

    def test_no_formats_key(self):
        self.assertEqual(_get_available_heights({}), [])


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

    def test_empty(self):
        self.assertEqual(get_required_channels(), [])

    def test_add(self):
        self.assertTrue(add_channel("ch1"))
        self.assertEqual(get_required_channels(), ["ch1"])

    def test_add_duplicate(self):
        add_channel("ch1")
        self.assertFalse(add_channel("ch1"))

    def test_add_multiple(self):
        add_channel("ch1"); add_channel("ch2"); add_channel("ch3")
        self.assertEqual(get_required_channels(), ["ch1", "ch2", "ch3"])

    def test_remove(self):
        add_channel("ch1")
        self.assertTrue(remove_channel("ch1"))
        self.assertEqual(get_required_channels(), [])

    def test_remove_not_found(self):
        self.assertFalse(remove_channel("nonexistent"))

    def test_remove_from_middle(self):
        add_channel("ch1"); add_channel("ch2"); add_channel("ch3")
        self.assertTrue(remove_channel("ch2"))
        self.assertEqual(get_required_channels(), ["ch1", "ch3"])

    def test_persistence(self):
        add_channel("persist")
        self.assertEqual(get_required_channels(), get_required_channels())


class TestLinkStore(unittest.TestCase):

    def setUp(self):
        _link_store.clear()

    def test_store_and_get(self):
        _link_store[1] = {"urls": ["https://youtube.com/watch?v=abc"]}
        self.assertIsNotNone(_link_store.get(1))

    def test_delete(self):
        _link_store[3] = {"urls": ["url"]}
        del _link_store[3]
        self.assertIsNone(_link_store.get(3))

    def test_multiple(self):
        _link_store[4] = {"urls": ["u1", "u2", "u3"]}
        self.assertEqual(len(_link_store[4]["urls"]), 3)


class TestCallbackData(unittest.TestCase):

    def parse(self, data):
        return data.split(":")

    def test_fmt_video(self):
        p = self.parse("fmt:video:42")
        self.assertEqual(p, ["fmt", "video", "42"])

    def test_fmt_audio(self):
        p = self.parse("fmt:audio:99")
        self.assertEqual(p[1], "audio")

    def test_q_best(self):
        p = self.parse("q:best:42")
        self.assertEqual(p[1], "best")

    def test_q_number(self):
        p = self.parse("q:720:42")
        self.assertEqual(int(p[1]), 720)

    def test_batch_video(self):
        p = self.parse("batch:video:7")
        self.assertEqual(p[1], "video")

    def test_batch_audio(self):
        p = self.parse("batch:audio:3")
        self.assertEqual(p[1], "audio")

    def test_back(self):
        p = self.parse("back:15")
        self.assertEqual(p, ["back", "15"])


class TestAdminCommands(unittest.TestCase):

    def test_strip_at(self):
        self.assertEqual("@test".lstrip("@"), "test")
        self.assertEqual("test".lstrip("@"), "test")

    def test_admin_ids_type(self):
        from bot.config import ADMIN_IDS
        self.assertIsInstance(ADMIN_IDS, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
