"""Service for YouTube metadata extraction via yt-dlp."""
import re
import logging
from datetime import datetime, timedelta

from flask import current_app

from .format_service import FormatService
from .errors import (
    InvalidYouTubeUrl, VideoNotFound, UnsupportedVideo, YouTubeBlocked,
)
from .ytdlp_options import is_youtube_restriction_error
from ..extensions import db
from ..models import Video

logger = logging.getLogger(__name__)


class YouTubeService:
    """Validate URLs, extract metadata, and normalize formats."""

    YOUTUBE_URL_PATTERNS = [
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([\w-]{11})'),
        re.compile(r'(?:https?://)?(?:www\.)?youtu\.be/([\w-]{11})'),
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([\w-]{11})'),
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/embed/([\w-]{11})'),
    ]

    def __init__(self):
        self.format_service = FormatService()

    def extract_video_id(self, url):
        """Extract the 11-char YouTube video ID from a URL."""
        url = (url or '').strip()
        for pattern in self.YOUTUBE_URL_PATTERNS:
            match = pattern.search(url)
            if match:
                return match.group(1)
        raise InvalidYouTubeUrl('Could not extract a YouTube video ID from the URL.')

    def analyze(self, url):
        """Analyze a YouTube URL, returning metadata + normalized formats."""
        video_id = self.extract_video_id(url)

        # Check cache
        cached = self._get_cached(video_id)
        if cached:
            return cached

        info = self._extract_info(url)
        if not info:
            raise VideoNotFound()

        if info.get('is_live'):
            raise UnsupportedVideo('Live streams are not supported.')

        max_duration = current_app.config.get('MAX_VIDEO_DURATION', 7200)
        duration = info.get('duration') or 0
        if duration and duration > max_duration:
            from .errors import DurationExceeded
            raise DurationExceeded(
                f'Video duration ({duration}s) exceeds the limit ({max_duration}s).'
            )

        formats = self.format_service.normalize(info.get('formats', []))

        video = self._save_video(info, url, formats)

        return {
            'video': video.to_dict(),
            'formats': formats,
        }

    def _get_cached(self, video_id):
        """Return cached analysis if fresh enough, else None."""
        ttl = current_app.config.get('METADATA_CACHE_TTL', 600)
        video = Video.query.filter_by(youtube_id=video_id).first()
        if not video or not video.metadata_fetched_at:
            return None

        age = datetime.utcnow() - video.metadata_fetched_at
        if age > timedelta(seconds=ttl):
            return None

        import json
        try:
            formats = json.loads(video.formats_json) if video.formats_json else {'video': [], 'audio': []}
        except (ValueError, TypeError):
            formats = {'video': [], 'audio': []}

        return {'video': video.to_dict(), 'formats': formats}

    def _extract_info(self, url):
        """Use yt-dlp to extract metadata without downloading."""
        try:
            import yt_dlp
        except ImportError:
            logger.error('yt-dlp is not installed.')
            raise VideoNotFound('yt-dlp backend is unavailable.')

        from .ytdlp_options import base_ydl_opts
        ydl_opts = base_ydl_opts()
        ydl_opts['skip_download'] = True

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            logger.warning('yt-dlp extraction failed: %s', e)
            if is_youtube_restriction_error(str(e)):
                raise YouTubeBlocked()
            raise VideoNotFound('The video could not be retrieved.')
        except Exception as e:
            logger.exception('Unexpected yt-dlp error')
            if is_youtube_restriction_error(str(e)):
                raise YouTubeBlocked()
            raise VideoNotFound('The video could not be retrieved.')

    def _save_video(self, info, url, formats):
        """Persist or update the video record with metadata + formats."""
        import json
        youtube_id = info.get('id')
        video = Video.query.filter_by(youtube_id=youtube_id).first()
        if not video:
            video = Video(youtube_id=youtube_id)
            db.session.add(video)

        video.url = url
        video.title = info.get('title', '')
        video.description = info.get('description')
        video.thumbnail_url = info.get('thumbnail')
        video.duration = info.get('duration')
        video.uploader = info.get('uploader') or info.get('channel')
        video.formats_json = json.dumps(formats)
        video.metadata_fetched_at = datetime.utcnow()

        db.session.commit()
        return video
