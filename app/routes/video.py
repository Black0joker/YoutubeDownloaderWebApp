"""Video analysis API routes."""
from flask import Blueprint, request, jsonify, current_app

from ..extensions import db
from ..schemas.video import validate_analyze_request
from ..services.youtube_service import YouTubeService
from ..services.errors import AppError
from ..models import Video

video_bp = Blueprint('video', __name__)
youtube_service = YouTubeService()


@video_bp.route('/analyze', methods=['POST'])
def analyze_video():
    """Analyze a YouTube URL and return metadata + normalized formats."""
    data = request.get_json(silent=True) or {}
    normalized, error = validate_analyze_request(data)
    if error:
        return jsonify({'error': {'code': 'VALIDATION_ERROR', 'message': error}}), 400

    try:
        result = youtube_service.analyze(normalized['url'])
        return jsonify(result), 200
    except AppError as e:
        return jsonify({'error': {'code': e.code, 'message': e.message}}), e.http_status
    except Exception as e:
        current_app.logger.exception('Unexpected error during analysis')
        return jsonify({'error': {'code': 'INTERNAL_ERROR', 'message': str(e)}}), 500


@video_bp.route('/<int:id>', methods=['GET'])
def get_video(id):
    """Retrieve cached video metadata by internal DB id."""
    video = Video.query.get(id)
    if not video:
        return jsonify({'error': {'code': 'VIDEO_NOT_FOUND', 'message': 'Video not found.'}}), 404
    return jsonify(video.to_dict()), 200


@video_bp.route('/by-youtube-id/<youtube_id>', methods=['GET'])
def get_video_by_youtube_id(youtube_id):
    """Retrieve cached video metadata by YouTube id."""
    video = Video.query.filter_by(youtube_id=youtube_id).first()
    if not video:
        return jsonify({'error': {'code': 'VIDEO_NOT_FOUND', 'message': 'Video not found.'}}), 404
    return jsonify(video.to_dict()), 200
