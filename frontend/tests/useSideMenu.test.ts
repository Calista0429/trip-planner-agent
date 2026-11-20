import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { SIDEBAR_COLLAPSED_KEY, useSideMenu } from '@/composables/useSideMenu'
import { installMatchMedia } from './helpers/matchMedia'

function run(mobile = false) {
  const media = installMatchMedia(mobile)
  const scope = effectScope()
  const menu = scope.run(() => useSideMenu())!
  return { media, scope, menu }
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('useSideMenu', () => {
  it('defaults to expanded and persists the collapse preference', () => {
    const { menu, scope } = run()
    expect(menu.collapsed.value).toBe(false)
    menu.toggleCollapsed()
    expect(menu.collapsed.value).toBe(true)
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_KEY)).toBe('true')
    menu.toggleCollapsed()
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_KEY)).toBe('false')
    scope.stop()
  })

  it.each([
    ['true', true],
    ['false', false],
    ['1', false],
    ['{"x":1}', false]
  ])('reads stored value %s as collapsed=%s', (stored, expected) => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, stored)
    const { menu, scope } = run()
    expect(menu.collapsed.value).toBe(expected)
    scope.stop()
  })

  it('keeps working when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    const { menu, scope } = run()
    expect(menu.collapsed.value).toBe(false)
    menu.toggleCollapsed()
    expect(menu.collapsed.value).toBe(true)
    scope.stop()
  })

  it('tracks the 760px breakpoint; the drawer only opens on mobile', () => {
    const { menu, media, scope } = run(false)
    expect(menu.isMobile.value).toBe(false)
    menu.openDrawer()
    expect(menu.drawerOpen.value).toBe(false)

    media.setMobile(true)
    expect(menu.isMobile.value).toBe(true)
    menu.openDrawer()
    expect(menu.drawerOpen.value).toBe(true)
    menu.closeDrawer()
    expect(menu.drawerOpen.value).toBe(false)
    scope.stop()
  })

  it('closes the drawer when crossing the breakpoint without touching the collapse preference', () => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, 'true')
    const { menu, media, scope } = run(true)
    menu.openDrawer()
    media.setMobile(false)
    expect(menu.drawerOpen.value).toBe(false)
    expect(menu.collapsed.value).toBe(true)
    expect(localStorage.getItem(SIDEBAR_COLLAPSED_KEY)).toBe('true')
    scope.stop()
  })

  it('never restores an open drawer and removes its listener on dispose', () => {
    const first = run(true)
    first.menu.openDrawer()
    first.scope.stop()
    expect(first.media.mobileListeners()).toBe(0)

    const second = run(true)
    expect(second.menu.drawerOpen.value).toBe(false)
    second.scope.stop()
  })
})
