/* Service Worker: empfängt Push-Nachrichten und öffnet den Chat beim Antippen. */
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let data = { title: 'Chat', body: 'Neue Nachricht', url: './' };
  try { data = Object.assign(data, event.data.json()); } catch (err) { /* leerer Push */ }
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    tag: data.url,
    renotify: true,
    data: data.url,
    icon: './static/icon-192.png',
    badge: './static/icon-192.png'
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data || './';
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    .then((list) => {
      for (const client of list) {
        if (!('focus' in client)) continue;
        // navigate() holt das offene Fenster in den richtigen Raum. Bei einem
        // nicht vom Worker kontrollierten Fenster schlaegt es fehl - dann
        // bleibt es beim blossen Fokussieren.
        if ('navigate' in client) {
          return client.navigate(url).then(
            (c) => (c || client).focus(),
            () => client.focus());
        }
        return client.focus();
      }
      return self.clients.openWindow(url);
    }));
});
