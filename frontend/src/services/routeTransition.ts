import { ref } from 'vue'

/**
 * One-shot name for the next route transition (App.vue's <router-view>).
 * Empty means "no animation", so ordinary navigation stays instant; the
 * planning overlay sets 'trip-reveal' right before it opens the result page.
 */
export const routeTransition = ref('')

export function playNextRouteTransition(name: string) {
  routeTransition.value = name
}

export function clearRouteTransition() {
  routeTransition.value = ''
}
