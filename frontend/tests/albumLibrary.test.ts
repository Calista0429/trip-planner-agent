import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Album } from '@/types'
import {
  ALBUM_LIBRARY_KEY,
  MAX_SAVED_ALBUMS,
  getAlbum,
  loadAlbums,
  removeAlbum,
  saveAlbum
} from '@/services/albumLibrary'

const album = (tripId: string, createdAt = '2026-11-20T08:00:00.000Z'): Album => ({
  tripId,
  title: `Trip ${tripId}`,
  style: 'comic',
  pictures: [{ imageUrl: `https://storage.googleapis.com/b/${tripId}.png/0`, description: 'd', location: 'l', pointsOfInterest: '- **A**' }],
  failed: [],
  createdAt
})

const writeRaw = (value: unknown) => localStorage.setItem(ALBUM_LIBRARY_KEY, JSON.stringify(value))

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('album library (this browser only)', () => {
  it('is empty when nothing was saved', () => {
    expect(loadAlbums()).toEqual([])
    expect(getAlbum('nope')).toBeNull()
  })

  it('saves an album and reads it back, newest first', () => {
    expect(saveAlbum(album('a'))).toBe(true)
    expect(saveAlbum(album('b'))).toBe(true)

    expect(loadAlbums().map(a => a.tripId)).toEqual(['b', 'a'])
    expect(getAlbum('a')).toEqual(album('a'))
    expect(JSON.parse(localStorage.getItem(ALBUM_LIBRARY_KEY)!).version).toBe(1)
  })

  it('keeps one copy per tripId, moved to the front', () => {
    saveAlbum(album('a'))
    saveAlbum(album('b'))
    saveAlbum({ ...album('a'), title: 'Renamed' })

    expect(loadAlbums().map(a => [a.tripId, a.title])).toEqual([['a', 'Renamed'], ['b', 'Trip b']])
  })

  it(`keeps at most ${MAX_SAVED_ALBUMS} albums, dropping the oldest`, () => {
    for (let i = 0; i <= MAX_SAVED_ALBUMS; i++) saveAlbum(album(`t${i}`))

    const ids = loadAlbums().map(a => a.tripId)
    expect(MAX_SAVED_ALBUMS).toBe(30)
    expect(ids).toHaveLength(30)
    expect(ids[0]).toBe('t30')
    expect(ids).not.toContain('t0')
  })

  it('reads the storage again before writing, so another tab’s album survives', () => {
    saveAlbum(album('a'))
    loadAlbums()
    // Another tab saves "other" behind this page's back.
    writeRaw({ version: 1, albums: [album('other'), album('a')] })

    saveAlbum(album('b'))

    expect(loadAlbums().map(a => a.tripId)).toEqual(['b', 'other', 'a'])
  })

  it('drops broken entries and keeps the good ones', () => {
    writeRaw({
      version: 1,
      albums: [
        album('good'),
        { ...album('style'), style: 'oil' },
        { ...album('url'), pictures: [{ ...album('x').pictures[0], imageUrl: 'javascript:alert(1)' }] },
        { ...album('date'), createdAt: 'yesterday' },
        { ...album('pics'), pictures: 'nope' },
        { title: 'no id' },
        null
      ]
    })

    expect(loadAlbums().map(a => a.tripId)).toEqual(['good'])
  })

  it('treats bad JSON or an unknown version as empty', () => {
    localStorage.setItem(ALBUM_LIBRARY_KEY, '{oops')
    expect(loadAlbums()).toEqual([])
    writeRaw({ version: 2, albums: [album('a')] })
    expect(loadAlbums()).toEqual([])
  })

  it('removes one album', () => {
    saveAlbum(album('a'))
    saveAlbum(album('b'))

    removeAlbum('a')

    expect(getAlbum('a')).toBeNull()
    expect(loadAlbums().map(a => a.tripId)).toEqual(['b'])
  })

  it('reports false instead of throwing when the storage is full', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })

    expect(saveAlbum(album('a'))).toBe(false)
  })

  it('reads as empty when the storage cannot be read', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })

    expect(loadAlbums()).toEqual([])
    expect(() => removeAlbum('a')).not.toThrow()
  })
})
