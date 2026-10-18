<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseModal from '@/components/ui/BaseModal.vue'
import { api } from '@/services/api'
import { apiErrorMessage } from '@/stores/auth'

const props = defineProps<{ orderId: string; supplierEmail: string | null; supplierName: string | null }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'sent'): void }>()
const { t, locale } = useI18n()

const to = ref(props.supplierEmail ?? '')
const message = ref('')
const lang = ref<'el' | 'en'>(locale.value === 'en' ? 'en' : 'el')
const sending = ref(false)
const error = ref('')

const pdfUrl = () => `${api.defaults.baseURL}/orders/${props.orderId}/pdf?lang=${lang.value}`

async function send() {
  sending.value = true; error.value = ''
  try {
    await api.post(`/orders/${props.orderId}/send`, { to: to.value.trim() || null, message: message.value || null, lang: lang.value })
    emit('sent'); emit('close')
  } catch (e) {
    error.value = apiErrorMessage(e) || t('common.error')
  } finally { sending.value = false }
}
</script>

<template>
  <BaseModal :title="t('po.sendTitle')" :subtitle="supplierName ?? undefined" @close="emit('close')">
    <div class="ui-field">
      <label class="ui-label">{{ t('po.to') }}</label>
      <input v-model="to" class="ui-input" type="email" required />
    </div>
    <div class="ui-field">
      <label class="ui-label">{{ t('po.message') }}</label>
      <textarea v-model="message" class="ui-textarea" rows="4" :placeholder="t('po.messagePlaceholder')" />
    </div>
    <div class="row">
      <label class="ui-label">{{ t('po.language') }}</label>
      <select v-model="lang" class="ui-select ui-input--sm lang">
        <option value="el">Ελληνικά</option><option value="en">English</option>
      </select>
      <a :href="pdfUrl()" target="_blank" rel="noopener" class="preview">{{ t('po.preview') }} ↗</a>
    </div>
    <p class="ui-hint">{{ t('po.replyHint') }}</p>
    <p v-if="error" class="ui-alert ui-alert--error">{{ error }}</p>
    <template #footer>
      <button class="ui-btn ui-btn--ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
      <button class="ui-btn ui-btn--primary" :disabled="!to || sending" @click="send">
        <span v-if="sending" class="ui-spinner" />{{ t('po.send') }}
      </button>
    </template>
  </BaseModal>
</template>

<style scoped>
.row { display: flex; align-items: center; gap: .6rem; }
.lang { width: 140px; }
.preview { margin-left: auto; color: var(--accent); font-size: .875rem; }
</style>
