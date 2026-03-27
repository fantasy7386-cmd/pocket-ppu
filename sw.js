// *** CHANGE THIS VERSION to trigger update on users' devices ***
const CACHE_VERSION = 'v20260328.0400';
const CACHE_NAME = 'pocket-ppu-' + CACHE_VERSION;

const ASSETS = [
  './',
  './index.html',
  './data.json',
  './teaching-notes.json',
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
];

// Install: cache all assets, activate immediately
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activate: delete ALL old caches, take control immediately
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch: stale-while-revalidate for app assets, passthrough for external APIs
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // NEVER cache external API calls (GitHub API, etc.)
  if (url.origin !== self.location.origin) {
    return; // let browser handle it directly
  }

  event.respondWith(
    caches.match(event.request).then(cached => {
      const fetchPromise = fetch(event.request).then(response => {
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);

      return cached || fetchPromise;
    })
  );
});
