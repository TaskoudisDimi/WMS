<script setup lang="ts">
import Sidebar from '@/components/Sidebar.vue'
import Topbar  from '@/components/Topbar.vue'
import { useAuthStore } from '@/stores/auth'
import DemoBanner from '@/components/onboarding/DemoBanner.vue'

const auth = useAuthStore()
</script>

<template>
  <div class="layout">
    <Sidebar />
    <div class="main">
      <DemoBanner />
      <Topbar />
      <div class="content">
        <router-view :key="auth.currentBusiness?.id" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  width: 100%;
  height: 100%;
  background: var(--bg);
  overflow: hidden;
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.content {
  flex: 1;
  overflow-y: auto;
}
</style>
