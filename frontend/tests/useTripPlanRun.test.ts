import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { StreamError, type StreamEvent, type StreamOptions } from '@/services/api'
import { HANDOFF_DELAY_MS, TICK_MS, useTripPlanRun, type TripPlanRunDeps } from '@/composables/useTripPlanRun'
import { stepStates } from '@/services/tripProgress'
import type { TripFormData, TripPlan } from '@/types'
import { samplePlan, sampleRequest } from './fixtures'

/** A stream whose events and completion are driven by the test. */
function controllableStream() {
  const calls: {
    request: TripFormData
    emit: (event: StreamEvent) => void
    resolve: (plan: TripPlan) => void
    reject: (error: unknown) => void
    options: StreamOptions
  }[] = []
  const stream = vi.fn((request: TripFormData, onEvent: (e: StreamEvent) => void, options: StreamOptions) => {
    return new Promise<TripPlan>((resolve, reject) => {
      calls.push({ request, emit: onEvent, resolve, reject, options })
    })
  })
  return { stream, calls }
}

const progress = (phase: string, attempt?: number): StreamEvent => ({ type: 'progress', phase, attempt })
const result = (status: string): StreamEvent => ({ type: 'result', success: true, status, message: status, data: samplePlan })
const flush = () => new Promise<void>((r) => queueMicrotask(r)).then(() => Promise.resolve())

function setup(extra: Partial<TripPlanRunDeps> = {}) {
  const { stream, calls } = controllableStream()
  const order: string[] = []
  const deps = {
    stream,
    savePlan: vi.fn(() => order.push('savePlan')),
    saveRequest: vi.fn(() => order.push('saveRequest')),
    saveMeta: vi.fn(() => order.push('saveMeta')),
    navigate: vi.fn(() => order.push('navigate')),
    onSettled: vi.fn(),
    onFailed: vi.fn(),
    now: () => Date.now(),
    ...extra
  }
  const run = useTripPlanRun(deps)
  return { run, deps, calls, order }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-12T10:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useTripPlanRun', () => {
  it('advances only on real events; waiting time alone never stamps or finishes', async () => {
    const { run, calls, deps } = setup()
    void run.submit(sampleRequest)
    calls[0].emit(progress('collecting_attractions'))

    await vi.advanceTimersByTimeAsync(10 * 60_000)
    expect(run.state.value.status).toBe('running')
    expect(stepStates(run.state.value)).toEqual(['active', 'pending', 'pending', 'pending'])
    expect(deps.savePlan).not.toHaveBeenCalled()
    expect(deps.navigate).not.toHaveBeenCalled()
    // The clock still shows real elapsed time.
    expect(run.clock.value - run.state.value.startedAt!).toBe(10 * 60_000)
  })

  it('saves plan → request → meta once, then navigates once after a valid result', async () => {
    const { run, calls, deps, order } = setup()
    const pending = run.submit(sampleRequest)
    const c = calls[0]
    for (const e of [progress('collecting_weather'), progress('building_query'), progress('generating', 1), progress('reranking')]) c.emit(e)
    c.emit(result('llm_success'))
    c.emit(result('fallback_success')) // duplicate terminal frame
    expect(deps.savePlan).not.toHaveBeenCalled() // nothing saved from the callback

    c.resolve(samplePlan)
    await pending
    expect(order).toEqual(['savePlan', 'saveRequest', 'saveMeta'])
    expect(deps.saveMeta).toHaveBeenCalledWith({ status: 'llm_success', message: 'llm_success', switchedModel: false })
    expect(run.state.value.status).toBe('success')
    expect(deps.onSettled).toHaveBeenCalledWith('success')

    await vi.advanceTimersByTimeAsync(HANDOFF_DELAY_MS)
    expect(order).toEqual(['savePlan', 'saveRequest', 'saveMeta', 'navigate'])
    await vi.advanceTimersByTimeAsync(5_000)
    expect(deps.navigate).toHaveBeenCalledTimes(1)
  })

  it('treats fallback_success as the basic plan and a switched-model success as normal', async () => {
    const a = setup()
    let pending = a.run.submit(sampleRequest)
    a.calls[0].emit(progress('generating', 1))
    a.calls[0].emit(progress('fallback'))
    expect(a.run.state.value.status).toBe('running')
    a.calls[0].emit(result('fallback_success'))
    a.calls[0].resolve(samplePlan)
    await pending
    expect(a.run.state.value.status).toBe('fallback')
    expect(a.deps.onSettled).toHaveBeenCalledWith('fallback')
    expect(stepStates(a.run.state.value)[3]).toBe('skipped')

    const b = setup()
    pending = b.run.submit(sampleRequest)
    for (const e of [progress('generating', 2), progress('switching_model'), progress('generating', 1), progress('reranking'), result('llm_success')]) {
      b.calls[0].emit(e)
    }
    b.calls[0].resolve(samplePlan)
    await pending
    expect(b.run.state.value.status).toBe('success')
    expect(b.deps.saveMeta).toHaveBeenCalledWith({ status: 'llm_success', message: 'llm_success', switchedModel: true })
  })

  it.each([
    ['http', new StreamError('http', 'Stream request failed: 500', 500)],
    ['sse', new StreamError('sse', 'LLM down')],
    ['failed', new StreamError('failed', 'no plan')],
    ['no_result', new StreamError('no_result', 'ended')],
    ['network', new TypeError('Failed to fetch')]
  ])('enters a persistent error state on %s without saving or navigating', async (kind, error) => {
    const { run, calls, deps } = setup()
    const pending = run.submit(sampleRequest)
    calls[0].emit(progress('building_query'))
    calls[0].reject(error)
    await pending

    expect(run.state.value.status).toBe('error')
    expect(run.state.value.errorKind).toBe(kind)
    expect(deps.savePlan).not.toHaveBeenCalled()
    expect(deps.saveRequest).not.toHaveBeenCalled()
    expect(deps.saveMeta).not.toHaveBeenCalled()
    // The old Home cleared everything after 600ms; the error must stay put.
    await vi.advanceTimersByTimeAsync(60_000)
    expect(run.state.value.status).toBe('error')
    expect(deps.navigate).not.toHaveBeenCalled()
    expect(deps.stream).toHaveBeenCalledTimes(1) // no automatic retry
    expect(run.request.value).toEqual(sampleRequest)
  })

  it('ignores duplicate submits while running or handing off', async () => {
    const { run, calls, deps } = setup()
    const pending = run.submit(sampleRequest)
    void run.submit(sampleRequest)
    void run.submit(sampleRequest)
    expect(deps.stream).toHaveBeenCalledTimes(1)
    calls[0].emit(result('llm_success'))
    calls[0].resolve(samplePlan)
    await pending
    void run.submit(sampleRequest) // during the hand-off pause
    expect(deps.stream).toHaveBeenCalledTimes(1)
  })

  it('an explicit retry starts a fresh run that stale events and promises cannot touch', async () => {
    const { run, calls, deps } = setup()
    const first = run.submit(sampleRequest)
    calls[0].emit(progress('generating', 3))
    calls[0].reject(new StreamError('sse', 'x'))
    await first
    expect(run.state.value.status).toBe('error')

    await vi.advanceTimersByTimeAsync(7_000)
    const retry = run.submit({ ...sampleRequest, city: '苏州市' })
    expect(deps.stream).toHaveBeenCalledTimes(2)
    expect(run.state.value.runId).toBe(2)
    expect(run.state.value.stage).toBe(0)
    expect(run.clock.value - run.state.value.startedAt!).toBe(0)

    // The first run's callback fires late: ignored.
    calls[0].emit(progress('reranking'))
    calls[0].emit(result('fallback_success'))
    expect(run.state.value.stage).toBe(0)

    calls[1].emit(progress('building_query'))
    calls[1].emit(result('llm_success'))
    calls[1].resolve(samplePlan)
    await retry
    expect(run.state.value.status).toBe('success')
    expect(deps.saveRequest).toHaveBeenCalledTimes(1)
    expect(deps.saveRequest).toHaveBeenCalledWith(expect.objectContaining({ city: '苏州市' }))
    expect(deps.saveMeta).toHaveBeenCalledWith(expect.objectContaining({ status: 'llm_success' }))
  })

  it('keeps at most one ticker and releases it on every terminal state', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval')
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval')
    const { run, calls } = setup()

    const p1 = run.submit(sampleRequest)
    expect(run.hasTicker()).toBe(true)
    calls[0].reject(new StreamError('no_result', 'x'))
    await p1
    expect(run.hasTicker()).toBe(false)

    const p2 = run.submit(sampleRequest)
    calls[1].emit(result('llm_success'))
    calls[1].resolve(samplePlan)
    await p2
    expect(run.hasTicker()).toBe(false)
    expect(setIntervalSpy).toHaveBeenCalledTimes(2)
    expect(clearIntervalSpy.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(setIntervalSpy.mock.calls.every(([, ms]) => ms === TICK_MS)).toBe(true)
  })

  it('freezes elapsed time at the terminal moment and stays accurate across a hidden tab', async () => {
    const { run, calls } = setup()
    const pending = run.submit(sampleRequest)
    // Simulate a throttled background tab: the clock jumps without interval ticks.
    vi.setSystemTime(Date.now() + 95_000)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(run.clock.value - run.state.value.startedAt!).toBe(95_000)

    calls[0].reject(new StreamError('sse', 'x'))
    await pending
    await vi.advanceTimersByTimeAsync(30_000)
    expect(run.state.value.finishedAt! - run.state.value.startedAt!).toBe(95_000)
  })

  it('is safe on unmount: no late navigation, no saves, request aborted locally', async () => {
    const { stream, calls } = controllableStream()
    const navigate = vi.fn()
    const savePlan = vi.fn()
    let api!: ReturnType<typeof useTripPlanRun>
    const Host = defineComponent({
      setup() {
        api = useTripPlanRun({ stream, navigate, savePlan, saveRequest: vi.fn(), saveMeta: vi.fn() })
        return () => h('div')
      }
    })

    // Case 1: unmount while running.
    let wrapper = mount(Host)
    const p1 = api.submit(sampleRequest)
    wrapper.unmount()
    expect(calls[0].options.signal?.aborted).toBe(true)
    expect(api.hasTicker()).toBe(false)
    calls[0].emit(result('llm_success'))
    calls[0].resolve(samplePlan)
    await p1
    expect(savePlan).not.toHaveBeenCalled()

    // Case 2: unmount during the hand-off pause.
    wrapper = mount(Host)
    const p2 = api.submit(sampleRequest)
    calls[1].emit(result('llm_success'))
    calls[1].resolve(samplePlan)
    await p2
    expect(api.hasPendingHandoff()).toBe(true)
    wrapper.unmount()
    expect(api.hasPendingHandoff()).toBe(false)
    await vi.advanceTimersByTimeAsync(HANDOFF_DELAY_MS * 4)
    expect(navigate).not.toHaveBeenCalled()
  })

  it('does not navigate if the plan resolves after the run was superseded', async () => {
    const { run, calls, deps } = setup()
    const p1 = run.submit(sampleRequest)
    run.dispose()
    calls[0].resolve(samplePlan)
    await p1
    await flush()
    await vi.advanceTimersByTimeAsync(HANDOFF_DELAY_MS)
    expect(deps.savePlan).not.toHaveBeenCalled()
    expect(deps.navigate).not.toHaveBeenCalled()
  })
})
