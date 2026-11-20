import { describe, expect, it } from 'vitest'
import { parsePointsOfInterest } from '@/utils/pointsOfInterest'

describe('parsePointsOfInterest', () => {
  it('splits a bold-name Markdown list into name and note', () => {
    expect(parsePointsOfInterest('- **Galata Bridge**: a bridge over the Golden Horn\n* **Karaköy**：cafés')).toEqual([
      { name: 'Galata Bridge', note: 'a bridge over the Golden Horn' },
      { name: 'Karaköy', note: 'cafés' }
    ])
  })

  it('handles items without bold names or notes, including a Chinese colon', () => {
    expect(parsePointsOfInterest('- Spice Bazaar: spices\n- Pera Museum\n* 翠湖公园：看红嘴鸥')).toEqual([
      { name: 'Spice Bazaar', note: 'spices' },
      { name: 'Pera Museum', note: '' },
      { name: '翠湖公园', note: '看红嘴鸥' }
    ])
  })

  it('skips lines that are not list items, and empty input', () => {
    expect(parsePointsOfInterest('Here are some places:\n\n- **A**: x')).toEqual([{ name: 'A', note: 'x' }])
    expect(parsePointsOfInterest('')).toEqual([])
  })

  it('keeps markup as plain text and drops link targets', () => {
    expect(parsePointsOfInterest('- **<img src=x onerror=alert(1)>**: see [site](javascript:alert(1))')).toEqual([
      { name: '<img src=x onerror=alert(1)>', note: 'see site' }
    ])
  })
})
