// Do not intercept navigation: let the browser handle the server's login challenge.
// Financial data is never cached for offline use.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
