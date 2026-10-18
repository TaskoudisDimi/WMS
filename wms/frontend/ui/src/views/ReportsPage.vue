<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/services/api'
import { intlLocale } from '@/i18n/format'

type Tab = 'valuation' | 'abc' | 'dead' | 'margins'
interface Report {
  days: number
  valuation: { total: number; missing_cost: number; by_category: { category: string; value: number }[]
    items: { sku: string; name: string; category: string | null; quantity: number; unit: string | null; cost_price: number; value: number }[] }
  abc: { total_revenue: number; counts: Record<'A' | 'B' | 'C', number>; revenue_share: Record<'A' | 'B' | 'C', number>
    items: { sku: string; name: string; units: number; revenue: number; share: number; cumulative: number; class: 'A' | 'B' | 'C' }[]
    no_sales: { sku: string; name: string }[] }
  margins: { total_profit: number; total_revenue: number
    items: { sku: string; name: string; units: number; revenue: number; cost: number; profit: number; margin_pct: number | null }[] }
  dead_stock: { value: number; days: number; items: { sku: string; name: string; quantity: number; unit: string | null; value: number | null; last_sale: string | null }[] }
}

const { t } = useI18n()
const auth = useAuthStore()
const bid = computed(() => auth.currentBusiness?.id ?? '')
const tab = ref<Tab>('valuation')
const days = ref(90)
const data = ref<Report | null>(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try { data.value = (await api.get('/reports', { params: { business_id: bid.value, days: days.value } })).data }
  finally { loading.value = false }
}
onMounted(load)
watch(days, load)

const money = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString(intlLocale(), { style: 'currency', currency: 'EUR', maximumFractionDigits: digits, minimumFractionDigits: digits })
const maxCategory = computed(() => Math.max(1, ...(data.value?.valuation.by_category.map(c => c.value) ?? [1])))

/** CSV with ; separator and BOM so Greek Excel opens it correctly */
function exportCsv() {
  if (!data.value) return
  const d = data.value
  const sets: Record<Tab, [string[], (string | number | null)[][]]> = {
    valuation: [['SKU', t('reports.cols.product'), t('reports.cols.category'), t('reports.cols.qty'), t('reports.cols.cost'), t('reports.cols.value')],
      d.valuation.items.map(r => [r.sku, r.name, r.category, r.quantity, r.cost_price, r.value])],
    abc: [['SKU', t('reports.cols.product'), t('reports.cols.class'), t('reports.cols.units'), t('reports.cols.revenue'), '%', t('reports.cols.cumulative')],
      d.abc.items.map(r => [r.sku, r.name, r.class, r.units, r.revenue, r.share, r.cumulative])],
    dead: [['SKU', t('reports.cols.product'), t('reports.cols.qty'), t('reports.cols.value'), t('reports.cols.lastSale')],
      d.dead_stock.items.map(r => [r.sku, r.name, r.quantity, r.value, r.last_sale])],
    margins: [['SKU', t('reports.cols.product'), t('reports.cols.units'), t('reports.cols.revenue'), t('reports.cols.cost'), t('reports.cols.profit'), t('reports.cols.margin')],
      d.margins.items.map(r => [r.sku, r.name, r.units, r.revenue, r.cost, r.profit, r.margin_pct])],
  }
  const [head, rows] = sets[tab.value]
  const cell = (v: string | number | null) => {
    if (v == null) return ''
    const s = typeof v === 'number' ? String(v).replace('.', ',') : v
    return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = '﻿' + [head, ...rows].map(r => r.map(cell).join(';')).join('\n')
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  a.download = `${tab.value}-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>

<template>
  <div class="ui-page">
    <div class="ui-toolbar">
      <div class="ui-tabs">
        <button v-for="k in (['valuation', 'abc', 'dead', 'margins'] as const)" :key="k" class="ui-tab" :class="{ active: tab === k }" @click="tab = k">
          {{ t(`reports.tabs.${k}`) }}
        </button>
      </div>
      <span class="spacer" />
      <select v-if="tab === 'abc' || tab === 'margins'" v-model.number="days" class="ui-select ui-input--sm period">
        <option :value="30">{{ t('reports.period', { n: 30 }) }}</option>
        <option :value="90">{{ t('reports.period', { n: 90 }) }}</option>
        <option :value="365">{{ t('reports.period', { n: 365 }) }}</option>
      </select>
      <button class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="!data" @click="exportCsv">{{ t('reports.export') }}</button>
    </div>

    <p v-if="loading && !data" class="ui-empty">{{ t('common.loading') }}</p>

    <template v-else-if="data">
      <!-- Valuation -->
      <template v-if="tab === 'valuation'">
        <div class="kpis">
          <div class="kpi"><span>{{ t('reports.valuation.total') }}</span><b>{{ money(data.valuation.total) }}</b></div>
          <div class="kpi"><span>{{ t('reports.valuation.products') }}</span><b>{{ data.valuation.items.length }}</b></div>
          <div v-if="data.valuation.missing_cost" class="kpi warn"><span>{{ t('reports.valuation.missingCost') }}</span><b>{{ data.valuation.missing_cost }}</b></div>
        </div>
        <div v-if="data.valuation.by_category.length" class="ui-card ui-card-body cats">
          <p class="ui-card-title">{{ t('reports.valuation.byCategory') }}</p>
          <div v-for="c in data.valuation.by_category" :key="c.category" class="cat">
            <span class="cat-name">{{ c.category }}</span>
            <span class="bar"><span :style="{ width: `${(c.value / maxCategory) * 100}%` }" /></span>
            <span class="num">{{ money(c.value) }}</span>
          </div>
        </div>
        <div class="ui-card ui-table-wrap">
          <table class="ui-table">
            <thead><tr><th>{{ t('reports.cols.product') }}</th><th class="num">{{ t('reports.cols.qty') }}</th><th class="num">{{ t('reports.cols.cost') }}</th><th class="num">{{ t('reports.cols.value') }}</th></tr></thead>
            <tbody><tr v-for="r in data.valuation.items" :key="r.sku">
              <td><span class="ui-mono ui-muted">{{ r.sku }}</span> {{ r.name }}</td>
              <td class="num">{{ r.quantity }} <span class="ui-muted">{{ r.unit }}</span></td>
              <td class="num">{{ money(r.cost_price, 2) }}</td><td class="num"><b>{{ money(r.value) }}</b></td>
            </tr></tbody>
          </table>
        </div>
      </template>

      <!-- ABC -->
      <template v-else-if="tab === 'abc'">
        <p class="ui-hint">{{ t('reports.abc.explain') }}</p>
        <div class="kpis">
          <div v-for="c in (['A', 'B', 'C'] as const)" :key="c" class="kpi">
            <span>{{ t('reports.abc.class', { c }) }}</span>
            <b>{{ t('reports.abc.products', { n: data.abc.counts[c] }) }}</b>
            <small>{{ t('reports.abc.ofRevenue', { p: data.abc.revenue_share[c] }) }}</small>
          </div>
        </div>
        <div class="ui-card ui-table-wrap">
          <table class="ui-table">
            <thead><tr><th></th><th>{{ t('reports.cols.product') }}</th><th class="num">{{ t('reports.cols.units') }}</th><th class="num">{{ t('reports.cols.revenue') }}</th><th class="num">%</th><th class="num">{{ t('reports.cols.cumulative') }}</th></tr></thead>
            <tbody>
              <tr v-for="r in data.abc.items" :key="r.sku">
                <td><span class="ui-badge" :class="{ 'ui-badge--accent': r.class === 'A', 'ui-badge--blue': r.class === 'B' }">{{ r.class }}</span></td>
                <td><span class="ui-mono ui-muted">{{ r.sku }}</span> {{ r.name }}</td>
                <td class="num">{{ r.units }}</td><td class="num">{{ money(r.revenue) }}</td>
                <td class="num">{{ r.share }}%</td><td class="num ui-muted">{{ r.cumulative }}%</td>
              </tr>
            </tbody>
          </table>
          <p v-if="data.abc.no_sales.length" class="ui-card-body ui-hint">{{ t('reports.abc.noSales', { n: data.abc.no_sales.length }) }}</p>
        </div>
      </template>

      <!-- Dead stock -->
      <template v-else-if="tab === 'dead'">
        <p class="ui-hint">{{ t('reports.dead.explain', { n: data.dead_stock.days }) }}</p>
        <div class="kpis">
          <div class="kpi"><span>{{ t('reports.dead.tied') }}</span><b>{{ money(data.dead_stock.value) }}</b></div>
          <div class="kpi"><span>{{ t('reports.valuation.products') }}</span><b>{{ data.dead_stock.items.length }}</b></div>
        </div>
        <div class="ui-card ui-table-wrap">
          <p v-if="!data.dead_stock.items.length" class="ui-empty">{{ t('reports.dead.none') }}</p>
          <table v-else class="ui-table">
            <thead><tr><th>{{ t('reports.cols.product') }}</th><th class="num">{{ t('reports.cols.qty') }}</th><th class="num">{{ t('reports.cols.value') }}</th><th class="num">{{ t('reports.cols.lastSale') }}</th></tr></thead>
            <tbody><tr v-for="r in data.dead_stock.items" :key="r.sku">
              <td><span class="ui-mono ui-muted">{{ r.sku }}</span> {{ r.name }}</td>
              <td class="num">{{ r.quantity }} <span class="ui-muted">{{ r.unit }}</span></td>
              <td class="num">{{ money(r.value) }}</td>
              <td class="num ui-muted">{{ r.last_sale ? new Date(r.last_sale).toLocaleDateString(intlLocale()) : t('reports.dead.never') }}</td>
            </tr></tbody>
          </table>
        </div>
      </template>

      <!-- Margins -->
      <template v-else>
        <div class="kpis">
          <div class="kpi"><span>{{ t('reports.margins.profit') }}</span><b>{{ money(data.margins.total_profit) }}</b></div>
          <div class="kpi"><span>{{ t('reports.margins.avg') }}</span>
            <b>{{ data.margins.total_revenue ? Math.round(data.margins.total_profit / data.margins.total_revenue * 1000) / 10 : 0 }}%</b></div>
        </div>
        <div class="ui-card ui-table-wrap">
          <p v-if="!data.margins.items.length" class="ui-empty">{{ t('reports.margins.none') }}</p>
          <table v-else class="ui-table">
            <thead><tr><th>{{ t('reports.cols.product') }}</th><th class="num">{{ t('reports.cols.units') }}</th><th class="num">{{ t('reports.cols.revenue') }}</th><th class="num">{{ t('reports.cols.cost') }}</th><th class="num">{{ t('reports.cols.profit') }}</th><th class="num">{{ t('reports.cols.margin') }}</th></tr></thead>
            <tbody><tr v-for="r in data.margins.items" :key="r.sku">
              <td><span class="ui-mono ui-muted">{{ r.sku }}</span> {{ r.name }}</td>
              <td class="num">{{ r.units }}</td><td class="num">{{ money(r.revenue) }}</td><td class="num">{{ money(r.cost) }}</td>
              <td class="num" :class="{ neg: r.profit < 0 }"><b>{{ money(r.profit) }}</b></td>
              <td class="num"><span class="ui-badge" :class="r.margin_pct == null ? '' : r.margin_pct < 10 ? 'ui-badge--red' : r.margin_pct < 25 ? 'ui-badge--amber' : 'ui-badge--green'">{{ r.margin_pct ?? '—' }}%</span></td>
            </tr></tbody>
          </table>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.period { width: 170px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .75rem; }
.kpi { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--r-lg); padding: .9rem 1rem; display: grid; gap: .2rem; }
.kpi span { font-size: .8rem; color: var(--text-muted); }
.kpi b { font-size: 1.4rem; font-weight: 650; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.kpi small { font-size: .78rem; color: var(--text-sub); }
.kpi.warn b { color: var(--amber); }
.cats { display: grid; gap: .55rem; }
.cat { display: grid; grid-template-columns: 160px 1fr 110px; gap: .75rem; align-items: center; font-size: .875rem; }
.cat-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar { height: 8px; background: var(--bg-hover); border-radius: 99px; overflow: hidden; }
.bar span { display: block; height: 100%; background: var(--accent); border-radius: inherit; }
.cat .num { text-align: right; font-variant-numeric: tabular-nums; }
.neg { color: var(--red); }
</style>
