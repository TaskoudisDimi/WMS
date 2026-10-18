<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Papa from 'papaparse'
import BaseModal from '@/components/ui/BaseModal.vue'
import { api } from '@/services/api'
import { apiErrorMessage } from '@/stores/auth'

/* Sales exported from any invoicing program (Epsilon, SoftOne, Prisma, Oxygen…) as
   CSV/Excel, one row per document line. Each document is imported once. */
const props = defineProps<{ businessId: string }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'imported'): void }>()
const { t } = useI18n()

type Field = 'document' | 'date' | 'customer' | 'sku' | 'quantity' | 'unit_price'
const FIELDS: Field[] = ['document', 'date', 'customer', 'sku', 'quantity', 'unit_price']
const ALIASES: Record<Field, string[]> = {
  document: ['document', 'doc', 'invoice', 'αριθμος', 'αρ. παραστατικου', 'παραστατικο', 'αρ', 'number', 'σειρα-αριθμος'],
  date: ['date', 'ημερομηνια', 'ημ/νια', 'ημνια'],
  customer: ['customer', 'client', 'πελατης', 'επωνυμια', 'συναλλασσομενος'],
  sku: ['sku', 'code', 'κωδικος', 'κωδικος ειδους', 'barcode', 'item code'],
  quantity: ['quantity', 'qty', 'ποσοτητα', 'ποσ.'],
  unit_price: ['price', 'unit price', 'τιμη', 'τιμη μοναδας', 'καθαρη τιμη'],
}
const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[_:]/g, ' ').trim()

const fileName = ref('')
const headers = ref<string[]>([])
const rows = ref<unknown[][]>([])
const mapping = ref<Record<Field, number | null>>(Object.fromEntries(FIELDS.map(f => [f, null])) as Record<Field, number | null>)
const updateStock = ref(true)
const saving = ref(false)
const error = ref('')
const result = ref<{ created: number; skipped: number; unmatched_skus: string[] } | null>(null)

async function onFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  error.value = ''; result.value = null; fileName.value = file.name
  try {
    let table: unknown[][]
    if (/\.xlsx$/i.test(file.name)) {
      const { readSheet } = await import('read-excel-file/browser')
      table = await readSheet(file)
    } else {
      table = Papa.parse<string[]>(await file.text(), { skipEmptyLines: 'greedy' }).data
    }
    if (table.length < 2) throw new Error(t('import.errors.empty'))
    headers.value = (table[0] ?? []).map(h => String(h ?? '').trim())
    rows.value = table.slice(1)
    const used = new Set<number>()
    for (const f of FIELDS) {
      const i = headers.value.findIndex((h, idx) => !used.has(idx) && ALIASES[f].includes(norm(h)))
      mapping.value[f] = i >= 0 ? i : null
      if (i >= 0) used.add(i)
    }
  } catch (err) {
    error.value = err instanceof Error && err.message ? err.message : t('import.errors.read')
  }
}

const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === '') return null
  if (typeof v === 'number') return v
  let s = String(v).trim().replace(/[€\s]/g, '')
  if (s.includes(',') && s.includes('.')) s = s.replace(/\./g, '').replace(',', '.')
  else if (s.includes(',')) s = s.replace(',', '.')
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}
/** Date objects (Excel), 17/10/2026 (Greek), 2026-10-17 (ISO) → YYYY-MM-DD */
const day = (v: unknown): string | null => {
  if (v instanceof Date) return v.toISOString().slice(0, 10)
  const s = String(v ?? '').trim()
  const gr = s.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})/)
  if (gr) return `${gr[3]}-${gr[2]!.padStart(2, '0')}-${gr[1]!.padStart(2, '0')}`
  return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : null
}

const parsed = computed(() => rows.value.map(r => {
  const c = (f: Field) => { const i = mapping.value[f]; return i === null ? null : r[i] }
  return {
    document: c('document') != null ? String(c('document')).trim() || null : null,
    date: day(c('date')), customer: c('customer') != null ? String(c('customer')).trim() || null : null,
    sku: String(c('sku') ?? '').trim(), quantity: num(c('quantity')), unit_price: num(c('unit_price')),
  }
}).filter(r => r.sku && r.quantity && r.quantity > 0))

const documents = computed(() => new Set(parsed.value.map(r => r.document ?? `${r.date}|${r.customer}`)).size)
const canImport = computed(() => mapping.value.sku !== null && mapping.value.quantity !== null && parsed.value.length > 0)

async function submit() {
  saving.value = true; error.value = ''
  try {
    const { data } = await api.post('/orders/import-sales', {
      business_id: props.businessId, rows: parsed.value, update_stock: updateStock.value,
    }, { timeout: 180_000 })
    result.value = data
    emit('imported')
  } catch (e) { error.value = apiErrorMessage(e) || t('common.error') }
  finally { saving.value = false }
}
</script>

<template>
  <BaseModal :title="t('salesImport.title')" :subtitle="t('salesImport.subtitle')" :width="760" @close="emit('close')">
    <template v-if="result">
      <p class="ui-alert ui-alert--success">{{ t('salesImport.done', { created: result.created, skipped: result.skipped }) }}</p>
      <p v-if="result.unmatched_skus.length" class="ui-alert ui-alert--warn">
        {{ t('salesImport.unmatched', { n: result.unmatched_skus.length }) }} {{ result.unmatched_skus.slice(0, 12).join(', ') }}
      </p>
    </template>
    <template v-else>
      <div class="pick">
        <label class="ui-btn ui-btn--ghost">
          <input type="file" accept=".csv,.xlsx,text/csv" hidden @change="onFile" />
          {{ fileName ? t('import.change') : t('import.choose') }}
        </label>
        <span v-if="fileName" class="ui-muted">{{ fileName }}</span>
      </div>
      <template v-if="headers.length">
        <div class="map-grid">
          <label v-for="f in FIELDS" :key="f" class="map-row">
            <span>{{ t(`salesImport.fields.${f}`) }}<b v-if="f === 'sku' || f === 'quantity'"> *</b></span>
            <select v-model="mapping[f]" class="ui-select ui-input--sm">
              <option :value="null">—</option>
              <option v-for="(h, i) in headers" :key="i" :value="i">{{ h || `#${i + 1}` }}</option>
            </select>
          </label>
        </div>
        <p class="ui-muted small">{{ t('salesImport.summary', { lines: parsed.length, docs: documents }) }}</p>
        <label class="ui-check"><input v-model="updateStock" type="checkbox" /> {{ t('salesImport.updateStock') }}</label>
        <p class="ui-hint">{{ updateStock ? t('salesImport.updateHint') : t('salesImport.historyHint') }}</p>
      </template>
    </template>
    <p v-if="error" class="ui-alert ui-alert--error">{{ error }}</p>
    <template #footer>
      <button class="ui-btn ui-btn--ghost" @click="emit('close')">{{ result ? t('common.close') : t('common.cancel') }}</button>
      <button v-if="!result" class="ui-btn ui-btn--primary" :disabled="!canImport || saving" @click="submit">
        <span v-if="saving" class="ui-spinner" />{{ t('salesImport.submit', { n: documents }) }}
      </button>
    </template>
  </BaseModal>
</template>

<style scoped>
.pick { display: flex; align-items: center; gap: .75rem; }
.pick label { cursor: pointer; }
.map-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .5rem .75rem; }
@media (max-width: 640px) { .map-grid { grid-template-columns: 1fr 1fr; } }
.map-row { display: flex; flex-direction: column; gap: .25rem; font-size: .8rem; color: var(--text-sub); }
.map-row b { color: var(--red); }
.small { font-size: .82rem; }
</style>
