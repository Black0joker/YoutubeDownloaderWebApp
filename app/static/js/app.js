// Shared helpers used across pages.
const App = {
    async request(url, options = {}) {
        const opts = Object.assign({
            headers: { 'Content-Type': 'application/json' },
        }, options);
        if (opts.body && typeof opts.body === 'object') {
            opts.body = JSON.stringify(opts.body);
        }
        const response = await fetch(url, opts);
        let data = null;
        try {
            data = await response.json();
        } catch (e) {
            // Non-JSON response (e.g. SSE or file).
        }
        if (!response.ok) {
            const message = (data && data.error && data.error.message) || `Request failed (${response.status})`;
            const err = new Error(message);
            err.code = data && data.error ? data.error.code : 'UNKNOWN';
            err.status = response.status;
            throw err;
        }
        return data;
    },

    formatDuration(seconds) {
        if (!seconds) return '--';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        if (h) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        return `${m}:${String(s).padStart(2, '0')}`;
    },

    formatBytes(bytes) {
        if (bytes == null || isNaN(bytes)) return '';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let value = Number(bytes);
        let i = 0;
        while (value >= 1024 && i < units.length - 1) {
            value /= 1024;
            i++;
        }
        const decimals = value >= 100 || i === 0 ? 0 : value >= 10 ? 1 : 2;
        return `${value.toFixed(decimals)} ${units[i]}`;
    },

    escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    },
};
