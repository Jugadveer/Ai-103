/* ===================================================================
   Service worker.

   Its job is to let the app install to a home screen and survive a
   dropped connection. The shell (page, styles, script, icons) is fetched
   live and kept as a fallback copy; everything under /api is always live
   with no fallback at all.

   Health data is never cached. A stale reading is worse than no reading,
   and caching it would also leave personal data sitting in a cache the
   user did not ask for.
   =================================================================== */

const CACHE = 'health-coach-v3';

const SHELL = [
  '/',
  '/static/app.css',
  '/static/app.js',
  '/static/icon.svg',
  '/static/icon-maskable.svg',
  '/manifest.webmanifest',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Live data only. Never serve a cached health reading.
  if (url.pathname.startsWith('/api/')) return;

  // Shell: network first, cache as the fallback.
  //
  // This was cache-first with a background refresh, which meant a deploy
  // took two page loads to appear: the first served the old file and only
  // then fetched the new one. Everybody testing this saw the previous
  // version and reasonably concluded nothing had changed.
  //
  // Cache-first buys offline use, but every screen here loads its data
  // from /api, which is never cached. An offline shell would render empty
  // furniture and no numbers. So the cache is a fallback for a dropped
  // connection, not the default path.
  event.respondWith(
    fetch(request)
      .then(response => {
        if (response && response.status === 200) {
          const copy = response.clone();
          caches.open(CACHE).then(c => c.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request))
  );
});
