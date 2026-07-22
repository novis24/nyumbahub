const CACHE = 'iselltz-static-v4';
const OLD_CACHES = ['isell-v1', 'isell-v2', 'isell-v3'];

const PRECACHE = [
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE || OLD_CACHES.includes(k)).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const { request } = e;
  const url = new URL(request.url);

  if (request.method !== 'GET' || url.origin !== location.origin) return;
  if (request.headers.get('HX-Request')) return;

  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(request, clone));
        }
        return res;
      }))
    );
  }
});

self.addEventListener('push', event => {
  if (!event.data) return;
  const payload = event.data.json();
  const notification = payload.notification || payload;
  event.waitUntil(self.registration.showNotification(notification.title || 'iSellTZ', {
    body: notification.body || 'A new marketplace update is available.',
    icon: '/static/icons/icon-192.png', badge: '/static/icons/icon-192.png',
    data: payload.data || {url: '/'},
  }));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow(event.notification.data?.url || '/'));
});
