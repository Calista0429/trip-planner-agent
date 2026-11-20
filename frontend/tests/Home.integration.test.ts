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
const { routeTransition, clearRouteTransition } = await import('@/services/routeTransition')

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
  clearRouteTransition()
  calls.length = 0
  sessionStorage.clear()
  sessionStorage.setItem('tripRequest', JSON.stringify(sampleRequest))
})

afterEach(() => {
  document.body.innerHTML = ''
})

// These drive the real Ant Design form end to end (~3s each alone); under a full
// parallel run they can pass the 5s default, so they get more room.
describe('Home.vue with the journey ticket', { timeout: 15_000 }, () => {
  it('sends every request field, shows the ticket, saves once and opens the result once', async () => {
    const { wrapper, push } = await mountHome()
    expect(wrapper.find('.journey-ticket').exists()).toBe(false)

    await submit(wrapper)
    expect(calls).toHaveLength(1)
    expect(calls[0].request).toEqual(sampleRequest)
    await flushPromises()
    expect(wrapper.find('.journey-ticket').exists()).toBe(true)
    const dialog = wrapper.find('[role="dialog"]')
    expect(dialog.attributes('aria-modal')).toBe('true')
    expect(dialog.attributes('aria-labelledby')).toBe(wrapper.find('.ticket-title').attributes('id'))
    expect(wrapper.find('section.home-layout').attributes('inert')).toBeDefined()
    expect(document.documentElement.style.overflow).toBe('hidden')
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
    expect(routeTransition.value).toBe('')

    await new Promise((r) => setTimeout(r, HANDOFF_DELAY_MS + 50))
    expect(push).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith({ path: '/result', query: { day: '1' } })
    expect(routeTransition.value).toBe('trip-reveal')
    wrapper.unmount()
    expect(document.documentElement.style.overflow).toBe('')
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

  it('"back to edit" closes the overlay, unlocks the page and focuses the submit button', async () => {
    const { wrapper } = await mountHome()
    await submit(wrapper)
    calls[0].reject(new StreamError('no_result', 'ended'))
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('连接在返回行程之前结束了')
    expect(document.activeElement?.classList.contains('ticket-retry')).toBe(true)

    await wrapper.find('.ticket-edit').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('section.home-layout').attributes('inert')).toBeUndefined()
    expect(document.documentElement.style.overflow).toBe('')
    expect(document.activeElement).toBe(wrapper.find('button.primary').element)
    expect(wrapper.find('button.primary').attributes('disabled')).toBeUndefined()
    expect(calls).toHaveLength(1)
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

// ---- Side-menu navigation: unsubmitted draft, generation lock ----

const { PLANNER_DRAFT_KEY } = await import('@/services/plannerDraft')
const { RouterView } = await import('vue-router')

async function mountShell(start = '/') {
  const Blank = defineComponent({ render: () => h('div', { class: 'blank' }) })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: Home },
      { path: '/albums', name: 'AlbumWorkspace', component: Blank },
      { path: '/result', name: 'Result', component: Blank }
    ]
  })
  router.push(start)
  await router.isReady()
  const Shell = defineComponent({ render: () => h(RouterView) })
  const wrapper = mount(Shell, { global: { plugins: [router, Antd] }, attachTo: document.body })
  await flushPromises()
  const home = () => wrapper.findComponent(Home).vm as any
  return { wrapper, router, home }
}

async function go(router: ReturnType<typeof createRouter>, path: string) {
  await router.push(path)
  await flushPromises()
}

describe('Home.vue drafts and leaving the page', { timeout: 15_000 }, () => {
  it('keeps unsubmitted edits when leaving right away and coming back', async () => {
    const { wrapper, router, home } = await mountShell()
    home().formData.free_text_input = '想看日落'
    home().formData.start_date = null
    home().formData.budget_constraint.amount = 0
    await flushPromises()
    home().formData.party.companion_type = 'friends' // picked by hand, differs from the 2-adult default
    home().optionsOpen = true
    await flushPromises()

    await go(router, '/albums') // before the 200ms debounce fires
    expect(wrapper.find('.blank').exists()).toBe(true)
    await go(router, '/')

    const form = home().formData
    expect(form.free_text_input).toBe('想看日落')
    expect(form.start_date).toBeNull()
    expect(form.end_date.format('YYYY-MM-DD')).toBe('2026-11-21')
    expect(form.budget_constraint.amount).toBe(0)
    expect(home().strictBudget).toBe(true)
    expect(form.party.companion_type).toBe('friends')
    expect(home().optionsOpen).toBe(true)
    expect(JSON.parse(sessionStorage.getItem('tripRequest')!)).toEqual(sampleRequest)
    wrapper.unmount()
  })

  it('keeps a province-only form', async () => {
    sessionStorage.clear()
    const { wrapper, router, home } = await mountShell()
    home().provinceCode = '330000'
    await flushPromises()
    await go(router, '/albums')
    await go(router, '/')
    expect(home().provinceCode).toBe('330000')
    expect(home().formData.city).toBe('')
    wrapper.unmount()
  })

  it('falls back to the submitted request when the draft is corrupt', async () => {
    sessionStorage.setItem(PLANNER_DRAFT_KEY, '{"version":1,')
    const { wrapper, home } = await mountShell()
    expect(home().formData.city).toBe('杭州市')
    expect(home().formData.party.adults).toBe(2)
    wrapper.unmount()
  })

  it('blocks leaving while running, then hands off once and clears the draft', async () => {
    const { wrapper, router, home } = await mountShell('/albums')
    await go(router, '/')
    home().formData.free_text_input = '安静一点'
    await submit(wrapper as never)
    expect(calls).toHaveLength(1)

    await go(router, '/albums')
    expect(router.currentRoute.value.name).toBe('Home')
    router.back()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Home')

    calls[0].emit({ type: 'result', success: true, status: 'fallback_success', data: samplePlan })
    calls[0].resolve(samplePlan)
    await flushPromises()
    // Still locked during the hand-off pause.
    await go(router, '/albums')
    expect(router.currentRoute.value.name).toBe('Home')

    await new Promise((r) => setTimeout(r, HANDOFF_DELAY_MS + 50))
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/result?day=1')
    expect(calls).toHaveLength(1)
    expect(sessionStorage.getItem(PLANNER_DRAFT_KEY)).toBeNull()
    expect(JSON.parse(sessionStorage.getItem('tripRequest')!).free_text_input).toBe('安静一点')
    wrapper.unmount()
  })

  it('allows leaving after a failure and keeps the input', async () => {
    const { wrapper, router, home } = await mountShell()
    home().formData.free_text_input = '再试一次'
    await submit(wrapper as never)
    calls[0].reject(new StreamError('sse', 'LLM timeout'))
    await flushPromises()
    await go(router, '/albums')
    expect(router.currentRoute.value.name).toBe('AlbumWorkspace')
    await go(router, '/')
    expect(home().formData.free_text_input).toBe('再试一次')
    wrapper.unmount()
  })
})
