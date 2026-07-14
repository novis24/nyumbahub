const CACHE = 'isell-v3';
const OFFLINE_URL = '/offline/';

const PRECACHE = [
  '/',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

// Install — pre-cache shell
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

// Activate — clear old caches
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch strategy:
// - Static assets (CSS, JS, fonts, images) → Cache first
// - Navigation (HTML pages) → Network first, fall back to cache
// - API / HTMX requests → Network only
self.addEventListener('fetch', (e) => {
  const { request } = e;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin
  if (request.method !== 'GET' || url.origin !== location.origin) return;

  // Static assets — cache first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(request, clone));
        return res;
      }))
    );
    return;
  }

  // HTMX partial requests — network only
  if (request.headers.get('HX-Request')) return;

  // HTML navigation — network first
  if (request.headers.get('Accept')?.includes('text/html')) {
    e.respondWith(
      fetch(request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(request, clone));
          return res;
        })
        .catch(() => caches.match(request).then(cached => cached || caches.match('/')))
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
