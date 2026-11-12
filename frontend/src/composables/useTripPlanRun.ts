import { computed, getCurrentInstance, onBeforeUnmount, shallowRef } from 'vue'
import { StreamError, streamTripPlan, type StreamEvent, type StreamOptions } from '@/services/api'
import { isFallbackStatus, saveMeta, savePlan, saveRequest, type TripPlanMeta } from '@/services/tripSession'
import {
  initialProgress,
  reduceProgress,
  type ProgressAction,
  type ProgressState
} from '@/services/tripProgress'
import type { TripFormData, TripPlan } from '@/types'

export interface TripPlanRunDeps {
  stream: (
    request: TripFormData,
    onEvent: (event: StreamEvent) => void,
    options: StreamOptions
  ) => Promise<TripPlan>
  savePlan: (plan: TripPlan) => void
  saveRequest: (request: TripFormData) => void
  saveMeta: (meta: TripPlanMeta) => void
  /** Open the result page. Called at most once per successful run. */
  navigate: () => void
  /** Optional toast / side effect once the plan has been saved. */
  onSettled?: (outcome: 'success' | 'fallback') => void
  onFailed?: (error: StreamError) => void
  now?: () => number
  /** How long the settled ticket stays up before navigating (ms). */
  handoffDelay?: () => number
}

/**
 * Pause after a valid result so the last seals land before the transition to
 * the result page. The plan is already saved by then; this never gates success.
 */
export const HANDOFF_DELAY_MS = 1000
/** Hand-off pause when the user prefers reduced motion. */
export const HANDOFF_DELAY_REDUCED_MS = 250
/** The elapsed display refreshes this often; it never advances the steps. */
export const TICK_MS = 1000

const defaultDeps = { stream: streamTripPlan, savePlan, saveRequest, saveMeta }

/**
 * Owns one planning run at a time: run-id isolation, a single elapsed ticker,
 * the save → navigate handoff (once), and cleanup on unmount.
 */
export function useTripPlanRun(overrides: Partial<TripPlanRunDeps> & Pick<TripPlanRunDeps, 'navigate'>) {
  const deps: TripPlanRunDeps = { ...defaultDeps, ...overrides }
  const now = deps.now ?? (() => Date.now())

  const state = shallowRef<ProgressState>(initialProgress())
  const clock = shallowRef(now())
  /** The request this run was started with (summary on the ticket). */
  const request = shallowRef<TripFormData | null>(null)

  let currentRun = 0
  let disposed = false
  let controller: AbortController | null = null
  let ticker: ReturnType<typeof setInterval> | null = null
  let handoffTimer: ReturnType<typeof setTimeout> | null = null

  const dispatch = (action: ProgressAction) => {
    state.value = reduceProgress(state.value, action)
  }

  const refreshClock = () => {
    clock.value = now()
  }

  const onVisibility = () => {
    if (typeof document !== 'undefined' && document.visibilityState === 'visible') refreshClock()
  }

  function startTicker() {
    stopTicker()
    refreshClock()
    ticker = setInterval(refreshClock, TICK_MS)
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onVisibility)
  }

  function stopTicker() {
    if (ticker !== null) {
      clearInterval(ticker)
      ticker = null
    }
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onVisibility)
    refreshClock()
  }

  function clearHandoff() {
    if (handoffTimer !== null) {
      clearTimeout(handoffTimer)
      handoffTimer = null
    }
  }

  const busy = computed(
    () => state.value.status === 'running' || state.value.status === 'success' || state.value.status === 'fallback'
  )

  async function submit(requestData: TripFormData): Promise<void> {
    // Duplicate submit while a run is active (or handing off) is ignored.
    if (disposed || busy.value) return

    clearHandoff()
    controller?.abort()
    const runId = ++currentRun
    const abort = new AbortController()
    controller = abort
    request.value = requestData
    dispatch({ type: 'start', runId, now: now() })
    startTicker()

    let resultStatus: string | undefined
    let resultMessage: string | undefined
    let switchedModel = false
    const stale = () => disposed || runId !== currentRun

    try {
      const plan = await deps.stream(
        requestData,
        (event) => {
          if (stale()) return
          if (event.type === 'progress' && event.phase === 'switching_model') switchedModel = true
          if (event.type === 'result' && resultStatus === undefined) {
            resultStatus = event.status
            resultMessage = event.message
          }
          dispatch({ type: 'event', runId, event, now: now() })
        },
        { signal: abort.signal }
      )
      if (stale()) return

      const fallback = isFallbackStatus(resultStatus)
      deps.savePlan(plan)
      deps.saveRequest(requestData)
      deps.saveMeta({ status: resultStatus, message: resultMessage, switchedModel })
      dispatch({ type: 'complete', runId, fallback, now: now() })
      stopTicker()
      deps.onSettled?.(fallback ? 'fallback' : 'success')

      handoffTimer = setTimeout(() => {
        handoffTimer = null
        if (stale()) return
        deps.navigate()
      }, deps.handoffDelay?.() ?? HANDOFF_DELAY_MS)
    } catch (error) {
      if (stale()) return
      const err =
        error instanceof StreamError
          ? error
          : new StreamError('network', (error as Error)?.message || 'Unknown error')
      dispatch({ type: 'fail', runId, kind: err.kind, message: err.message, status: err.status, now: now() })
      stopTicker()
      deps.onFailed?.(err)
    } finally {
      if (controller === abort) controller = null
    }
  }

  /** Back to idle (e.g. the user dismisses an error). Never cancels a running request. */
  function reset() {
    if (state.value.status === 'running') return
    clearHandoff()
    dispatch({ type: 'reset' })
  }

  function dispose() {
    disposed = true
    currentRun++
    clearHandoff()
    stopTicker()
    // Stops the local fetch only; the server-side run is not cancelled.
    controller?.abort()
    controller = null
  }

  if (getCurrentInstance()) onBeforeUnmount(dispose)

  return {
    state,
    clock,
    request,
    busy,
    submit,
    reset,
    dispose,
    /** Test hook: whether a ticker interval is live. */
    hasTicker: () => ticker !== null,
    hasPendingHandoff: () => handoffTimer !== null
  }
}
