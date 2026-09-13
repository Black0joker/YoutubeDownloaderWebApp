"""Flask application factory."""
import os
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, redirect, request, url_for
from flask_migrate import Migrate
from flask_login import current_user
from sqlalchemy import event

from .config import Config
from .extensions import db, login_manager


def _enable_sqlite_wal(dbapi_conn, connection_record):
    """Enable WAL mode on SQLite connections for better concurrency."""
    cursor = dbapi_conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')
    cursor.close()


# Endpoints reachable without authentication.
_AUTH_EXEMPT_ENDPOINTS = frozenset({'auth.login', 'auth.logout', 'static'})

# URL prefixes that respond with JSON 401 instead of a redirect.
_API_PREFIXES = ('/api/', '/admin/api/')


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure instance and download directories exist
    os.makedirs(os.path.join(str(app.config['BASEDIR']), 'instance'), exist_ok=True)
    os.makedirs(app.config['DOWNLOAD_DIR'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    @login_manager.user_loader
    def load_user(user_id):
        from .models.user import User
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    # Enable WAL mode for SQLite
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        with app.app_context():
            event.listen(db.engine, 'connect', _enable_sqlite_wal)

    # Configure logging
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            try:
                os.mkdir('logs')
            except OSError:
                pass
        try:
            file_handler = RotatingFileHandler(
                'logs/youtube_downloader.log',
                maxBytes=10240,
                backupCount=10
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
            app.logger.setLevel(logging.INFO)
        except OSError:
            pass

    # Register blueprints
    from .routes import main_bp, video_bp, download_bp
    from .routes.admin import admin_bp
    from .routes.auth import auth_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(video_bp, url_prefix='/api/videos')
    app.register_blueprint(download_bp, url_prefix='/api/downloads')
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)

    # Global authentication guard: every route requires login unless exempt.
    @app.before_request
    def require_authentication():
        if request.endpoint in _AUTH_EXEMPT_ENDPOINTS:
            return None
        if current_user.is_authenticated:
            return None
        if request.path.startswith(_API_PREFIXES):
            return jsonify({
                'error': {
                    'code': 'AUTH_REQUIRED',
                    'message': 'Authentication required.',
                }
            }), 401
        return redirect(url_for('auth.login', next=request.path))

    # Register CLI commands
    _register_cli(app)

    # Create database tables and seed the admin user
    with app.app_context():
        db.create_all()
        _ensure_admin_user(app)
        _recover_interrupted_jobs(app)

    return app


def _recover_interrupted_jobs(app):
    """Fail jobs that were active when the server last shut down.

    The default worker backend runs downloads in in-process threads,
    which cannot survive a restart. Without this recovery such jobs
    stay 'downloading' forever with frozen progress, and their SSE
    streams never reach a terminal state.
    """
    from datetime import datetime
    from .models import DownloadJob, JobStatus

    stale = DownloadJob.query.filter(
        DownloadJob.status.in_(JobStatus.ACTIVE)
    ).all()
    for job in stale:
        job.status = JobStatus.FAILED
        job.error_message = (
            'The server restarted while this download was running. '
            'Please start the download again.'
        )
        job.completed_at = datetime.utcnow()
    if stale:
        db.session.commit()
        app.logger.warning(
            'Marked %d interrupted download job(s) as failed.', len(stale)
        )


def _ensure_admin_user(app):
    """Create the admin user from configuration if it does not exist."""
    from .models.user import User

    username = app.config.get('ADMIN_USERNAME')
    password = app.config.get('ADMIN_PASSWORD')
    if not username or not password:
        app.logger.warning(
            'ADMIN_USERNAME/ADMIN_PASSWORD not configured; no admin user created.'
        )
        return

    user = User.query.filter_by(username=username).first()
    if user is None:
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        app.logger.info('Created admin user "%s".', username)


def _register_cli(app):
    """Register Flask CLI commands."""
    import click

    @app.cli.command('cleanup')
    @click.option('--all', 'clear_all', is_flag=True,
                  help='Delete ALL completed downloads regardless of age.')
    def cleanup_command(clear_all):
        """Run the file cleanup process."""
        from .services.cleanup_service import CleanupService
        summary = CleanupService().run(clear_completed=clear_all)
        click.echo(f"Cleanup complete: {summary}")

    @app.cli.command('health')
    def health_command():
        """Check FFmpeg, yt-dlp, and Redis availability."""
        import shutil
        ffmpeg = shutil.which('ffmpeg')
        click.echo(f"FFmpeg: {'✓ Found' if ffmpeg else '✗ Not found'}")
        try:
            import yt_dlp
            click.echo(f"yt-dlp: ✓ Installed (v{yt_dlp.version.__version__})")
        except ImportError:
            click.echo("yt-dlp: ✗ Not installed")
        try:
            from redis import Redis
            conn = Redis.from_url(app.config['REDIS_URL'], socket_connect_timeout=2)
            conn.ping()
            click.echo("Redis: ✓ Connected")
        except Exception:
            click.echo("Redis: ✗ Not available (thread fallback will be used)")

    @app.cli.command('set-admin-password')
    @click.argument('new_password', required=False)
    def set_admin_password_command(new_password):
        """Reset the admin user's password (falls back to ADMIN_PASSWORD env)."""
        from .models.user import User

        username = app.config.get('ADMIN_USERNAME', 'admin')
        password = new_password or app.config.get('ADMIN_PASSWORD')
        if not password:
            click.echo('Error: provide NEW_PASSWORD or set ADMIN_PASSWORD.')
            raise SystemExit(1)

        with app.app_context():
            user = User.query.filter_by(username=username).first()
            if user is None:
                user = User(username=username)
                db.session.add(user)
            user.set_password(password)
            db.session.commit()
            click.echo(f'Password updated for admin user "{username}".')
