import type { StreamErrorKind, StreamEvent } from './api'

/**
 * Pure state for the "journey ticket" progress UI.
 *
 * The four steps are a UI grouping of the backend SSE phases, not extra backend
 * events. Progress events are node-completion updates, so a step is only
 * confirmed finished when a *later* phase arrives (or a valid result ends the run).
 * Nothing here advances on time: the wall clock only feeds the elapsed display.
 */

export type RunStatus = 'idle' | 'running' | 'success' | 'fallback' | 'error'
export type StepState = 'pending' | 'active' | 'complete' | 'skipped' | 'error'
export type StepIndex = 0 | 1 | 2 | 3

export const STEP_KEYS = ['research', 'route', 'itinerary', 'review'] as const

export interface ProgressState {
  runId: number
  status: RunStatus
  /** Highest UI step reached so far (never decreases within a run). */
  stage: StepIndex
  /** Rank of the last accepted phase; copy only follows phases of equal or higher rank. */
  rank: number
  /** Last accepted phase (drives the short description). */
  phase: string | null
  attempt: number | null
  switchedModel: boolean
  /** A `progress:fallback` event arrived: the template plan is being prepared. */
  fallbackPreparing: boolean
  /** A `reranking` event arrived, so the review step really ran. */
  reviewed: boolean
  startedAt: number | null
  lastEventAt: number | null
  finishedAt: number | null
  errorKind: StreamErrorKind | null
  errorMessage: string | null
  errorStatus: number | null
}

/** Phase → [rank, step]. Unknown phases (e.g. critic nodes) are ignored. */
const PHASES: Record<string, [number, StepIndex]> = {
  collecting_attractions: [0, 0],
  collecting_weather: [0, 0],
  collecting_hotels: [0, 0],
  collecting_context: [1, 0],
  building_query: [2, 1],
  generating: [3, 2],
  switching_model: [3, 2],
  reranking: [4, 3],
  fallback: [4, 2]
}

export function knownPhase(phase: string | undefined | null): phase is string {
  return !!phase && Object.prototype.hasOwnProperty.call(PHASES, phase)
}

export function initialProgress(): ProgressState {
  return {
    runId: 0,
    status: 'idle',
    stage: 0,
    rank: -1,
    phase: null,
    attempt: null,
    switchedModel: false,
    fallbackPreparing: false,
    reviewed: false,
    startedAt: null,
    lastEventAt: null,
    finishedAt: null,
    errorKind: null,
    errorMessage: null,
    errorStatus: null
  }
}

export type ProgressAction =
  | { type: 'start'; runId: number; now: number }
  | { type: 'event'; runId: number; event: StreamEvent; now: number }
  | { type: 'complete'; runId: number; fallback: boolean; now: number }
  | {
      type: 'fail'
      runId: number
      kind: StreamErrorKind
      message: string
      status?: number
      now: number
    }
  | { type: 'reset' }

export function reduceProgress(state: ProgressState, action: ProgressAction): ProgressState {
  switch (action.type) {
    case 'start':
      // Every run starts from scratch; the run id isolates stale callbacks.
      return { ...initialProgress(), runId: action.runId, status: 'running', startedAt: action.now, lastEventAt: action.now }

    case 'reset':
      return initialProgress()

    case 'event': {
      if (action.runId !== state.runId || state.status !== 'running') return state
      const { event } = action
      if (event.type !== 'progress' || !knownPhase(event.phase)) return state
      const [rank, step] = PHASES[event.phase]
      const next: ProgressState = { ...state, lastEventAt: action.now }

      if (event.phase === 'switching_model') next.switchedModel = true
      if (event.phase === 'reranking') next.reviewed = true
      if (event.phase === 'fallback') next.fallbackPreparing = true

      // Late or duplicate lower-rank events never move the step or copy backwards.
      if (rank < state.rank) return next
      next.rank = rank
      next.stage = Math.max(state.stage, step) as StepIndex
      next.phase = event.phase
      if (event.phase === 'generating') {
        const attempt = Number(event.attempt)
        next.attempt = Number.isFinite(attempt) && attempt > 0 ? attempt : null
      } else if (event.phase === 'switching_model') {
        // Attempt numbering restarts on the other model; keep the copy neutral.
        next.attempt = null
      }
      return next
    }

    case 'complete':
      if (action.runId !== state.runId || state.status !== 'running') return state
      return {
        ...state,
        status: action.fallback ? 'fallback' : 'success',
        stage: 3,
        finishedAt: action.now,
        lastEventAt: action.now
      }

    case 'fail':
      if (action.runId !== state.runId || state.status !== 'running') return state
      return {
        ...state,
        status: 'error',
        finishedAt: action.now,
        errorKind: action.kind,
        errorMessage: action.message,
        errorStatus: action.status ?? null
      }
  }
}

/** Per-step display state derived from the run state. */
export function stepStates(state: ProgressState): StepState[] {
  return STEP_KEYS.map((_, index): StepState => {
    switch (state.status) {
      case 'idle':
        return 'pending'
      case 'success':
        return 'complete'
      case 'fallback':
        // The template plan skipped review unless reranking really ran.
        if (index === 3) return state.reviewed ? 'complete' : 'skipped'
        return 'complete'
      case 'error':
        if (index < state.stage) return 'complete'
        return index === state.stage ? 'error' : 'pending'
      case 'running':
        if (index < state.stage) return 'complete'
        return index === state.stage ? 'active' : 'pending'
    }
  })
}

export function elapsedMs(state: ProgressState, now: number): number {
  if (state.startedAt == null) return 0
  const end = state.finishedAt ?? now
  return Math.max(0, end - state.startedAt)
}

export function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000)
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

/** No progress event for this long: show a neutral "still working" status. */
export const QUIET_AFTER_MS = 25_000

export function isQuiet(state: ProgressState, now: number): boolean {
  return state.status === 'running' && state.lastEventAt != null && now - state.lastEventAt >= QUIET_AFTER_MS
}
