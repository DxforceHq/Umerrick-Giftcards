const CACHE = 'umerrick-prices-shell-v4';
const ASSETS = __PRICE_STATIC_ASSETS__;
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const previousPage = await caches.match('/prices/');
    const cache = await caches.open(CACHE);
    if (previousPage && !(await cache.match('/prices/'))) await cache.put('/prices/', previousPage);
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith('umerrick-prices-shell-') && key !== CACHE).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('message', event => {
  if (event.data?.type === 'CLEAR_PRICE_PAGE') {
    event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('umerrick-prices-shell-')).map(async key => (await caches.open(key)).delete('/prices/')))));
    return;
  }
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
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).then(response => {
      if (response.ok && !response.redirected && response.headers.get('X-Price-Offline') === 'staff' && response.url.endsWith('/prices/')) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE).then(cache => cache.put('/prices/', copy)));
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
