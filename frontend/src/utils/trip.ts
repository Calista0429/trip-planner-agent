import type { Hotel, TripPlan } from '@/types'

export interface DisplayHotel {
  hotel: Hotel
  /** True when the day has no hotel of its own and reuses an earlier night's stay. */
  isCarriedOver: boolean
}

/**
 * The hotel to show for a day. A day without its own hotel (typically the
 * departure day) reuses the most recent previous night's stay. This is display
 * only: it never adds a night or touches the plan's budget.
 */
export const getDisplayHotel = (plan: TripPlan | null, dayIndex: number): DisplayHotel | null => {
  const days = plan?.days || []
  const own = days[dayIndex]?.hotel
  if (own) return { hotel: own, isCarriedOver: false }
  for (let index = dayIndex - 1; index >= 0; index -= 1) {
    const previous = days[index]?.hotel
    if (previous) return { hotel: previous, isCarriedOver: true }
  }
  return null
}

/** A finite number, including a real 0. null/undefined/NaN/'' are "missing". */
export const isAmount = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)

export const formatMoney = (value: number, locale: 'zh' | 'en'): string =>
  `¥${value.toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', { maximumFractionDigits: 0 })}`

/** "2026-11-11" -> { month: 11, day: 11 }, or null when not an ISO date. */
export const splitDate = (date: string | undefined): { year: number; month: number; day: number } | null => {
  const match = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(String(date || ''))
  if (!match) return null
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) }
}
