"""Tests for authentication: login page, route protection, logout."""
from tests.conftest import TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD


class TestLoginPage:
    def test_login_page_renders(self, client):
        resp = client.get('/login')
        assert resp.status_code == 200
        assert b'Admin Login' in resp.data

    def test_login_wrong_password(self, client):
        resp = client.post('/login', data={
            'username': TEST_ADMIN_USERNAME,
            'password': 'wrong-password',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'Invalid username or password' in resp.data

    def test_login_unknown_user(self, client):
        resp = client.post('/login', data={
            'username': 'nobody',
            'password': 'whatever',
        }, follow_redirects=True)
        assert b'Invalid username or password' in resp.data

    def test_login_success_redirects_home(self, client):
        resp = client.post('/login', data={
            'username': TEST_ADMIN_USERNAME,
            'password': TEST_ADMIN_PASSWORD,
        })
        assert resp.status_code in (301, 302)
        assert resp.headers['Location'].endswith('/')


class TestRouteProtection:
    def test_page_redirects_to_login(self, client):
        for path in ('/', '/downloads', '/admin/'):
            resp = client.get(path)
            assert resp.status_code in (301, 302), path
            assert '/login' in resp.headers['Location'], path

    def test_api_returns_401_json(self, client):
        resp = client.get('/api/downloads')
        assert resp.status_code == 401
        assert resp.get_json()['error']['code'] == 'AUTH_REQUIRED'

    def test_admin_api_returns_401_json(self, client):
        resp = client.get('/admin/api/stats')
        assert resp.status_code == 401

    def test_authenticated_pages_ok(self, auth_client):
        assert auth_client.get('/').status_code == 200
        assert auth_client.get('/downloads').status_code == 200
        assert auth_client.get('/admin/').status_code == 200

    def test_next_parameter_respected(self, client):
        client.post('/login', data={
            'username': TEST_ADMIN_USERNAME,
            'password': TEST_ADMIN_PASSWORD,
        })
        # Log in via the next flow on a fresh sequence
        resp = client.get('/login?next=%2Fdownloads')
        assert resp.status_code in (301, 302)
        assert resp.headers['Location'].endswith('/downloads')

    def test_open_redirect_blocked(self, client):
        resp = client.post('/login?next=https%3A%2F%2Fevil.example.com', data={
            'username': TEST_ADMIN_USERNAME,
            'password': TEST_ADMIN_PASSWORD,
        })
        assert resp.status_code in (301, 302)
        assert 'evil.example.com' not in resp.headers['Location']


class TestLogout:
    def test_logout_then_protected(self, auth_client):
        resp = auth_client.get('/logout')
        assert resp.status_code in (301, 302)
        assert '/login' in resp.headers['Location']
        # Session is gone: protected page redirects again
        resp = auth_client.get('/')
        assert resp.status_code in (301, 302)
        assert '/login' in resp.headers['Location']
