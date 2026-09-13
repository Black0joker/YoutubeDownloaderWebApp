"""Validation for video analysis requests."""


def validate_analyze_request(data):
    """Validate an analyze request payload.

    Returns (normalized_dict, None) on success or (None, error_message) on failure.
    """
    data = data or {}
    url = (data.get('url') or '').strip()
    if not url:
        return None, 'A YouTube URL is required.'
    if len(url) > 2000:
        return None, 'URL is too long.'
    return {'url': url}, None
