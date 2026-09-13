# syntax=docker/dockerfile:1

# ============================================================
# YouTube Video & Audio Downloader
# Flask + SQLite + yt-dlp + FFmpeg (+ optional Node.js runtime)
# ============================================================
FROM python:3.12-slim

# Unbuffered logs, no .pyc files, quieter pip
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ---- System dependencies ----
# ffmpeg : merges video+audio streams and converts audio (mp3/m4a)
# nodejs : yt-dlp JavaScript runtime (helps current YouTube extraction)
# curl   : used by the HEALTHCHECK below
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ---- Non-root runtime user ----
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /opt/youtube-downloader

# ---- Python dependencies (separate layer for caching) ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Application code ----
COPY app ./app
COPY run.py .

# ---- Runtime dirs (database, media, logs) owned by appuser ----
RUN mkdir -p instance downloads logs \
    && chown -R appuser:appuser /opt/youtube-downloader

USER appuser

EXPOSE 5000

# /login is auth-exempt, so it is a safe liveness target.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:5000/login > /dev/null || exit 1

# Threaded gunicorn: SSE streams hold a request thread, and downloads run as
# daemon threads inside the worker process. A single worker keeps SQLite
# writes simple; scale out with WORKER_BACKEND=rq + Redis + rq workers instead.
CMD ["gunicorn", "--worker-class", "gthread", "--workers", "1", "--threads", "16", "--timeout", "120", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-", "run:app"]
