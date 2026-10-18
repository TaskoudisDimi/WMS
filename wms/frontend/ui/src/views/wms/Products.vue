<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'
import { api } from '@/services/api'
import ImportProductsModal from '@/components/products/ImportProductsModal.vue'
import BarcodeScanner from '@/components/BarcodeScanner.vue'
import BaseModal from '@/components/ui/BaseModal.vue'

const auth = useAuthStore()
const { t } = useI18n()

interface Product {
  id: string
  sku: string
  name: string
  category: string | null
  unit: string
  reorder_point: number
  cost_price: number | null
  sell_price: number | null
  barcode: string | null
  supplier: string | null
  supplier_id: string | null
  lead_time_days: number
  track_expiry: boolean
  min_order_qty: number
  order_multiple: number
}

const products   = ref<Product[]>([])
const loading    = ref(true)
const error      = ref('')
const showModal  = ref(false)
const editId     = ref<string | null>(null)
const saving     = ref(false)
const deleteTarget = ref<string | null>(null)
const showImport = ref(false)
const scanFor    = ref<'search' | 'form' | null>(null)
const search     = ref('')

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return products.value
  return products.value.filter(p =>
    p.sku.toLowerCase().includes(q) || p.name.toLowerCase().includes(q) ||
    (p.barcode ?? '').includes(q) || (p.supplier ?? '').toLowerCase().includes(q))
})

function onScanned(code: string) {
  if (scanFor.value === 'form') form.value.barcode = code
  else search.value = code
  scanFor.value = null
}

const emptyForm = () => ({
  sku: '', name: '', category: '', unit: 'τεμ',
  reorder_point: 0, cost_price: '', sell_price: '',
  barcode: '', supplier_id: '', lead_time_days: 7, track_expiry: false,
  min_order_qty: 0, order_multiple: 1,
})
const suppliers = ref<{ id: string; name: string; lead_time_days: number | null }[]>([])

function onSupplierChange() {
  const s = suppliers.value.find(x => x.id === form.value.supplier_id)
  if (s?.lead_time_days && !editId.value) form.value.lead_time_days = s.lead_time_days
}
const form = ref(emptyForm())

const businessId = computed(() => auth.currentBusiness?.id ?? '')

async function load() {
  if (!businessId.value) { loading.value = false; return }
  loading.value = true; error.value = ''
  try {
    const [r, sup] = await Promise.all([
      api.get('/products', { params: { business_id: businessId.value } }),
      api.get('/suppliers', { params: { business_id: businessId.value } }),
    ])
    products.value = r.data
    suppliers.value = sup.data
  } catch { error.value = t('wms.errorLoad') }
  finally { loading.value = false }
}

onMounted(load)

function openCreate() {
  editId.value = null
  form.value = emptyForm()
  showModal.value = true
}

function openEdit(p: Product) {
  editId.value = p.id
  form.value = {
    sku: p.sku, name: p.name, category: p.category ?? '',
    unit: p.unit, reorder_point: p.reorder_point,
    cost_price: p.cost_price != null ? String(p.cost_price) : '',
    sell_price: p.sell_price != null ? String(p.sell_price) : '',
    barcode: p.barcode ?? '', supplier_id: p.supplier_id ?? '',
    lead_time_days: p.lead_time_days ?? 7, track_expiry: !!p.track_expiry,
    min_order_qty: p.min_order_qty ?? 0, order_multiple: p.order_multiple ?? 1,
  }
  showModal.value = true
}

async function save() {
  if (!form.value.sku || !form.value.name) return
  saving.value = true
  try {
    const payload = {
      sku: form.value.sku,
      name: form.value.name,
      category: form.value.category || null,
      unit: form.value.unit,
      reorder_point: Number(form.value.reorder_point) || 0,
      cost_price: form.value.cost_price !== '' ? Number(form.value.cost_price) : null,
      sell_price: form.value.sell_price !== '' ? Number(form.value.sell_price) : null,
      barcode: form.value.barcode || null,
      supplier_id: form.value.supplier_id || null,
      min_order_qty: Math.max(0, Number(form.value.min_order_qty) || 0),
      order_multiple: Math.max(1, Number(form.value.order_multiple) || 1),
      lead_time_days: Math.max(1, Number(form.value.lead_time_days) || 7),
      track_expiry: form.value.track_expiry,
    }
    if (editId.value) {
      await api.patch(`/products/${editId.value}`, payload)
    } else {
      await api.post('/products', { ...payload, business_id: businessId.value })
    }
    showModal.value = false
    await load()
  } finally { saving.value = false }
}

async function confirmDelete(id: string) {
  try {
    await api.delete(`/products/${id}`)
    deleteTarget.value = null
    await load()
  } catch { /* ignore */ }
}
</script>

<template>
  <div class="page">

    <div class="ui-toolbar">
      <div class="search">
        <input v-model="search" class="ui-input ui-input--sm" :placeholder="t('wms.products.search')" />
        <button class="ui-icon-btn" :title="t('scanner.title')" :aria-label="t('scanner.title')" @click="scanFor = 'search'">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 8v8M11 8v8M14 8v8M17 8v8"/></svg>
        </button>
      </div>
      <span class="spacer" />
      <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="showImport = true">{{ t('import.button') }}</button>
      <button class="ui-btn ui-btn--primary ui-btn--sm" @click="openCreate">{{ t('wms.products.addBtn') }}</button>
    </div>

    <div v-if="loading" class="state-msg">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="state-msg state-msg--error">{{ error }}</div>

    <div v-else-if="products.length === 0" class="empty-state">
      <div class="empty-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>
        </svg>
      </div>
      <p class="empty-title">{{ t('wms.products.empty.title') }}</p>
      <p class="empty-hint">{{ t('wms.products.empty.hint') }}</p>
      <div class="empty-actions">
        <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="showImport = true">{{ t('import.button') }}</button>
        <button class="btn-primary" @click="openCreate">{{ t('wms.products.addBtn') }}</button>
      </div>
    </div>

    <div v-else class="card">
      <div class="tbl-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th>{{ t('wms.products.table.sku') }}</th>
              <th>{{ t('wms.products.table.name') }}</th>
              <th>{{ t('wms.products.table.category') }}</th>
              <th>{{ t('wms.products.table.supplier') }}</th>
              <th class="num">{{ t('wms.products.table.reorderPoint') }}</th>
              <th class="num">{{ t('wms.products.table.costPrice') }}</th>
              <th class="num">{{ t('wms.products.table.sellPrice') }}</th>
              <th class="act"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in filtered" :key="p.id">
              <td><span class="sku-badge">{{ p.sku }}</span></td>
              <td class="fw">{{ p.name }}</td>
              <td class="muted">{{ p.category || '—' }}</td>
              <td class="muted">{{ p.supplier || '—' }}</td>
              <td class="num">{{ p.reorder_point }}</td>
              <td class="num muted">{{ p.cost_price != null ? '€' + p.cost_price : '—' }}</td>
              <td class="num muted">{{ p.sell_price != null ? '€' + p.sell_price : '—' }}</td>
              <td class="act">
                <div class="row-actions">
                  <button class="icon-btn" @click="openEdit(p)" :title="t('common.edit')">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                      <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                  </button>
                  <button v-if="deleteTarget !== p.id" class="icon-btn icon-btn--danger"
                    @click="deleteTarget = p.id" :title="t('common.delete')">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
                      <path d="M10 11v6M14 11v6M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/>
                    </svg>
                  </button>
                  <template v-else>
                    <button class="icon-btn icon-btn--confirm" @click="confirmDelete(p.id)">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                    </button>
                    <button class="icon-btn" @click="deleteTarget = null">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                  </template>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
          <div class="modal">
            <div class="modal-head">
              <h2 class="modal-title">{{ editId ? t('wms.products.modal.editTitle') : t('wms.products.modal.createTitle') }}</h2>
              <button class="icon-btn" @click="showModal = false">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div class="modal-body">
              <div class="form-row">
                <label class="label">{{ t('wms.products.table.sku') }} *</label>
                <input v-model="form.sku" class="input" :placeholder="t('wms.products.table.sku')" />
              </div>
              <div class="form-row">
                <label class="label">{{ t('wms.products.table.name') }} *</label>
                <input v-model="form.name" class="input" :placeholder="t('wms.products.table.name')" />
              </div>
              <div class="form-2col">
                <div class="form-row">
                  <label class="label">{{ t('wms.products.table.category') }}</label>
                  <input v-model="form.category" class="input" :placeholder="t('wms.products.table.category')" />
                </div>
                <div class="form-row">
                  <label class="label">{{ t('wms.products.table.unit') }}</label>
                  <input v-model="form.unit" class="input" />
                </div>
              </div>
              <div class="form-row">
                <label class="label">{{ t('wms.products.table.barcode') }}</label>
                <div class="with-btn">
                  <input v-model="form.barcode" class="input" inputmode="numeric" />
                  <button class="ui-icon-btn" type="button" :aria-label="t('scanner.title')" @click="scanFor = 'form'">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 8v8M11 8v8M14 8v8M17 8v8"/></svg>
                  </button>
                </div>
              </div>
              <div class="form-2col">
                <div class="form-row">
                  <label class="label">{{ t('wms.products.table.supplier') }}</label>
                  <select v-model="form.supplier_id" class="input" @change="onSupplierChange">
                    <option value="">—</option>
                    <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
                  </select>
                  <router-link to="/suppliers" class="hint-link">{{ t('suppliers.manage') }}</router-link>
                </div>
                <div class="form-row">
                  <label class="label">{{ t('wms.products.table.leadTime') }}</label>
                  <input v-model="form.lead_time_days" class="input" type="number" min="1" />
                </div>
              </div>
              <div class="form-row">
                <label class="label">{{ t('wms.products.table.reorderPoint') }}</label>
                <input v-model="form.reorder_point" class="input" type="number" min="0" />
              </div>
              <div class="form-2col">
                <div class="form-row">
                  <label class="label">{{ t('wms.products.minOrderQty') }}</label>
                  <input v-model="form.min_order_qty" class="input" type="number" min="0" />
                </div>
                <div class="form-row">
                  <label class="label">{{ t('wms.products.orderMultiple') }}</label>
                  <input v-model="form.order_multiple" class="input" type="number" min="1" />
                </div>
              </div>
              <label class="ui-check"><input v-model="form.track_expiry" type="checkbox" /> {{ t('wms.products.trackExpiry') }}</label>
              <div class="form-2col">
                <div class="form-row">
                  <label class="label">{{ t('wms.products.table.costPrice') }}</label>
                  <input v-model="form.cost_price" class="input" type="number" step="0.01" min="0" placeholder="0.00" />
                </div>
                <div class="form-row">
                  <label class="label">{{ t('wms.products.table.sellPrice') }}</label>
                  <input v-model="form.sell_price" class="input" type="number" step="0.01" min="0" placeholder="0.00" />
                </div>
              </div>
            </div>
            <div class="modal-foot">
              <button class="btn-ghost" @click="showModal = false">{{ t('common.cancel') }}</button>
              <button class="btn-primary" :disabled="saving || !form.sku || !form.name" @click="save">
                {{ saving ? t('common.loading') : t('common.save') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <ImportProductsModal v-if="showImport" :business-id="businessId" @close="showImport = false" @imported="load" />

    <BaseModal v-if="scanFor" :title="t('scanner.title')" @close="scanFor = null">
      <BarcodeScanner @detected="onScanned" />
    </BaseModal>
  </div>
</template>

<style scoped>
.search { display: flex; align-items: center; gap: .25rem; width: min(360px, 100%); }
.search .ui-input { flex: 1; }
.with-btn { display: flex; gap: .4rem; align-items: center; }
.with-btn .input { flex: 1; }
.hint-link { font-size: .78rem; color: var(--accent); margin-top: .2rem; }
.empty-actions { display: flex; gap: .5rem; justify-content: center; }
.page {
  padding: 2rem;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.page-header { display: flex; align-items: center; justify-content: flex-end; }
.header-icon {
  width: 40px; height: 40px;
  background: rgba(var(--accent-rgb), .08);
  border: 1px solid rgba(var(--accent-rgb), .18);
  border-radius: var(--r-lg);
  display: flex; align-items: center; justify-content: center;
  color: var(--teal); flex-shrink: 0;
}
.header-text { flex: 1; }
.page-title { font-size: 1.2rem; font-weight: 600; color: var(--text); margin: 0; letter-spacing: -.01em; }
.page-sub   { font-size: .75rem; color: var(--text-muted); margin: .15rem 0 0; }

.btn-primary {
  display: inline-flex; align-items: center; gap: .4rem;
  background: var(--teal); color: var(--accent-text); border: none;
  border-radius: var(--r); padding: .5rem 1rem;
  font-size: .8rem; font-weight: 600; cursor: pointer;
  transition: opacity .15s; white-space: nowrap;
}
.btn-primary:hover { opacity: .88; }
.btn-primary:disabled { opacity: .45; cursor: not-allowed; }

.btn-ghost {
  background: transparent; border: 1px solid var(--border);
  color: var(--text-sub); border-radius: var(--r);
  padding: .5rem 1rem; font-size: .8rem; cursor: pointer;
  transition: border-color .15s;
}
.btn-ghost:hover { border-color: var(--border-mid); }

.state-msg { font-size: .82rem; color: var(--text-muted); padding: 2rem; text-align: center; }
.state-msg--error { color: var(--red); }

.empty-state {
  display: flex; flex-direction: column; align-items: center;
  gap: .75rem; padding: 3rem 1rem;
}
.empty-icon {
  width: 48px; height: 48px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--r-xl);
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted);
}
.empty-title { font-size: .92rem; font-weight: 600; color: var(--text); margin: 0; }
.empty-hint  { font-size: .78rem; color: var(--text-muted); margin: 0; }

.card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--r-lg); overflow: hidden; }
.tbl-wrap { overflow-x: auto; }
.tbl { width: 100%; border-collapse: collapse; font-size: .8rem; }
.tbl thead { background: var(--bg); border-bottom: 1px solid var(--border); }
.tbl th {
  padding: .65rem 1rem; font-size: .75rem; font-weight: 600;
  color: var(--text-muted); text-align: left; white-space: nowrap;
}
.tbl th.num, .tbl td.num { text-align: right; }
.tbl th.act, .tbl td.act { width: 90px; text-align: right; padding-right: .75rem; }
.tbl td {
  padding: .75rem 1rem; color: var(--text-sub);
  border-bottom: 1px solid var(--border);
}
.tbl tbody tr:last-child td { border-bottom: none; }
.tbl tbody tr:hover { background: var(--bg-hover); }
.tbl td.fw   { color: var(--text); font-weight: 500; }
.tbl td.muted { color: var(--text-muted); }

.sku-badge {
  display: inline-block;
   
  color: var(--text-sub); font-size: .71rem; font-weight: 600;
  padding: .1rem .45rem; border-radius: var(--r);
  font-family: 'Geist Mono Variable', ui-monospace, monospace; letter-spacing: .03em;
}

.row-actions {
  display: flex; align-items: center; justify-content: flex-end;
  gap: .3rem; opacity: 0; transition: opacity .15s;
}
.tbl tbody tr:hover .row-actions { opacity: 1; }

.icon-btn {
  width: 26px; height: 26px;
  background: transparent; border: 1px solid transparent;
  border-radius: var(--r); display: flex; align-items: center; justify-content: center;
  color: var(--text-muted); cursor: pointer;
  transition: background .12s, color .12s, border-color .12s;
}
.icon-btn:hover { background: var(--bg-hover); border-color: var(--border); color: var(--text-sub); }
.icon-btn--danger:hover  { background: var(--red-bg); border-color: rgba(var(--red-rgb), .25); color: var(--red); }
.icon-btn--confirm       { color: var(--green); }
.icon-btn--confirm:hover { background: var(--green-bg); border-color: rgba(var(--green-rgb), .25); color: var(--green); }

.modal-overlay {
  position: fixed; inset: 0; background: var(--overlay);
  display: flex; align-items: center; justify-content: center;
  z-index: 200; padding: 1rem;
}
.modal {
  background: var(--bg-card); border: 1px solid var(--border-mid);
  border-radius: var(--r-xl); width: 100%; max-width: 460px;
  box-shadow: var(--shadow-lg);
}
.modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--border);
}
.modal-title { font-size: .92rem; font-weight: 600; color: var(--text); margin: 0; }
.modal-body  { padding: 1.25rem; display: flex; flex-direction: column; gap: .8rem; }
.modal-foot  {
  display: flex; justify-content: flex-end; gap: .5rem;
  padding: .8rem 1.25rem; border-top: 1px solid var(--border);
}

.form-row { display: flex; flex-direction: column; gap: .28rem; }
.form-2col { display: grid; grid-template-columns: 1fr 1fr; gap: .8rem; }
.label { font-size: .71rem; font-weight: 500; color: var(--text-sub); }
.input {
  background: var(--bg); border: 1px solid var(--border);
  border-radius: var(--r); color: var(--text); font-size: .82rem;
  padding: .48rem .7rem; outline: none; transition: border-color .15s;
  width: 100%; box-sizing: border-box;
}
.input:focus { border-color: var(--teal); }
.input::placeholder { color: var(--text-muted); }

.modal-enter-active { transition: all .18s cubic-bezier(.2,.8,.3,1); }
.modal-leave-active { transition: all .12s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-from .modal { transform: scale(.94) translateY(8px); }
</style>
