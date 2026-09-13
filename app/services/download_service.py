"""Service for executing download jobs using yt-dlp and FFmpeg."""
import os
import glob
import logging
import re
import shutil
import subprocess
from datetime import datetime

from flask import current_app

from .errors import (
    FormatNotAvailable, DownloadFailed, FFmpegNotFound, DownloadCancelled
)
from ..extensions import db
from ..models import Video, DownloadJob, JobStatus, DownloadType
from .file_service import FileService
from .ytdlp_options import base_ydl_opts, is_youtube_restriction_error

logger = logging.getLogger(__name__)

# Throttle progress DB writes to avoid hammering SQLite.
PROGRESS_MIN_DELTA = 1.0  # percent

# Matches ANSI escape sequences (colors, cursor control, etc.).
_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')


def strip_ansi(value):
    """Remove ANSI escape sequences from a string (e.g. yt-dlp colors)."""
    if not value:
        return None
    cleaned = _ANSI_RE.sub('', value).strip()
    return cleaned or None


class DownloadService:
    """Build yt-dlp options, perform downloads, merge/convert via FFmpeg,
    and persist job status. Independent of the worker mechanism."""

    def __init__(self):
        self.file_service = FileService()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate_request(self, payload):
        """Validate a download request payload and return the Video + params.

        Raises FormatNotAvailable / AppError subclasses on invalid input.
        """
        from .errors import AppError

        video_id = payload.get('video_id')
        dl_type = payload.get('type')
        video_format_id = payload.get('video_format_id')
        audio_format_id = payload.get('audio_format_id')
        output_format = payload.get('output_format')

        if dl_type not in DownloadType.ALL:
            raise FormatNotAvailable(f"Invalid download type: {dl_type}")

        video = Video.query.filter_by(youtube_id=str(video_id)).first() \
            or Video.query.get(video_id)
        if not video:
            raise FormatNotAvailable('Video not found for download.')

        if dl_type in (DownloadType.VIDEO_AUDIO, DownloadType.VIDEO) and not video_format_id:
            raise FormatNotAvailable('A video format is required for this download type.')

        if dl_type == DownloadType.AUDIO and output_format not in ('mp3', 'm4a'):
            # Default audio output to mp3 if not specified
            output_format = output_format or 'mp3'

        if dl_type == DownloadType.VIDEO_AUDIO:
            output_format = output_format or 'mp4'

        return {
            'video': video,
            'type': dl_type,
            'video_format_id': video_format_id,
            'audio_format_id': audio_format_id,
            'output_format': output_format,
        }

    # ------------------------------------------------------------------
    # Job creation
    # ------------------------------------------------------------------
    def create_job(self, validated):
        """Create and persist a DownloadJob in queued state."""
        video = validated['video']
        job = DownloadJob(
            video_id=video.id,
            type=validated['type'],
            video_format_id=validated.get('video_format_id'),
            audio_format_id=validated.get('audio_format_id'),
            output_format=validated.get('output_format'),
            status=JobStatus.QUEUED,
        )
        db.session.add(job)
        db.session.commit()
        logger.info('Download job created: %s', job.job_id)
        return job

    # ------------------------------------------------------------------
    # Execution (called by worker inside app context)
    # ------------------------------------------------------------------
    def process_job(self, job_id):
        """Run the full download pipeline for a job ID."""
        job = DownloadJob.query.filter_by(job_id=job_id).first()
        if not job:
            logger.error('Job not found: %s', job_id)
            return

        if job.status == JobStatus.CANCELLED:
            return

        job.status = JobStatus.DOWNLOADING
        job.started_at = datetime.utcnow()
        db.session.commit()

        try:
            self._check_ffmpeg(job)
            filepath = self._download(job)

            # Fresh DB check: the ORM object in this session can be stale.
            self._check_cancelled(job.job_id)

            # Mark processing while finalizing / verifying
            job.status = JobStatus.PROCESSING
            db.session.commit()

            if not filepath or not os.path.exists(filepath):
                raise DownloadFailed('Output file was not produced.')

            job.file_path = filepath
            job.file_size = self.file_service.get_file_size(filepath)
            job.progress = 100.0
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            db.session.commit()
            logger.info('Download completed: %s -> %s', job.job_id, filepath)

        except DownloadCancelled:
            db.session.rollback()
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.utcnow()
            db.session.commit()
            removed = self.file_service.delete_job_files(job.job_id)
            logger.info('Download cancelled: %s (%d file(s) removed)',
                        job.job_id, removed)

        except Exception as e:
            logger.exception('Download failed for job %s', job.job_id)
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.session.commit()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _check_ffmpeg(self, job):
        needs_ffmpeg = (
            job.type == DownloadType.VIDEO_AUDIO or
            job.type == DownloadType.AUDIO
        )
        if needs_ffmpeg and shutil.which('ffmpeg') is None:
            raise FFmpegNotFound()

    def _build_format_selector(self, job):
        if job.type == DownloadType.VIDEO_AUDIO:
            if job.video_format_id and job.audio_format_id:
                return f"{job.video_format_id}+{job.audio_format_id}"
            if job.video_format_id:
                return f"{job.video_format_id}+bestaudio/best"
            return "bestvideo+bestaudio/best"
        if job.type == DownloadType.VIDEO:
            return job.video_format_id or "bestvideo/best"
        if job.type == DownloadType.AUDIO:
            return job.audio_format_id or "bestaudio/best"
        return "best"

    def _download(self, job):
        try:
            import yt_dlp
        except ImportError:
            raise DownloadFailed('yt-dlp backend is unavailable.')

        video = job.video
        job_dir = self.file_service.get_job_dir(job.job_id)
        outtmpl = os.path.join(job_dir, f"job-{job.job_id}.%(ext)s")

        # Remove stale partial outputs
        for stale in glob.glob(os.path.join(job_dir, f"job-{job.job_id}.*")):
            try:
                os.remove(stale)
            except OSError:
                pass

        progress_state = {'last': -PROGRESS_MIN_DELTA}

        def progress_hook(d):
            self._progress_hook(job, d, progress_state)

        ydl_opts = base_ydl_opts()
        ydl_opts.update({
            'format': self._build_format_selector(job),
            'outtmpl': outtmpl,
            'progress_hooks': [progress_hook],
            'restrictfilenames': True,
        })

        if job.type == DownloadType.VIDEO_AUDIO:
            ydl_opts['merge_output_format'] = job.output_format or 'mp4'

        if job.type == DownloadType.AUDIO:
            codec = 'mp3' if (job.output_format or 'mp3') == 'mp3' else 'm4a'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': codec,
                'preferredquality': '192',
            }]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video.url])
        except DownloadCancelled:
            raise
        except Exception as e:
            if is_youtube_restriction_error(str(e)):
                raise DownloadFailed(
                    'YouTube is blocking or restricting requests from this '
                    'server (bot check or forced-streaming experiment). '
                    'Configure YTDLP_COOKIES_FILE / YTDLP_COOKIES_FROM_BROWSER '
                    'and/or YTDLP_PROXY, or try again later.'
                )
            raise DownloadFailed(f'yt-dlp download failed: {e}')

        return self._locate_output(job_dir, job)

    def _check_cancelled(self, job_id):
        """Raise DownloadCancelled if the job was cancelled in the DB.

        The cancel endpoint flips the status in the database; this scalar
        query (bypassing the ORM identity map) is the polling point the
        worker consults to stop a running download.
        """
        fresh_status = db.session.execute(
            db.select(DownloadJob.status).where(DownloadJob.job_id == job_id)
        ).scalar()
        if fresh_status == JobStatus.CANCELLED:
            raise DownloadCancelled()

    def _progress_hook(self, job, d, state):
        status = d.get('status')
        try:
            # Consult the cancel flag on every hook call so a running
            # download stops promptly.
            self._check_cancelled(job.job_id)

            if status == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes') or 0
                percent = (downloaded / total * 100.0) if total else 0.0

                # Throttle DB writes
                if abs(percent - state['last']) < PROGRESS_MIN_DELTA:
                    return
                state['last'] = percent

                job.progress = min(percent, 99.9)
                job.speed = strip_ansi(d.get('_speed_str'))
                eta = d.get('eta')
                job.eta = int(eta) if eta is not None else None
                # Show the expected file size while downloading; the exact
                # on-disk size is written when the job completes.
                if total and not job.file_size:
                    job.file_size = int(total)
                # Note: do NOT set job.status here — writing DOWNLOADING
                # would overwrite a status that was just changed to
                # CANCELLED by the cancel endpoint in another session.
                db.session.commit()

            elif status == 'finished':
                # Finished a fragment / stream; moving to processing/merge.
                if job.type == DownloadType.VIDEO_AUDIO or job.type == DownloadType.AUDIO:
                    job.status = JobStatus.PROCESSING
                    job.progress = 99.9
                    db.session.commit()
        except DownloadCancelled:
            db.session.rollback()
            raise
        except Exception:
            db.session.rollback()

    def _locate_output(self, job_dir, job):
        """Find the produced output file in the job directory."""
        prefix = f"job-{job.job_id}."
        candidates = glob.glob(os.path.join(job_dir, prefix + "*"))
        # Exclude partial/temp files
        candidates = [
            c for c in candidates
            if not c.endswith(('.part', '.ytdl', '.temp'))
        ]
        if not candidates:
            return None
        # Prefer the requested output extension if present
        ext = job.output_format
        if ext:
            for c in candidates:
                if c.endswith('.' + ext):
                    return c
        # Otherwise newest/largest
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidates[0]
