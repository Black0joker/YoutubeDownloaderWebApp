"""Tests for yt-dlp option helpers and YouTube restriction detection."""
from app.services.ytdlp_options import (
    is_bot_check_error,
    is_youtube_restriction_error,
)


class TestBotCheckDetection:
    def test_sign_in_marker(self):
        err = "ERROR: Sign in to confirm you\u2019re not a bot."
        assert is_bot_check_error(err)

    def test_cookies_marker(self):
        assert is_bot_check_error('use --cookies to authenticate')

    def test_unrelated_error(self):
        assert not is_bot_check_error('Video unavailable')

    def test_none_input(self):
        assert not is_bot_check_error(None)


class TestRestrictionDetection:
    def test_covers_bot_check(self):
        err = 'ERROR: Sign in to confirm you\u2019re not a bot.'
        assert is_youtube_restriction_error(err)

    def test_page_reload_marker(self):
        err = 'ERROR: [youtube] abc12345678: The page needs to be reloaded.'
        assert is_youtube_restriction_error(err)

    def test_only_images_marker(self):
        err = 'WARNING: Only images are available for download.'
        assert is_youtube_restriction_error(err)

    def test_unrelated_error(self):
        assert not is_youtube_restriction_error('Requested format is not available')

    def test_none_input(self):
        assert not is_youtube_restriction_error(None)
