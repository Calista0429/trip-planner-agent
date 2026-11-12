import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Antd from 'ant-design-vue'
import { defineComponent, h } from 'vue'
import type { StreamEvent, StreamOptions } from '@/services/api'
import type { TripFormData, TripPlan } from '@/types'
import { samplePlan, sampleRequest } from './fixtures'

// Drive the real Home.vue with a controllable stream instead of the network.
const calls: { request: TripFormData; emit: (e: StreamEvent) => void; resolve: (p: TripPlan) => void; reject: (e: unknown) => void; options: StreamOptions }[] = []
vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>()
  return {
    ...actual,
    streamTripPlan: vi.fn(
      (request: TripFormData, emit: (e: StreamEvent) => void, options: StreamOptions) =>
        new Promise<TripPlan>((resolve, reject) => calls.push({ request, emit, resolve, reject, options }))
    )
  }
})

const { StreamError } = await import('@/services/api')
const { default: Home } = await import('@/views/Home.vue')
const { HANDOFF_DELAY_MS } = await import('@/composables/useTripPlanRun')

beforeAll(() => {
  // jsdom lacks these; Ant Design and the carousel query them.
  window.matchMedia ||= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false
  })) as unknown as typeof window.matchMedia
  Element.prototype.scrollIntoView ||= function () {}
})

function makeRouter() {
  const Blank = defineComponent({ render: () => h('div') })
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: Home },
      { path: '/result', name: 'Result', component: Blank }
    ]
  })
}

async function mountHome() {
  const router = makeRouter()
  router.push('/')
  await router.isReady()
  const push = vi.spyOn(router, 'push')
  const wrapper = mount(Home, { global: { plugins: [router, Antd] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, push }
}

async function submit(wrapper: Awaited<ReturnType<typeof mountHome>>['wrapper']) {
  await wrapper.find('form').trigger('submit')
  // Ant Design validates asynchronously before @finish.
  for (let i = 0; i < 10 && calls.length === 0; i++) await flushPromises()
}

beforeEach(() => {
  calls.length = 0
  sessionStorage.clear()
  sessionStorage.setItem('tripRequest', JSON.stringify(sampleRequest))
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('Home.vue with the journey ticket', () => {
  it('sends every request field, shows the ticket, saves once and opens the result once', async () => {
    const { wrapper, push } = await mountHome()
    expect(wrapper.find('.journey-ticket').exists()).toBe(false)

    await submit(wrapper)
    expect(calls).toHaveLength(1)
    expect(calls[0].request).toEqual(sampleRequest)
    await flushPromises()
    expect(wrapper.find('.journey-ticket').exists()).toBe(true)
    expect(wrapper.find('.ticket-summary').text()).toContain('杭州市')
    expect(wrapper.find('button.primary').attributes('disabled')).toBeDefined()

    // A second submit while running is ignored.
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(calls).toHaveLength(1)

    calls[0].emit({ type: 'progress', phase: 'building_query' })
    calls[0].emit({ type: 'progress', phase: 'generating', attempt: 1 })
    await flushPromises()
    expect(wrapper.find('.ticket-title').text()).toBe('正在编排行程')
    expect(sessionStorage.getItem('tripPlanMeta')).toBeNull()

    calls[0].emit({ type: 'result', success: true, status: 'llm_success', message: 'ok', data: samplePlan })
    calls[0].resolve(samplePlan)
    await flushPromises()
    expect(JSON.parse(sessionStorage.getItem('tripPlan')!).city).toBe('杭州市')
    expect(JSON.parse(sessionStorage.getItem('tripPlanMeta')!)).toEqual({ status: 'llm_success', message: 'ok', switchedModel: false })
    expect(wrapper.find('.ticket-title').text()).toBe('行程已准备好')
    expect(push).not.toHaveBeenCalled()

    await new Promise((r) => setTimeout(r, HANDOFF_DELAY_MS + 50))
    expect(push).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith({ path: '/result', query: { day: '1' } })
    wrapper.unmount()
  })

  it('keeps the error and the form after a failure, then retries manually as a new run', async () => {
    const { wrapper, push } = await mountHome()
    await submit(wrapper)
    calls[0].emit({ type: 'progress', phase: 'collecting_hotels' })
    calls[0].reject(new StreamError('sse', 'LLM timeout'))
    await flushPromises()

    // The old Home cleared the progress after 600ms; the error must persist.
    await new Promise((r) => setTimeout(r, 700))
    expect(wrapper.find('[role="alert"]').text()).toContain('LLM timeout')
    expect(wrapper.find('button.primary').attributes('disabled')).toBeUndefined()
    expect(sessionStorage.getItem('tripPlan')).toBeNull()
    expect(push).not.toHaveBeenCalled()
    expect(calls).toHaveLength(1) // no automatic retry

    await wrapper.find('.ticket-retry').trigger('click')
    for (let i = 0; i < 10 && calls.length < 2; i++) await flushPromises()
    expect(calls).toHaveLength(2)
    expect(calls[1].request).toEqual(sampleRequest) // form values were kept
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.ticket-title').text()).toBe('正在查找旅行资料')

    // A late event from the failed run does not leak into the retry.
    calls[0].emit({ type: 'progress', phase: 'reranking' })
    await flushPromises()
    expect(wrapper.find('.ticket-title').text()).toBe('正在查找旅行资料')
    wrapper.unmount()
  })

  it('does not navigate or save after leaving the page mid-run', async () => {
    const { wrapper, push } = await mountHome()
    await submit(wrapper)
    wrapper.unmount()
    expect(calls[0].options.signal?.aborted).toBe(true)
    calls[0].emit({ type: 'result', success: true, status: 'llm_success', data: samplePlan })
    calls[0].resolve(samplePlan)
    await flushPromises()
    await new Promise((r) => setTimeout(r, HANDOFF_DELAY_MS + 50))
    expect(push).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('tripPlan')).toBeNull()
  })
})
