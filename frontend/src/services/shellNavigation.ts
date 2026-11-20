import { getCurrentInstance, inject, onBeforeUnmount, watch, type InjectionKey, type Ref } from 'vue'

/**
 * Set to true by a page while leaving it would break work in progress
 * (plan generation, export). App.vue provides it and makes the header,
 * side menu and footer non-interactive while it is true.
 */
export const SHELL_NAVIGATION_BLOCKED: InjectionKey<Ref<boolean>> = Symbol('shellNavigationBlocked')

/**
 * Mirror a page's busy flag into the shell lock, and release it on unmount.
 * Pages mounted without App (unit tests) simply get no lock.
 */
export function useShellNavigationLock(source: () => boolean) {
  const blocked = inject(SHELL_NAVIGATION_BLOCKED, null)
  if (!blocked) return
  watch(source, value => (blocked.value = value), { immediate: true })
  if (getCurrentInstance()) onBeforeUnmount(() => (blocked.value = false))
}
