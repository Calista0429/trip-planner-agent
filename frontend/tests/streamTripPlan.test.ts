import { afterEach, describe, expect, it, vi } from 'vitest'
import { StreamError, streamTripPlan, type StreamEvent } from '@/services/api'
import type { TripFormData } from '@/types'
import { samplePlan } from './fixtures'

const request = { city: '杭州市' } as TripFormData
const frame = (payload: unknown, event = 'message') => `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`

/** A fetch Response whose body yields the given chunks (strings), optionally failing at the end. */
function sseResponse(chunks: string[], opts: { failAfter?: boolean; status?: number } = {}) {
  const encoder = new TextEncoder()
  let index = 0
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index++]))
      } else if (opts.failAfter) {
        controller.error(new TypeError('network error'))
      } else {
        controller.close()
      }
    }
  })
  return new Response(body, { status: opts.status ?? 200, headers: { 'Content-Type': 'text/event-stream' } })
}

function mockFetch(response: Response | Promise<Response>) {
  const fn = vi.fn((_url: string, _init?: RequestInit) => Promise.resolve(response))
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
})

async function expectKind(promise: Promise<unknown>, kind: StreamError['kind']) {
  const error = await promise.then(
    () => null,
    (e) => e
  )
  expect(error).toBeInstanceOf(StreamError)
  expect((error as StreamError).kind).toBe(kind)
  return error as StreamError
}

describe('streamTripPlan', () => {
  it('parses frames split across chunks and resolves with the plan', async () => {
    const all =
      frame({ type: 'progress', phase: 'collecting_weather', message: 'x' }) +
      frame({ type: 'progress', phase: 'generating', attempt: 1 }) +
      frame({ type: 'result', success: true, status: 'llm_success', message: 'ok', data: samplePlan })
    // Split at awkward offsets, including inside a JSON payload and between \n\n.
    const chunks = [all.slice(0, 7), all.slice(7, 60), all.slice(60, 61), all.slice(61, 200), all.slice(200)]
    const fetchFn = mockFetch(sseResponse(chunks))
    const events: StreamEvent[] = []

    const plan = await streamTripPlan(request, (e) => events.push(e))

    expect(plan.city).toBe(samplePlan.city)
    expect(events.map((e) => e.phase ?? e.type)).toEqual(['collecting_weather', 'generating', 'result'])
    const [url, init] = fetchFn.mock.calls[0]
    expect(url).toBe('/api/trip/plan/stream')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual(request)
  })

  it('handles CRLF framing and a final frame without a trailing blank line', async () => {
    const result = `data: ${JSON.stringify({ type: 'result', success: true, status: 'llm_success', data: samplePlan })}`
    mockFetch(sseResponse([frame({ type: 'progress', phase: 'building_query' }).replace(/\n/g, '\r\n'), result]))
    const plan = await streamTripPlan(request, () => {})
    expect(plan.days.length).toBe(samplePlan.days.length)
  })

  it('ignores duplicate result frames after the first one', async () => {
    const events: StreamEvent[] = []
    mockFetch(
      sseResponse([
        frame({ type: 'result', success: true, status: 'llm_success', data: samplePlan }),
        frame({ type: 'result', success: true, status: 'fallback_success', data: samplePlan }),
        frame({ type: 'progress', phase: 'fallback' })
      ])
    )
    await streamTripPlan(request, (e) => events.push(e))
    expect(events).toHaveLength(1)
    expect(events[0].status).toBe('llm_success')
  })

  it('rejects an HTTP failure with its status', async () => {
    mockFetch(new Response('nope', { status: 502 }))
    const error = await expectKind(streamTripPlan(request, () => {}), 'http')
    expect(error.status).toBe(502)
  })

  it('rejects when fetch itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    await expectKind(streamTripPlan(request, () => {}), 'network')
  })

  it('rejects an SSE error frame with the server message', async () => {
    mockFetch(sseResponse([frame({ type: 'progress', phase: 'generating', attempt: 1 }), frame({ type: 'error', message: 'LLM down' })]))
    const error = await expectKind(streamTripPlan(request, () => {}), 'sse')
    expect(error.message).toBe('LLM down')
  })

  it('rejects success=false and results without a usable plan', async () => {
    mockFetch(sseResponse([frame({ type: 'result', success: false, status: 'unknown', data: null })]))
    await expectKind(streamTripPlan(request, () => {}), 'failed')

    mockFetch(sseResponse([frame({ type: 'result', success: true, status: 'llm_success', data: { city: 'x', days: [] } })]))
    await expectKind(streamTripPlan(request, () => {}), 'failed')
  })

  it('rejects a stream that ends without a result', async () => {
    mockFetch(sseResponse([frame({ type: 'progress', phase: 'reranking' })]))
    await expectKind(streamTripPlan(request, () => {}), 'no_result')
  })

  it('rejects a connection that drops mid-stream', async () => {
    mockFetch(sseResponse([frame({ type: 'progress', phase: 'generating', attempt: 1 })], { failAfter: true }))
    await expectKind(streamTripPlan(request, () => {}), 'network')
  })

  it('passes the AbortSignal through and reports an aborted run', async () => {
    const controller = new AbortController()
    const fetchFn = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      })
    })
    vi.stubGlobal('fetch', fetchFn)
    const pending = streamTripPlan(request, () => {}, { signal: controller.signal })
    controller.abort()
    await expectKind(pending, 'aborted')
    expect(fetchFn.mock.calls[0][1]?.signal).toBe(controller.signal)
  })

  it('stays compatible with the old two-argument call', async () => {
    mockFetch(sseResponse([frame({ type: 'result', success: true, status: 'llm_success', data: samplePlan })]))
    await expect(streamTripPlan(request, () => {})).resolves.toBeTruthy()
  })
})
