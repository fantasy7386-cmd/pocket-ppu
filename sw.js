// *** CHANGE THIS VERSION to trigger update on users' devices ***
const CACHE_VERSION = 'v1';
const CACHE_NAME = 'pocket-ppu-' + CACHE_VERSION;

const ASSETS = [
  './',
  './index.html',
  './data.json',
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

// Fetch: stale-while-revalidate strategy
// Returns cached version instantly (fast), while fetching fresh copy in background.
// Next time the app opens, it will use the updated version.
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(cached => {
      // Fetch fresh copy in background
      const fetchPromise = fetch(event.request).then(response => {
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);

      // Return cached immediately if available, otherwise wait for fetch
      return cached || fetchPromise;
    })
  );
});
