import axios from 'axios'
import type { TripFormData, TripPlan, TripPlanResponse } from '@/types'

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()

export const API_BASE_URL = configuredApiBaseUrl
  ? configuredApiBaseUrl.replace(/\/$/, '')
  : ''

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 600000, // 10分钟超时
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 生成旅行计划
 */
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

// A single Server-Sent Events frame emitted by POST /api/trip/plan/stream.
export interface StreamEvent {
  type: 'progress' | 'result' | 'error'
  phase?: string
  attempt?: number
  message?: string
  status?: string
  success?: boolean
  data?: TripPlan | null
}

/**
 * Why a streamed planning run did not produce a usable plan.
 * - http: non-2xx response or no body
 * - network: fetch / read failed (offline, connection dropped mid-stream)
 * - sse: the server sent an `error` frame
 * - failed: a `result` frame with success=false or without a usable plan
 * - no_result: the stream closed before any result frame
 * - aborted: the caller aborted via AbortSignal (local only; the server run is not cancelled)
 */
export type StreamErrorKind = 'http' | 'network' | 'sse' | 'failed' | 'no_result' | 'aborted'

export class StreamError extends Error {
  readonly kind: StreamErrorKind
  readonly status?: number

  constructor(kind: StreamErrorKind, message: string, status?: number) {
    super(message)
    this.name = 'StreamError'
    this.kind = kind
    this.status = status
  }
}

export interface StreamOptions {
  /** Abort the local fetch. This does not cancel the planning run on the server. */
  signal?: AbortSignal
}

/** A result frame's plan is usable only if it looks like a TripPlan with days. */
export function isUsablePlan(plan: unknown): plan is TripPlan {
  return (
    !!plan &&
    typeof plan === 'object' &&
    Array.isArray((plan as TripPlan).days) &&
    (plan as TripPlan).days.length > 0
  )
}

// Parse one raw SSE frame ("event: ...\ndata: {json}") into its JSON payload.
function parseSseFrame(frame: string): StreamEvent | null {
  let dataStr = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('data:')) {
      dataStr += line.slice(5).trim()
    }
  }
  if (!dataStr) return null
  try {
    return JSON.parse(dataStr) as StreamEvent
  } catch {
    return null
  }
}

function isAbort(error: unknown, signal?: AbortSignal): boolean {
  return !!signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')
}

/**
 * Generate a trip plan while streaming progress over SSE.
 *
 * Calls `onEvent` for every frame (progress/result/error) and resolves with the
 * TripPlan carried by the first successful `result` frame once the stream ends.
 * Rejects with a StreamError for every failure path. Note: the axios timeout
 * above does not apply here; this uses fetch and has no client-side deadline.
 */
export async function streamTripPlan(
  formData: TripFormData,
  onEvent: (event: StreamEvent) => void,
  options: StreamOptions = {}
): Promise<TripPlan> {
  const { signal } = options
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/trip/plan/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
      signal
    })
  } catch (error) {
    if (isAbort(error, signal)) throw new StreamError('aborted', 'Request aborted')
    throw new StreamError('network', (error as Error)?.message || 'Network error')
  }

  if (!response.ok || !response.body) {
    throw new StreamError('http', `Stream request failed: ${response.status}`, response.status)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: TripPlan | null = null
  let sawResult = false

  const handleFrame = (frame: string) => {
    const event = parseSseFrame(frame)
    if (!event) return
    // Ignore anything after the first result frame (duplicates, stray progress).
    if (sawResult) return
    onEvent(event)
    if (event.type === 'error') {
      throw new StreamError('sse', event.message || 'Stream reported an error')
    }
    if (event.type === 'result') {
      sawResult = true
      if (event.success === false || !isUsablePlan(event.data)) {
        throw new StreamError('failed', event.message || 'The planner returned no usable plan')
      }
      result = event.data
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE frames are separated by a blank line; keep the trailing partial frame.
      const frames = buffer.replace(/\r\n/g, '\n').split('\n\n')
      buffer = frames.pop() ?? ''
      for (const frame of frames) handleFrame(frame)
    }
    buffer += decoder.decode()
    if (buffer.trim()) handleFrame(buffer)
  } catch (error) {
    reader.cancel().catch(() => {})
    if (error instanceof StreamError) throw error
    if (isAbort(error, signal)) throw new StreamError('aborted', 'Request aborted')
    throw new StreamError('network', (error as Error)?.message || 'Connection lost')
  }

  if (!result) {
    throw new StreamError('no_result', 'Stream ended without a result')
  }
  return result
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export default apiClient
