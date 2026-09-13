"""Authentication routes: login and logout."""
from datetime import datetime
from urllib.parse import urlparse

from flask import (
    Blueprint, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_user, logout_user

from ..extensions import db
from ..models.user import User

auth_bp = Blueprint('auth', __name__)


def _safe_next(next_url):
    """Return next_url only if it is a same-site relative path.

    Prevents open-redirect attacks via the ?next= parameter.
    """
    if not next_url:
        return None
    parsed = urlparse(next_url)
    if parsed.netloc or parsed.scheme:
        return None
    if not next_url.startswith('/'):
        return None
    return next_url


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Render the login form and authenticate the user."""
    if current_user.is_authenticated:
        return redirect(_safe_next(request.args.get('next')) or url_for('main.index'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        user = User.query.filter_by(username=username).first()
        if user is not None and user.check_password(password):
            login_user(user, remember=bool(request.form.get('remember')))
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            next_url = _safe_next(request.args.get('next')) or url_for('main.index')
            return redirect(next_url)

        flash('Invalid username or password.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """Log the current user out and return to the login page."""
    logout_user()
    return redirect(url_for('auth.login'))
