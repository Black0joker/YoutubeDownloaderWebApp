"""Admin dashboard routes."""
import os
import shutil
import subprocess

from flask import Blueprint, render_template, jsonify, current_app, request

from ..extensions import db
from ..models import Video, DownloadJob, JobStatus
from ..services.file_service import FileService
from ..services.cleanup_service import CleanupService

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/')
def dashboard():
    """Render the admin dashboard page."""
    return render_template('admin.html')


@admin_bp.route('/api/stats')
def stats():
    """Return system statistics for the dashboard."""
    file_service = FileService()

    total_videos = Video.query.count()
    total_downloads = DownloadJob.query.count()
    active_jobs = DownloadJob.query.filter(
        DownloadJob.status.in_(JobStatus.ACTIVE)
    ).count()
    completed_jobs = DownloadJob.query.filter_by(status=JobStatus.COMPLETED).count()
    failed_jobs = DownloadJob.query.filter_by(status=JobStatus.FAILED).count()

    storage_bytes = file_service.get_total_storage_bytes()

    # System health checks
    ffmpeg_ok = shutil.which('ffmpeg') is not None
    ytdlp_ok = _check_ytdlp()
    redis_ok = _check_redis()
    disk = shutil.disk_usage(file_service.get_download_root())

    return jsonify({
        'videos': total_videos,
        'downloads': total_downloads,
        'active_jobs': active_jobs,
        'completed_jobs': completed_jobs,
        'failed_jobs': failed_jobs,
        'storage_bytes': storage_bytes,
        'storage_human': _human_size(storage_bytes),
        'disk_total': disk.total,
        'disk_free': disk.free,
        'health': {
            'ffmpeg': ffmpeg_ok,
            'ytdlp': ytdlp_ok,
            'redis': redis_ok,
        },
    }), 200


@admin_bp.route('/api/jobs')
def jobs():
    """Return all jobs for the admin table."""
    all_jobs = DownloadJob.query.order_by(DownloadJob.created_at.desc()).limit(200).all()
    return jsonify({'jobs': [j.to_dict() for j in all_jobs]}), 200


@admin_bp.route('/api/cleanup', methods=['POST'])
def run_cleanup():
    """Manually trigger the cleanup process.

    Optional JSON body:
        {"clear_completed": true}  expire ALL completed downloads
        {"max_age_hours": N}       override the age threshold
    """
    data = request.get_json(silent=True) or {}
    # Manual cleanup deletes ALL completed downloads by default;
    # callers can opt out with {"clear_completed": false}.
    clear_completed = bool(data.get('clear_completed', True))
    max_age_hours = data.get('max_age_hours')
    if max_age_hours is not None:
        try:
            max_age_hours = float(max_age_hours)
        except (TypeError, ValueError):
            return jsonify({'error': {
                'code': 'VALIDATION_ERROR',
                'message': 'max_age_hours must be a number.',
            }}), 400

    service = CleanupService()
    summary = service.run(
        clear_completed=clear_completed, max_age_hours=max_age_hours
    )
    return jsonify(summary), 200


def _check_ytdlp():
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        return False


def _check_redis():
    try:
        from redis import Redis
        conn = Redis.from_url(current_app.config.get('REDIS_URL'), socket_connect_timeout=1)
        conn.ping()
        return True
    except Exception:
        return False


def _human_size(num_bytes):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if num_bytes < 1024:
            return f'{num_bytes:.1f} {unit}'
        num_bytes /= 1024.0
    return f'{num_bytes:.1f} PB'
