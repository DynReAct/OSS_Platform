// Initialize client timezone immediately on page load
(function() {
    // Set timezone immediately when DOM is ready
    function setTimezone() {
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        const clientTzStore = document.querySelector('[id="client-tz"]');
        if (clientTzStore) {
            clientTzStore.setAttribute('data-initialization-data', timezone);
        }
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setTimezone);
    } else {
        setTimezone();
    }
})();
