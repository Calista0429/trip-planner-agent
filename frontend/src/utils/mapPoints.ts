import type { Meal, TripPlan } from '@/types'
import { isLodgingBreakfastMeal, isValidLocation, normalizeLocation } from './geo'
import { getDisplayHotel } from './trip'

export type MapCategory = 'hotel' | 'attraction' | 'meal'

export interface MapPoint {
  /** Stable id shared by the list ("view on map") and the marker. */
  key: string
  category: MapCategory
  dayIndex: number
  name: string
  address?: string
  description?: string
  longitude: number
  latitude: number
  /** Short glyph drawn inside the marker (attraction number, meal initial, stay). */
  glyph: string
  mealType?: Meal['type']
  carriedOver?: boolean
}

export const attractionKey = (day: number, index: number) => `d${day}-a${index}`
export const hotelKey = (day: number) => `d${day}-h`
export const mealKey = (day: number, index: number) => `d${day}-m${index}`

export interface DayPointsResult {
  points: MapPoint[]
  /** Places that exist in the plan but have no usable coordinates. */
  missing: number
}

export interface GlyphLabels {
  hotel: string
  breakfast: string
  lunch: string
  dinner: string
  snack: string
}

/**
 * Map points for one day. Invalid/missing coordinates are counted, never drawn;
 * breakfast at the lodging is not a separate place.
 */
export function buildDayPoints(plan: TripPlan | null, dayIndex: number, glyphs: GlyphLabels): DayPointsResult {
  const day = plan?.days?.[dayIndex]
  const points: MapPoint[] = []
  let missing = 0
  if (!day) return { points, missing }

  const display = getDisplayHotel(plan, dayIndex)
  if (display) {
    if (isValidLocation(display.hotel.location)) {
      const loc = normalizeLocation(display.hotel.location)
      points.push({
        key: hotelKey(dayIndex),
        category: 'hotel',
        dayIndex,
        name: display.hotel.name,
        address: display.hotel.address,
        longitude: loc.longitude,
        latitude: loc.latitude,
        glyph: glyphs.hotel,
        carriedOver: display.isCarriedOver
      })
    } else {
      missing += 1
    }
  }

  ;(day.attractions || []).forEach((attraction, index) => {
    if (!isValidLocation(attraction.location)) {
      missing += 1
      return
    }
    const loc = normalizeLocation(attraction.location)
    points.push({
      key: attractionKey(dayIndex, index),
      category: 'attraction',
      dayIndex,
      name: attraction.name,
      address: attraction.address,
      description: attraction.description,
      longitude: loc.longitude,
      latitude: loc.latitude,
      glyph: String(index + 1)
    })
  })

  ;(day.meals || []).forEach((meal, index) => {
    if (isLodgingBreakfastMeal(meal.type, meal.name)) return
    if (!isValidLocation(meal.location)) {
      missing += 1
      return
    }
    const loc = normalizeLocation(meal.location)
    points.push({
      key: mealKey(dayIndex, index),
      category: 'meal',
      dayIndex,
      name: meal.name,
      address: meal.address,
      description: meal.description,
      longitude: loc.longitude,
      latitude: loc.latitude,
      glyph: glyphs[meal.type] ?? glyphs.snack,
      mealType: meal.type
    })
  })

  return { points, missing }
}

/**
 * Visiting order for the connecting line: stay → breakfast → first sight →
 * lunch → remaining sights → snack → dinner → back to stay. This is the plan's
 * order, not a navigation route.
 */
export function routeOrder(points: MapPoint[]): MapPoint[] {
  const hotel = points.find(p => p.category === 'hotel')
  const sights = points.filter(p => p.category === 'attraction')
  const meals = (type: Meal['type']) => points.filter(p => p.category === 'meal' && p.mealType === type)
  const route: MapPoint[] = []
  if (hotel) route.push(hotel)
  route.push(...meals('breakfast'))
  if (sights[0]) route.push(sights[0])
  route.push(...meals('lunch'))
  route.push(...sights.slice(1))
  route.push(...meals('snack'))
  route.push(...meals('dinner'))
  if (hotel && route.length > 1) route.push(hotel)
  return route
}
