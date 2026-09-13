"""Configuration settings for the application."""
import os
from pathlib import Path


def _resolve_sqlite_uri(raw_uri, basedir, default_path):
    """Return a database URI, resolving relative sqlite paths against basedir.

    Flask's CLI auto-loads .env; a relative sqlite:///instance/app.db value
    would otherwise resolve against the current working directory and fail.
    """
    uri = (raw_uri or '').strip()
    if not uri:
        return f'sqlite:///{default_path}'
    if uri.startswith('sqlite:///') and not uri.startswith('sqlite:////'):
        relative = uri[len('sqlite:///'):]
        if not os.path.isabs(relative):
            return f'sqlite:///{os.path.join(str(basedir), relative)}'
    return uri


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')

    # Admin account (seeded on first startup)
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

    # Session cookie security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = 7 * 24 * 3600  # 7 days

    # Base directory (project root)
    BASEDIR = Path(__file__).resolve().parent.parent

    # Database (resolve relative sqlite paths against BASEDIR)
    _default_db = BASEDIR / 'instance' / 'app.db'
    SQLALCHEMY_DATABASE_URI = _resolve_sqlite_uri(
        os.environ.get('DATABASE_URL'), BASEDIR, _default_db
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Download directory (absolute path)
    _dl = os.environ.get('DOWNLOAD_DIR', 'downloads')
    DOWNLOAD_DIR = _dl if os.path.isabs(_dl) else str(BASEDIR / _dl)

    # Download limits
    MAX_VIDEO_DURATION = int(os.environ.get('MAX_VIDEO_DURATION', 7200))  # 2 hours
    MAX_FILE_SIZE_MB = int(os.environ.get('MAX_FILE_SIZE_MB', 2048))  # 2GB
    MAX_CONCURRENT_JOBS = int(os.environ.get('MAX_CONCURRENT_JOBS', 3))

    # Cache settings
    METADATA_CACHE_TTL = int(os.environ.get('METADATA_CACHE_TTL', 600))  # 10 minutes

    # Cleanup settings
    CLEANUP_MAX_AGE_HOURS = int(os.environ.get('CLEANUP_MAX_AGE_HOURS', 24))
    CLEANUP_MAX_STORAGE_GB = int(os.environ.get('CLEANUP_MAX_STORAGE_GB', 10))

    # Redis
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    # Worker backend: 'thread' (self-contained) or 'rq' (requires Redis + rq worker)
    WORKER_BACKEND = os.environ.get('WORKER_BACKEND', 'thread')

    # Optional yt-dlp cookies (bypass YouTube's bot/sign-in wall).
    # Set one or the other, not both.
    YTDLP_COOKIES_FILE = os.environ.get('YTDLP_COOKIES_FILE')
    YTDLP_COOKIES_FROM_BROWSER = os.environ.get('YTDLP_COOKIES_FROM_BROWSER')
    # Optional proxy for all yt-dlp traffic, e.g. when YouTube blocks
    # this server's IP: YTDLP_PROXY=http://user:pass@host:port
    YTDLP_PROXY = os.environ.get('YTDLP_PROXY')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
