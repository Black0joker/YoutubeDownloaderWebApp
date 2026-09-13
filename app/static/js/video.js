// Handles URL analysis and the format selection / download UI.
(function () {
    const analyzeBtn = document.getElementById('analyze-btn');
    const urlInput = document.getElementById('url-input');
    const clipboardBtn = document.getElementById('clipboard-btn');
    const statusBox = document.getElementById('analyze-status');
    const resultContainer = document.getElementById('video-result');

    let currentVideo = null;
    let currentFormats = null;

    function showStatus(message, isError) {
        if (!statusBox) return;
        statusBox.classList.remove('hidden');
        statusBox.classList.toggle('error', !!isError);
        statusBox.textContent = message;
    }

    function hideStatus() {
        if (statusBox) statusBox.classList.add('hidden');
    }

    async function analyze(url) {
        showStatus('Analyzing video…', false);
        const data = await App.request('/api/videos/analyze', {
            method: 'POST',
            body: { url },
        });
        currentVideo = data.video;
        currentFormats = data.formats;
        hideStatus();
        renderResult();
    }

    function renderResult() {
        if (!resultContainer || !currentVideo) return;
        const v = currentVideo;
        const videoFormats = (currentFormats && currentFormats.video) || [];
        const audioFormats = (currentFormats && currentFormats.audio) || [];

        const videoOptions = videoFormats.map(f =>
            `<option value="${App.escapeHtml(f.format_id)}">${App.escapeHtml(f.quality)}${f.fps ? ' @ ' + Math.round(f.fps) + 'fps' : ''} (${App.escapeHtml(f.ext || '')})</option>`
        ).join('');
        const audioOptions = audioFormats.map(f =>
            `<option value="${App.escapeHtml(f.format_id)}">${App.escapeHtml(f.quality)} (${App.escapeHtml(f.ext || '')})</option>`
        ).join('');

        resultContainer.classList.remove('hidden');
        resultContainer.innerHTML = `
            <div class="video-header">
                ${v.thumbnail_url ? `<img src="${App.escapeHtml(v.thumbnail_url)}" alt="thumbnail">` : ''}
                <div class="video-meta">
                    <h2>${App.escapeHtml(v.title)}</h2>
                    <p>${App.escapeHtml(v.uploader || '')}</p>
                    <p>${App.formatDuration(v.duration)}</p>
                </div>
            </div>
            <div class="download-options">
                <div class="option-group">
                    <label>Download type</label>
                    <div class="radio-group">
                        <label><input type="radio" name="dl-type" value="video_audio" checked> Video + Audio</label>
                        <label><input type="radio" name="dl-type" value="video"> Video only</label>
                        <label><input type="radio" name="dl-type" value="audio"> Audio only</label>
                    </div>
                </div>
                <div class="option-group" id="video-quality-group">
                    <label>Video quality</label>
                    <select id="video-quality">${videoOptions || '<option value="">No video formats</option>'}</select>
                </div>
                <div class="option-group" id="audio-quality-group">
                    <label>Audio quality</label>
                    <select id="audio-quality">${audioOptions || '<option value="">No audio formats</option>'}</select>
                </div>
                <div class="option-group">
                    <label>Output format</label>
                    <select id="output-format"></select>
                </div>
                <div class="download-actions">
                    <button class="btn btn-primary" id="download-btn">Download</button>
                </div>
                <div id="download-progress" class="hidden" style="margin-top:1rem;">
                    <div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div>
                    <div class="progress-meta">
                        <span id="progress-text">0%</span>
                        <span id="progress-speed"></span>
                    </div>
                </div>
            </div>
        `;
        bindOptionEvents();
        updateOutputFormats();
    }

    function getType() {
        const checked = document.querySelector('input[name="dl-type"]:checked');
        return checked ? checked.value : 'video_audio';
    }

    function updateOutputFormats() {
        const outputSelect = document.getElementById('output-format');
        if (!outputSelect) return;
        const type = getType();
        let options = [];
        if (type === 'audio') {
            options = ['mp3', 'm4a'];
        } else {
            options = ['mp4', 'mkv'];
        }
        outputSelect.innerHTML = options.map(o => `<option value="${o}">${o.toUpperCase()}</option>`).join('');

        const videoGroup = document.getElementById('video-quality-group');
        const audioGroup = document.getElementById('audio-quality-group');
        if (videoGroup) videoGroup.style.display = (type === 'audio') ? 'none' : '';
        if (audioGroup) audioGroup.style.display = (type === 'video') ? 'none' : '';
    }

    function bindOptionEvents() {
        document.querySelectorAll('input[name="dl-type"]').forEach(el => {
            el.addEventListener('change', updateOutputFormats);
        });
        const dlBtn = document.getElementById('download-btn');
        if (dlBtn) dlBtn.addEventListener('click', startDownload);
    }

    async function startDownload() {
        const type = getType();
        const payload = {
            video_id: currentVideo.youtube_id,
            type: type,
            output_format: document.getElementById('output-format').value,
        };
        if (type !== 'audio') {
            payload.video_format_id = document.getElementById('video-quality').value;
        }
        if (type === 'video_audio') {
            payload.audio_format_id = document.getElementById('audio-quality').value;
        }

        const dlBtn = document.getElementById('download-btn');
        dlBtn.disabled = true;
        try {
            const res = await App.request('/api/downloads', { method: 'POST', body: payload });
            dlBtn.textContent = 'Queued';
            trackProgress(res.job_id);
        } catch (err) {
            dlBtn.disabled = false;
            showStatus(err.message, true);
        }
    }

    function trackProgress(jobId) {
        const progressBox = document.getElementById('download-progress');
        const fill = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');
        const speed = document.getElementById('progress-speed');
        progressBox.classList.remove('hidden');

        const TERMINAL = ['completed', 'failed', 'cancelled', 'expired'];
        let lastStatus = null;

        const source = new EventSource(`/api/downloads/${jobId}/events`);
        source.onmessage = (event) => {
            let data;
            try { data = JSON.parse(event.data); } catch (e) { return; }
            if (data.error) {
                source.close();
                text.textContent = data.error;
                return;
            }
            lastStatus = data.status;
            fill.style.width = `${data.progress || 0}%`;
            text.textContent = `${(data.progress || 0).toFixed(0)}% — ${data.status}`;
            speed.textContent = data.speed || '';

            if (TERMINAL.includes(data.status)) {
                source.close();
                if (data.status === 'completed') {
                    text.innerHTML = `Completed! <a href="/api/downloads/${jobId}/file">Download file</a>`;
                } else if (data.status === 'failed') {
                    text.textContent = `Failed: ${data.error_message || 'unknown error'}`;
                }
            }
        };
        // On transient errors let EventSource auto-reconnect; only stop
        // permanently once a terminal state was received.
        source.onerror = () => {
            if (TERMINAL.includes(lastStatus)) {
                source.close();
            }
        };
    }

    function extractYouTubeUrl(text) {
        if (!text) return null;
        const patterns = [
            /(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?(?:[^\s]*&)?v=([\w-]{11})/i,
            /(?:https?:\/\/)?(?:www\.)?youtu\.be\/([\w-]{11})/i,
            /(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([\w-]{11})/i,
            /(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([\w-]{11})/i,
        ];
        for (const pattern of patterns) {
            const match = text.match(pattern);
            if (match) return 'https://www.youtube.com/watch?v=' + match[1];
        }
        return null;
    }

    async function pasteFromClipboard() {
        if (!navigator.clipboard || !navigator.clipboard.readText) {
            showStatus('Clipboard access is not supported in this browser.', true);
            return;
        }
        try {
            const text = await navigator.clipboard.readText();
            const url = extractYouTubeUrl(text);
            if (!url) {
                showStatus('No YouTube URL found in the clipboard.', true);
                return;
            }
            urlInput.value = url;
            hideStatus();
            analyzeBtn.click();
        } catch (err) {
            showStatus('Could not read the clipboard. Allow clipboard access and try again.', true);
        }
    }

    if (analyzeBtn && urlInput) {
        analyzeBtn.addEventListener('click', () => {
            const url = urlInput.value.trim();
            if (!url) {
                showStatus('Please paste a YouTube URL.', true);
                return;
            }
            analyze(url).catch(err => showStatus(err.message, true));
        });
        urlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') analyzeBtn.click();
        });
        if (clipboardBtn) {
            clipboardBtn.addEventListener('click', pasteFromClipboard);
        }
    }

    // If on /video/<id> page, load cached metadata.
    const videoContainer = document.getElementById('video-container');
    if (videoContainer) {
        const videoId = videoContainer.dataset.videoId;
        App.request(`/api/videos/by-youtube-id/${videoId}`)
            .then(video => {
                currentVideo = video;
                return App.request('/api/videos/analyze', {
                    method: 'POST',
                    body: { url: video.url },
                });
            })
            .then(data => {
                currentVideo = data.video;
                currentFormats = data.formats;
                videoContainer.innerHTML = '';
                videoContainer.appendChild(resultContainer);
                resultContainer.classList.remove('hidden');
                renderResult();
            })
            .catch(err => {
                videoContainer.innerHTML = `<div class="status-box error">${App.escapeHtml(err.message)}</div>`;
            });
    }
})();
