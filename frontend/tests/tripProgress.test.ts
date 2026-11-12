import { describe, expect, it } from 'vitest'
import type { StreamEvent } from '@/services/api'
import {
  QUIET_AFTER_MS,
  elapsedMs,
  formatElapsed,
  initialProgress,
  isQuiet,
  reduceProgress,
  stepStates,
  type ProgressAction,
  type ProgressState
} from '@/services/tripProgress'

const RUN = 1
const progress = (phase: string, attempt?: number): StreamEvent => ({ type: 'progress', phase, attempt })

function run(events: StreamEvent[], start = 0): ProgressState {
  let state = reduceProgress(initialProgress(), { type: 'start', runId: RUN, now: start })
  events.forEach((event, i) => {
    state = reduceProgress(state, { type: 'event', runId: RUN, event, now: start + (i + 1) * 1000 })
  })
  return state
}

describe('reduceProgress', () => {
  it('walks the normal phase sequence through the four steps', () => {
    let state = run([])
    expect(state.status).toBe('running')
    expect(stepStates(state)).toEqual(['active', 'pending', 'pending', 'pending'])

    state = run([progress('collecting_attractions'), progress('collecting_weather'), progress('collecting_hotels')])
    // One or all collectors returning does not finish the research step by itself.
    expect(stepStates(state)).toEqual(['active', 'pending', 'pending', 'pending'])

    state = run([progress('collecting_weather'), progress('collecting_context'), progress('building_query')])
    expect(stepStates(state)).toEqual(['complete', 'active', 'pending', 'pending'])

    state = run([progress('building_query'), progress('generating', 1)])
    expect(stepStates(state)).toEqual(['complete', 'complete', 'active', 'pending'])

    state = run([progress('building_query'), progress('generating', 1), progress('reranking')])
    expect(stepStates(state)).toEqual(['complete', 'complete', 'complete', 'active'])
    // reranking is still a running event; only a valid result completes the run.
    expect(state.status).toBe('running')

    state = reduceProgress(state, { type: 'complete', runId: RUN, fallback: false, now: 99_000 })
    expect(state.status).toBe('success')
    expect(stepStates(state)).toEqual(['complete', 'complete', 'complete', 'complete'])
  })

  it('accepts collectors in any order and ignores duplicates, late low phases and unknown phases', () => {
    const state = run([
      progress('collecting_hotels'),
      progress('collecting_hotels'),
      progress('collecting_attractions'),
      progress('building_query'),
      progress('collecting_weather'), // late lower-rank event
      progress('collecting_context'),
      progress('critic_review'), // unknown phase
      { type: 'progress' } // no phase
    ])
    expect(state.stage).toBe(1)
    expect(state.phase).toBe('building_query')
    expect(stepStates(state)).toEqual(['complete', 'active', 'pending', 'pending'])
  })

  it('keeps copy monotonic within the research step', () => {
    const state = run([progress('collecting_context'), progress('collecting_weather')])
    expect(state.phase).toBe('collecting_context')
  })

  it('treats growing attempts as normal candidates and keeps progress across a model switch', () => {
    let state = run([progress('building_query'), progress('generating', 1), progress('generating', 2), progress('generating', 3)])
    expect(state.attempt).toBe(3)
    expect(state.status).toBe('running')
    const startedAt = state.startedAt

    state = reduceProgress(state, { type: 'event', runId: RUN, event: progress('switching_model'), now: 10_000 })
    expect(state.switchedModel).toBe(true)
    expect(state.attempt).toBeNull()
    expect(state.stage).toBe(2)

    state = reduceProgress(state, { type: 'event', runId: RUN, event: progress('generating', 1), now: 11_000 })
    expect(state.attempt).toBe(1)
    expect(state.stage).toBe(2)
    expect(state.startedAt).toBe(startedAt)
    expect(stepStates(state)).toEqual(['complete', 'complete', 'active', 'pending'])
  })

  it('keeps progress:fallback running and shows review as skipped on a fallback result', () => {
    let state = run([progress('building_query'), progress('generating', 1), progress('fallback')])
    expect(state.status).toBe('running')
    expect(state.fallbackPreparing).toBe(true)
    expect(stepStates(state)).toEqual(['complete', 'complete', 'active', 'pending'])

    state = reduceProgress(state, { type: 'complete', runId: RUN, fallback: true, now: 50_000 })
    expect(state.status).toBe('fallback')
    expect(stepStates(state)).toEqual(['complete', 'complete', 'complete', 'skipped'])
  })

  it('does not confuse a model switch followed by a normal success with a fallback', () => {
    let state = run([progress('generating', 1), progress('switching_model'), progress('generating', 1), progress('reranking')])
    state = reduceProgress(state, { type: 'complete', runId: RUN, fallback: false, now: 60_000 })
    expect(state.status).toBe('success')
    expect(state.switchedModel).toBe(true)
    expect(stepStates(state)).toEqual(['complete', 'complete', 'complete', 'complete'])
  })

  it('marks the current step as interrupted on error and freezes the clock', () => {
    let state = run([progress('building_query'), progress('generating', 1)], 0)
    state = reduceProgress(state, { type: 'fail', runId: RUN, kind: 'sse', message: 'boom', now: 42_000 })
    expect(state.status).toBe('error')
    expect(stepStates(state)).toEqual(['complete', 'complete', 'error', 'pending'])
    expect(elapsedMs(state, 999_000)).toBe(42_000)
  })

  it('ignores actions from a stale run and anything after a terminal state', () => {
    let state = run([progress('generating', 1)])
    const before = state
    state = reduceProgress(state, { type: 'event', runId: RUN + 1, event: progress('reranking'), now: 1 })
    state = reduceProgress(state, { type: 'complete', runId: RUN + 1, fallback: false, now: 1 })
    expect(state).toBe(before)

    state = reduceProgress(state, { type: 'complete', runId: RUN, fallback: false, now: 5_000 })
    const done = state
    const late: ProgressAction[] = [
      { type: 'event', runId: RUN, event: progress('fallback'), now: 6_000 },
      { type: 'complete', runId: RUN, fallback: true, now: 6_000 },
      { type: 'fail', runId: RUN, kind: 'network', message: 'x', now: 6_000 }
    ]
    for (const action of late) state = reduceProgress(state, action)
    expect(state).toBe(done)
  })

  it('a new start resets steps, flags and the clock', () => {
    let state = run([progress('generating', 2), progress('switching_model')])
    state = reduceProgress(state, { type: 'fail', runId: RUN, kind: 'network', message: 'x', now: 9_000 })
    state = reduceProgress(state, { type: 'start', runId: RUN + 1, now: 20_000 })
    expect(state).toMatchObject({ runId: 2, status: 'running', stage: 0, switchedModel: false, errorKind: null, startedAt: 20_000 })
  })
})

describe('time helpers', () => {
  it('formats elapsed time as mm:ss from the start time, not from ticks', () => {
    const state = run([], 1_000)
    expect(formatElapsed(elapsedMs(state, 1_000 + 65_400))).toBe('01:05')
    expect(formatElapsed(0)).toBe('00:00')
  })

  it('flags a quiet wait without moving any step', () => {
    const state = run([progress('generating', 1)], 0)
    const lastEvent = state.lastEventAt!
    expect(isQuiet(state, lastEvent + QUIET_AFTER_MS - 1)).toBe(false)
    expect(isQuiet(state, lastEvent + QUIET_AFTER_MS)).toBe(true)
    expect(stepStates(state)).toEqual(['complete', 'complete', 'active', 'pending'])
  })
})
