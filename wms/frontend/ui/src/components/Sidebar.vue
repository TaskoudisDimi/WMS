<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import BrandMark from '@/components/BrandMark.vue'

const route = useRoute()
const { t } = useI18n()
const COLLAPSE_KEY = 'sidebar-collapsed'
const collapsed = ref(false)
try { collapsed.value = localStorage.getItem(COLLAPSE_KEY) === '1' } catch { /* storage unavailable */ }
const toggle = () => {
  collapsed.value = !collapsed.value
  try { localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0') } catch { /* storage unavailable */ }
}

const menuGroups = [
  {
    labelKey: 'sidebar.analytics',
    items: [
      {
        key: 'nav.dashboard',
        path: '/dashboard',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7" rx="1.5"/>
          <rect x="14" y="3" width="7" height="7" rx="1.5"/>
          <rect x="3" y="14" width="7" height="7" rx="1.5"/>
          <rect x="14" y="14" width="7" height="7" rx="1.5"/>
        </svg>`,
      },
      {
        key: 'nav.salesForecast',
        path: '/sales',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>
          <polyline points="16 7 22 7 22 13"/>
        </svg>`,
      },
      {
        key: 'nav.assistant',
        path: '/assistant',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-5.1A8 8 0 1 1 21 12z"/><path d="M8.5 11h.01M12 11h.01M15.5 11h.01"/></svg>`,
      },
      {
        key: 'nav.reports',
        path: '/reports',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>`,
      },
      {
        key: 'nav.customerAnalysis',
        path: '/customers',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
          <circle cx="9" cy="7" r="4"/>
          <path d="M23 21v-2a4 4 0 00-3-3.87"/>
          <path d="M16 3.13a4 4 0 010 7.75"/>
        </svg>`,
      },
    ],
  },
  {
    labelKey: 'sidebar.warehouse',
    items: [
      {
        key: 'nav.inventory',
        path: '/inventory',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="7" width="20" height="14" rx="2"/>
          <path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/>
          <line x1="12" y1="12" x2="12" y2="16"/>
          <line x1="10" y1="14" x2="14" y2="14"/>
        </svg>`,
      },
      {
        key: 'nav.products',
        path: '/products',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>`,
      },
      {
        key: 'nav.stocktake',
        path: '/stocktake',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1z"/><path d="M8 6H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-2"/><path d="m9 14 2 2 4-4"/></svg>`,
      },
      {
        key: 'nav.suppliers',
        path: '/suppliers',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M1 6h13v10H1zM14 10h4l4 3v3h-8z"/><circle cx="5.5" cy="18" r="2"/><circle cx="17.5" cy="18" r="2"/></svg>`,
      },
      {
        key: 'nav.orders',
        path: '/orders',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="9" y1="13" x2="15" y2="13"/>
          <line x1="9" y1="17" x2="15" y2="17"/>
          <polyline points="9 9 10 9 11 9"/>
        </svg>`,
      },
    ],
  },
  {
    labelKey: 'sidebar.data',
    items: [
      {
        key: 'nav.datasets',
        path: '/datasets',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3"/>
          <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
          <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
        </svg>`,
      },
    ],
  },
  {
    labelKey: 'sidebar.system',
    items: [
      {
        key: 'nav.settings',
        path: '/settings',
        icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
        </svg>`,
      },
    ],
  },
]
</script>

<template>
  <aside :class="['sidebar', { 'sidebar--collapsed': collapsed }]">

    <div class="brand-row">
      <router-link to="/dashboard" class="brand-link" :aria-label="t('nav.dashboard')">
        <BrandMark :size="26" :with-name="!collapsed" />
      </router-link>
      <button class="collapse-btn" :aria-label="collapsed ? t('sidebar.expand') : t('sidebar.collapse')" :aria-expanded="!collapsed" @click="toggle">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M9 4v16"/>
        </svg>
      </button>
    </div>

    <nav class="nav">
      <div v-for="group in menuGroups" :key="group.labelKey" class="group">
        <p class="group-label" :class="{ 'group-label--hidden': collapsed }">{{ t(group.labelKey) }}</p>
        <router-link
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          :class="['nav-link', { active: route.path === item.path }]"
          :title="collapsed ? t(item.key) : undefined"
          :aria-current="route.path === item.path ? 'page' : undefined"
        >
          <span class="nav-icon" v-html="item.icon" />
          <span v-if="!collapsed" class="nav-label">{{ t(item.key) }}</span>
        </router-link>
      </div>
    </nav>

  </aside>
</template>

<style scoped>
.sidebar {
  width: 232px;
  height: 100%;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: .75rem .6rem;
  transition: width .2s cubic-bezier(.4, 0, .2, 1);
  overflow: hidden;
  flex-shrink: 0;
}
.sidebar--collapsed { width: 60px; }

.brand-row {
  display: flex; align-items: center; justify-content: space-between;
  height: 40px; padding: 0 .1rem 0 .4rem;
  margin-bottom: .75rem;
}
.sidebar--collapsed .brand-row { flex-direction: column; height: auto; gap: .5rem; padding: 0; }
.brand-link { display: flex; }
.collapse-btn {
  width: 30px; height: 30px; flex-shrink: 0;
  display: grid; place-items: center;
  border-radius: var(--r);
  background: transparent; color: var(--text-muted); cursor: pointer;
  transition: background .12s, color .12s;
}
.collapse-btn:hover { background: var(--bg-hover); color: var(--text); }

.nav { display: flex; flex-direction: column; gap: 1rem; flex: 1; overflow-y: auto; }
.group { display: flex; flex-direction: column; gap: 1px; }
.group-label {
  font-size: .75rem; font-weight: 500;
  color: var(--text-muted);
  padding: 0 .65rem .3rem;
  white-space: nowrap;
}
.group-label--hidden { height: 1px; padding: 0; margin: 0 .5rem .3rem; background: var(--border); color: transparent; overflow: hidden; }

.nav-link {
  display: flex; align-items: center; gap: .65rem;
  height: 34px; padding: 0 .65rem;
  border-radius: var(--r);
  color: var(--text-sub);
  font-size: .875rem; font-weight: 500;
  white-space: nowrap;
  transition: background .12s, color .12s;
}
.sidebar--collapsed .nav-link { justify-content: center; padding: 0; }
.nav-link:hover { background: var(--bg-hover); color: var(--text); }
.nav-link.active {
  background: var(--bg-card);
  color: var(--text);
  box-shadow: var(--shadow), inset 0 0 0 1px var(--border);
}
.nav-link.active .nav-icon { color: var(--accent); }

.nav-icon { width: 16px; height: 16px; flex-shrink: 0; display: flex; color: var(--text-muted); }
.nav-link:hover .nav-icon { color: var(--text-sub); }
</style>
