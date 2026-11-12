import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TripTransitionOverlay from '@/components/home/TripTransitionOverlay.vue'
import { initialProgress, reduceProgress, type ProgressState } from '@/services/tripProgress'

const running = (): ProgressState => reduceProgress(initialProgress(), { type: 'start', runId: 1, now: 0 })
const failed = (): ProgressState =>
  reduceProgress(running(), { type: 'fail', runId: 1, kind: 'network', message: 'x', now: 1000 })

afterEach(() => {
  document.body.innerHTML = ''
  document.documentElement.style.overflow = ''
})

describe('TripTransitionOverlay', () => {
  it('locks page scroll while open and restores it when closed or unmounted', async () => {
    document.documentElement.style.overflow = 'scroll'
    const w = mount(TripTransitionOverlay, { props: { open: true, state: running(), now: 0 }, attachTo: document.body })
    expect(document.documentElement.style.overflow).toBe('hidden')
    await w.setProps({ open: false })
    expect(document.documentElement.style.overflow).toBe('scroll')
    await w.setProps({ open: true })
    w.unmount()
    expect(document.documentElement.style.overflow).toBe('scroll')
  })

  it('takes focus on open and keeps Tab inside the dialog', async () => {
    const w = mount(TripTransitionOverlay, { props: { open: true, state: running(), now: 0 }, attachTo: document.body })
    await w.vm.$nextTick()
    const dialog = w.find('[role="dialog"]')
    expect(document.activeElement).toBe(dialog.element)
    await dialog.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(dialog.element)
    w.unmount()
  })

  it('cannot be dismissed with Escape while running, only after an error', async () => {
    const w = mount(TripTransitionOverlay, { props: { open: true, state: running(), now: 0 }, attachTo: document.body })
    await w.find('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toBeUndefined()

    await w.setProps({ state: failed() })
    await w.vm.$nextTick()
    expect(document.activeElement?.classList.contains('ticket-retry')).toBe(true)
    await w.find('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toHaveLength(1)

    // Tab wraps between the two error actions.
    const retry = w.find('.ticket-retry').element as HTMLElement
    const edit = w.find('.ticket-edit').element as HTMLElement
    retry.focus()
    await w.find('[role="dialog"]').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(edit)
    w.unmount()
  })
})
