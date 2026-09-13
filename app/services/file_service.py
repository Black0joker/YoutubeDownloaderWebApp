"""Service for file storage management."""
import glob
import os
import re
import shutil
import unicodedata
from pathlib import Path

from flask import current_app


class FileService:
    """Manage safe file paths, filenames, and cleanup."""

    def get_download_root(self):
        root = current_app.config.get('DOWNLOAD_DIR', 'downloads')
        if not os.path.isabs(root):
            base = current_app.config.get('BASEDIR') or Path(current_app.root_path).parent
            root = os.path.join(str(base), root)
        os.makedirs(root, exist_ok=True)
        return os.path.abspath(root)

    def get_job_dir(self, job_id):
        """Shard files by first two characters of the job ID."""
        shard = job_id[:2] if job_id else '00'
        directory = os.path.join(self.get_download_root(), shard)
        os.makedirs(directory, exist_ok=True)
        return directory

    def sanitize_filename(self, title):
        """Create a filesystem-safe slug from a video title."""
        title = unicodedata.normalize('NFKD', title or 'video')
        title = title.encode('ascii', 'ignore').decode('ascii')
        title = re.sub(r'[^\w\s-]', '', title).strip().lower()
        title = re.sub(r'[-\s]+', '-', title)
        return title[:80] or 'video'

    def build_output_path(self, job_id, title, extension):
        """Build a safe output path for a download job."""
        safe_title = self.sanitize_filename(title)
        filename = f"{safe_title}-{job_id}.{extension}"
        return os.path.join(self.get_job_dir(job_id), filename)

    def get_file_size(self, path):
        try:
            return os.path.getsize(path)
        except OSError:
            return None

    def delete_job_files(self, job_id):
        """Delete every file produced for a job (any extension).

        Returns the number of files removed. Partial downloads, fragments
        and temp files are included.
        """
        directory = self.get_job_dir(job_id)
        removed = 0
        for path in glob.glob(os.path.join(directory, f"job-{job_id}.*")):
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
        if removed and not os.listdir(directory):
            try:
                os.rmdir(directory)
            except OSError:
                pass
        return removed

    def delete_file(self, path):
        try:
            if path and os.path.exists(path):
                os.remove(path)
                # Clean up empty shard directory
                parent = os.path.dirname(path)
                if parent and os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
                return True
        except OSError:
            return False
        return False

    def get_total_storage_bytes(self):
        root = self.get_download_root()
        total = 0
        for dirpath, _dirnames, filenames in os.walk(root):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return total
