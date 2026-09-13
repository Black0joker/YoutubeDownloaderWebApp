// Downloads history page logic.
//
// Live updates are delivered exclusively over Server-Sent Events
// (/api/downloads/<id>/events). The list API is called once per page
// load (and once when a job reaches a terminal state) — no polling.
(function () {
    const listEl = document.getElementById('downloads-list');
    if (!listEl) return;

    const TERMINAL = ['completed', 'failed', 'cancelled', 'expired'];

    const activeJobIds = new Set();   // jobs we believe are still running
    const sources = new Map();        // job_id -> EventSource
    let loading = false;
    let reloadScheduled = false;

    async function loadDownloads() {
        if (loading) return;
        loading = true;
        try {
            const data = await App.request('/api/downloads?limit=50');
            renderDownloads(data.jobs || []);
            (data.jobs || []).forEach(job => {
                if (!TERMINAL.includes(job.status)) {
                    activeJobIds.add(job.job_id);
                    trackJob(job.job_id);
                }
            });
        } catch (err) {
            listEl.innerHTML = `<div class="status-box error">${App.escapeHtml(err.message)}</div>`;
        } finally {
            loading = false;
        }
    }

    function renderDownloads(jobs) {
        if (!jobs.length) {
            listEl.innerHTML = '<p class="empty">No downloads yet. Start one from the home page.</p>';
            return;
        }
        listEl.innerHTML = jobs.map(job => jobCard(job)).join('');
        bindActions();
    }

    function jobCard(job) {
        const title = (job.video && job.video.title) || 'Unknown video';
        const isTerminal = TERMINAL.includes(job.status);
        const progress = job.progress || 0;

        let actions = '';
        if (job.status === 'completed') {
            actions += `<a class="btn btn-primary" href="/api/downloads/${job.job_id}/file">Download File</a>`;
        }
        if (!isTerminal) {
            actions += `<button class="btn btn-danger" data-action="cancel" data-id="${job.job_id}">Cancel</button>`;
        }
        actions += `<button class="btn btn-danger" data-action="delete" data-id="${job.job_id}" title="Remove this download and its file">Delete</button>`;

        return `
        <div class="download-card" id="job-${job.job_id}">
            <div class="download-card-header">
                <span class="download-card-title">${App.escapeHtml(title)}</span>
                <span class="badge badge-${job.status}">${job.status}</span>
            </div>
            <div class="progress-track">
                <div class="progress-fill" style="width:${progress}%"></div>
            </div>
            <div class="progress-meta">
                <span class="progress-text">${progress.toFixed(0)}%</span>
                <span class="progress-speed">${job.speed || ''}</span>
                <span class="progress-size">${App.formatBytes(job.file_size)}</span>
            </div>
            <div class="download-card-actions" style="margin-top:0.75rem;">
                ${actions}
            </div>
        </div>`;
    }

    function bindActions() {
        listEl.querySelectorAll('[data-action="cancel"]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                try {
                    await App.request(`/api/downloads/${id}/cancel`, { method: 'POST' });
                    loadDownloads();
                } catch (err) {
                    alert(err.message);
                }
            });
        });

        listEl.querySelectorAll('[data-action="delete"]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                if (!confirm('Delete this download and its file? This cannot be undone.')) {
                    return;
                }
                btn.disabled = true;
                try {
                    await App.request(`/api/downloads/${id}`, { method: 'DELETE' });
                    stopTracking(id);
                    loadDownloads();
                } catch (err) {
                    btn.disabled = false;
                    alert(err.message);
                }
            });
        });
    }

    // ------------------------------------------------------------------
    // Live tracking: Server-Sent Events only (no polling)
    // ------------------------------------------------------------------
    function trackJob(jobId) {
        if (sources.has(jobId)) return;

        const source = new EventSource(`/api/downloads/${jobId}/events`);
        sources.set(jobId, source);
        console.info(`[downloads] SSE opened for job ${jobId}`);

        source.onopen = () => {
            console.info(`[downloads] SSE connected for job ${jobId}`);
        };

        source.onmessage = (event) => {
            let data;
            try { data = JSON.parse(event.data); } catch (e) { return; }

            if (data.error) {
                // Job deleted or unknown: stop everything for it.
                stopTracking(jobId);
                scheduleReload();
                return;
            }

            updateJobCard(jobId, data);

            if (TERMINAL.includes(data.status)) {
                stopTracking(jobId);
                scheduleReload();
            }
        };

        source.onerror = () => {
            // The stream dropped. EventSource reconnects automatically and
            // keeps retrying while the job is active.
            console.warn(`[downloads] SSE connection lost for job ${jobId}; reconnecting...`);
        };
    }

    function stopTracking(jobId) {
        const source = sources.get(jobId);
        if (source) {
            source.close();
            sources.delete(jobId);
        }
        activeJobIds.delete(jobId);
    }

    function scheduleReload() {
        // Debounced one-time refresh: action buttons change on terminal states.
        if (reloadScheduled) return;
        reloadScheduled = true;
        setTimeout(() => {
            reloadScheduled = false;
            loadDownloads();
        }, 500);
    }

    function updateJobCard(jobId, data) {
        const card = document.getElementById(`job-${jobId}`);
        if (!card) return;
        const badge = card.querySelector('.badge');
        if (badge) {
            badge.className = `badge badge-${data.status}`;
            badge.textContent = data.status;
        }
        const fill = card.querySelector('.progress-fill');
        if (fill) fill.style.width = `${data.progress || 0}%`;
        const text = card.querySelector('.progress-text');
        if (text) text.textContent = `${(data.progress || 0).toFixed(0)}%`;
        const speed = card.querySelector('.progress-speed');
        if (speed) speed.textContent = data.speed || '';
        const size = card.querySelector('.progress-size');
        if (size) size.textContent = App.formatBytes(data.file_size);
    }

    loadDownloads();
})();
