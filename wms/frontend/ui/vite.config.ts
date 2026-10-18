import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath, URL } from 'node:url'

// API calls whose last response is kept for offline use (stock-take in a warehouse
// without signal). Everything else always goes to the network.
const OFFLINE_API = ['/api/auth/me', '/api/inventory', '/api/products', '/api/suppliers']

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'WMS — Warehouse management',
        short_name: 'WMS',
        description: 'Stock, orders and forecasts for small businesses',
        lang: 'el',
        start_url: '/dashboard',
        scope: '/',
        display: 'standalone',
        background_color: '#f5f7f7',
        theme_color: '#107d71',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
        shortcuts: [
          { name: 'Απογραφή', short_name: 'Απογραφή', url: '/stocktake', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
          { name: 'Αποθεματικό', short_name: 'Απόθεμα', url: '/inventory', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        cleanupOutdatedCaches: true,
        runtimeCaching: [{
          urlPattern: ({ url, request }) => request.method === 'GET' && OFFLINE_API.includes(url.pathname),
          handler: 'NetworkFirst',
          options: {
            cacheName: 'wms-api',
            networkTimeoutSeconds: 5,
            expiration: { maxEntries: 50, maxAgeSeconds: 7 * 24 * 3600 },
            cacheableResponse: { statuses: [200] },
          },
        }],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  }
})
