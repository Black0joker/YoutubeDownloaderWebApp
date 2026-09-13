"""Tests for format normalization and YouTube URL parsing."""
import pytest

from app.services.format_service import FormatService
from app.services.youtube_service import YouTubeService
from app.services.errors import InvalidYouTubeUrl


class TestExtractYouTubeId:
    def setup_method(self):
        self.service = YouTubeService()

    @pytest.mark.parametrize('url,expected', [
        ('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'dQw4w9WgXcQ'),
        ('https://youtu.be/dQw4w9WgXcQ', 'dQw4w9WgXcQ'),
        ('https://www.youtube.com/shorts/dQw4w9WgXcQ', 'dQw4w9WgXcQ'),
        ('https://www.youtube.com/embed/dQw4w9WgXcQ', 'dQw4w9WgXcQ'),
    ])
    def test_extract_valid_ids(self, url, expected):
        assert self.service.extract_video_id(url) == expected

    def test_invalid_url_raises(self):
        with pytest.raises(InvalidYouTubeUrl):
            self.service.extract_video_id('https://example.com/video')

    def test_empty_url_raises(self):
        with pytest.raises(InvalidYouTubeUrl):
            self.service.extract_video_id('')


class TestFormatNormalization:
    def setup_method(self):
        self.service = FormatService()

    def _raw_formats(self):
        return [
            # Video-only streams
            {'format_id': '137', 'vcodec': 'avc1', 'acodec': 'none',
             'height': 1080, 'width': 1920, 'fps': 30, 'ext': 'mp4',
             'filesize': 250000000},
            {'format_id': '136', 'vcodec': 'avc1', 'acodec': 'none',
             'height': 720, 'width': 1280, 'fps': 30, 'ext': 'mp4',
             'filesize': 120000000},
            # Duplicate 1080p in webm (should be deduped, mp4 preferred)
            {'format_id': '248', 'vcodec': 'vp9', 'acodec': 'none',
             'height': 1080, 'width': 1920, 'fps': 30, 'ext': 'webm',
             'filesize': 200000000},
            # Audio-only streams
            {'format_id': '140', 'vcodec': 'none', 'acodec': 'mp4a',
             'abr': 128, 'ext': 'm4a', 'filesize': 5000000},
            {'format_id': '251', 'vcodec': 'none', 'acodec': 'opus',
             'abr': 160, 'ext': 'webm', 'filesize': 6000000},
        ]

    def test_normalize_separates_video_and_audio(self):
        result = self.service.normalize(self._raw_formats())
        assert 'video' in result
        assert 'audio' in result
        assert len(result['video']) >= 2
        assert len(result['audio']) >= 2

    def test_video_sorted_by_height_desc(self):
        result = self.service.normalize(self._raw_formats())
        heights = [f['height'] for f in result['video']]
        assert heights == sorted(heights, reverse=True)

    def test_dedupes_same_resolution(self):
        result = self.service.normalize(self._raw_formats())
        heights = [f['height'] for f in result['video']]
        # 1080p appears twice in raw but should be deduped to one
        assert heights.count(1080) == 1

    def test_prefers_mp4_for_video(self):
        result = self.service.normalize(self._raw_formats())
        top = [f for f in result['video'] if f['height'] == 1080][0]
        assert top['ext'] == 'mp4'

    def test_audio_sorted_by_bitrate_desc(self):
        result = self.service.normalize(self._raw_formats())
        bitrates = [f['bitrate'] for f in result['audio']]
        assert bitrates == sorted(bitrates, reverse=True)

    def test_empty_formats(self):
        result = self.service.normalize([])
        assert result == {'video': [], 'audio': []}
