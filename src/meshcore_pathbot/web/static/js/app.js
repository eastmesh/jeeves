/* MeshCore PathBot - Minimal JS */

// Auto-dismiss toast notifications after 5 seconds
document.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id === 'toast-container') {
        const toasts = event.detail.target.querySelectorAll('.toast');
        toasts.forEach(function(toast) {
            setTimeout(function() {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(20px)';
                toast.style.transition = 'all 0.3s ease-in';
                setTimeout(function() {
                    toast.remove();
                }, 300);
            }, 5000);
        });
    }
});

// SSE message handling for the message feed
// Parse incoming SSE data and create table rows
document.addEventListener('htmx:sseMessage', function(event) {
    if (event.detail.type === 'msg_in' || event.detail.type === 'msg_out') {
        try {
            var data = JSON.parse(event.detail.data);
            var tbody = document.getElementById('message-list');
            if (!tbody) return;

            var tr = document.createElement('tr');
            var direction = event.detail.type === 'msg_out' ? 'out' : 'in';

            // Format timestamp with fixed precision so it doesn't collapse
            // to minute-level output on some locales.
            var ts = '--';
            var tsTitle = '';
            if (data.timestamp) {
                var date = new Date(data.timestamp * 1000);
                ts = date.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false,
                });
                tsTitle = date.toLocaleString();
            }
            var peer = data.sender || data.recipient || '--';
            var text = data.text || '';

            var badgeClass = direction === 'out' ? 'badge-out' : 'badge-in';
            var badgeText = direction === 'out' ? 'OUT' : 'IN';

            tr.innerHTML =
                '<td><small title="' + tsTitle + '">' + ts + '</small></td>' +
                '<td><span class="' + badgeClass + '">' + badgeText + '</span></td>' +
                '<td>' + peer + '</td>' +
                '<td>' + text + '</td>';

            tbody.insertBefore(tr, tbody.firstChild);

            // Keep max 200 rows
            while (tbody.children.length > 200) {
                tbody.removeChild(tbody.lastChild);
            }
        } catch (e) {
            console.warn('Failed to parse SSE message:', e);
        }
    }
});

// Fetch initial uptime on page load
document.addEventListener('DOMContentLoaded', function() {
    var uptimeEl = document.getElementById('uptime');
    if (uptimeEl) {
        htmx.trigger(uptimeEl, 'htmx:load');
    }
});
