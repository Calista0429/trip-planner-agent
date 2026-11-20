import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PLANNER_DRAFT_KEY, clearPlannerDraft, loadPlannerDraft, savePlannerDraft, type PlannerDraft } from '@/services/plannerDraft'

const draft: PlannerDraft = {
  version: 1,
  provinceCode: '330000',
  form: {
    city: '',
    start_date: null,
    end_date: '2026-12-03',
    transportation: '公共交通',
    accommodation: '经济型酒店',
    preferences: ['美食'],
    free_text_input: '想看日落',
    party: { adults: null, children: 0, elders: 1, companion_type: 'family_with_elders' },
    budget_constraint: { amount: 0, budget_level: 'premium' }
  },
  strictBudget: true,
  optionsOpen: true
}

beforeEach(() => sessionStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('plannerDraft', () => {
  it('round-trips incomplete input, keeping null and 0 apart', () => {
    savePlannerDraft(draft)
    expect(loadPlannerDraft()).toEqual(draft)
  })

  it('does not touch the submitted request keys', () => {
    savePlannerDraft(draft)
    expect(sessionStorage.getItem('tripRequest')).toBeNull()
    expect(Object.keys(sessionStorage)).toEqual([PLANNER_DRAFT_KEY])
  })

  it('clears the draft', () => {
    savePlannerDraft(draft)
    clearPlannerDraft()
    expect(loadPlannerDraft()).toBeNull()
  })

  it.each([
    ['broken JSON', '{"version":1,'],
    ['wrong version', JSON.stringify({ ...draft, version: 2 })],
    ['not an object', '"hello"'],
    ['missing form', JSON.stringify({ ...draft, form: undefined })],
    ['bad date', JSON.stringify({ ...draft, form: { ...draft.form, start_date: '2026-13-45' } })],
    ['date with time', JSON.stringify({ ...draft, form: { ...draft.form, start_date: '2026-12-01T00:00' } })],
    ['wrong party type', JSON.stringify({ ...draft, form: { ...draft.form, party: { ...draft.form.party, adults: '2' } } })],
    ['negative count', JSON.stringify({ ...draft, form: { ...draft.form, party: { ...draft.form.party, elders: -1 } } })],
    ['preferences not strings', JSON.stringify({ ...draft, form: { ...draft.form, preferences: [1] } })]
  ])('ignores a stored draft with %s', (_label, raw) => {
    sessionStorage.setItem(PLANNER_DRAFT_KEY, raw)
    expect(loadPlannerDraft()).toBeNull()
  })

  it('drops unknown fields instead of copying them through', () => {
    sessionStorage.setItem(PLANNER_DRAFT_KEY, JSON.stringify({ ...draft, extra: 1, form: { ...draft.form, __proto__x: 1 } }))
    const loaded = loadPlannerDraft()!
    expect(loaded).toEqual(draft)
    expect('extra' in loaded).toBe(false)
  })

  it('survives storage that throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('denied')
    })
    expect(() => savePlannerDraft(draft)).not.toThrow()
    expect(loadPlannerDraft()).toBeNull()
    expect(() => clearPlannerDraft()).not.toThrow()
  })
})
