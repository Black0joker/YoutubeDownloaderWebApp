"""Entry point for the YouTube Downloader application."""
import os

from werkzeug.serving import WSGIRequestHandler

from app import create_app

# Speak full HTTP/1.1: Werkzeug's HTTP/1.0 default forces
# 'Connection: close' on every response, which breaks long-lived
# Server-Sent-Events streams in browsers (they treat the connection as
# about to close). With HTTP/1.1 keep-alive the SSE stream stays open.
WSGIRequestHandler.protocol_version = 'HTTP/1.1'

app = create_app()

if __name__ == "__main__":
    # The Werkzeug auto-reloader can conflict with SQLite in background
    # contexts, so it is disabled here. Use gunicorn for production.
    app.run(
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_DEBUG', '0') == '1',
        use_reloader=False,
    )
