"""Validation for download requests."""
from ..models import DownloadType

ALLOWED_VIDEO_OUTPUTS = ('mp4', 'mkv', 'webm')
ALLOWED_AUDIO_OUTPUTS = ('mp3', 'm4a')


def validate_download_request(data):
    """Validate a download request payload.

    Returns (normalized_dict, None) on success or (None, error_message) on failure.
    """
    data = data or {}
    errors = []

    video_id = (data.get('video_id') or '').strip()
    if not video_id:
        errors.append('video_id is required.')

    dl_type = data.get('type')
    if dl_type not in DownloadType.ALL:
        errors.append(f"type must be one of {DownloadType.ALL}.")

    video_format_id = data.get('video_format_id')
    audio_format_id = data.get('audio_format_id')
    output_format = (data.get('output_format') or '').strip().lower() or None

    if dl_type in (DownloadType.VIDEO_AUDIO, DownloadType.VIDEO):
        if not video_format_id:
            errors.append('video_format_id is required for this download type.')
        if output_format and output_format not in ALLOWED_VIDEO_OUTPUTS:
            errors.append(f"output_format must be one of {ALLOWED_VIDEO_OUTPUTS}.")

    if dl_type == DownloadType.AUDIO:
        if output_format and output_format not in ALLOWED_AUDIO_OUTPUTS:
            errors.append(f"output_format must be one of {ALLOWED_AUDIO_OUTPUTS}.")

    if errors:
        return None, ' '.join(errors)

    return {
        'video_id': video_id,
        'type': dl_type,
        'video_format_id': video_format_id,
        'audio_format_id': audio_format_id,
        'output_format': output_format,
    }, None
