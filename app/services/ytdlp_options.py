"""Shared helpers for building yt-dlp options."""
import os
import shutil

# Phrases yt-dlp uses when YouTube demands sign-in (bot detection).
BOT_CHECK_MARKERS = ('sign in to confirm', 'not a bot', 'use --cookies')

# Phrases for YouTube's stream-restriction walls, e.g. the SABR-only
# streaming experiment (https://github.com/yt-dlp/yt-dlp/issues/12482),
# where the video is reachable but no downloadable stream URLs are served.
RESTRICTION_MARKERS = (
    'the page needs to be reloaded',
    'only images are available',
)


def is_bot_check_error(error_text):
    """True when an yt-dlp error is YouTube's bot/sign-in wall."""
    lowered = (error_text or '').lower()
    return any(marker in lowered for marker in BOT_CHECK_MARKERS)


def is_youtube_restriction_error(error_text):
    """True for bot walls AND stream-restriction (SABR) walls."""
    lowered = (error_text or '').lower()
    markers = BOT_CHECK_MARKERS + RESTRICTION_MARKERS
    return any(marker in lowered for marker in markers)


def cookie_options():
    """Return cookie/proxy yt-dlp options when configured.

    Cookies authenticate requests with a real YouTube/Google session and
    a proxy routes traffic through another IP; both help bypass the
    'confirm you're not a bot' wall YouTube raises against datacenter /
    heavily-used IPs.
    """
    try:
        from flask import current_app, has_app_context
        if not has_app_context():
            return {}
        opts = {}
        cookie_file = current_app.config.get('YTDLP_COOKIES_FILE')
        if cookie_file:
            opts['cookiefile'] = cookie_file
        browser = current_app.config.get('YTDLP_COOKIES_FROM_BROWSER')
        if browser:
            opts['cookiesfrombrowser'] = (browser,)
        proxy = current_app.config.get('YTDLP_PROXY')
        if proxy:
            opts['proxy'] = proxy
        return opts
    except Exception:
        return {}


def _find_node():
    """Locate the node executable, including nvm installs.

    The server may be launched with a minimal PATH (e.g. via setsid/nohup)
    that excludes the nvm bin directory, so shutil.which() alone can miss
    an installed Node.js.
    """
    found = shutil.which('node')
    if found:
        return found
    candidates = []
    for base in (os.path.expanduser('~/.nvm/versions/node'),
                 '/usr/local/nvm/versions/node'):
        if os.path.isdir(base):
            try:
                versions = sorted(os.listdir(base), reverse=True)
            except OSError:
                continue
            for v in versions:
                candidates.append(os.path.join(base, v, 'bin', 'node'))
    for candidate in candidates:
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def js_runtime_options():
    """Return yt-dlp js_runtimes config using node when available.

    YouTube extraction requires a JavaScript runtime in current yt-dlp.
    Returns a dict suitable for merging into yt-dlp options, or an empty
    dict when no supported runtime is found.
    """
    node = _find_node()
    if node:
        return {'js_runtimes': {'node': {'path': node}}}
    if shutil.which('deno'):
        return {'js_runtimes': {'deno': {}}}
    return {}


def base_ydl_opts():
    """Common yt-dlp options shared across extraction and download."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        # Prevent ANSI terminal color codes from leaking into parsed
        # output (e.g. the speed string shown in the UI).
        'color': 'no_color',
    }
    opts.update(js_runtime_options())
    opts.update(cookie_options())
    return opts
