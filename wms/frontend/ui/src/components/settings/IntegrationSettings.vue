<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore, apiErrorMessage } from '@/stores/auth'
import { api } from '@/services/api'
import { intlLocale } from '@/i18n/format'

type Provider = 'woocommerce' | 'shopify' | 'elorus'
interface Integration {
  id: string; provider: Provider; secret?: string; enabled: boolean; webhook_url: string | null; last_event_at: string | null
  last_sync_at?: string | null; last_error?: string | null
}

const { t } = useI18n()
const auth = useAuthStore()
const bid = computed(() => auth.currentBusiness?.id ?? '')
const list = ref<Integration[]>([])
const error = ref('')
const shopifySecret = ref('')
const copied = ref('')

// Elorus
const elorusKey = ref('')
const elorusOrg = ref('')
const historyDays = ref(90)
const connecting = ref(false)
const syncing = ref(false)
const syncResult = ref<{ imported: number; already: number; documents: number; unmatched_skus: string[]; error?: string } | null>(null)

async function connectElorus() {
  connecting.value = true; error.value = ''
  try {
    await api.post('/integrations/elorus', { business_id: bid.value, api_key: elorusKey.value.trim(),
      organization_id: elorusOrg.value.trim(), history_days: historyDays.value })
    elorusKey.value = ''; elorusOrg.value = ''
    await load()
  } catch (e) { error.value = apiErrorMessage(e) || t('common.error') }
  finally { connecting.value = false }
}

async function syncNow(i: Integration) {
  syncing.value = true; syncResult.value = null
  try { syncResult.value = (await api.post(`/integrations/${i.id}/sync`, null, { timeout: 180_000 })).data; await load() }
  catch (e) { error.value = apiErrorMessage(e) || t('common.error') }
  finally { syncing.value = false }
}

const byProvider = (p: Provider) => list.value.find(i => i.provider === p)

async function load() {
  try { list.value = (await api.get('/integrations', { params: { business_id: bid.value } })).data }
  catch (e) { error.value = apiErrorMessage(e) || t('common.error') }
}
onMounted(load)

async function connect(provider: Provider) {
  error.value = ''
  try {
    await api.post('/integrations', { business_id: bid.value, provider, secret: provider === 'shopify' ? shopifySecret.value : null })
    shopifySecret.value = ''
    await load()
  } catch (e) { error.value = apiErrorMessage(e) || t('common.error') }
}

async function toggle(i: Integration) {
  await api.patch(`/integrations/${i.id}`, { enabled: !i.enabled })
  await load()
}

async function remove(i: Integration) {
  if (!confirm(t('integrations.confirmRemove'))) return
  await api.delete(`/integrations/${i.id}`)
  await load()
}

async function copy(text: string, what: string) {
  try { await navigator.clipboard.writeText(text); copied.value = what; setTimeout(() => (copied.value = ''), 1500) } catch { /* ignore */ }
}
</script>

<template>
  <div class="ui-card invoicing">
    <div class="ui-card-head">
      <div>
        <p class="ui-card-title">{{ t('invoicing.title') }}</p>
        <p class="ui-card-sub">{{ t('invoicing.sub') }}</p>
      </div>
    </div>
    <section class="ui-card-body provider">
      <div class="p-head">
        <strong>Elorus</strong>
        <template v-if="byProvider('elorus')">
          <span class="ui-badge" :class="byProvider('elorus')!.last_error ? 'ui-badge--red' : byProvider('elorus')!.enabled ? 'ui-badge--green' : ''">
            {{ byProvider('elorus')!.last_error ? t('invoicing.error') : byProvider('elorus')!.enabled ? t('integrations.active') : t('integrations.paused') }}
          </span>
          <span v-if="byProvider('elorus')!.last_sync_at" class="ui-muted small">
            {{ t('invoicing.lastSync', { when: new Date(byProvider('elorus')!.last_sync_at!).toLocaleString(intlLocale()) }) }}
          </span>
        </template>
      </div>

      <template v-if="byProvider('elorus')">
        <p v-if="byProvider('elorus')!.last_error" class="ui-alert ui-alert--error">{{ byProvider('elorus')!.last_error }}</p>
        <p class="ui-hint">{{ t('invoicing.howItWorks') }}</p>
        <p v-if="syncResult" class="ui-alert" :class="syncResult.error ? 'ui-alert--error' : 'ui-alert--success'">
          {{ syncResult.error || t('invoicing.syncResult', { imported: syncResult.imported, docs: syncResult.documents }) }}
          <template v-if="syncResult.unmatched_skus?.length"><br>{{ t('invoicing.unmatched') }} {{ syncResult.unmatched_skus.join(', ') }}</template>
        </p>
        <div class="actions">
          <button class="ui-btn ui-btn--primary ui-btn--sm" :disabled="syncing || !byProvider('elorus')!.enabled" @click="syncNow(byProvider('elorus')!)">
            <span v-if="syncing" class="ui-spinner" />{{ t('invoicing.syncNow') }}
          </button>
          <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="toggle(byProvider('elorus')!)">{{ byProvider('elorus')!.enabled ? t('integrations.pause') : t('integrations.resume') }}</button>
          <button class="ui-btn ui-btn--danger ui-btn--sm" @click="remove(byProvider('elorus')!)">{{ t('integrations.disconnect') }}</button>
        </div>
      </template>

      <template v-else>
        <p class="ui-hint">{{ t('invoicing.elorusSetup') }}</p>
        <div class="ui-grid-2">
          <div class="ui-field"><label class="ui-label">API key</label><input v-model="elorusKey" class="ui-input ui-input--sm ui-mono" autocomplete="off" /></div>
          <div class="ui-field"><label class="ui-label">Organization ID</label><input v-model="elorusOrg" class="ui-input ui-input--sm ui-mono" autocomplete="off" /></div>
        </div>
        <label class="ui-check"><input type="checkbox" :checked="historyDays > 0" @change="historyDays = ($event.target as HTMLInputElement).checked ? 90 : 0" /> {{ t('invoicing.history') }}</label>
        <div><button class="ui-btn ui-btn--primary ui-btn--sm" :disabled="connecting || elorusKey.length < 10 || !elorusOrg" @click="connectElorus">
          <span v-if="connecting" class="ui-spinner" />{{ t('integrations.connect') }}
        </button></div>
      </template>
    </section>
    <p class="ui-card-body ui-hint">
      {{ t('invoicing.otherPrograms') }} <router-link to="/orders" class="link">{{ t('salesImport.button') }} →</router-link>
    </p>
  </div>

  <div class="ui-card">
    <div class="ui-card-head">
      <div>
        <p class="ui-card-title">{{ t('integrations.title') }}</p>
        <p class="ui-card-sub">{{ t('integrations.sub') }}</p>
      </div>
    </div>
    <p v-if="error" class="ui-card-body ui-alert ui-alert--error">{{ error }}</p>

    <section v-for="p in (['woocommerce', 'shopify'] as const)" :key="p" class="ui-card-body provider">
      <div class="p-head">
        <strong>{{ p === 'woocommerce' ? 'WooCommerce' : 'Shopify' }}</strong>
        <template v-if="byProvider(p)">
          <span class="ui-badge" :class="byProvider(p)!.enabled ? 'ui-badge--green' : ''">
            {{ byProvider(p)!.enabled ? t('integrations.active') : t('integrations.paused') }}
          </span>
          <span v-if="byProvider(p)!.last_event_at" class="ui-muted small">
            {{ t('integrations.lastOrder', { when: new Date(byProvider(p)!.last_event_at!).toLocaleString(intlLocale()) }) }}
          </span>
        </template>
      </div>

      <template v-if="byProvider(p)">
        <div class="ui-field">
          <label class="ui-label">{{ t('integrations.url') }}</label>
          <div class="copy-row">
            <input class="ui-input ui-input--sm ui-mono" readonly :value="byProvider(p)!.webhook_url" />
            <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="copy(byProvider(p)!.webhook_url ?? '', p + 'url')">{{ copied === p + 'url' ? t('draft.copied') : t('draft.copy') }}</button>
          </div>
        </div>
        <div v-if="p === 'woocommerce'" class="ui-field">
          <label class="ui-label">{{ t('integrations.secret') }}</label>
          <div class="copy-row">
            <input class="ui-input ui-input--sm ui-mono" readonly :value="byProvider(p)!.secret" />
            <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="copy(byProvider(p)!.secret ?? '', p + 'secret')">{{ copied === p + 'secret' ? t('draft.copied') : t('draft.copy') }}</button>
          </div>
        </div>
        <p class="ui-hint">{{ t(`integrations.steps.${p}`) }}</p>
        <div class="actions">
          <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="toggle(byProvider(p)!)">{{ byProvider(p)!.enabled ? t('integrations.pause') : t('integrations.resume') }}</button>
          <button class="ui-btn ui-btn--danger ui-btn--sm" @click="remove(byProvider(p)!)">{{ t('integrations.disconnect') }}</button>
        </div>
      </template>

      <template v-else>
        <p class="ui-hint">{{ t(`integrations.about.${p}`) }}</p>
        <div v-if="p === 'shopify'" class="copy-row">
          <input v-model="shopifySecret" class="ui-input ui-input--sm" :placeholder="t('integrations.shopifySecret')" />
          <button class="ui-btn ui-btn--primary ui-btn--sm" :disabled="shopifySecret.length < 8" @click="connect(p)">{{ t('integrations.connect') }}</button>
        </div>
        <div v-else><button class="ui-btn ui-btn--primary ui-btn--sm" @click="connect(p)">{{ t('integrations.connect') }}</button></div>
      </template>
    </section>
    <p class="ui-card-body ui-hint">{{ t('integrations.skuNote') }}</p>
  </div>
</template>

<style scoped>
.provider { display: flex; flex-direction: column; gap: .75rem; border-bottom: 1px solid var(--border-light); }
.p-head { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
.copy-row { display: flex; gap: .5rem; }
.copy-row .ui-input { flex: 1; }
.actions { display: flex; gap: .5rem; }
.small { font-size: .8rem; }
.invoicing { margin-bottom: 1.25rem; }
.link { color: var(--accent); }
</style>
