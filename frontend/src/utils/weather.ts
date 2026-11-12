import type { WeatherInfo } from '@/types'

const UNKNOWN = /未知|暂无|无预报|远期|unknown|n\/a/i

/** Condition text, or '' when it is missing / an "unknown" placeholder. */
export const knownText = (value: unknown): string => {
  if (value === null || value === undefined) return ''
  const text = String(value).trim()
  return text && !UNKNOWN.test(text) ? text : ''
}

/**
 * Parse a temperature without inventing one. A real 0 or negative value is kept;
 * null, '', '未知' and other non-numeric text become null (shown as "—").
 */
export const parseTemperature = (value: unknown): number | null => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (value === null || value === undefined) return null
  const text = String(value).replace(/℃|°C|°/gi, '').trim()
  if (!/^[+-]?\d+(\.\d+)?$/.test(text)) return null
  return Number(text)
}

export const formatTemperature = (value: number | null): string =>
  value === null ? '—' : String(value)

export type WeatherIconKind = 'unknown' | 'storm' | 'rain' | 'snow' | 'sun' | 'fog' | 'cloud'

export const weatherIconKind = (condition: string): WeatherIconKind => {
  if (!condition) return 'unknown'
  if (/雷/.test(condition)) return 'storm'
  if (/雨/.test(condition)) return 'rain'
  if (/雪|冰雹/.test(condition)) return 'snow'
  if (/雾|霾|沙|尘/.test(condition)) return 'fog'
  if (/晴/.test(condition) && !/云|阴/.test(condition)) return 'sun'
  return 'cloud'
}

/** Match weather to a plan day strictly by date; never by position. */
export const weatherForDate = (weather: WeatherInfo[] | undefined, date: string): WeatherInfo | null => {
  if (!date || !Array.isArray(weather)) return null
  return weather.find(item => item && String(item.date).trim() === date.trim()) ?? null
}
