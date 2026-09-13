"""Main routes for rendering pages."""
from flask import Blueprint, render_template
from ..models import DownloadJob, JobStatus

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Home page with URL input and recent downloads."""
    recent_jobs = DownloadJob.query.order_by(DownloadJob.created_at.desc()).limit(5).all()
    return render_template('index.html', recent_jobs=recent_jobs)


@main_bp.route('/video/<video_id>')
def video_page(video_id):
    """Video details page (format selection UI)."""
    return render_template('video.html', video_id=video_id)


@main_bp.route('/downloads')
def downloads_page():
    """Download history page."""
    return render_template('downloads.html')
