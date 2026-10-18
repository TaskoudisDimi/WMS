<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'
import { intlLocale } from '@/i18n/format'
import { api } from '@/services/api'
import OnboardingGuide from '@/components/onboarding/OnboardingGuide.vue'

const auth  = useAuthStore()
const { t } = useI18n()

interface Order {
  id: string
  type: 'purchase' | 'sale'
  status: string
  party_name: string | null
  created_at: string
}

const loading      = ref(true)
const totalRevenue = ref<number | null>(null)
const totalCustomers = ref<number | null>(null)
const totalOrders  = ref<number | null>(null)
const recentOrders = ref<Order[]>([])
const criticalItems = ref<{ sku: string; name: string; quantity: number; reorder_point: number }[]>([])
const ordersLoaded = ref(false)

interface Anomaly { kind: 'sales_drop' | 'sales_spike' | 'stock_loss' | 'revenue_drop'; severity: string; name?: string; sku?: string; actual: number; expected: number }
const anomalies = ref<Anomaly[]>([])
// A brand-new business sees the welcome steps instead of empty KPIs
const guide = ref<'welcome' | 'checklist' | 'hidden'>('hidden')

const businessId = computed(() => auth.currentBusiness?.id ?? '')

onMounted(async () => {
  if (!businessId.value) { loading.value = false; return }

  const [customersRes, ordersRes, suggestionsRes] = await Promise.allSettled([
    api.get('/customers/analysis', { params: { business_id: businessId.value } }),
    api.get('/orders', { params: { business_id: businessId.value } }),
    api.get('/inventory/reorder-suggestions', { params: { business_id: businessId.value } }),
  ])
  api.get('/inventory/anomalies', { params: { business_id: businessId.value } })
    .then(r => { anomalies.value = r.data })
    .catch(() => { anomalies.value = [] })

  if (customersRes.status === 'fulfilled') {
    totalRevenue.value = customersRes.value.data.summary?.total_revenue ?? 0
    totalCustomers.value = customersRes.value.data.summary?.total_customers ?? 0
  }

  if (ordersRes.status === 'fulfilled') {
    const orders: Order[] = ordersRes.value.data || []
    totalOrders.value = orders.length
    recentOrders.value = [...orders]
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 6)
    ordersLoaded.value = true
  }

  if (suggestionsRes.status === 'fulfilled') {
    criticalItems.value = (suggestionsRes.value.data as any[])
      .filter(s => s.urgency === 'critical')
      .slice(0, 6)
      .map(s => ({ sku: s.sku, name: s.name, quantity: s.current_stock, reorder_point: s.reorder_point }))
  }

  loading.value = false
})

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(intlLocale(), { day: '2-digit', month: 'short' })
}
function fmtRevenue(n: number | null) {
  if (n === null) return '—'
  return '€' + n.toLocaleString(intlLocale(), { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}
function anomalyText(a: Anomaly) {
  return t(`dashboard.anomaly.${a.kind}`, {
    name: a.name ?? '', actual: a.kind === 'revenue_drop' ? fmtRevenue(a.actual) : a.actual,
    expected: a.kind === 'revenue_drop' ? fmtRevenue(a.expected) : Math.round(a.expected),
  })
}

function fmtNum(n: number | null) {
  if (n === null) return '—'
  return n.toLocaleString(intlLocale())
}
</script>

<template>
  <OnboardingGuide @state="guide = $event" />
  <div v-if="guide !== 'welcome'" class="dash">

    <!-- Header -->
    <div class="header">
      <div>
        <h1 class="greeting">
          {{ t('dashboard.greeting', { name: auth.user?.full_name?.split(' ')[0] || '' }) }}
        </h1>
        <p class="biz-name">{{ auth.currentBusiness?.name }}</p>
      </div>
      <span class="date-chip">
        {{ new Date().toLocaleDateString(intlLocale(), { weekday: 'long', day: 'numeric', month: 'long' }) }}
      </span>
    </div>

    <!-- KPIs -->
    <div class="kpi-row">
      <div class="kpi">
        <div class="kpi-label">{{ t('dashboard.kpi.totalRevenue') }}</div>
        <div class="kpi-value" :class="{ 'kpi-value--empty': totalRevenue === null || totalRevenue === 0 }">
          {{ fmtRevenue(totalRevenue) }}
        </div>
        <div class="kpi-sub">{{ t('dashboard.kpi.fromOrders') }}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">{{ t('dashboard.kpi.orders') }}</div>
        <div class="kpi-value" :class="{ 'kpi-value--empty': totalOrders === null || totalOrders === 0 }">
          {{ fmtNum(totalOrders) }}
        </div>
        <div class="kpi-sub">{{ t('dashboard.kpi.totalCreated') }}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">{{ t('dashboard.kpi.customers') }}</div>
        <div class="kpi-value" :class="{ 'kpi-value--empty': totalCustomers === null || totalCustomers === 0 }">
          {{ fmtNum(totalCustomers) }}
        </div>
        <div class="kpi-sub">{{ t('dashboard.kpi.uniqueBuyers') }}</div>
      </div>
      <div class="kpi" :class="{ 'kpi--alert': criticalItems.length > 0 }">
        <div class="kpi-label">{{ t('dashboard.kpi.criticalStock') }}</div>
        <div class="kpi-value" :class="criticalItems.length > 0 ? 'kpi-value--red' : 'kpi-value--empty'">
          {{ criticalItems.length > 0 ? criticalItems.length : '—' }}
        </div>
        <div class="kpi-sub">{{ t('dashboard.kpi.belowReorder') }}</div>
      </div>
    </div>

    <!-- Main content -->
    <div class="panels">

      <!-- Recent Orders -->
      <div class="panel">
        <div class="panel-head">
          <span class="panel-title">{{ t('dashboard.recentOrders') }}</span>
          <router-link to="/orders" class="panel-link">{{ t('dashboard.viewAll') }} →</router-link>
        </div>

        <div v-if="loading" class="panel-loading">{{ t('common.loading') }}</div>
        <template v-else-if="recentOrders.length === 0">
          <div class="panel-empty">
            <p>{{ t('dashboard.noOrders') }}</p>
            <router-link to="/orders" class="panel-cta">{{ t('dashboard.createOrder') }}</router-link>
          </div>
        </template>
        <template v-else>
          <table class="mini-tbl">
            <thead>
              <tr>
                <th>{{ t('wms.orders.table.party') }}</th>
                <th>{{ t('wms.orders.table.type') }}</th>
                <th>{{ t('wms.orders.table.status') }}</th>
                <th class="right">{{ t('wms.orders.table.date') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="o in recentOrders" :key="o.id">
                <td class="fw">{{ o.party_name || '—' }}</td>
                <td>
                  <span class="badge" :class="o.type === 'purchase' ? 'badge--teal' : 'badge--green'">
                    {{ t(`wms.orders.type.${o.type}`) }}
                  </span>
                </td>
                <td>
                  <span class="badge"
                    :class="{
                      'badge--muted':  o.status === 'draft',
                      'badge--teal':   o.status === 'confirmed',
                      'badge--green':  o.status === 'completed',
                      'badge--red':    o.status === 'cancelled',
                    }">
                    {{ t(`wms.orders.status.${o.status}`) }}
                  </span>
                </td>
                <td class="right muted">{{ fmtDate(o.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>

      <!-- Critical Stock -->
      <div class="panel">
        <div class="panel-head">
          <span class="panel-title">{{ t('dashboard.criticalStock') }}</span>
          <router-link to="/inventory" class="panel-link">{{ t('dashboard.viewAll') }} →</router-link>
        </div>

        <div v-if="loading" class="panel-loading">{{ t('common.loading') }}</div>
        <template v-else-if="criticalItems.length === 0">
          <div class="panel-empty panel-empty--ok">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <p>{{ t('dashboard.allStocked') }}</p>
          </div>
        </template>
        <template v-else>
          <div class="stock-list">
            <div v-for="item in criticalItems" :key="item.sku" class="stock-row">
              <div class="stock-info">
                <span class="stock-sku">{{ item.sku }}</span>
                <span class="stock-name">{{ item.name }}</span>
              </div>
              <div class="stock-qty">
                <span class="qty-num qty-num--red">{{ item.quantity }}</span>
                <span class="qty-sep">/</span>
                <span class="qty-reorder">{{ item.reorder_point }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>

    </div>


    <!-- Unusual activity -->
    <div v-if="anomalies.length" class="panel anomalies">
      <div class="panel-head">
        <span class="panel-title">{{ t('dashboard.unusual') }}</span>
        <router-link to="/assistant" class="panel-link">{{ t('dashboard.askAssistant') }} →</router-link>
      </div>
      <ul class="anomaly-list">
        <li v-for="(a, i) in anomalies.slice(0, 6)" :key="i">
          <span class="dot" :class="`dot--${a.severity}`" />
          <span>{{ anomalyText(a) }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.anomalies { margin-top: 1rem; }
.anomaly-list { list-style: none; display: flex; flex-direction: column; }
.anomaly-list li { display: flex; gap: .65rem; align-items: baseline; padding: .6rem 1.25rem; border-top: 1px solid var(--border-light); font-size: .875rem; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; transform: translateY(-1px); background: var(--text-muted); }
.dot--critical { background: var(--red); }
.dot--warning { background: var(--amber); }
.dot--info { background: var(--blue); }
.dash {
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
  background: var(--bg);
}

/* Header */
.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid var(--border);
}
.greeting {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text);
  margin: 0;
  letter-spacing: -.02em;
}
.biz-name {
  font-size: .75rem;
  color: var(--text-muted);
  margin: .2rem 0 0;
}
.date-chip {
  font-size: .73rem;
  color: var(--text-muted);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: .3rem .7rem;
  white-space: nowrap;
  align-self: flex-start;
}

/* KPI Row */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: .85rem;
}
@media (max-width: 900px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 500px) { .kpi-row { grid-template-columns: 1fr; } }

.kpi {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 1.1rem 1.2rem;
  display: flex;
  flex-direction: column;
  gap: .35rem;
  transition: border-color .2s;
}
.kpi:hover { border-color: var(--border-mid); }
.kpi--alert { border-color: rgba(var(--red-rgb), .3); background: rgba(var(--red-rgb), .03); }

.kpi-label {
  font-size: .75rem;
  font-weight: 600;
  color: var(--text-muted);
  }
.kpi-value {
  font-size: 1.65rem;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -.03em;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.kpi-value--empty { color: var(--text-muted); font-weight: 400; }
.kpi-value--red   { color: var(--red); }
.kpi-sub {
  font-size: .68rem;
  color: var(--text-muted);
  margin-top: .1rem;
}

/* Panels */
.panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}
@media (max-width: 750px) { .panels { grid-template-columns: 1fr; } }

.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 1.1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: .85rem;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title {
  font-size: .8rem;
  font-weight: 600;
  color: var(--text);
}
.panel-link {
  font-size: .72rem;
  color: var(--teal);
  text-decoration: none;
  opacity: .8;
  transition: opacity .15s;
}
.panel-link:hover { opacity: 1; }
.panel-loading {
  font-size: .78rem;
  color: var(--text-muted);
  padding: .75rem 0;
}
.panel-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: .5rem;
  padding: 1.5rem 0;
  text-align: center;
}
.panel-empty p { font-size: .8rem; color: var(--text-muted); margin: 0; }
.panel-empty--ok { flex-direction: row; justify-content: center; padding: 1.25rem 0; }
.panel-empty--ok svg { color: var(--green); }
.panel-empty--ok p { color: var(--green); font-weight: 500; }
.panel-cta {
  font-size: .75rem;
  color: var(--teal);
  text-decoration: none;
  border: 1px solid rgba(var(--accent-rgb), .25);
  border-radius: var(--r);
  padding: .3rem .8rem;
  margin-top: .25rem;
  transition: background .15s;
}
.panel-cta:hover { background: rgba(var(--accent-rgb), .06); }

/* Mini Table */
.mini-tbl { width: 100%; border-collapse: collapse; }
.mini-tbl th {
  font-size: .75rem;
  font-weight: 600;
  color: var(--text-muted);
  padding: 0 .5rem .5rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
.mini-tbl th.right { text-align: right; }
.mini-tbl td {
  padding: .55rem .5rem;
  font-size: .78rem;
  color: var(--text-sub);
  border-bottom: 1px solid var(--border-light);
  vertical-align: middle;
}
.mini-tbl tbody tr:last-child td { border-bottom: none; }
.mini-tbl tbody tr:hover { background: var(--bg-hover); }
.mini-tbl td.fw    { color: var(--text); font-weight: 500; }
.mini-tbl td.right { text-align: right; }
.mini-tbl td.muted { color: var(--text-muted); }

/* Badges */
.badge {
  display: inline-block;
  font-size: .65rem;
  font-weight: 600;
  padding: .12rem .45rem;
  border-radius: var(--r);
  letter-spacing: .02em;
  text-transform: capitalize;
}
.badge--teal  { background: rgba(var(--blue-rgb), .1);  color: var(--blue);  }
.badge--green { background: var(--green-bg);       color: var(--green); }
.badge--red   { background: var(--red-bg);         color: var(--red);   }
.badge--muted { background: var(--bg-hover);       color: var(--text-muted); }

/* Stock list */
.stock-list { display: flex; flex-direction: column; }
.stock-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: .55rem .5rem;
  border-bottom: 1px solid var(--border-light);
  transition: background .12s;
}
.stock-row:last-child { border-bottom: none; }
.stock-row:hover { background: var(--bg-hover); }
.stock-info { display: flex; align-items: center; gap: .55rem; min-width: 0; }
.stock-sku  { font-size: .68rem; color: var(--text-sub); font-family: 'Geist Mono Variable', ui-monospace, monospace; font-weight: 600; flex-shrink: 0; }
.stock-name { font-size: .78rem; color: var(--text-sub); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stock-qty  { display: flex; align-items: center; gap: .2rem; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.qty-num    { font-size: .8rem; font-weight: 600; color: var(--text); }
.qty-num--red { color: var(--red); }
.qty-sep    { font-size: .72rem; color: var(--text-muted); }
.qty-reorder { font-size: .72rem; color: var(--text-muted); }
</style>
