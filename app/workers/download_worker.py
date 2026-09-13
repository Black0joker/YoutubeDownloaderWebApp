"""Background download worker.

The core download logic lives in DownloadService and is independent of the
queue mechanism. This module dispatches jobs either to an RQ worker (when
configured and Redis is available) or to a daemon thread for simple,
self-contained deployments.
"""
import threading
import logging

from flask import current_app

logger = logging.getLogger(__name__)


def enqueue_download(job_id):
    """Enqueue a download job.

    Returns the backend used: 'rq' or 'thread'.
    """
    app = current_app._get_current_object()
    backend = app.config.get('WORKER_BACKEND', 'thread')

    if backend == 'rq':
        try:
            return _enqueue_rq(app, job_id), 'rq'
        except Exception as e:
            logger.warning('RQ enqueue failed (%s); falling back to thread.', e)

    _start_thread(app, job_id)
    return 'thread'


def _enqueue_rq(app, job_id):
    from rq import Queue
    from redis import Redis
    conn = Redis.from_url(app.config['REDIS_URL'], socket_connect_timeout=2)
    conn.ping()
    queue = Queue(connection=conn)
    queue.enqueue(rq_download_task, job_id)
    return 'rq'


def _start_thread(app, job_id):
    worker = threading.Thread(
        target=_thread_download,
        args=(app, job_id),
        name=f'download-{job_id[:8]}',
        daemon=True,
    )
    worker.start()


def _thread_download(app, job_id):
    """Run a download inside a background thread with its own app context."""
    from ..services.download_service import DownloadService
    with app.app_context():
        DownloadService().process_job(job_id)


def rq_download_task(job_id):
    """RQ task entry point. Executed by an RQ worker process."""
    from app import create_app
    from ..services.download_service import DownloadService
    app = create_app()
    with app.app_context():
        DownloadService().process_job(job_id)
