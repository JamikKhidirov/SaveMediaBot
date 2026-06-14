"""
Integration + E2E tests for SaveMediaBot.

Tests the full pipeline with mocked external dependencies:
  - In-memory store lifecycle
  - Subscription gate flow (subscribed / not subscribed)
  - Format selection callbacks
  - Quality selection callbacks
  - Batch download flow
  - Back-navigation
  - Compression logic boundary
  - Admin command parsing
"""
import sys
import os
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))

from bot.handlers.download import (
    _link_store, _pending_store,
    _ensure_subscribed, cb_check_subscription,
    _handle_single, _handle_batch,
    cb_format_video, cb_format_audio, cb_quality,
    cb_batch_video, cb_batch_audio, cb_back,
    _process_download, _process_batch,
)
from bot.services.subscription import (
    add_channel, remove_channel, get_required_channels,
    save_required_channels, CHANNELS_FILE, check_subscriptions, is_subscribed,
)
from bot.utils import extract_urls, is_shorts, short_label, URL_PATTERN
from bot.handlers.admin import _is_admin


def _make_message(
    text: str = "",
    user_id: int = 12345,
    username: str = "testuser",
    message_id: int = 1,
    chat_id: int = 999,
) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.message_id = message_id
    msg.chat.id = chat_id
    msg.from_user.id = user_id
    msg.from_user.username = username
    msg.from_user.full_name = "Test User"
    msg.bot = AsyncMock()
    msg.answer = AsyncMock(return_value=MagicMock(message_id=message_id + 100))
    msg.answer_audio = AsyncMock()
    msg.answer_video = AsyncMock()
    msg.delete = AsyncMock()
    msg.edit_text = AsyncMock()
    return msg


def _make_async_mock_msg():
    m = MagicMock()
    m.delete = AsyncMock()
    m.edit_text = AsyncMock()
    m.answer_audio = AsyncMock()
    m.answer_video = AsyncMock()
    return m


def _make_callback(
    data: str = "",
    user_id: int = 12345,
    message_id: int = 1,
) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.message = _make_message(user_id=user_id, message_id=message_id)
    cb.from_user.id = user_id
    cb.bot = AsyncMock()
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock(return_value=_make_async_mock_msg())
    cb.message.answer_audio = AsyncMock()
    cb.message.answer_video = AsyncMock()
    cb.message.delete = AsyncMock()
    return cb


# ───────────────────────────── Setup/teardown ─────────────────────────────

def setUpModule():
    global _backup_channels
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, encoding="utf-8") as f:
            _backup_channels = f.read()
    else:
        _backup_channels = None
    save_required_channels([])


def tearDownModule():
    if _backup_channels is not None:
        with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
            f.write(_backup_channels)
    else:
        if os.path.exists(CHANNELS_FILE):
            os.remove(CHANNELS_FILE)


# ───────────────────────── Tests ─────────────────────────

class TestIntegrationLinkStore(unittest.TestCase):
    """Full lifecycle of _link_store throughout a download flow."""

    def setUp(self):
        _link_store.clear()
        _pending_store.clear()

    def test_single_link_full_lifecycle(self):
        _link_store[10] = {"urls": ["https://youtube.com/watch?v=abc"]}
        self.assertIn(10, _link_store)
        entry = _link_store[10]
        self.assertEqual(len(entry["urls"]), 1)
        del _link_store[10]
        self.assertNotIn(10, _link_store)

    def test_batch_link_lifecycle(self):
        urls = ["https://youtube.com/a", "https://instagram.com/b", "https://tiktok.com/c"]
        _link_store[20] = {"urls": urls}
        self.assertEqual(len(_link_store[20]["urls"]), 3)
        del _link_store[20]
        self.assertNotIn(20, _link_store)

    def test_multiple_independent_sessions(self):
        _link_store[1] = {"urls": ["url1"]}
        _link_store[2] = {"urls": ["url2"]}
        _link_store[3] = {"urls": ["url3"]}
        self.assertEqual(len(_link_store), 3)
        del _link_store[2]
        self.assertIn(1, _link_store)
        self.assertNotIn(2, _link_store)
        self.assertIn(3, _link_store)


class TestIntegrationSubscriptionGate(unittest.TestCase):
    """Subscription check flow with mocked bot."""

    def setUp(self):
        _link_store.clear()
        _pending_store.clear()
        for ch in get_required_channels():
            remove_channel(ch)

    async def _asyncSetUp(self):
        pass

    def test_no_channels_required(self):
        """If no channels configured, subscription passes."""
        msg = _make_message()
        result = self._run_async(_ensure_subscribed(msg))
        self.assertTrue(result)

    def test_subscribed_user_passes(self):
        """User subscribed to all channels → passes."""
        add_channel("test_channel")
        msg = _make_message(user_id=42)
        msg.bot.get_chat_member = AsyncMock()
        member = MagicMock()
        member.status = "member"
        msg.bot.get_chat_member.return_value = member

        result = self._run_async(_ensure_subscribed(msg))
        self.assertTrue(result)

    def test_unsubscribed_user_blocked(self):
        """User not subscribed → blocked, message sent."""
        add_channel("required_ch")
        msg = _make_message(user_id=99)
        msg.bot.get_chat_member = AsyncMock(side_effect=Exception("Not found"))
        msg.answer = AsyncMock()

        result = self._run_async(_ensure_subscribed(msg))
        self.assertFalse(result)
        msg.answer.assert_called_once()

    def test_unsubscribed_saves_pending(self):
        """Pending store saves text for unsubscribed user."""
        add_channel("required_ch")
        msg = _make_message(text="https://youtube.com/watch?v=abc", user_id=88)
        msg.bot.get_chat_member = AsyncMock(side_effect=Exception("Not found"))
        msg.answer = AsyncMock()

        from bot.handlers.download import handle_link

        async def run():
            urls = extract_urls(msg.text)
            if not urls:
                return
            if not await _ensure_subscribed(msg):
                _pending_store[msg.from_user.id] = msg.text

        self._run_async(run())
        self.assertEqual(_pending_store.get(88), "https://youtube.com/watch?v=abc")

    def test_check_sub_callback_clears_pending(self):
        """After successful sub check, pending store is cleared."""
        _pending_store[55] = "https://youtube.com/watch?v=abc"
        cb = _make_callback(data="check_sub", user_id=55)
        cb.bot.get_chat_member = AsyncMock()
        member = MagicMock()
        member.status = "member"
        cb.bot.get_chat_member.return_value = member
        cb.message.delete = AsyncMock()

        self._run_async(cb_check_subscription(cb))
        self.assertNotIn(55, _pending_store)
        cb.message.delete.assert_called_once()

    def test_check_sub_no_pending(self):
        """User clicks check_sub but nothing pending."""
        cb = _make_callback(data="check_sub", user_id=66)
        self._run_async(cb_check_subscription(cb))
        cb.answer.assert_called_once()

    def test_multiple_channels_all_unsubscribed(self):
        """Multiple channels → all shown to user."""
        add_channel("ch1")
        add_channel("ch2")
        add_channel("ch3")
        msg = _make_message(user_id=77)
        msg.bot.get_chat_member = AsyncMock(side_effect=Exception("Not found"))
        msg.answer = AsyncMock()

        self._run_async(_ensure_subscribed(msg))
        call_args = msg.answer.call_args
        self.assertIn("ch1", call_args[0][0])
        self.assertIn("ch2", call_args[0][0])
        self.assertIn("ch3", call_args[0][0])

    @staticmethod
    def _run_async(coro):
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class TestIntegrationHandlers(unittest.TestCase):
    """Handler logic without real aiogram dispatcher."""

    def setUp(self):
        _link_store.clear()
        _pending_store.clear()

    def test_handle_single_stores_link(self):
        msg = _make_message(message_id=50)
        self._run_async(_handle_single(msg, "https://youtube.com/watch?v=abc"))
        # Check that _link_store was populated
        # The answer returns with message_id = 150 (50+100)
        self.assertTrue(
            any(
                entry["urls"][0] == "https://youtube.com/watch?v=abc"
                for entry in _link_store.values()
            ),
        )
        msg.answer.assert_called_once()

    def test_handle_batch_stores_links(self):
        urls = ["https://youtube.com/a", "https://youtube.com/b"]
        msg = _make_message(message_id=60)
        self._run_async(_handle_batch(msg, urls))
        self.assertTrue(
            any(len(entry["urls"]) == 2 for entry in _link_store.values())
        )

    def test_cb_format_video_missing_entry(self):
        cb = _make_callback(data="fmt:video:999", message_id=1)
        self._run_async(cb_format_video(cb))
        cb.answer.assert_called_once()

    def test_cb_format_video_valid(self):
        _link_store[1] = {"urls": ["https://youtube.com/watch?v=abc"]}
        cb = _make_callback(data="fmt:video:1", message_id=1)
        self._run_async(cb_format_video(cb))
        cb.message.edit_text.assert_called()

    def test_cb_format_audio_valid(self):
        _link_store[2] = {"urls": ["https://youtube.com/watch?v=abc"]}
        cb = _make_callback(data="fmt:audio:2", message_id=2)
        with patch("bot.handlers.download.download", AsyncMock(return_value="/tmp/test.mp3")):
            with patch("bot.handlers.download.os.path.exists", return_value=True):
                with patch("bot.handlers.download.cleanup", AsyncMock()):
                    self._run_async(cb_format_audio(cb))
                    cb.message.edit_text.assert_called()

    def test_cb_quality_best(self):
        _link_store[3] = {"urls": ["https://youtube.com/watch?v=abc"]}
        cb = _make_callback(data="q:best:3", message_id=3)
        with patch("bot.handlers.download.download", AsyncMock(return_value="/tmp/test.mp4")):
            with patch("bot.handlers.download.os.path.exists", return_value=True):
                with patch("bot.handlers.download.compress_video", AsyncMock(return_value="/tmp/test.mp4")):
                    with patch("bot.handlers.download.cleanup", AsyncMock()):
                        self._run_async(cb_quality(cb))
                        cb.message.edit_text.assert_called()

    def test_cb_quality_number(self):
        _link_store[4] = {"urls": ["https://youtube.com/watch?v=abc"]}
        cb = _make_callback(data="q:720:4", message_id=4)
        with patch("bot.handlers.download.download", AsyncMock(return_value="/tmp/test.mp4")):
            with patch("bot.handlers.download.os.path.exists", return_value=True):
                with patch("bot.handlers.download.compress_video", AsyncMock(return_value="/tmp/test.mp4")):
                    with patch("bot.handlers.download.cleanup", AsyncMock()):
                        self._run_async(cb_quality(cb))

    def test_cb_back_navigation(self):
        _link_store[5] = {"urls": ["https://youtube.com/watch?v=abc"]}
        cb = _make_callback(data="back:5", message_id=5)
        self._run_async(cb_back(cb))
        cb.message.edit_text.assert_called()

    def test_cb_batch_video(self):
        _link_store[6] = {"urls": ["https://youtube.com/a", "https://youtube.com/b"]}
        cb = _make_callback(data="batch:video:6", message_id=6)
        tmp = os.path.join(tempfile.gettempdir(), "test_batch.mp4")
        open(tmp, "w").close()
        try:
            with patch("bot.handlers.download.download", AsyncMock(return_value=tmp)):
                with patch("bot.handlers.download.os.path.exists", return_value=True):
                    with patch("bot.handlers.download.compress_video", AsyncMock(return_value=tmp)):
                        with patch("bot.handlers.download.cleanup", AsyncMock()):
                            self._run_async(cb_batch_video(cb))
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_cb_batch_audio(self):
        _link_store[7] = {"urls": ["https://youtube.com/a", "https://youtube.com/b"]}
        cb = _make_callback(data="batch:audio:7", message_id=7)
        tmp = os.path.join(tempfile.gettempdir(), "test_batch.mp3")
        open(tmp, "w").close()
        try:
            with patch("bot.handlers.download.download", AsyncMock(return_value=tmp)):
                with patch("bot.handlers.download.os.path.exists", return_value=True):
                    with patch("bot.handlers.download.cleanup", AsyncMock()):
                        self._run_async(cb_batch_audio(cb))
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_process_download_deletes_link_store(self):
        _link_store[8] = {"urls": ["https://youtube.com/watch?v=abc"]}
        cb = _make_callback(data="q:best:8", message_id=8)
        with patch("bot.handlers.download.download", AsyncMock(return_value=os.path.join(tempfile.gettempdir(), "test.mp4"))):
            tmp = os.path.join(tempfile.gettempdir(), "test.mp4")
            open(tmp, "w").close()
            try:
                with patch("bot.handlers.download.os.path.exists", return_value=True):
                    with patch("bot.handlers.download.compress_video", AsyncMock(return_value=tmp)):
                        with patch("bot.handlers.download.cleanup", AsyncMock()):
                            self._run_async(
                                _process_download(cb, "https://youtube.com/watch?v=abc", audio_only=False, msg_id=8)
                            )
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        self.assertNotIn(8, _link_store)

    def test_process_download_error_file_not_found(self):
        cb = _make_callback(data="fmt:video:9", message_id=9)
        with patch("bot.handlers.download.download", AsyncMock(return_value=None)):
            self._run_async(
                _process_download(cb, "https://youtube.com/watch?v=abc", audio_only=False, msg_id=9)
            )
        cb.message.edit_text.assert_called()

    @staticmethod
    def _run_async(coro):
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class TestIntegrationCompression(unittest.TestCase):
    """Compression boundary conditions."""

    def test_small_file_not_compressed(self):
        """File under 50MB → compression returns original."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"0" * (10 * 1024 * 1024))  # 10MB
            small_path = f.name

        from bot.services.downloader import _compress
        result = _compress(small_path)
        self.assertEqual(result, small_path)
        os.unlink(small_path)

    def test_large_file_compression_attempt(self):
        """File >50MB → compression attempted (ffmpeg may not be installed)."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"0" * (60 * 1024 * 1024))  # 60MB
            large_path = f.name

        from bot.services.downloader import _compress
        result = _compress(large_path)
        self.assertTrue(os.path.exists(result))
        os.unlink(result)


class TestIntegrationURLParsing(unittest.TestCase):
    """End-to-end URL parsing from real-world examples."""

    def test_youtube_full_url(self):
        urls = extract_urls("Check this out: https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(len(urls), 1)
        self.assertIn("youtube.com/watch?v=dQw4w9WgXcQ", urls[0])

    def test_youtube_short_url(self):
        urls = extract_urls("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(len(urls), 1)
        self.assertIn("youtu.be", urls[0])

    def test_youtube_shorts_url(self):
        urls = extract_urls("https://youtube.com/shorts/abc123")
        self.assertEqual(len(urls), 1)
        self.assertTrue(is_shorts(urls[0]))

    def test_instagram_reel(self):
        urls = extract_urls("https://www.instagram.com/reel/ABC123/")
        self.assertEqual(len(urls), 1)
        self.assertIn("instagram.com/reel", urls[0])

    def test_tiktok_full(self):
        urls = extract_urls("https://www.tiktok.com/@user/video/123456789")
        self.assertEqual(len(urls), 1)
        self.assertIn("tiktok.com/@user", urls[0])

    def test_vk_video(self):
        urls = extract_urls("https://vk.com/video-123456_789012")
        self.assertEqual(len(urls), 1)
        self.assertIn("vk.com/video", urls[0])

    def test_twitter_status(self):
        urls = extract_urls("https://twitter.com/user/status/123456789")
        self.assertEqual(len(urls), 1)
        self.assertIn("twitter.com/user", urls[0])

    def test_x_status(self):
        urls = extract_urls("https://x.com/user/status/123456789")
        self.assertEqual(len(urls), 1)
        self.assertIn("x.com/user", urls[0])

    def test_batch_real_world(self):
        text = (
            "Смотри какие видео:\n"
            "https://youtube.com/watch?v=abc\n"
            "https://instagram.com/reel/xyz/\n"
            "https://tiktok.com/@user/video/123"
        )
        urls = extract_urls(text)
        self.assertEqual(len(urls), 3)
        self.assertTrue(all("http" in u for u in urls))

    def test_no_links_in_regular_text(self):
        self.assertEqual(extract_urls("Привет! Как дела?"), [])
        self.assertEqual(extract_urls(""), [])

    def test_short_label_mapping(self):
        self.assertEqual(short_label("https://youtube.com/shorts/x"), "🎬 Shorts")
        self.assertEqual(short_label("https://youtube.com/watch?v=x"), "🎬 Видео")
        self.assertEqual(short_label("https://instagram.com/p/x/"), "🎬 Видео")
        self.assertEqual(short_label("https://tiktok.com/@u/v/1"), "🎬 Видео")


class TestIntegrationAdminFlow(unittest.TestCase):
    """Admin command simulation."""

    def setUp(self):
        self._backup = None
        if os.path.exists(CHANNELS_FILE):
            with open(CHANNELS_FILE, encoding="utf-8") as f:
                self._backup = f.read()
        save_required_channels([])

    def tearDown(self):
        if self._backup is not None:
            with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
                f.write(self._backup)
        else:
            if os.path.exists(CHANNELS_FILE):
                os.remove(CHANNELS_FILE)

    def test_is_admin_valid(self):
        with patch("bot.handlers.admin.ADMIN_IDS", [12345]):
            self.assertTrue(_is_admin(12345))
            self.assertFalse(_is_admin(99999))

    def test_add_remove_cycle(self):
        self.assertTrue(add_channel("my_channel"))
        self.assertEqual(get_required_channels(), ["my_channel"])
        self.assertTrue(remove_channel("my_channel"))
        self.assertEqual(get_required_channels(), [])

    def test_list_channels(self):
        add_channel("ch_a")
        add_channel("ch_b")
        channels = get_required_channels()
        self.assertEqual(len(channels), 2)
        self.assertIn("ch_a", channels)
        self.assertIn("ch_b", channels)

    def test_is_subscribed_check(self):
        """Simulate bot.get_chat_member response."""
        bot = AsyncMock()
        member = MagicMock()
        member.status = "member"
        bot.get_chat_member.return_value = member

        result = self._run_async(is_subscribed(bot, 12345, "some_channel"))
        self.assertTrue(result)
        bot.get_chat_member.assert_called_once_with(chat_id="some_channel", user_id=12345)

    def test_is_subscribed_exception(self):
        """If get_chat_member raises, user is not subscribed."""
        bot = AsyncMock()
        bot.get_chat_member = AsyncMock(side_effect=Exception("bot not in channel"))

        result = self._run_async(is_subscribed(bot, 12345, "some_channel"))
        self.assertFalse(result)

    def test_check_subscriptions_multiple(self):
        """check_subscriptions returns only unsubscribed channels."""
        add_channel("subscribed_ch")
        add_channel("unsubscribed_ch")

        bot = AsyncMock()

        async def side_effect(chat_id, user_id):
            member = MagicMock()
            if chat_id == "subscribed_ch":
                member.status = "member"
            else:
                raise Exception("not found")
            return member

        bot.get_chat_member = AsyncMock(side_effect=side_effect)

        unsubscribed = self._run_async(check_subscriptions(bot, 12345))
        self.assertEqual(unsubscribed, ["unsubscribed_ch"])

    @staticmethod
    def _run_async(coro):
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class TestIntegrationPendingStore(unittest.TestCase):
    """_pending_store lifecycle."""

    def setUp(self):
        _pending_store.clear()

    def test_store_and_retrieve(self):
        _pending_store[100] = "https://youtube.com/watch?v=abc"
        self.assertEqual(_pending_store[100], "https://youtube.com/watch?v=abc")

    def test_overwrite(self):
        _pending_store[100] = "first"
        _pending_store[100] = "second"
        self.assertEqual(_pending_store[100], "second")

    def test_delete(self):
        _pending_store[100] = "text"
        del _pending_store[100]
        self.assertNotIn(100, _pending_store)

    def test_missing_returns_none(self):
        self.assertIsNone(_pending_store.get(999))


class TestEdgeCases(unittest.TestCase):
    """Edge cases and error resilience."""

    def test_url_with_timestamp(self):
        urls = extract_urls("https://youtube.com/watch?v=abc&t=120s")
        self.assertEqual(len(urls), 1)
        self.assertIn("t=120", urls[0])

    def test_url_with_unicode(self):
        urls = extract_urls("https://youtube.com/watch?v=abc#t=1m15sю")
        self.assertEqual(len(urls), 1)

    def test_url_in_parentheses(self):
        urls = extract_urls("(https://youtube.com/watch?v=abc)")
        self.assertEqual(len(urls), 1)

    def test_url_in_quotes(self):
        urls = extract_urls('"https://youtube.com/watch?v=abc"')
        self.assertEqual(len(urls), 1)

    def test_extremely_long_text_without_urls(self):
        long_text = "без ссылок " * 1000
        self.assertEqual(extract_urls(long_text), [])

    def test_cleanup_nonexistent_file(self):
        from bot.services.downloader import cleanup as cl
        self._run_async(cl("/nonexistent/path/file.mp4"))

    def test_cleanup_existing_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp = f.name
        from bot.services.downloader import cleanup as cl
        self._run_async(cl(tmp))
        self.assertFalse(os.path.exists(tmp))

    def test_info_cache_key_missing(self):
        from bot.services.downloader import _get_available_heights
        self.assertEqual(_get_available_heights({"formats": None}), [])

    def test_channel_with_dashes(self):
        add_channel("my-channel_name")
        ch = get_required_channels()
        self.assertIn("my-channel_name", ch)
        remove_channel("my-channel_name")

    def test_empty_admin_ids(self):
        from bot.config import ADMIN_IDS
        self.assertIsInstance(ADMIN_IDS, list)

    @staticmethod
    def _run_async(coro):
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            return loop.run_until_complete(coro)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
