<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore, apiErrorMessage } from '@/stores/auth'
import { api } from '@/services/api'
import BarcodeScanner from '@/components/BarcodeScanner.vue'
import { useOnline } from '@/composables/useNetwork'

interface Item { quantity: number; products: { id: string; sku: string; name: string; unit: string; barcode: string | null } }
interface Line { product_id: string; sku: string; name: string; unit: string; system: number; counted: number | null }

const { t } = useI18n()
const auth = useAuthStore()
const businessId = computed(() => auth.currentBusiness?.id ?? '')
const draftKey = computed(() => `stocktake:${businessId.value}`)
// Counts applied without signal wait here and are sent when the connection returns.
// Sending twice is harmless: the API takes absolute counts, not differences.
const queueKey = computed(() => `stocktake-queue:${businessId.value}`)
const online = useOnline()
const queued = ref(0)

type Payload = { business_id: string; note: string | null; lines: { product_id: string; counted: number | null }[] }
const readQueue = (): Payload[] => { try { return JSON.parse(localStorage.getItem(queueKey.value) || '[]') } catch { return [] } }
const writeQueue = (q: Payload[]) => { try { localStorage.setItem(queueKey.value, JSON.stringify(q)) } catch { /* ignore */ } queued.value = q.length }

async function flushQueue() {
  const q = readQueue()
  if (!q.length || !navigator.onLine) { queued.value = q.length; return }
  let sent = 0
  while (q.length) {
    try { await api.post('/inventory/stocktake', q[0]); q.shift(); sent++ } catch { break }
  }
  writeQueue(q)
  if (sent) {
    message.value = { type: 'success', text: t('stocktake.syncedOffline', { n: sent }) }
    items.value = (await api.get('/inventory', { params: { business_id: businessId.value } })).data
  }
}
watch(online, v => { if (v) flushQueue() })

const items = ref<Item[]>([])
const lines = ref<Line[]>([])
const search = ref('')
const message = ref<{ type: 'error' | 'success'; text: string } | null>(null)
const applying = ref(false)
const scanning = ref(false)
const note = ref('')

onMounted(async () => {
  const r = await api.get('/inventory', { params: { business_id: businessId.value } })
  items.value = r.data
  try {
    const saved = JSON.parse(localStorage.getItem(draftKey.value) || '[]') as Line[]
    lines.value = saved.map(l => ({ ...l, system: items.value.find(i => i.products.id === l.product_id)?.quantity ?? l.system }))
  } catch { /* no draft */ }
  flushQueue()
})

watch(lines, v => {
  try { localStorage.setItem(draftKey.value, JSON.stringify(v)) } catch { /* storage unavailable */ }
}, { deep: true })

const matches = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (q.length < 2) return []
  return items.value.filter(i => i.products.sku.toLowerCase().includes(q) || i.products.name.toLowerCase().includes(q)
    || (i.products.barcode ?? '').includes(q)).slice(0, 8)
})

async function add(item: Item, increment = false) {
  const existing = lines.value.find(l => l.product_id === item.products.id)
  if (existing) {
    if (increment) existing.counted = (existing.counted ?? 0) + 1
  } else {
    lines.value.unshift({ product_id: item.products.id, sku: item.products.sku, name: item.products.name,
      unit: item.products.unit, system: item.quantity, counted: increment ? 1 : null })
  }
  search.value = ''
  await nextTick()
  if (!increment) document.querySelector<HTMLInputElement>(`#count-${item.products.id}`)?.focus()
}

function onScanned(code: string) {
  message.value = null
  const item = items.value.find(i => i.products.barcode === code || i.products.sku.toLowerCase() === code.toLowerCase())
  if (item) add(item, true)  // each scan of a unit counts one
  else message.value = { type: 'error', text: t('scanner.notFound', { code }) }
}

const counted = computed(() => lines.value.filter(l => l.counted !== null))
const differences = computed(() => counted.value.filter(l => l.counted !== l.system))

async function apply() {
  applying.value = true; message.value = null
  const payload: Payload = {
    business_id: businessId.value, note: note.value || null,
    lines: counted.value.map(l => ({ product_id: l.product_id, counted: l.counted })),
  }
  const queueIt = () => {
    writeQueue([...readQueue(), payload])
    lines.value = []
    message.value = { type: 'success', text: t('stocktake.queued') }
  }
  if (!navigator.onLine) { queueIt(); applying.value = false; return }
  try {
    const r = await api.post('/inventory/stocktake', payload)
    message.value = { type: 'success', text: t('stocktake.applied', { n: r.data.changed.length }) }
    lines.value = []
    const inv = await api.get('/inventory', { params: { business_id: businessId.value } })
    items.value = inv.data
  } catch (e) {
    // No response at all = network dropped mid-request → keep it for later
    if ((e as { response?: unknown }).response === undefined) queueIt()
    else message.value = { type: 'error', text: apiErrorMessage(e) || t('common.error') }
  } finally { applying.value = false }
}

function clearAll() {
  if (lines.value.length && !confirm(t('stocktake.confirmClear'))) return
  lines.value = []
}
</script>

<template>
  <div class="ui-page">
    <div class="ui-card">
      <div class="ui-card-head">
        <div>
          <p class="ui-card-title">{{ t('stocktake.addTitle') }}</p>
          <p class="ui-card-sub">{{ t('stocktake.addSub') }}</p>
        </div>
        <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="scanning = !scanning">
          {{ scanning ? t('scanner.stop') : t('scanner.title') }}
        </button>
      </div>
      <div class="ui-card-body add">
        <BarcodeScanner v-if="scanning" continuous @detected="onScanned" />
        <div class="search">
          <input v-model="search" class="ui-input" :placeholder="t('stocktake.search')" />
          <ul v-if="matches.length" class="results">
            <li v-for="m in matches" :key="m.products.id">
              <button @click="add(m)">
                <span class="ui-mono ui-muted">{{ m.products.sku }}</span> {{ m.products.name }}
                <span class="ui-muted right">{{ t('stocktake.inSystem', { n: m.quantity }) }}</span>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <p v-if="!online || queued" class="ui-alert ui-alert--warn">
      {{ !online ? t('stocktake.offline') : '' }} {{ queued ? t('stocktake.pending', { n: queued }) : '' }}
    </p>
    <p v-if="message" class="ui-alert" :class="message.type === 'error' ? 'ui-alert--error' : 'ui-alert--success'">{{ message.text }}</p>

    <div class="ui-card">
      <div class="ui-card-head">
        <div>
          <p class="ui-card-title">{{ t('stocktake.countTitle') }}</p>
          <p class="ui-card-sub">{{ t('stocktake.countSub', { n: counted.length, d: differences.length }) }}</p>
        </div>
        <button v-if="lines.length" class="ui-btn ui-btn--ghost ui-btn--sm" @click="clearAll">{{ t('stocktake.clear') }}</button>
      </div>
      <div v-if="!lines.length" class="ui-empty">{{ t('stocktake.empty') }}</div>
      <div v-else class="ui-table-wrap">
        <table class="ui-table">
          <thead><tr>
            <th>{{ t('wms.inventory.table.name') }}</th>
            <th class="num">{{ t('stocktake.system') }}</th>
            <th class="num">{{ t('stocktake.counted') }}</th>
            <th class="num">{{ t('stocktake.diff') }}</th><th></th>
          </tr></thead>
          <tbody>
            <tr v-for="l in lines" :key="l.product_id">
              <td><span class="ui-mono ui-muted">{{ l.sku }}</span> {{ l.name }}</td>
              <td class="num">{{ l.system }}</td>
              <td class="num">
                <input :id="`count-${l.product_id}`" v-model.number="l.counted" class="ui-input ui-input--sm count" type="number" min="0" inputmode="numeric" />
              </td>
              <td class="num">
                <span v-if="l.counted !== null && l.counted !== l.system" class="ui-badge" :class="l.counted < l.system ? 'ui-badge--red' : 'ui-badge--green'">
                  {{ l.counted > l.system ? '+' : '' }}{{ l.counted - l.system }}
                </span>
                <span v-else-if="l.counted !== null" class="ui-muted">0</span>
              </td>
              <td class="num">
                <button class="ui-icon-btn" :aria-label="t('common.delete')" @click="lines = lines.filter(x => x !== l)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="counted.length" class="ui-card-body foot">
        <input v-model="note" class="ui-input ui-input--sm" :placeholder="t('stocktake.note')" />
        <button class="ui-btn ui-btn--primary" :disabled="applying" @click="apply">
          <span v-if="applying" class="ui-spinner" />{{ t('stocktake.apply', { n: differences.length }) }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.add { display: flex; flex-direction: column; gap: .75rem; }
.search { position: relative; }
.results {
  list-style: none; position: absolute; z-index: 5; left: 0; right: 0; top: calc(100% + 4px);
  background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--r-lg); box-shadow: var(--shadow-lg); padding: .25rem;
}
.results button { width: 100%; display: flex; gap: .5rem; align-items: center; text-align: left; background: none; padding: .5rem .6rem; border-radius: var(--r); cursor: pointer; font-size: .875rem; }
.results button:hover { background: var(--bg-hover); }
.right { margin-left: auto; font-size: .8rem; }
.count { width: 90px; text-align: right; margin-left: auto; }
.foot { display: flex; gap: .5rem; justify-content: flex-end; border-top: 1px solid var(--border-light); }
.foot .ui-input { max-width: 320px; }
</style>
