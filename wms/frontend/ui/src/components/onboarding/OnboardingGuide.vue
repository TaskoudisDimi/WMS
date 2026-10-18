<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore, apiErrorMessage } from '@/stores/auth'
import { api } from '@/services/api'
import ImportProductsModal from '@/components/products/ImportProductsModal.vue'

type Step = 'products' | 'suppliers' | 'orders' | 'sales_source' | 'team'
interface Status { dismissed: boolean; steps: Record<Step, boolean> }

const emit = defineEmits<{ (e: 'state', s: 'welcome' | 'checklist' | 'hidden'): void }>()
const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const bid = computed(() => auth.currentBusiness?.id ?? '')

const status = ref<Status | null>(null)
const showImport = ref(false)
const creatingDemo = ref(false)
const error = ref('')

const MAIN: Step[] = ['products', 'suppliers', 'orders']
const EXTRA: Step[] = ['sales_source', 'team']
const LINKS: Record<Step, string> = { products: '/products', suppliers: '/suppliers', orders: '/orders',
  sales_source: '/settings?tab=integrations', team: '/settings?tab=team' }

const mode = computed<'welcome' | 'checklist' | 'hidden'>(() => {
  if (!status.value || status.value.dismissed) return 'hidden'
  if (!status.value.steps.products) return 'welcome'
  return [...MAIN, ...EXTRA].every(s => status.value!.steps[s]) ? 'hidden' : 'checklist'
})
const done = computed(() => status.value ? [...MAIN, ...EXTRA].filter(s => status.value!.steps[s]).length : 0)

async function load() {
  try { status.value = (await api.get('/onboarding', { params: { business_id: bid.value } })).data }
  catch { status.value = null }
  emit('state', mode.value)
}
onMounted(load)

async function dismiss() {
  await api.post('/onboarding/dismiss', { business_id: bid.value })
  if (status.value) status.value.dismissed = true
  emit('state', 'hidden')
}

async function tryDemo() {
  creatingDemo.value = true; error.value = ''
  try {
    const { data } = await api.post('/onboarding/demo', null, { timeout: 120_000 })
    await auth.fetchUser()
    auth.switchBusiness(data.business_id)   // AppLayout re-mounts the page for the new business
  } catch (e) {
    error.value = apiErrorMessage(e) || t('common.error')
  } finally { creatingDemo.value = false }
}

function go(step: Step) {
  if (step === 'products') showImport.value = true
  else router.push(LINKS[step])
}
</script>

<template>
  <!-- First run: nothing in the business yet -->
  <section v-if="mode === 'welcome'" class="welcome">
    <p class="eyebrow">{{ t('onboarding.eyebrow') }}</p>
    <h1>{{ t('onboarding.title', { name: auth.user?.full_name?.split(' ')[0] ?? '' }) }}</h1>
    <p class="lead">{{ t('onboarding.lead') }}</p>

    <ol class="steps">
      <li v-for="(s, i) in MAIN" :key="s" :class="{ done: status!.steps[s] }">
        <span class="n">{{ status!.steps[s] ? '✓' : i + 1 }}</span>
        <div>
          <h3>{{ t(`onboarding.steps.${s}.title`) }}</h3>
          <p>{{ t(`onboarding.steps.${s}.body`) }}</p>
        </div>
        <button class="ui-btn ui-btn--sm" :class="i === 0 ? 'ui-btn--primary' : 'ui-btn--ghost'" @click="go(s)">
          {{ t(`onboarding.steps.${s}.cta`) }}
        </button>
      </li>
    </ol>

    <div class="demo">
      <div>
        <strong>{{ t('onboarding.demo.title') }}</strong>
        <p>{{ t('onboarding.demo.body') }}</p>
      </div>
      <button class="ui-btn ui-btn--ghost" :disabled="creatingDemo" @click="tryDemo">
        <span v-if="creatingDemo" class="ui-spinner" />{{ creatingDemo ? t('onboarding.demo.creating') : t('onboarding.demo.cta') }}
      </button>
    </div>
    <p v-if="error" class="ui-alert ui-alert--error">{{ error }}</p>
    <button class="skip" @click="dismiss">{{ t('onboarding.skip') }}</button>
  </section>

  <!-- Getting there: compact checklist -->
  <section v-else-if="mode === 'checklist'" class="checklist ui-card">
    <div class="head">
      <div>
        <p class="ui-card-title">{{ t('onboarding.checklistTitle') }}</p>
        <p class="ui-card-sub">{{ t('onboarding.progress', { done, total: MAIN.length + EXTRA.length }) }}</p>
      </div>
      <button class="ui-icon-btn" :aria-label="t('onboarding.hide')" :title="t('onboarding.hide')" @click="dismiss">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
      </button>
    </div>
    <div class="items">
      <button v-for="s in [...MAIN, ...EXTRA]" :key="s" class="item" :class="{ done: status!.steps[s] }" @click="go(s)">
        <span class="tick">{{ status!.steps[s] ? '✓' : '' }}</span>
        {{ t(`onboarding.steps.${s}.short`) }}
        <span v-if="EXTRA.includes(s)" class="ui-muted opt">{{ t('common.optional') }}</span>
      </button>
    </div>
  </section>

  <ImportProductsModal v-if="showImport" :business-id="bid" @close="showImport = false; load()" @imported="load" />
</template>

<style scoped>
.welcome { max-width: 760px; margin: 2rem auto; padding: 0 1rem; }
.eyebrow { color: var(--accent); font-weight: 600; font-size: .85rem; }
h1 { margin-top: .4rem; font-size: clamp(1.6rem, 3vw, 2.1rem); font-weight: 660; letter-spacing: -.03em; }
.lead { margin-top: .5rem; color: var(--text-sub); font-size: 1rem; max-width: 36rem; }
.steps { list-style: none; margin-top: 1.75rem; display: grid; gap: .6rem; }
.steps li {
  display: grid; grid-template-columns: 36px 1fr auto; gap: 1rem; align-items: center;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 1rem 1.1rem;
}
.steps li.done { opacity: .65; }
.n { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; font-weight: 650;
  background: var(--accent-soft); color: var(--accent); }
.steps h3 { font-size: .98rem; font-weight: 620; }
.steps p { font-size: .87rem; color: var(--text-sub); margin-top: .15rem; }
@media (max-width: 560px) { .steps li { grid-template-columns: 32px 1fr; } .steps li .ui-btn { grid-column: 2; justify-self: start; } }
.demo { margin-top: 1.25rem; display: flex; gap: 1rem; align-items: center; justify-content: space-between;
  padding: 1rem 1.1rem; border-radius: var(--r-lg); border: 1px dashed var(--border-mid); flex-wrap: wrap; }
.demo p { font-size: .87rem; color: var(--text-sub); margin-top: .15rem; max-width: 32rem; }
.skip { margin-top: 1.25rem; background: none; color: var(--text-muted); font-size: .85rem; cursor: pointer; text-decoration: underline; }

.checklist { margin: 1.5rem 2rem 0; }
@media (max-width: 640px) { .checklist { margin: 1rem 1rem 0; } }
.head { display: flex; justify-content: space-between; align-items: flex-start; padding: 1rem 1.25rem .5rem; }
.items { display: flex; flex-wrap: wrap; gap: .5rem; padding: .25rem 1.25rem 1rem; }
.item { display: inline-flex; align-items: center; gap: .45rem; padding: .4rem .75rem; border-radius: 99px;
  border: 1px solid var(--border); background: var(--bg); font-size: .85rem; color: var(--text); cursor: pointer; }
.item:hover { border-color: var(--accent-line); }
.item.done { color: var(--text-muted); text-decoration: line-through; }
.tick { width: 16px; height: 16px; border-radius: 50%; border: 1.5px solid var(--border-mid); display: grid; place-items: center;
  font-size: .65rem; color: var(--accent-text); }
.item.done .tick { background: var(--accent); border-color: var(--accent); }
.opt { font-size: .75rem; }
</style>
