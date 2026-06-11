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
  data?: TripPlan
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

/**
 * Generate a trip plan while streaming progress over SSE.
 *
 * Calls `onEvent` for every frame (progress/result/error) and resolves with the
 * final TripPlan carried by the terminal `result` frame.
 */
export async function streamTripPlan(
  formData: TripFormData,
  onEvent: (event: StreamEvent) => void
): Promise<TripPlan> {
  const response = await fetch(`${API_BASE_URL}/api/trip/plan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(formData)
  })

  if (!response.ok || !response.body) {
    throw new Error(`Stream request failed: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: TripPlan | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line; keep the trailing partial frame.
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      const event = parseSseFrame(frame)
      if (!event) continue
      onEvent(event)
      if (event.type === 'error') {
        throw new Error(event.message || 'Stream reported an error')
      }
      if (event.type === 'result' && event.data) {
        result = event.data
      }
    }
  }

  if (!result) {
    throw new Error('Stream ended without a result')
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
