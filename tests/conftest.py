"""Shared pytest fixtures."""
import tempfile

import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db

TEST_ADMIN_USERNAME = 'admin'
TEST_ADMIN_PASSWORD = 'test-password-123'


class TestConfig(TestingConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    DOWNLOAD_DIR = tempfile.mkdtemp()
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    ADMIN_USERNAME = TEST_ADMIN_USERNAME
    ADMIN_PASSWORD = TEST_ADMIN_PASSWORD


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """Test client that is already logged in as the admin user."""
    client = app.test_client()
    resp = client.post('/login', data={
        'username': TEST_ADMIN_USERNAME,
        'password': TEST_ADMIN_PASSWORD,
    }, follow_redirects=False)
    assert resp.status_code in (301, 302), 'login should succeed in tests'
    return client


@pytest.fixture
def runner(app):
    return app.test_cli_runner()
