import type { TripFormData, TripPlan } from '@/types'

/** Minimal valid TripPlan for test streams (test-only data, not used by the app). */
export const samplePlan = {
  city: '杭州市',
  start_date: '2026-11-20',
  end_date: '2026-11-21',
  days: [
    { date: '2026-11-20', day_index: 0, description: '', transportation: '公共交通', accommodation: '经济型酒店', attractions: [], meals: [] },
    { date: '2026-11-21', day_index: 1, description: '', transportation: '公共交通', accommodation: '经济型酒店', attractions: [], meals: [] }
  ],
  weather_info: [],
  overall_suggestions: ''
} as unknown as TripPlan

export const sampleRequest: TripFormData = {
  city: '杭州市',
  start_date: '2026-11-20',
  end_date: '2026-11-21',
  travel_days: 2,
  transportation: '公共交通',
  accommodation: '经济型酒店',
  preferences: ['历史文化'],
  free_text_input: '',
  party: { adults: 2, children: 0, elders: 0, total: 2, companion_type: 'couple' },
  budget_constraint: { amount: 3000, scope: 'total', currency: 'CNY', budget_level: 'standard', strictness: 'hard' }
}
