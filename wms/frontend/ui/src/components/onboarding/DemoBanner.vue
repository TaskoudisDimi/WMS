<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/services/api'

const { t } = useI18n()
const auth = useAuthStore()
const realBusiness = computed(() => auth.businesses.find(b => !b.is_demo))
const deleting = ref(false)

async function deleteDemo() {
  if (!auth.currentBusiness || !confirm(t('onboarding.demo.confirmDelete'))) return
  deleting.value = true
  try {
    await api.delete(`/businesses/${auth.currentBusiness.id}`)
    await auth.fetchUser()
    if (realBusiness.value) auth.switchBusiness(realBusiness.value.id)
  } finally { deleting.value = false }
}
</script>

<template>
  <div v-if="auth.currentBusiness?.is_demo" class="banner" role="status">
    <span><strong>{{ t('onboarding.demo.bannerTitle') }}</strong> {{ t('onboarding.demo.bannerBody') }}</span>
    <span class="actions">
      <button v-if="realBusiness" @click="auth.switchBusiness(realBusiness.id)">{{ t('onboarding.demo.back') }}</button>
      <button :disabled="deleting" @click="deleteDemo">{{ t('onboarding.demo.delete') }}</button>
    </span>
  </div>
</template>

<style scoped>
.banner { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;
  padding: .55rem 1.5rem; background: var(--brand-dark); color: #fff; font-size: .85rem; }
.banner strong { font-weight: 650; margin-right: .35rem; }
.actions { display: flex; gap: .5rem; }
.actions button { background: rgba(255, 255, 255, .14); color: #fff; border-radius: var(--r); padding: .3rem .7rem; font-size: .8rem; cursor: pointer; }
.actions button:hover { background: rgba(255, 255, 255, .24); }
</style>
