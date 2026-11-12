import type { Location } from '@/types'

/**
 * A coordinate is usable only when both parts are finite numbers in range and
 * it is not null island. Missing/zero coords would otherwise render off West
 * Africa, and swapped lng/lat drags the whole map away.
 */
export const isValidLocation = (location: unknown): location is Location => {
  if (!location || typeof location !== 'object') return false
  const raw = location as Record<string, unknown>
  if (raw.longitude === null || raw.latitude === null) return false
  if (raw.longitude === '' || raw.latitude === '') return false
  const longitude = Number(raw.longitude)
  const latitude = Number(raw.latitude)
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return false
  if (longitude === 0 && latitude === 0) return false
  if (longitude < -180 || longitude > 180) return false
  if (latitude < -90 || latitude > 90) return false
  return true
}

export const normalizeLocation = (location: Location): Location => ({
  longitude: Number(location.longitude),
  latitude: Number(location.latitude)
})

const LODGING_BREAKFAST = ['酒店早餐', '民宿早餐', '客栈早餐', '住宿早餐', 'hotel breakfast']

/** Breakfast eaten at the lodging is not a separate place on the map. */
export const isLodgingBreakfastMeal = (type: string, name: string): boolean => {
  if (type !== 'breakfast') return false
  const lower = String(name || '').toLowerCase()
  return LODGING_BREAKFAST.some(keyword => lower.includes(keyword))
}
