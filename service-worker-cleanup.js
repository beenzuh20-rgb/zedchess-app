// Service Worker Cleanup - Removes any stale service workers from Firebase versions
if ('serviceWorker' in navigator) {
  // Unregister all service workers
  navigator.serviceWorker.getRegistrations().then(function(registrations) {
    for (let registration of registrations) {
      console.log('[Cleanup] Unregistering service worker:', registration.scope);
      registration.unregister().then(function(success) {
        if (success) {
          console.log('[Cleanup] Successfully unregistered service worker');
        } else {
          console.log('[Cleanup] Failed to unregister service worker');
        }
      });
    }
  });

  // Clear all caches
  if ('caches' in window) {
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(cacheName) {
          console.log('[Cleanup] Deleting cache:', cacheName);
          return caches.delete(cacheName);
        })
      );
    }).then(function() {
      console.log('[Cleanup] All caches cleared');
    });
  }
}