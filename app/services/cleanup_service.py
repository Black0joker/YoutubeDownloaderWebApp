"""Service for cleaning up old download files and enforcing storage limits.

Cleanup fully purges a download: the media file on disk, the DownloadJob
record, and the Video record once no other job references it. This keeps
both the downloads directory and the database from growing without bound.
"""
import logging
from datetime import datetime, timedelta

from flask import current_app

from ..extensions import db
from ..models import DownloadJob, JobStatus, Video
from .file_service import FileService

logger = logging.getLogger(__name__)


class CleanupService:
    """Delete stale files, job records, and orphaned videos; enforce storage caps."""

    def __init__(self):
        self.file_service = FileService()

    def run(self, clear_completed=False, max_age_hours=None):
        """Run all cleanup policies and return a summary.

        Args:
            clear_completed: when True, purge ALL completed downloads
                regardless of age (manual full cleanup).
            max_age_hours: override CLEANUP_MAX_AGE_HOURS for this run.
        """
        expired, expired_freed = self.expire_old_files(
            clear_completed=clear_completed, max_age_hours=max_age_hours
        )
        freed = expired_freed + self.enforce_storage_limit()
        return {'expired_count': expired, 'storage_freed_bytes': freed}

    def expire_old_files(self, clear_completed=False, max_age_hours=None):
        """Purge completed downloads older than CLEANUP_MAX_AGE_HOURS.

        With clear_completed=True every completed download is purged.
        Returns (purged_count, freed_bytes).
        """
        query = DownloadJob.query.filter(
            DownloadJob.status == JobStatus.COMPLETED,
            DownloadJob.file_path.isnot(None),
        )

        if not clear_completed:
            if max_age_hours is None:
                max_age_hours = current_app.config.get('CLEANUP_MAX_AGE_HOURS', 24)
            cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
            query = query.filter(DownloadJob.completed_at < cutoff)

        jobs = query.all()
        return self._purge_jobs(jobs)

    def enforce_storage_limit(self):
        """Purge oldest completed downloads until under CLEANUP_MAX_STORAGE_GB.

        Returns the number of bytes freed.
        """
        max_gb = current_app.config.get('CLEANUP_MAX_STORAGE_GB', 10)
        max_bytes = max_gb * 1024 ** 3

        total = self.file_service.get_total_storage_bytes()
        if total <= max_bytes:
            return 0

        jobs = DownloadJob.query.filter(
            DownloadJob.status == JobStatus.COMPLETED,
            DownloadJob.file_path.isnot(None),
        ).order_by(DownloadJob.completed_at.asc()).all()

        to_purge = []
        projected_freed = 0
        for job in jobs:
            if total - projected_freed <= max_bytes:
                break
            size = job.file_size or self.file_service.get_file_size(job.file_path) or 0
            projected_freed += size
            to_purge.append(job)

        if not to_purge:
            return 0
        _count, freed = self._purge_jobs(to_purge)
        return freed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _purge_jobs(self, jobs):
        """Delete files, DownloadJob records, and orphaned Videos.

        Returns (purged_count, freed_bytes).
        """
        if not jobs:
            return 0, 0

        freed_bytes = 0
        video_ids = set()
        for job in jobs:
            if job.file_path:
                freed_bytes += (
                    job.file_size
                    or self.file_service.get_file_size(job.file_path)
                    or 0
                )
                self.file_service.delete_file(job.file_path)
            if job.video_id is not None:
                video_ids.add(job.video_id)
            db.session.delete(job)

        # Flush job deletions so the orphan check below sees current rows.
        db.session.flush()
        for video_id in video_ids:
            self._delete_video_if_orphaned(video_id)
        db.session.commit()

        logger.info(
            'Cleanup purged %d download(s) (%d bytes freed).',
            len(jobs), freed_bytes,
        )
        return len(jobs), freed_bytes

    def _delete_video_if_orphaned(self, video_id):
        """Delete a Video once no DownloadJob references it anymore."""
        remaining = DownloadJob.query.filter_by(video_id=video_id).count()
        if remaining:
            return
        video = db.session.get(Video, video_id)
        if video is not None:
            db.session.delete(video)
