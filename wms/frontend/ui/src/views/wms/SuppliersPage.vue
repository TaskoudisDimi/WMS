<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore, apiErrorMessage } from '@/stores/auth'
import { api } from '@/services/api'
import BaseModal from '@/components/ui/BaseModal.vue'

export interface Supplier {
  id: string; name: string; contact_name: string | null; email: string | null; phone: string | null
  vat_number: string | null; address: string | null; notes: string | null
  lead_time_days: number | null; min_order_value: number | null; product_count: number
}

const { t } = useI18n()
const auth = useAuthStore()
const bid = computed(() => auth.currentBusiness?.id ?? '')

const suppliers = ref<Supplier[]>([])
const loading = ref(true)
const search = ref('')
const editing = ref<Partial<Supplier> | null>(null)
const saving = ref(false)
const error = ref('')

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return q ? suppliers.value.filter(s => [s.name, s.contact_name, s.email].some(v => (v ?? '').toLowerCase().includes(q)))
    : suppliers.value
})

async function load() {
  loading.value = true
  try { suppliers.value = (await api.get('/suppliers', { params: { business_id: bid.value } })).data }
  finally { loading.value = false }
}
onMounted(load)

function open(s?: Supplier) {
  error.value = ''
  editing.value = s ? { ...s } : { name: '' }
}

async function save() {
  if (!editing.value?.name?.trim()) return
  saving.value = true; error.value = ''
  const { id, ...fields } = editing.value
  const payload = Object.fromEntries(Object.entries(fields)
    .filter(([k]) => k !== 'product_count' && k !== 'created_at' && k !== 'business_id')
    .map(([k, v]) => [k, v === '' ? null : v]))
  try {
    if (id) await api.patch(`/suppliers/${id}`, payload)
    else await api.post('/suppliers', { ...payload, business_id: bid.value })
    editing.value = null
    await load()
  } catch (e) {
    const m = apiErrorMessage(e)
    error.value = m === 'A supplier with this name already exists' ? t('suppliers.exists') : m || t('common.error')
  } finally { saving.value = false }
}

async function remove(s: Supplier) {
  if (!confirm(t('suppliers.confirmDelete', { name: s.name, n: s.product_count }))) return
  await api.delete(`/suppliers/${s.id}`)
  editing.value = null
  await load()
}
</script>

<template>
  <div class="ui-page">
    <div class="ui-toolbar">
      <input v-model="search" class="ui-input ui-input--sm search" :placeholder="t('suppliers.search')" />
      <span class="spacer" />
      <button class="ui-btn ui-btn--primary ui-btn--sm" @click="open()">{{ t('suppliers.add') }}</button>
    </div>

    <div class="ui-card">
      <p v-if="loading" class="ui-empty">{{ t('common.loading') }}</p>
      <div v-else-if="!suppliers.length" class="ui-empty">
        <strong>{{ t('suppliers.emptyTitle') }}</strong>{{ t('suppliers.emptyHint') }}
      </div>
      <div v-else class="ui-table-wrap">
        <table class="ui-table">
          <thead><tr>
            <th>{{ t('suppliers.name') }}</th><th>{{ t('suppliers.contact') }}</th>
            <th class="num">{{ t('suppliers.leadTime') }}</th><th class="num">{{ t('suppliers.products') }}</th><th></th>
          </tr></thead>
          <tbody>
            <tr v-for="s in filtered" :key="s.id" class="clickable" @click="open(s)">
              <td><strong>{{ s.name }}</strong><div v-if="s.vat_number" class="ui-muted small">{{ t('suppliers.vat') }} {{ s.vat_number }}</div></td>
              <td>
                <div>{{ s.contact_name || '—' }}</div>
                <div class="ui-muted small">{{ [s.email, s.phone].filter(Boolean).join(' · ') }}</div>
                <span v-if="!s.email" class="ui-badge ui-badge--amber">{{ t('suppliers.noEmail') }}</span>
              </td>
              <td class="num">{{ s.lead_time_days ? t('suppliers.days', { n: s.lead_time_days }) : '—' }}</td>
              <td class="num">{{ s.product_count }}</td>
              <td class="num"><span class="ui-muted">›</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <BaseModal v-if="editing" :title="editing.id ? editing.name! : t('suppliers.add')" :width="600" @close="editing = null">
      <div class="ui-field">
        <label class="ui-label">{{ t('suppliers.name') }} *</label>
        <input v-model="editing.name" class="ui-input" autofocus />
      </div>
      <div class="ui-grid-2">
        <div class="ui-field"><label class="ui-label">{{ t('suppliers.contactName') }}</label><input v-model="editing.contact_name" class="ui-input" /></div>
        <div class="ui-field"><label class="ui-label">{{ t('suppliers.phone') }}</label><input v-model="editing.phone" class="ui-input" type="tel" /></div>
        <div class="ui-field"><label class="ui-label">{{ t('suppliers.email') }}</label><input v-model="editing.email" class="ui-input" type="email" /></div>
        <div class="ui-field"><label class="ui-label">{{ t('suppliers.vat') }}</label><input v-model="editing.vat_number" class="ui-input" /></div>
      </div>
      <div class="ui-field"><label class="ui-label">{{ t('suppliers.address') }}</label><input v-model="editing.address" class="ui-input" /></div>
      <div class="ui-grid-2">
        <div class="ui-field">
          <label class="ui-label">{{ t('suppliers.leadTime') }}</label>
          <input v-model.number="editing.lead_time_days" class="ui-input" type="number" min="1" />
        </div>
        <div class="ui-field">
          <label class="ui-label">{{ t('suppliers.minOrder') }}</label>
          <input v-model.number="editing.min_order_value" class="ui-input" type="number" min="0" step="0.01" />
        </div>
      </div>
      <div class="ui-field"><label class="ui-label">{{ t('suppliers.notes') }}</label><textarea v-model="editing.notes" class="ui-textarea" rows="3" /></div>
      <p class="ui-hint">{{ t('suppliers.emailHint') }}</p>
      <p v-if="error" class="ui-alert ui-alert--error">{{ error }}</p>
      <template #footer>
        <button v-if="editing.id" class="ui-btn ui-btn--danger left" @click="remove(editing as Supplier)">{{ t('common.delete') }}</button>
        <button class="ui-btn ui-btn--ghost" @click="editing = null">{{ t('common.cancel') }}</button>
        <button class="ui-btn ui-btn--primary" :disabled="saving || !editing.name?.trim()" @click="save">{{ t('common.save') }}</button>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
.search { width: min(320px, 100%); }
.small { font-size: .8rem; margin-top: .1rem; }
.clickable { cursor: pointer; }
.clickable:hover td { background: var(--bg-hover); }
.left { margin-right: auto; }
</style>
