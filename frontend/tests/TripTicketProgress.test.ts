import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TripTicketProgress from '@/components/home/TripTicketProgress.vue'
import { setLocale } from '@/i18n'
import type { StreamEvent } from '@/services/api'
import { QUIET_AFTER_MS, initialProgress, reduceProgress, type ProgressAction, type ProgressState } from '@/services/tripProgress'

const T0 = 1_000_000
const progress = (phase: string, attempt?: number): StreamEvent => ({ type: 'progress', phase, attempt })

function build(events: StreamEvent[], end?: Omit<ProgressAction & { type: 'complete' | 'fail' }, 'runId'>): ProgressState {
  let s = reduceProgress(initialProgress(), { type: 'start', runId: 1, now: T0 })
  events.forEach((event, i) => {
    s = reduceProgress(s, { type: 'event', runId: 1, event, now: T0 + (i + 1) * 1000 })
  })
  if (end) s = reduceProgress(s, { ...end, runId: 1 } as ProgressAction)
  return s
}

const summary = ['杭州市', '11月20日 – 11月21日', '2 天', '2 人']
const states = (w: ReturnType<typeof mount>) => w.findAll('.ticket-checkpoint').map((li) => li.attributes('data-state'))

afterEach(() => setLocale('zh'))

describe('TripTicketProgress', () => {
  it('renders the request summary, the active step and the real elapsed time', () => {
    const state = build([progress('building_query')])
    const w = mount(TripTicketProgress, { props: { state, now: T0 + 65_000, summary } })

    expect(w.find('.ticket-summary').text()).toContain('杭州市')
    expect(w.find('.ticket-summary').text()).toContain('2 天')
    expect(w.find('.ticket-title').text()).toBe('正在整理路线')
    expect(states(w)).toEqual(['complete', 'active', 'pending', 'pending'])
    const current = w.findAll('[aria-current="step"]')
    expect(current).toHaveLength(1)
    expect(current[0].text()).toContain('整理路线')
    expect(w.find('.ticket-elapsed').text()).toBe('已等待 01:05')
    // No fake percentages, countdowns or demo identifiers.
    expect(w.text()).not.toMatch(/%|剩余|航班|预订号/)
  })

  it('keeps the elapsed clock out of the live region and does not re-create seals on ticks', async () => {
    const state = build([progress('generating', 1)])
    const w = mount(TripTicketProgress, { props: { state, now: T0 + 5_000, summary } })
    const live = w.find('[role="status"]')
    expect(live.attributes('aria-live')).toBe('polite')
    expect(live.text()).toBe('正在编排行程')
    expect(w.find('[aria-busy]').exists()).toBe(false)
    const sealBefore = w.findAll('.ticket-seal')[1].element

    await w.setProps({ now: T0 + 6_000 })
    expect(live.text()).toBe('正在编排行程')
    expect(w.find('.ticket-elapsed').text()).toBe('已等待 00:06')
    expect(w.findAll('.ticket-seal')[1].element).toBe(sealBefore)
  })

  it('uses neutral copy for more candidates and for a model switch', async () => {
    const w = mount(TripTicketProgress, { props: { state: build([progress('generating', 2)]), now: T0 } })
    expect(w.find('.ticket-detail').text()).toBe('继续编排行程，可能会比较多个候选方案。')
    expect(w.text()).not.toMatch(/失败|重试/)

    await w.setProps({ state: build([progress('generating', 2), progress('switching_model')]) })
    expect(w.find('.ticket-detail').text()).toBe('正在尝试另一种编排方式。')
    expect(states(w)).toEqual(['complete', 'complete', 'active', 'pending'])
  })

  it('shows a neutral quiet status during a long silent wait without moving steps', () => {
    const state = build([progress('generating', 1)])
    const w = mount(TripTicketProgress, { props: { state, now: state.lastEventAt! + QUIET_AFTER_MS } })
    expect(w.find('.ticket-status').text()).toBe('仍在处理，请稍候')
    expect(states(w)).toEqual(['complete', 'complete', 'active', 'pending'])
  })

  it('shows a basic-plan preparation while progress:fallback is running', () => {
    const w = mount(TripTicketProgress, { props: { state: build([progress('generating', 1), progress('fallback')]), now: T0 } })
    expect(w.find('.ticket-title').text()).toBe('正在准备基础行程')
    expect(w.attributes('data-status')).toBe('running')
    expect(w.find('[aria-current="step"] .ticket-seal-state').text()).toBe('基础方案')
  })

  it('settles success with all seals complete and no active scan', () => {
    const state = build([progress('reranking')], { type: 'complete', fallback: false, now: T0 + 42_000 })
    const w = mount(TripTicketProgress, { props: { state, now: T0 + 99_000 } })
    expect(states(w)).toEqual(['complete', 'complete', 'complete', 'complete'])
    expect(w.find('[aria-current="step"]').exists()).toBe(false)
    expect(w.find('.ticket-title').text()).toBe('行程已准备好')
    expect(w.find('.ticket-elapsed').text()).toBe('用时 00:42')
  })

  it('settles a fallback result as a basic plan with review not run', () => {
    const state = build([progress('generating', 1), progress('fallback')], { type: 'complete', fallback: true, now: T0 + 9_000 })
    const w = mount(TripTicketProgress, { props: { state, now: T0 + 9_000 } })
    expect(w.attributes('data-status')).toBe('fallback')
    expect(w.find('.ticket-title').text()).toBe('基础行程已就绪')
    expect(states(w)).toEqual(['complete', 'complete', 'complete', 'skipped'])
    expect(w.findAll('.ticket-checkpoint')[3].text()).toContain('未进行')
  })

  it('renders errors as an alert with a manual retry', async () => {
    const state = build([progress('building_query')], { type: 'fail', kind: 'http', message: 'x', status: 502, now: T0 + 3_000 })
    const w = mount(TripTicketProgress, { props: { state, now: T0 + 3_000 } })
    const alert = w.find('[role="alert"]')
    expect(alert.text()).toContain('HTTP 502')
    expect(alert.text()).toContain('表单内容已保留')
    expect(w.find('[role="status"]').text()).toBe('')
    expect(w.find('.ticket-edit').text()).toBe('返回修改')
    expect(states(w)).toEqual(['complete', 'error', 'pending', 'pending'])
    await w.find('.ticket-retry').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
    await w.find('.ticket-edit').trigger('click')
    expect(w.emitted('edit')).toHaveLength(1)
  })

  it('switches every string to English', () => {
    setLocale('en')
    const state = build([progress('building_query'), progress('generating', 1)])
    const w = mount(TripTicketProgress, { props: { state, now: T0 + 3_000, summary: ['Hangzhou', 'Nov 20 – Nov 21', '2 days'] } })
    expect(w.find('.ticket-title').text()).toBe('Arranging your days')
    expect(w.find('.ticket-elapsed').text()).toBe('Waiting 00:03')
    expect(w.findAll('.ticket-checkpoint strong').map((s) => s.text())).toEqual(['Find info', 'Shape route', 'Arrange days', 'Check plan'])
    expect(w.text()).not.toMatch(/[一-鿿]/)
  })

  it('announces the English terminal state without Chinese punctuation', () => {
    setLocale('en')
    const state = build([progress('reranking')], { type: 'complete', fallback: false, now: T0 + 1_000 })
    const w = mount(TripTicketProgress, { props: { state, now: T0 + 1_000 } })
    expect(w.find('[role="status"]').text()).toBe('Your trip is ready. Opening your itinerary.')
  })
})
