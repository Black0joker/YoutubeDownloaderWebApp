"""Video model for storing YouTube video metadata."""
from datetime import datetime
from ..extensions import db


class Video(db.Model):
    """Model representing a YouTube video's metadata."""
    __tablename__ = 'videos'

    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    thumbnail_url = db.Column(db.String(500))
    duration = db.Column(db.Integer)  # in seconds
    uploader = db.Column(db.String(200))
    formats_json = db.Column(db.Text)  # cached normalized formats (JSON)
    metadata_fetched_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with download jobs
    download_jobs = db.relationship('DownloadJob', backref='video', lazy='dynamic')

    def to_dict(self):
        """Convert video to dictionary representation."""
        return {
            'id': self.id,
            'youtube_id': self.youtube_id,
            'url': self.url,
            'title': self.title,
            'description': self.description,
            'thumbnail_url': self.thumbnail_url,
            'duration': self.duration,
            'uploader': self.uploader,
            'metadata_fetched_at': self.metadata_fetched_at.isoformat() if self.metadata_fetched_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<Video {self.youtube_id}: {self.title}>'
