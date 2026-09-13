"""Download job model for tracking download tasks."""
import re
import uuid
from datetime import datetime
from ..extensions import db

# Strips ANSI escape sequences (e.g. terminal colors from yt-dlp output).
_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')


def _clean_speed(value):
    """Return a display-safe speed string without ANSI escape codes."""
    if not value:
        return None
    cleaned = _ANSI_RE.sub('', value).strip()
    return cleaned or None


class JobStatus:
    """Download job state machine states."""
    QUEUED = 'queued'
    DOWNLOADING = 'downloading'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    EXPIRED = 'expired'

    ACTIVE = (QUEUED, DOWNLOADING, PROCESSING)
    TERMINAL = (COMPLETED, FAILED, CANCELLED, EXPIRED)


class DownloadType:
    """Download type options."""
    VIDEO_AUDIO = 'video_audio'
    VIDEO = 'video'
    AUDIO = 'audio'

    ALL = (VIDEO_AUDIO, VIDEO, AUDIO)


def generate_uuid():
    return str(uuid.uuid4())


class DownloadJob(db.Model):
    """Model representing a download job."""
    __tablename__ = 'download_jobs'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), unique=True, nullable=False, index=True, default=generate_uuid)
    video_id = db.Column(db.Integer, db.ForeignKey('videos.id'), nullable=False)

    # Job parameters
    type = db.Column(db.String(20), nullable=False)
    video_format_id = db.Column(db.String(20))
    audio_format_id = db.Column(db.String(20))
    output_format = db.Column(db.String(20))

    # Status & progress
    status = db.Column(db.String(20), default=JobStatus.QUEUED, index=True)
    progress = db.Column(db.Float, default=0.0)
    speed = db.Column(db.String(50))
    eta = db.Column(db.Integer)

    # Result
    file_path = db.Column(db.String(500))
    file_size = db.Column(db.Integer)  # bytes
    error_message = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'job_id': self.job_id,
            'video_id': self.video_id,
            'video': self.video.to_dict() if self.video else None,
            'type': self.type,
            'video_format_id': self.video_format_id,
            'audio_format_id': self.audio_format_id,
            'output_format': self.output_format,
            'status': self.status,
            'progress': round(self.progress, 1) if self.progress is not None else 0.0,
            'speed': _clean_speed(self.speed),
            'eta': self.eta,
            'file_size': self.file_size,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }

    def to_status_dict(self):
        """Lightweight status dict used by polling/SSE."""
        return {
            'job_id': self.job_id,
            'status': self.status,
            'progress': round(self.progress, 1) if self.progress is not None else 0.0,
            'speed': _clean_speed(self.speed),
            'eta': self.eta,
            'file_size': self.file_size,
            'error_message': self.error_message,
        }

    def is_active(self):
        return self.status in JobStatus.ACTIVE

    def is_terminal(self):
        return self.status in JobStatus.TERMINAL

    def __repr__(self):
        return f'<DownloadJob {self.job_id} [{self.status}]>'
