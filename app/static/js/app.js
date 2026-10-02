document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('health-check-btn');
    const status = document.getElementById('health-status');

    if (!btn || !status) return;

    btn.addEventListener('click', async () => {
        try {
            const response = await fetch('/api/health');
            const data = await response.json();
            status.textContent = `Status: ${data.status} (${data.service})`;
        } catch (error) {
            status.textContent = 'Status: unavailable';
        }
    });
});
