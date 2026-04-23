self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(clients.claim()));

self.addEventListener('push', function(event) {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch(e) {}

  const title = data.title || '💰 PriceWatch Alert!';
  const options = {
    body: data.body || 'Il prezzo è sceso!',
    icon: './icon-192.png',
    badge: './icon-192.png',
    tag: data.productId || 'price-alert',
    requireInteraction: true,
    vibrate: [200, 100, 200],
    data: { url: data.url || './' },
    actions: [
      { action: 'open', title: 'Vedi prodotto' },
      { action: 'dismiss', title: 'Chiudi' }
    ]
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  if (event.action === 'dismiss') return;

  const url = event.notification.data?.url || './';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(wins => {
      for (const w of wins) {
        if ('focus' in w) return w.focus();
      }
      return clients.openWindow(url);
    })
  );
});
