"""Routes package."""
from .main import main_bp
from .video import video_bp
from .download import download_bp

__all__ = ['main_bp', 'video_bp', 'download_bp']
