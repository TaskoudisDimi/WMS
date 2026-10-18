<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'
import PrefsToggles from '@/components/PrefsToggles.vue'
import { useInstall, useOnline } from '@/composables/useNetwork'

const auth   = useAuthStore()
const route  = useRoute()
const router = useRouter()
const { t } = useI18n()
const online = useOnline()
const { canInstall, install } = useInstall()

const showUserMenu = ref(false)

const pageTitle = computed(() => {
  const map: Record<string, string> = {
    '/dashboard': t('nav.dashboard'),
    '/sales':     t('nav.salesForecast'),
    '/customers': t('nav.customerAnalysis'),
    '/datasets':  t('nav.datasets'),
    '/settings':  t('nav.settings'),
    '/inventory': t('nav.inventory'),
    '/products':  t('nav.products'),
    '/orders':    t('nav.orders'),
    '/stocktake': t('nav.stocktake'),
    '/assistant': t('nav.assistant'),
    '/suppliers': t('nav.suppliers'),
    '/reports':   t('nav.reports'),
  }
  return map[route.path] || ''
})

const pageSub = computed(() => {
  const map: Record<string, string> = {
    '/dashboard': t('topbar.sub.dashboard'),
    '/sales':     t('topbar.sub.sales'),
    '/customers': t('topbar.sub.customers'),
    '/datasets':  t('topbar.sub.datasets'),
    '/settings':  t('topbar.sub.settings'),
    '/inventory': t('topbar.sub.inventory'),
    '/products':  t('topbar.sub.products'),
    '/orders':    t('topbar.sub.orders'),
    '/stocktake': t('topbar.sub.stocktake'),
    '/assistant': t('topbar.sub.assistant'),
    '/suppliers': t('topbar.sub.suppliers'),
    '/reports':   t('topbar.sub.reports'),
  }
  return map[route.path] || ''
})

const initials = computed(() => {
  const name = auth.user?.full_name ?? ''
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) || 'U'
})

const logout = async () => {
  showUserMenu.value = false
  await auth.logout(router)
}

const menuHost = ref<HTMLElement | null>(null)
const onDocClick = (e: MouseEvent) => {
  if (menuHost.value && !menuHost.value.contains(e.target as Node)) showUserMenu.value = false
}
const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') showUserMenu.value = false }
onMounted(() => { document.addEventListener('click', onDocClick); document.addEventListener('keydown', onKey) })
onBeforeUnmount(() => { document.removeEventListener('click', onDocClick); document.removeEventListener('keydown', onKey) })

const goSettings = () => { showUserMenu.value = false; router.push('/settings') }
</script>

<template>
  <header class="topbar">
    <div class="titles">
      <h1 class="page-title">{{ pageTitle }}</h1>
      <span v-if="pageSub" class="page-sub">{{ pageSub }}</span>
    </div>

    <div class="actions">
      <span v-if="!online" class="offline">{{ t('topbar.offline') }}</span>
      <PrefsToggles />

      <div ref="menuHost" class="menu-host">
        <button class="user-btn" :aria-expanded="showUserMenu" aria-haspopup="menu" @click="showUserMenu = !showUserMenu">
          <span class="avatar">{{ initials }}</span>
        </button>

        <Transition name="pop">
          <div v-if="showUserMenu" class="menu" role="menu">
            <div class="menu-user">
              <p class="menu-name">{{ auth.user?.full_name }}</p>
              <p class="menu-email">{{ auth.user?.email }}</p>
              <p v-if="auth.currentBusiness && auth.businesses.length < 2" class="menu-biz">{{ auth.currentBusiness.name }}</p>
            </div>
            <template v-if="auth.businesses.length > 1">
              <p class="menu-label">{{ t('topbar.switchBusiness') }}</p>
              <button v-for="b in auth.businesses" :key="b.id" class="menu-item" role="menuitemradio"
                :aria-checked="b.id === auth.currentBusiness?.id" @click="auth.switchBusiness(b.id); showUserMenu = false">
                <span class="check">{{ b.id === auth.currentBusiness?.id ? '✓' : '' }}</span>{{ b.name }}
              </button>
              <div class="menu-sep" />
            </template>
            <button v-if="canInstall" class="menu-item" role="menuitem" @click="install(); showUserMenu = false">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2" width="12" height="20" rx="2"/><path d="M12 7v7M9 11l3 3 3-3"/></svg>
              {{ t('topbar.install') }}
            </button>
            <button class="menu-item" role="menuitem" @click="goSettings">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>
              {{ t('nav.settings') }}
            </button>
            <button class="menu-item menu-item--danger" role="menuitem" @click="logout">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l-5-5 5-5M5 12h11"/></svg>
              {{ t('auth.logout') }}
            </button>
          </div>
        </Transition>
      </div>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  height: 56px;
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  padding: 0 1.5rem;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 20;
}
.titles { display: flex; align-items: baseline; gap: .75rem; min-width: 0; }
.page-title { font-size: 1rem; font-weight: 600; letter-spacing: -.01em; white-space: nowrap; }
.page-sub { font-size: .85rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 640px) { .page-sub { display: none; } }

.actions { display: flex; align-items: center; gap: .5rem; }

.menu-host { position: relative; }
.user-btn { display: flex; padding: 2px; border-radius: 50%; background: transparent; cursor: pointer; }
.user-btn:hover .avatar { border-color: var(--text-muted); }
.avatar {
  width: 30px; height: 30px; border-radius: 50%;
  display: grid; place-items: center;
  font-size: .75rem; font-weight: 600;
  background: var(--bg-card); color: var(--text-sub);
  border: 1px solid var(--border-mid);
  transition: border-color .12s;
}

.menu {
  position: absolute; right: 0; top: calc(100% + 6px);
  width: 240px; padding: .3rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
  z-index: 50;
}
.menu-user { padding: .55rem .6rem .65rem; margin-bottom: .3rem; border-bottom: 1px solid var(--border-light); }
.menu-name { font-size: .875rem; font-weight: 600; }
.menu-email, .menu-biz { font-size: .8rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.menu-biz { margin-top: .35rem; color: var(--text-sub); }
.menu-item {
  width: 100%; display: flex; align-items: center; gap: .6rem;
  height: 34px; padding: 0 .6rem;
  border-radius: var(--r);
  background: transparent; font-size: .875rem; color: var(--text-sub); text-align: left; cursor: pointer;
}
.menu-item:hover { background: var(--bg-hover); color: var(--text); }
.offline { font-size: .78rem; font-weight: 550; color: var(--amber); background: rgba(var(--amber-rgb), .12); padding: .2rem .55rem; border-radius: 99px; }
.menu-label { font-size: .75rem; color: var(--text-muted); padding: .35rem .6rem .2rem; }
.menu-sep { height: 1px; background: var(--border-light); margin: .3rem 0; }
.check { width: 14px; color: var(--accent); font-weight: 700; }
.menu-item--danger:hover { background: var(--red-bg); color: var(--red); }

.pop-enter-active, .pop-leave-active { transition: opacity .12s, transform .12s; transform-origin: top right; }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: scale(.97) translateY(-2px); }
</style>
