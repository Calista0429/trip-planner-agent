import { afterEach, describe, expect, it, vi } from 'vitest'
import { AlbumUploadError, uploadAlbumPhotos } from '@/services/api'

const upstream = {
  tripId: 'abc',
  title: 'THE GALATA CAPER',
  style: 'watercolor-journal',
  pictures: [{ imageUrl: 'https://storage.googleapis.com/b/x.png/0', description: 'A tower', location: 'Istanbul', pointsOfInterest: '' }],
  failed: [{ file: 'b.png', reason: 'no_image' }]
}

function mockFetch(response: Response | Error) {
  const fn = vi.fn((_url: string, _init?: RequestInit) =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response))
  vi.stubGlobal('fetch', fn)
  return fn
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const photo = (name = 'a.png') => new File(['A'], name, { type: 'image/png' })

async function errorOf(promise: Promise<unknown>) {
  const error = await promise.then(() => null, e => e)
  expect(error).toBeInstanceOf(AlbumUploadError)
  return error as AlbumUploadError
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('uploadAlbumPhotos', () => {
  it('posts every photo as a "file" part plus the style, and stamps createdAt', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-11-20T08:00:00Z'))
    const fetchFn = mockFetch(json(200, upstream))

    const album = await uploadAlbumPhotos([photo('a.png'), photo('b.jpg')], 'watercolor-journal')

    expect(album).toEqual({ ...upstream, createdAt: '2026-11-20T08:00:00.000Z' })
    const [url, init] = fetchFn.mock.calls[0]
    expect(url).toBe('/api/comic/upload')
    expect(init?.method).toBe('POST')
    const form = init?.body as FormData
    expect(form.getAll('file').map(f => (f as File).name)).toEqual(['a.png', 'b.jpg'])
    expect(form.get('style')).toBe('watercolor-journal')
  })

  it('reports the backend error code and the per-photo reasons', async () => {
    mockFetch(json(502, { error: 'all_failed', failed: [{ file: 'a.png', reason: 'rate_limited' }] }))

    const error = await errorOf(uploadAlbumPhotos([photo()], 'comic'))

    expect(error.code).toBe('all_failed')
    expect(error.failed).toEqual([{ file: 'a.png', reason: 'rate_limited' }])
  })

  it('treats a non-JSON error body as comic_failed', async () => {
    mockFetch(new Response('Bad Gateway', { status: 502 }))

    expect((await errorOf(uploadAlbumPhotos([photo()], 'comic'))).code).toBe('comic_failed')
  })

  it('reports network when fetch itself fails', async () => {
    mockFetch(new TypeError('Failed to fetch'))

    expect((await errorOf(uploadAlbumPhotos([photo()], 'comic'))).code).toBe('network')
  })
})
