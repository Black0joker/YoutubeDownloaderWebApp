# YouTube Video & Audio Downloader

A full-featured web application for downloading YouTube videos and audio, built with **Flask**, **SQLite**, **SQLAlchemy**, **yt-dlp**, and **FFmpeg**.

## Features

- Paste any YouTube URL (`watch`, `youtu.be`, Shorts, embed)
- Analyze videos to retrieve metadata and available formats
- Choose download type:
  - **Video + Audio** (streams merged with FFmpeg)
  - **Video only**
  - **Audio only** (MP3 / M4A conversion via FFmpeg)
- Select video quality, audio quality, and output format
- Real-time progress via **Server-Sent Events (SSE)**
- Download history with status, progress, and file download
- Automatic cleanup of old files (age + storage-limit policies)
- Background downloads (thread worker by default; RQ + Redis supported)
- Metadata caching (SQLite, configurable TTL)
- Admin dashboard with stats, jobs, and health checks
- CLI commands: `flask health`, `flask cleanup`

## Requirements

| Component | Version |
|---|---|
| Python | 3.10+ |
| FFmpeg | required (merging / audio conversion) |
| yt-dlp | installed via requirements.txt |
| Node.js | recommended (yt-dlp JS runtime for full format list) |
| Redis | optional (only when `WORKER_BACKEND=rq`) |

## Quick Start

```bash
# 1. Clone / enter the project
cd youtube-downloader

# 2. Create a virtualenv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure (edit .env as needed)
cp .env .env  # .env already contains development defaults

# 4. Run the server
python run.py
# → http://localhost:5000
```

Database tables are created automatically on first start (`instance/app.db`).

### Verify your environment

```bash
flask health
```

## Authentication

All routes (pages, API, SSE, file downloads, admin) are protected by session-based authentication.

- **Login page:** `/login` — unauthenticated page requests redirect there (`?next=` supported, open redirects blocked).
- **Unauthenticated API requests** receive `401 {"error": {"code": "AUTH_REQUIRED"}}`.
- The admin account is **seeded on first startup** from `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`.
- Default dev credentials: `admin` / `admin123` — **change them before production**.
- Reset a password anytime: `flask set-admin-password <new-password>`
- Login attempts are rate-limited (15/min per IP). Session cookies are HttpOnly with `SameSite=Lax`; "remember me" lasts 7 days.

## Configuration

All settings live in `.env`:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | dev key | Flask secret key |
| `DATABASE_URL` | `sqlite:///instance/app.db` | Database URI (relative sqlite paths resolve to project root) |
| `DOWNLOAD_DIR` | `downloads` | Where media files are stored |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection (RQ backend) |
| `WORKER_BACKEND` | `thread` | `thread` (self-contained) or `rq` (needs Redis + rq worker) |
| `METADATA_CACHE_TTL` | `600` | Analysis cache lifetime (seconds) |
| `MAX_VIDEO_DURATION` | `7200` | Reject videos longer than this (seconds) |
| `MAX_FILE_SIZE_MB` | `2048` | Max file size (MB) |
| `MAX_CONCURRENT_JOBS` | `3` | Max simultaneous active downloads |
| `CLEANUP_MAX_AGE_HOURS` | `24` | Completed files older than this are expired |
| `CLEANUP_MAX_STORAGE_GB` | `10` | Storage cap; oldest files removed beyond it |
| `YTDLP_COOKIES_FILE` | — | Path to a Netscape-format cookies.txt to bypass YouTube bot checks |
| `YTDLP_COOKIES_FROM_BROWSER` | — | Browser name (e.g. `firefox`) to read YouTube cookies from |
| `YTDLP_PROXY` | — | Proxy URL for all yt-dlp traffic (e.g. when YouTube blocks this server's IP) |

## Architecture

```
Browser (HTML/CSS/JS + SSE)
   │ HTTP
Flask (routes → services → yt-dlp / FFmpeg → SQLite)
   │
Background worker (thread or RQ) performs downloads
   │
downloads/<shard>/<file>   (media files on disk, metadata in SQLite)
```

Key principle: **downloads never happen inside the HTTP request.** Flask creates a job and returns immediately; a background worker runs yt-dlp/FFmpeg and updates job progress, which the browser receives via SSE.

### Job lifecycle

```
queued → downloading → processing → completed
                            │
                            └→ failed / cancelled / expired
```

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/videos/analyze` | Analyze a YouTube URL → metadata + formats |
| `GET` | `/api/videos/<id>` | Cached video metadata (DB id) |
| `GET` | `/api/videos/by-youtube-id/<yt_id>` | Cached video metadata (YouTube id) |
| `POST` | `/api/downloads` | Create a download job |
| `GET` | `/api/downloads` | List jobs (`?status=`, `?limit=`) |
| `GET` | `/api/downloads/<job_id>` | Job status |
| `GET` | `/api/downloads/<job_id>/events` | SSE progress stream |
| `GET` | `/api/downloads/<job_id>/file` | Download completed file |
| `POST` | `/api/downloads/<job_id>/cancel` | Cancel a job |
| `DELETE` | `/api/downloads/<job_id>` | Delete a job (removes file + record; 409 if still running) |
| `POST` | `/admin/api/cleanup` | Manual cleanup — deletes ALL completed downloads by default; `{"clear_completed": false}` for age/cap policy only, `{"max_age_hours": N}` to override the threshold |

### Example: analyze

```bash
curl -X POST http://localhost:5000/api/videos/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

### Example: download (video + audio)

```bash
curl -X POST http://localhost:5000/api/downloads \
  -H 'Content-Type: application/json' \
  -d '{
    "video_id": "dQw4w9WgXcQ",
    "type": "video_audio",
    "video_format_id": "137",
    "audio_format_id": "140",
    "output_format": "mp4"
  }'
```

## Background Workers

### Default: thread backend (no extra services)

Downloads run in daemon threads inside the Flask process. Best for development and small deployments.

### RQ + Redis (production)

```bash
export WORKER_BACKEND=rq
redis-server &          # start Redis
rq worker --url redis://localhost:6379/0 &   # start RQ worker
python run.py           # or gunicorn
```

The core download logic is queue-agnostic (`DownloadService`), so the backend can be swapped without touching it.

## Cleanup

Automatic cleanup expires old completed files and enforces the storage cap.

```bash
flask cleanup              # age + storage-cap policies only
flask cleanup --all        # delete ALL completed downloads regardless of age
```

The **manual** cleanup (`POST /admin/api/cleanup` and the admin dashboard button)
deletes ALL completed downloads by default. Send `{"clear_completed": false}` to
apply only the age/storage-cap policies, or `{"max_age_hours": N}` to override the threshold.

For scheduled cleanup, add a cron entry:

```
0 * * * * cd /path/to/youtube-downloader && venv/bin/flask cleanup
```

## Admin Dashboard

Visit `/admin` for statistics (videos, downloads, active/failed jobs, storage), a job table, system health (FFmpeg / yt-dlp / Redis), and a manual cleanup trigger (with an "Also delete all completed downloads" option).

Individual downloads can be removed from the **My Downloads** page (per-job **Delete** button) or via `DELETE /api/downloads/<job_id>`.

## Testing

```bash
pytest tests/ -v
```

Tests cover URL parsing, format normalization, request validation, the job state machine, and API routes. Integration tests use an in-memory SQLite database and never hit YouTube.

## Project Structure

```
youtube-downloader/
├── app/
│   ├── __init__.py          # app factory, WAL mode, CLI commands
│   ├── config.py            # configuration
│   ├── extensions.py        # db, login_manager
│   ├── models/              # Video, DownloadJob
│   ├── routes/              # main, video, download, admin
│   ├── schemas/             # request validation
│   ├── services/            # youtube, format, download, file, cleanup
│   ├── workers/             # thread / RQ dispatch
│   ├── templates/           # base, index, video, downloads, admin
│   └── static/              # css / js
├── downloads/               # media files (sharded by job id)
├── instance/                # app.db
├── tests/
├── .env
├── requirements.txt
├── run.py
└── README.md
```

## Production Deployment

```bash
gunicorn -w 2 -b 0.0.0.0:5000 --threads 4 'run:app'
```

Recommended production stack: Gunicorn (or behind Nginx/Caddy) + Redis + RQ worker + FFmpeg. For SSE with Gunicorn, use `--worker-class gthread` or keep thread-based workers.

## Security Notes

- URLs are validated against YouTube domains only (no arbitrary URL downloads).
- Filenames are sanitized; files are stored in sharded, server-generated paths.
- All subprocess/yt-dlp usage avoids shell interpolation.
- Rate limits and concurrency/storage caps protect against abuse.

## Legal

Use this application only for content you are authorized to download. Respect YouTube's Terms of Service and applicable copyright law.
