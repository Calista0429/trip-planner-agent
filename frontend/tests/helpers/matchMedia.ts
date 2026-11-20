/**
 * A controllable window.matchMedia for jsdom. `setMobile(true)` flips every
 * `(max-width: 760px)` query and notifies its listeners like a real resize.
 */
type Listener = (event: { matches: boolean; media: string }) => void

export function installMatchMedia(initialMobile = false) {
  let mobile = initialMobile
  const listeners = new Set<{ media: string; fn: Listener }>()
  const matches = (media: string) => (media.includes('max-width: 760px') ? mobile : false)

  window.matchMedia = ((media: string) => ({
    get matches() {
      return matches(media)
    },
    media,
    onchange: null,
    addListener: (fn: Listener) => listeners.add({ media, fn }),
    removeListener: (fn: Listener) => listeners.forEach(l => l.fn === fn && listeners.delete(l)),
    addEventListener: (_: string, fn: Listener) => listeners.add({ media, fn }),
    removeEventListener: (_: string, fn: Listener) => listeners.forEach(l => l.fn === fn && listeners.delete(l)),
    dispatchEvent: () => false
  })) as unknown as typeof window.matchMedia

  return {
    setMobile(next: boolean) {
      mobile = next
      listeners.forEach(l => l.fn({ matches: matches(l.media), media: l.media }))
    },
    /** Listeners still registered for the mobile breakpoint. */
    mobileListeners: () => [...listeners].filter(l => l.media.includes('max-width: 760px')).length
  }
}
