"""Integration tests for API routes (authenticated)."""
from datetime import datetime

import pytest


_job_counter = {'n': 0}


def _make_job(app, status='completed', file_path=None, title='Test Video'):
    """Insert a Video + DownloadJob fixture row and return the job_id."""
    from app.extensions import db
    from app.models import DownloadJob, Video

    _job_counter['n'] += 1
    with app.app_context():
        video = Video(
            youtube_id=f'dl{_job_counter["n"]:04d}{status[:6]}',
            url='https://www.youtube.com/watch?v=deltest',
            title=title,
        )
        db.session.add(video)
        db.session.commit()
        job = DownloadJob(
            video_id=video.id,
            type='audio',
            audio_format_id='140',
            output_format='mp3',
            status=status,
            file_path=file_path,
            completed_at=datetime.utcnow() if status == 'completed' else None,
        )
        db.session.add(job)
        db.session.commit()
        return job.job_id


class TestHomeRoutes:
    def test_index(self, auth_client):
        resp = auth_client.get('/')
        assert resp.status_code == 200
        assert b'YouTube' in resp.data

    def test_downloads_page(self, auth_client):
        resp = auth_client.get('/downloads')
        assert resp.status_code == 200

    def test_admin_dashboard(self, auth_client):
        resp = auth_client.get('/admin/')
        assert resp.status_code == 200


class TestAnalyzeRoute:
    def test_missing_url(self, auth_client):
        resp = auth_client.post('/api/videos/analyze', json={})
        assert resp.status_code == 400
        assert resp.get_json()['error']['code'] == 'VALIDATION_ERROR'

    def test_invalid_url(self, auth_client):
        resp = auth_client.post('/api/videos/analyze',
                                json={'url': 'https://example.com/notyoutube'})
        assert resp.status_code == 400
        assert resp.get_json()['error']['code'] == 'INVALID_YOUTUBE_URL'


class TestDownloadRoutes:
    def test_create_download_validation_error(self, auth_client):
        resp = auth_client.post('/api/downloads', json={'type': 'bogus'})
        assert resp.status_code == 400

    def test_list_downloads_empty(self, auth_client):
        resp = auth_client.get('/api/downloads')
        assert resp.status_code == 200
        assert resp.get_json()['jobs'] == []

    def test_get_missing_job(self, auth_client):
        resp = auth_client.get('/api/downloads/nonexistent-id')
        assert resp.status_code == 404

    def test_admin_stats(self, auth_client):
        resp = auth_client.get('/admin/api/stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'downloads' in data
        assert 'health' in data


class TestDeleteJob:
    def test_delete_existing_job(self, app, auth_client):
        job_id = _make_job(app, status='completed')
        resp = auth_client.delete(f'/api/downloads/{job_id}')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['deleted'] is True
        assert body['job_id'] == job_id
        # Record is gone
        resp = auth_client.get(f'/api/downloads/{job_id}')
        assert resp.status_code == 404

    def test_delete_missing_job(self, auth_client):
        resp = auth_client.delete('/api/downloads/does-not-exist')
        assert resp.status_code == 404
        assert resp.get_json()['error']['code'] == 'JOB_NOT_FOUND'

    def test_delete_active_job_conflict(self, app, auth_client):
        job_id = _make_job(app, status='downloading')
        resp = auth_client.delete(f'/api/downloads/{job_id}')
        assert resp.status_code == 409
        assert resp.get_json()['error']['code'] == 'JOB_ACTIVE'

    def test_delete_requires_auth(self, app, client):
        job_id = _make_job(app, status='completed')
        resp = client.delete(f'/api/downloads/{job_id}')
        assert resp.status_code == 401


class TestCleanup:
    def test_cleanup_requires_auth(self, client):
        resp = client.post('/admin/api/cleanup')
        assert resp.status_code == 401

    def test_cleanup_default_clears_all_completed(self, app, auth_client):
        """Manual cleanup without a body purges ALL completed downloads."""
        _make_job(app, status='completed', file_path='/nonexistent/file.mp4')

        resp = auth_client.post('/admin/api/cleanup', json={})
        assert resp.status_code == 200
        assert resp.get_json()['expired_count'] == 1

        from app.extensions import db
        from app.models import DownloadJob, Video
        with app.app_context():
            assert DownloadJob.query.count() == 0
            assert Video.query.count() == 0

    def test_cleanup_keeps_video_with_other_jobs(self, app, auth_client):
        """A video is only removed once every one of its jobs is purged."""
        from app.extensions import db
        from app.models import DownloadJob, Video
        with app.app_context():
            video = Video(
                youtube_id='sharedvid001',
                url='https://www.youtube.com/watch?v=sharedvid001',
                title='Shared Video',
            )
            db.session.add(video)
            db.session.commit()
            completed = DownloadJob(
                video_id=video.id, type='audio', output_format='mp3',
                status='completed', file_path='/nonexistent/a.mp3',
                completed_at=datetime.utcnow(),
            )
            active = DownloadJob(
                video_id=video.id, type='audio', output_format='mp3',
                status='downloading',
            )
            db.session.add_all([completed, active])
            db.session.commit()
            video_id = video.id

        resp = auth_client.post('/admin/api/cleanup', json={})
        assert resp.status_code == 200
        assert resp.get_json()['expired_count'] == 1

        with app.app_context():
            assert db.session.get(Video, video_id) is not None
            assert DownloadJob.query.count() == 1

    def test_cleanup_policy_only_mode(self, app, auth_client):
        """clear_completed=false applies the age limit only."""
        _make_job(app, status='completed', file_path='/nonexistent/file.mp4')

        resp = auth_client.post('/admin/api/cleanup', json={'clear_completed': False})
        assert resp.status_code == 200
        assert resp.get_json()['expired_count'] == 0

    def test_cleanup_invalid_max_age(self, auth_client):
        resp = auth_client.post('/admin/api/cleanup', json={'max_age_hours': 'abc'})
        assert resp.status_code == 400


class TestFileDownloadName:
    def _make_completed_job_with_file(self, app, title):
        """Create a completed job backed by a real temp file."""
        import os
        with app.app_context():
            root = app.config['DOWNLOAD_DIR']
        os.makedirs(root, exist_ok=True)
        path = os.path.join(root, f'job-fixture-{_job_counter["n"] + 1}.mp3')
        with open(path, 'wb') as f:
            f.write(b'x' * 32)
        return _make_job(app, status='completed', file_path=path, title=title), path

    def test_ascii_title_used_as_filename(self, app, auth_client):
        job_id, _ = self._make_completed_job_with_file(app, 'Me at the zoo')
        resp = auth_client.get(f'/api/downloads/{job_id}/file')
        assert resp.status_code == 200
        cd = resp.headers.get('Content-Disposition', '')
        assert 'Me at the zoo.mp3' in cd

    def test_unicode_title_encoded_rfc5987(self, app, auth_client):
        job_id, _ = self._make_completed_job_with_file(app, '\u0641\u064a\u062f\u064a\u0648 \u062a\u062c\u0631\u064a\u0628\u064a')
        resp = auth_client.get(f'/api/downloads/{job_id}/file')
        assert resp.status_code == 200
        cd = resp.headers.get('Content-Disposition', '')
        assert "filename*=UTF-8''" in cd

    def test_unsafe_characters_sanitized(self, app, auth_client):
        job_id, _ = self._make_completed_job_with_file(
            app, 'Bad/Title: With*Unsafe?Chars'
        )
        resp = auth_client.get(f'/api/downloads/{job_id}/file')
        assert resp.status_code == 200
        cd = resp.headers.get('Content-Disposition', '')
        assert 'Bad Title With Unsafe Chars.mp3' in cd

    def test_missing_video_falls_back(self):
        """A job whose video record is missing still gets a usable name."""
        from app.routes.download import _title_filename
        assert _title_filename(None, 'mp4') == 'video.mp4'
        assert _title_filename('   ', '') == 'video'


class TestSpeedSanitization:
    ANSI_SPEED = '\x1b[0;32m 11.54MiB/s\x1b[0m'

    def test_strip_ansi_helper(self):
        from app.services.download_service import strip_ansi
        assert strip_ansi(self.ANSI_SPEED) == '11.54MiB/s'
        assert strip_ansi('1.2MiB/s') == '1.2MiB/s'
        assert strip_ansi(None) is None
        assert strip_ansi('\x1b[0m') is None

    def test_serialization_cleans_speed(self):
        """Existing DB rows with ANSI codes serialize cleanly."""
        from app.models import DownloadJob
        job = DownloadJob(
            video_id=1, type='audio', speed=self.ANSI_SPEED,
        )
        assert job.to_status_dict()['speed'] == '11.54MiB/s'
        assert job.to_dict()['speed'] == '11.54MiB/s'

    def test_status_dict_includes_file_size(self):
        from app.models import DownloadJob
        job = DownloadJob(video_id=1, type='audio', file_size=11108540)
        assert job.to_status_dict()['file_size'] == 11108540

class TestEventsStreamRobustness:
    def test_events_for_missing_job_returns_sse_error(self, auth_client):
        """A deleted/unknown job must yield an SSE error event, not a JSON
        404 (which would make EventSource retry forever)."""
        resp = auth_client.get('/api/downloads/does-not-exist/events')
        assert resp.status_code == 200
        assert 'text/event-stream' in resp.headers.get('Content-Type', '')
        body = resp.get_data(as_text=True)
        assert '"error"' in body and 'Job not found.' in body

    def test_interrupted_jobs_recovered_on_startup(self, app):
        """Jobs still active when the server restarts are marked failed."""
        from app import _recover_interrupted_jobs
        from app.extensions import db
        from app.models import DownloadJob, JobStatus

        with app.app_context():
            job = DownloadJob(video_id=1, type='audio', status=JobStatus.DOWNLOADING)
            db.session.add(job)
            db.session.commit()
            job_id = job.job_id

        _recover_interrupted_jobs(app)

        with app.app_context():
            job = DownloadJob.query.filter_by(job_id=job_id).first()
            assert job.status == JobStatus.FAILED
            assert 'restarted' in job.error_message
            assert job.completed_at is not None
