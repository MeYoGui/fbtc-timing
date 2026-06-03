// Kairos service worker — intentionally no caching.
// Exists only to satisfy the PWA installability requirement (Chrome/Android
// require a registered service worker to offer "Add to Home Screen").
// There is no 'fetch' handler, so every request goes straight to the network
// and the dashboard always shows fresh data.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// ── Web Push ──────────────────────────────────────────────────────────────
self.addEventListener('push', (event) => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (e) { payload = {}; }
  const title = payload.title || 'Kairos';
  const options = {
    body: payload.body || '',
    icon: '/fbtc-timing/icons/icon-192.png',
    data: { url: payload.url || '/fbtc-timing/' },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/fbtc-timing/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const c of clients) {
        if (c.url.includes('/fbtc-timing/') && 'focus' in c) return c.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});
