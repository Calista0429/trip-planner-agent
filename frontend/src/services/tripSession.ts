import type { TripFormData, TripPlan } from '@/types'

// sessionStorage hand-off between Home and Result. `tripPlan` is the existing
// key and keeps its exact shape; the request and generation meta are additive
// so the result page can show party size / budget cap / fallback state without
// guessing them from the plan.
const PLAN_KEY = 'tripPlan'
const REQUEST_KEY = 'tripRequest'
const META_KEY = 'tripPlanMeta'

export interface TripPlanMeta {
  /** Final graph status from the SSE result frame, e.g. llm_success / fallback_success. */
  status?: string
  message?: string
  /** True when the stream reported switching to the fallback model. */
  switchedModel?: boolean
}

function read<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function write(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value))
  } catch (err) {
    console.warn(`sessionStorage write failed: ${key}`, err)
  }
}

export const loadPlan = (): TripPlan | null => {
  const plan = read<TripPlan>(PLAN_KEY)
  return plan && Array.isArray(plan.days) ? plan : null
}
export const savePlan = (plan: TripPlan) => write(PLAN_KEY, plan)

export const loadRequest = (): TripFormData | null => read<TripFormData>(REQUEST_KEY)
export const saveRequest = (request: TripFormData) => write(REQUEST_KEY, request)

export const loadMeta = (): TripPlanMeta | null => read<TripPlanMeta>(META_KEY)
export const saveMeta = (meta: TripPlanMeta) => write(META_KEY, meta)

/** A fallback plan came from the deterministic template, not the LLM. */
export const isFallbackStatus = (status?: string): boolean =>
  !!status && (status === 'fallback_success' || status.startsWith('fallback'))
