"""Application-level error types."""


class AppError(Exception):
    """Base application error."""
    code = 'APP_ERROR'
    message = 'An application error occurred.'
    http_status = 500

    def __init__(self, message=None):
        if message:
            self.message = message
        super().__init__(self.message)


class InvalidYouTubeUrl(AppError):
    code = 'INVALID_YOUTUBE_URL'
    message = 'The provided URL is not a valid YouTube URL.'
    http_status = 400


class VideoNotFound(AppError):
    code = 'VIDEO_NOT_FOUND'
    message = 'The requested YouTube video could not be found.'
    http_status = 404


class UnsupportedVideo(AppError):
    code = 'UNSUPPORTED_VIDEO'
    message = 'This video is not supported (e.g. live streams or playlists).'
    http_status = 400


class FormatNotAvailable(AppError):
    code = 'FORMAT_NOT_AVAILABLE'
    message = 'The requested format is not available for this video.'
    http_status = 400


class DownloadFailed(AppError):
    code = 'DOWNLOAD_FAILED'
    message = 'The download failed.'
    http_status = 500


class FFmpegNotFound(AppError):
    code = 'FFMPEG_NOT_FOUND'
    message = 'FFmpeg is required for this operation but was not found.'
    http_status = 500


class StorageLimitExceeded(AppError):
    code = 'STORAGE_LIMIT_EXCEEDED'
    message = 'The storage limit has been exceeded.'
    http_status = 507


class DownloadCancelled(AppError):
    code = 'DOWNLOAD_CANCELLED'
    message = 'The download was cancelled.'
    http_status = 400


class DurationExceeded(AppError):
    code = 'DURATION_EXCEEDED'
    message = 'The video duration exceeds the allowed limit.'
    http_status = 400


class TooManyJobs(AppError):
    code = 'TOO_MANY_JOBS'
    message = 'The maximum number of concurrent jobs has been reached.'
    http_status = 429


class YouTubeBlocked(AppError):
    code = 'YOUTUBE_BLOCKED'
    message = (
        'YouTube is blocking or restricting requests from this server '
        '(bot check or forced-streaming experiment). Configure cookies via '
        'YTDLP_COOKIES_FILE / YTDLP_COOKIES_FROM_BROWSER and/or a proxy via '
        'YTDLP_PROXY, or try again later.'
    )
    http_status = 503
