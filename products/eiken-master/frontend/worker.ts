/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

self.addEventListener('push', (event) => {
  if (!event.data) return
  let payload: { title?: string; body?: string; icon?: string; url?: string }
  try {
    payload = event.data.json()
  } catch {
    payload = { title: '英検マスター', body: event.data.text() }
  }
  const title = payload.title ?? '英検マスター'
  const options: NotificationOptions = {
    body: payload.body ?? '',
    icon: payload.icon ?? '/icon-192.png',
    badge: '/icon-192.png',
    data: { url: payload.url ?? '/' },
  }
  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url: string = (event.notification.data as { url?: string })?.url ?? '/'
  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        const focused = clients.find((c) => c.url.includes(url) && 'focus' in c)
        if (focused) return focused.focus()
        return self.clients.openWindow(url)
      })
  )
})
