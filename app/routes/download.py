"""Download job API routes."""
import json
import re
import time
import os

from flask import (
    Blueprint, request, jsonify, current_app, Response, send_file, abort
)

from ..extensions import db
from ..models import DownloadJob, JobStatus, DownloadType
from ..schemas.download import validate_download_request
from ..services.download_service import DownloadService
from ..services.errors import AppError, TooManyJobs
from ..services.file_service import FileService
from ..workers.download_worker import enqueue_download

download_bp = Blueprint('download', __name__)
download_service = DownloadService()

MIME_TYPES = {
    'mp4': 'video/mp4',
    'mkv': 'video/x-matroska',
    'webm': 'video/webm',
    'mp3': 'audio/mpeg',
    'm4a': 'audio/mp4',
}


def _title_filename(title, extension):
    """Build a safe, human-readable download filename from the video title.

    Unicode is preserved; Werkzeug encodes non-ASCII names via RFC 5987
    (filename*) automatically.
    """
    name = (title or 'video').strip()
    # Strip characters that are unsafe in filenames on common OSes.
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip(' .')
    name = name[:120].strip() or 'video'
    return f'{name}.{extension}' if extension else name


@download_bp.route('', methods=['POST'])
def create_download():
    """Create a download job and enqueue it."""
    data = request.get_json(silent=True) or {}

    normalized, error = validate_download_request(data)
    if error:
        return jsonify({'error': {'code': 'VALIDATION_ERROR', 'message': error}}), 400

    # Enforce max concurrent active jobs
    max_concurrent = current_app.config.get('MAX_CONCURRENT_JOBS', 3)
    active_count = DownloadJob.query.filter(
        DownloadJob.status.in_(JobStatus.ACTIVE)
    ).count()
    if active_count >= max_concurrent:
        return jsonify({'error': {
            'code': 'TOO_MANY_JOBS',
            'message': f'Maximum concurrent downloads ({max_concurrent}) reached.'
        }}), 429

    try:
        validated = download_service.validate_request(normalized)
        job = download_service.create_job(validated)
        backend = enqueue_download(job.job_id)
        current_app.logger.info(
            'Job %s enqueued via %s', job.job_id, backend
        )
        return jsonify({'job_id': job.job_id, 'status': job.status}), 202
    except AppError as e:
        return jsonify({'error': {'code': e.code, 'message': e.message}}), e.http_status
    except Exception as e:
        current_app.logger.exception('Failed to create download job')
        return jsonify({'error': {'code': 'INTERNAL_ERROR', 'message': str(e)}}), 500


@download_bp.route('', methods=['GET'])
def list_downloads():
    """List download jobs."""
    status_filter = request.args.get('status')
    limit = min(int(request.args.get('limit', 50)), 200)

    query = DownloadJob.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    jobs = query.order_by(DownloadJob.created_at.desc()).limit(limit).all()

    return jsonify({'jobs': [j.to_dict() for j in jobs]}), 200


@download_bp.route('/<job_id>', methods=['GET'])
def get_download(job_id):
    """Get status of a download job."""
    job = DownloadJob.query.filter_by(job_id=job_id).first()
    if not job:
        return jsonify({'error': {'code': 'JOB_NOT_FOUND', 'message': 'Job not found.'}}), 404
    return jsonify(job.to_dict()), 200


@download_bp.route('/<job_id>', methods=['DELETE'])
def delete_download(job_id):
    """Delete a download job, removing its file and database record.

    Active (downloading/processing) jobs must be cancelled first.
    """
    job = DownloadJob.query.filter_by(job_id=job_id).first()
    if not job:
        return jsonify({'error': {'code': 'JOB_NOT_FOUND', 'message': 'Job not found.'}}), 404

    if job.status in (JobStatus.DOWNLOADING, JobStatus.PROCESSING):
        return jsonify({'error': {
            'code': 'JOB_ACTIVE',
            'message': 'This job is still running. Cancel it first, then delete.',
        }}), 409

    file_deleted = False
    if job.file_path:
        file_deleted = FileService().delete_file(job.file_path)

    db.session.delete(job)
    db.session.commit()
    current_app.logger.info('Job %s deleted (file_removed=%s).', job_id, file_deleted)

    return jsonify({
        'deleted': True,
        'job_id': job_id,
        'file_deleted': file_deleted,
    }), 200


@download_bp.route('/<job_id>/events', methods=['GET'])
def job_events(job_id):
    """Server-Sent Events stream of job progress."""
    # Note: do NOT set 'Connection' here. Werkzeug manages that header
    # itself; setting it manually produced duplicate, conflicting
    # Connection headers (keep-alive + close), which makes browsers
    # drop the SSE stream almost immediately.
    sse_headers = {
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
    }

    job = DownloadJob.query.filter_by(job_id=job_id).first()
    if not job:
        # Emit an SSE error event instead of a JSON 404: a JSON error makes
        # EventSource retry forever, while an error event lets the client
        # close the stream cleanly.
        def missing():
            yield f"data: {json.dumps({'error': 'Job not found.'})}\n\n"
        return Response(missing(), mimetype='text/event-stream', headers=sse_headers)

    app = current_app._get_current_object()

    def generate():
        with app.app_context():
            # ~30 minutes max at 0.5s intervals
            timeout_iterations = 3600
            for _ in range(timeout_iterations):
                # Expire cached ORM objects so the re-query below reloads
                # fresh values from SQLite. Without this, the session's
                # identity map returns the stale first snapshot forever.
                db.session.expire_all()
                j = DownloadJob.query.filter_by(job_id=job_id).first()
                if not j:
                    yield f"data: {json.dumps({'error': 'Job not found.'})}\n\n"
                    break
                payload = j.to_status_dict()
                yield f"data: {json.dumps(payload)}\n\n"
                if j.is_terminal():
                    break
                time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream', headers=sse_headers)


@download_bp.route('/<job_id>/file', methods=['GET'])
def download_file(job_id):
    """Download the completed media file."""
    job = DownloadJob.query.filter_by(job_id=job_id).first()
    if not job:
        return jsonify({'error': {'code': 'JOB_NOT_FOUND', 'message': 'Job not found.'}}), 404
    if job.status != JobStatus.COMPLETED:
        return jsonify({'error': {
            'code': 'NOT_COMPLETED',
            'message': 'The download has not completed yet.'
        }}), 400
    if not job.file_path or not os.path.exists(job.file_path):
        return jsonify({'error': {
            'code': 'FILE_MISSING',
            'message': 'The file is no longer available.'
        }}), 410

    ext = os.path.splitext(job.file_path)[1].lstrip('.').lower()
    mimetype = MIME_TYPES.get(ext, 'application/octet-stream')
    # Serve the file under the video's title, not the on-disk (job id) name.
    title = job.video.title if job.video else None
    filename = _title_filename(title, ext)
    return send_file(job.file_path, mimetype=mimetype,
                     as_attachment=True, download_name=filename)


@download_bp.route('/<job_id>/cancel', methods=['POST'])
def cancel_download(job_id):
    """Cancel a queued or active download job."""
    job = DownloadJob.query.filter_by(job_id=job_id).first()
    if not job:
        return jsonify({'error': {'code': 'JOB_NOT_FOUND', 'message': 'Job not found.'}}), 404

    if job.is_terminal():
        return jsonify({'error': {
            'code': 'ALREADY_TERMINAL',
            'message': f'Job is already {job.status}.'
        }}), 400

    job.status = JobStatus.CANCELLED
    job.completed_at = db.func.now()
    db.session.commit()
    return jsonify({'job_id': job.job_id, 'status': job.status}), 200
