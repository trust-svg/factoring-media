import type { NextConfig } from 'next'
import withPWAInit from '@ducanh2912/next-pwa'

const withPWA = withPWAInit({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development',
  register: true,
  workboxOptions: {
    skipWaiting: true,
    runtimeCaching: [
      {
        // Cache due flashcards for offline review (NetworkFirst: prefer fresh, fall back to cache)
        urlPattern: /\/flashcards\/due/,
        handler: 'NetworkFirst',
        options: {
          cacheName: 'flashcards-due',
          networkTimeoutSeconds: 5,
          expiration: { maxEntries: 1, maxAgeSeconds: 86400 },
          cacheableResponse: { statuses: [0, 200] },
        },
      },
    ],
  },
})

const nextConfig: NextConfig = {
  output: 'standalone',
}

export default withPWA(nextConfig)
