import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import { registerSW } from 'virtual:pwa-register'
// Self-hosted fonts: no request to Google Fonts (keeps visitor IPs off third parties)
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './assets/main.css'
import './assets/ui.css'

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate) 

const app = createApp(App)
app.use(i18n)
app.use(pinia)                        
app.use(router)
app.mount('#app')

// Installable app + offline shell (see vite.config.ts). Updates apply on next load.
registerSW({ immediate: true })

// Error tracking — only when a DSN is configured at build time
if (import.meta.env.VITE_SENTRY_DSN) {
  import('@sentry/vue').then(Sentry => Sentry.init({
    app,
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    integrations: [Sentry.browserTracingIntegration({ router })],
    tracesSampleRate: 0.1,
  }))
}