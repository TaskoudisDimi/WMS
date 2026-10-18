import { onBeforeUnmount, onMounted, ref } from 'vue'

/** navigator.onLine as a ref (true when the device thinks it has a connection). */
export function useOnline() {
  const online = ref(navigator.onLine)
  const update = () => { online.value = navigator.onLine }
  onMounted(() => { window.addEventListener('online', update); window.addEventListener('offline', update) })
  onBeforeUnmount(() => { window.removeEventListener('online', update); window.removeEventListener('offline', update) })
  return online
}

interface InstallPromptEvent extends Event { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> }
let deferred: InstallPromptEvent | null = null
const canInstall = ref(false)
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferred = e as InstallPromptEvent; canInstall.value = true })
window.addEventListener('appinstalled', () => { deferred = null; canInstall.value = false })

/** "Install app" (Chrome/Edge/Android). iOS installs via Share → Add to Home Screen. */
export function useInstall() {
  const install = async () => {
    if (!deferred) return
    await deferred.prompt()
    await deferred.userChoice
    deferred = null
    canInstall.value = false
  }
  return { canInstall, install }
}
