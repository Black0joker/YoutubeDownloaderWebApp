"""Tests for download request validation and job state machine."""
import pytest

from app.schemas.download import validate_download_request
from app.models import JobStatus, DownloadType


class TestDownloadSchema:
    def test_valid_video_audio(self):
        payload = {
            'video_id': 'abc123',
            'type': 'video_audio',
            'video_format_id': '137',
            'audio_format_id': '140',
            'output_format': 'mp4',
        }
        data, error = validate_download_request(payload)
        assert error is None
        assert data['type'] == 'video_audio'

    def test_missing_video_id(self):
        payload = {'type': 'video_audio', 'video_format_id': '137'}
        data, error = validate_download_request(payload)
        assert data is None
        assert 'video_id' in error

    def test_invalid_type(self):
        payload = {'video_id': 'abc', 'type': 'bogus'}
        data, error = validate_download_request(payload)
        assert data is None
        assert 'type' in error

    def test_video_requires_video_format(self):
        payload = {'video_id': 'abc', 'type': 'video'}
        data, error = validate_download_request(payload)
        assert data is None
        assert 'video_format_id' in error

    def test_invalid_output_format_for_video(self):
        payload = {
            'video_id': 'abc', 'type': 'video',
            'video_format_id': '137', 'output_format': 'mp3',
        }
        data, error = validate_download_request(payload)
        assert data is None
        assert 'output_format' in error

    def test_audio_allows_mp3(self):
        payload = {
            'video_id': 'abc', 'type': 'audio',
            'audio_format_id': '140', 'output_format': 'mp3',
        }
        data, error = validate_download_request(payload)
        assert error is None


class TestJobStateMachine:
    def test_active_states(self):
        assert JobStatus.QUEUED in JobStatus.ACTIVE
        assert JobStatus.DOWNLOADING in JobStatus.ACTIVE
        assert JobStatus.PROCESSING in JobStatus.ACTIVE

    def test_terminal_states(self):
        for s in (JobStatus.COMPLETED, JobStatus.FAILED,
                  JobStatus.CANCELLED, JobStatus.EXPIRED):
            assert s in JobStatus.TERMINAL

    def test_download_types(self):
        assert set(DownloadType.ALL) == {'video_audio', 'video', 'audio'}
