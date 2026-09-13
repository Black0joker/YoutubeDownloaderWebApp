"""Request validation schemas package."""
from .video import validate_analyze_request
from .download import validate_download_request

__all__ = ['validate_analyze_request', 'validate_download_request']
