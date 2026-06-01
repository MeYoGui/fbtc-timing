// Kairos service worker — intentionally no caching.
// Exists only to satisfy the PWA installability requirement (Chrome/Android
// require a registered service worker to offer "Add to Home Screen").
// There is no 'fetch' handler, so every request goes straight to the network
// and the dashboard always shows fresh data.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
