const CACHE = 'umerrick-prices-shell-v1';
const ASSETS = ['/static/css/app.css', '/static/css/retail-workspace.css', '/static/js/app-shell.js', '/static/js/camera-permission.js', '/static/js/prices.js', '/static/brand/umerrick-logo-cutout.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => Promise.allSettled(ASSETS.map(url => cache.add(url)))));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('umerrick-prices-shell-') && key !== CACHE).map(key => caches.delete(key)))));
  self.clients.claim();
});
self.addEventListener('message', event => {
  if (event.data?.type !== 'CACHE_PRICE_PAGE') return;
  event.waitUntil(fetch('/prices/', { credentials: 'same-origin', cache: 'no-store' }).then(response => {
    if (response.ok && !response.redirected && response.headers.get('X-Price-Offline') === 'staff' && new URL(response.url).pathname === '/prices/') {
      return caches.open(CACHE).then(cache => cache.put('/prices/', response));
    }
  }).catch(() => {}));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== 'GET') return;
  if (url.pathname === '/prices/' && event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).then(response => {
      if (response.ok && !response.redirected && response.headers.get('X-Price-Offline') === 'staff' && response.url.endsWith('/prices/')) {
        const copy = response.clone(); caches.open(CACHE).then(cache => cache.put('/prices/', copy));
      }
      return response;
    }).catch(async () => (await caches.match('/prices/')) || Response.error()));
  } else if (url.pathname.startsWith('/static/')) {
    event.respondWith(fetch(event.request).then(response => {
      if (response.ok) { const copy = response.clone(); caches.open(CACHE).then(cache => cache.put(event.request, copy)); }
      return response;
    }).catch(async () => (await caches.match(event.request, { ignoreSearch: true })) || Response.error()));
  }
});
