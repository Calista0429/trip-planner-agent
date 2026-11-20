import { getCurrentScope, onScopeDispose, ref } from 'vue'

export const SIDEBAR_COLLAPSED_KEY = 'tripPlanner.sidebarCollapsed.v1'
export const MOBILE_QUERY = '(max-width: 760px)'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  } catch {
    return false
  }
}

function writeCollapsed(value: boolean) {
  try {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, value ? 'true' : 'false')
  } catch {
    // Private mode / quota: the toggle still works for this visit.
  }
}

/**
 * Desktop collapse preference (persisted) and the mobile drawer (memory only;
 * it never reopens on its own). Crossing the 760px breakpoint closes the
 * drawer and leaves the desktop preference alone.
 */
export function useSideMenu() {
  const collapsed = ref(readCollapsed())
  const query = typeof window !== 'undefined' ? window.matchMedia?.(MOBILE_QUERY) : undefined
  const isMobile = ref(!!query?.matches)
  const drawerOpen = ref(false)

  const onChange = (event: MediaQueryListEvent) => {
    isMobile.value = event.matches
    drawerOpen.value = false
  }

  if (query) {
    // Safari < 14 only has the deprecated addListener.
    if (query.addEventListener) query.addEventListener('change', onChange)
    else query.addListener?.(onChange)
  }

  if (getCurrentScope()) {
    onScopeDispose(() => {
      if (!query) return
      if (query.removeEventListener) query.removeEventListener('change', onChange)
      else query.removeListener?.(onChange)
    })
  }

  function toggleCollapsed() {
    collapsed.value = !collapsed.value
    writeCollapsed(collapsed.value)
  }

  function openDrawer() {
    if (isMobile.value) drawerOpen.value = true
  }

  function closeDrawer() {
    drawerOpen.value = false
  }

  return { collapsed, isMobile, drawerOpen, toggleCollapsed, openDrawer, closeDrawer }
}
