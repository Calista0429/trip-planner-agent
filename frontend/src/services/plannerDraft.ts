import type { TripFormData } from '@/types'

/**
 * The planning form as the user left it, kept for this tab only. Separate from
 * `tripRequest` (the last *submitted* request), which it must never overwrite.
 * Derived values (party total, trip length, budget strictness) are not stored;
 * Home recomputes them from these fields.
 */
export const PLANNER_DRAFT_KEY = 'tripPlanner.formDraft.v1'

type DraftParty = Omit<TripFormData['party'], 'total' | 'adults' | 'children' | 'elders'> & {
  adults: number | null
  children: number | null
  elders: number | null
}

export type PlannerDraftForm = Pick<
  TripFormData,
  'city' | 'transportation' | 'accommodation' | 'preferences' | 'free_text_input'
> & {
  start_date: string | null
  end_date: string | null
  party: DraftParty
  budget_constraint: Pick<TripFormData['budget_constraint'], 'amount' | 'budget_level'>
}

export interface PlannerDraft {
  version: 1
  provinceCode: string | null
  form: PlannerDraftForm
  strictBudget: boolean
  optionsOpen: boolean
}

const COMPANION_TYPES: DraftParty['companion_type'][] = [
  'solo', 'couple', 'friends', 'family_with_children', 'family_with_elders', 'business', 'other'
]
const BUDGET_LEVELS: PlannerDraftForm['budget_constraint']['budget_level'][] = [
  'limited', 'standard', 'comfortable', 'premium', 'luxury'
]

type Unknown = Record<string, unknown>

const isObject = (v: unknown): v is Unknown => !!v && typeof v === 'object' && !Array.isArray(v)
const isString = (v: unknown): v is string => typeof v === 'string'
const isCount = (v: unknown): v is number | null => v === null || (Number.isInteger(v) && (v as number) >= 0)
const isAmount = (v: unknown): v is number | null =>
  v === null || (typeof v === 'number' && Number.isFinite(v) && v >= 0)

/** `YYYY-MM-DD` that is also a real calendar day (no time part). */
function isDay(v: unknown): v is string | null {
  if (v === null) return true
  if (!isString(v) || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false
  const date = new Date(`${v}T00:00:00Z`)
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === v
}

/** Rebuild a draft from untrusted JSON, field by field; anything off returns null. */
function parse(raw: unknown): PlannerDraft | null {
  if (!isObject(raw) || raw.version !== 1) return null
  const { form } = raw
  if (!isObject(form) || !isObject(form.party) || !isObject(form.budget_constraint)) return null
  const { party, budget_constraint: budget } = form
  const ok =
    (raw.provinceCode === null || isString(raw.provinceCode)) &&
    typeof raw.strictBudget === 'boolean' &&
    typeof raw.optionsOpen === 'boolean' &&
    isString(form.city) &&
    isDay(form.start_date) &&
    isDay(form.end_date) &&
    isString(form.transportation) &&
    isString(form.accommodation) &&
    Array.isArray(form.preferences) &&
    form.preferences.every(isString) &&
    isString(form.free_text_input) &&
    isCount(party.adults) &&
    isCount(party.children) &&
    isCount(party.elders) &&
    COMPANION_TYPES.includes(party.companion_type as DraftParty['companion_type']) &&
    isAmount(budget.amount) &&
    BUDGET_LEVELS.includes(budget.budget_level as PlannerDraftForm['budget_constraint']['budget_level'])
  if (!ok) return null
  return {
    version: 1,
    provinceCode: raw.provinceCode as string | null,
    strictBudget: raw.strictBudget as boolean,
    optionsOpen: raw.optionsOpen as boolean,
    form: {
      city: form.city as string,
      start_date: form.start_date as string | null,
      end_date: form.end_date as string | null,
      transportation: form.transportation as string,
      accommodation: form.accommodation as string,
      preferences: [...(form.preferences as string[])],
      free_text_input: form.free_text_input as string,
      party: {
        adults: party.adults as number | null,
        children: party.children as number | null,
        elders: party.elders as number | null,
        companion_type: party.companion_type as DraftParty['companion_type']
      },
      budget_constraint: {
        amount: budget.amount as number | null,
        budget_level: budget.budget_level as PlannerDraftForm['budget_constraint']['budget_level']
      }
    }
  }
}

export function loadPlannerDraft(): PlannerDraft | null {
  try {
    const raw = sessionStorage.getItem(PLANNER_DRAFT_KEY)
    return raw ? parse(JSON.parse(raw)) : null
  } catch {
    return null
  }
}

export function savePlannerDraft(draft: PlannerDraft): void {
  try {
    sessionStorage.setItem(PLANNER_DRAFT_KEY, JSON.stringify(draft))
  } catch {
    // Storage full or blocked: the form keeps working from memory.
  }
}

export function clearPlannerDraft(): void {
  try {
    sessionStorage.removeItem(PLANNER_DRAFT_KEY)
  } catch {
    // Nothing to do; a stale draft is ignored once a newer request exists.
  }
}
