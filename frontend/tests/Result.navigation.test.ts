import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import Antd from 'ant-design-vue'
import { defineComponent, h } from 'vue'
import { samplePlan, sampleRequest } from './fixtures'

// The real map needs the Amap JS API; this page test only cares about leaving.
// `snapshot.gate` lets a test hold the export in its map-snapshot phase.
const snapshot = vi.hoisted(() => ({ gate: null as Promise<void> | null }))
vi.mock('@/components/result/TripMap.vue', () => ({
  default: defineComponent({
    name: 'TripMap',
    setup(_, { expose }) {
      expose({
        snapshotAll: async () => {
          if (snapshot.gate) await snapshot.gate
          return null
        }
      })
      return () => h('div', { class: 'trip-map-stub' })
    }
  })
}))

const { default: Result } = await import('@/views/Result.vue')
const { PLANNER_DRAFT_KEY } = await import('@/services/plannerDraft')

beforeAll(() => {
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

beforeEach(() => {
  sessionStorage.clear()
  sessionStorage.setItem('tripPlan', JSON.stringify(samplePlan))
  sessionStorage.setItem('tripRequest', JSON.stringify(sampleRequest))
  vi.stubGlobal('fetch', vi.fn(async () => ({ json: async () => ({}) })))
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

async function mountResult() {
  const Blank = defineComponent({ render: () => h('div', { class: 'blank' }) })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: Blank },
      { path: '/albums', name: 'AlbumWorkspace', component: Blank },
      { path: '/result', name: 'Result', component: Result }
    ]
  })
  router.push('/result?day=1')
  await router.isReady()
  const Shell = defineComponent({ render: () => h(RouterView) })
  const wrapper = mount(Shell, { global: { plugins: [router, Antd] }, attachTo: document.body })
  await flushPromises()
  const page = () => wrapper.findComponent(Result).vm as any
  return { wrapper, router, page }
}

// Closed confirms can linger in the DOM while animating out; use the newest one.
const leaveDialog = () =>
  [...document.querySelectorAll('.ant-modal-confirm')].filter(el => el.textContent?.includes('还有未保存的修改')).pop()
const dialogButton = (label: string) =>
  [...(leaveDialog()?.querySelectorAll('button') ?? [])].find(b => b.textContent?.replace(/\s/g, '') === label) as HTMLButtonElement

async function settle() {
  for (let i = 0; i < 5; i++) await flushPromises()
}

describe('Result.vue leaving the page', () => {
  it('leaves freely without edits, and after entering edit mode without changing anything', async () => {
    const { wrapper, router, page } = await mountResult()
    await router.push('/albums')
    await settle()
    expect(router.currentRoute.value.name).toBe('AlbumWorkspace')

    await router.push('/result')
    await settle()
    page().toggleEditMode()
    await router.push('/albums')
    await settle()
    expect(leaveDialog()).toBeUndefined()
    expect(router.currentRoute.value.name).toBe('AlbumWorkspace')
    wrapper.unmount()
  })

  it('asks before dropping unsaved edits: keep editing stays, discard leaves without saving', async () => {
    const { wrapper, router, page } = await mountResult()
    page().toggleEditMode()
    page().tripPlan.days[0].description = '改过的安排'
    await flushPromises()

    void router.push('/albums')
    await settle()
    expect(leaveDialog()).toBeDefined()
    dialogButton('继续编辑').click()
    await settle()
    expect(router.currentRoute.value.name).toBe('Result')
    expect(page().editMode).toBe(true)
    expect(page().tripPlan.days[0].description).toBe('改过的安排')

    void router.push('/albums')
    await settle()
    dialogButton('放弃修改并离开').click()
    await settle()
    expect(router.currentRoute.value.name).toBe('AlbumWorkspace')
    expect(JSON.parse(sessionStorage.getItem('tripPlan')!).days[0].description).toBe('')
    wrapper.unmount()
  })

  it('does not leave while exporting', async () => {
    const { wrapper, router, page } = await mountResult()
    page().exporting = true
    await router.push('/albums')
    await settle()
    expect(router.currentRoute.value.name).toBe('Result')
    page().exporting = false
    wrapper.unmount()
  })

  it('stays locked for the whole export, including the map snapshot before the sheet renders', async () => {
    let release!: () => void
    snapshot.gate = new Promise<void>(r => (release = r))
    const { wrapper, router, page } = await mountResult()
    void page().exportAsImage()
    await flushPromises()
    await router.push('/albums')
    await settle()
    expect(router.currentRoute.value.name).toBe('Result')
    release()
    snapshot.gate = null
    await settle()
    wrapper.unmount()
  })

  it('"Edit trip details" drops the unsubmitted draft and keeps the submitted request', async () => {
    sessionStorage.setItem(PLANNER_DRAFT_KEY, JSON.stringify({ version: 1 }))
    const { wrapper, router } = await mountResult()
    const button = wrapper.findAll('button').find(b => b.text() === '编辑旅行条件')!
    await button.trigger('click')
    await settle()
    expect(router.currentRoute.value.name).toBe('Home')
    expect(sessionStorage.getItem(PLANNER_DRAFT_KEY)).toBeNull()
    expect(JSON.parse(sessionStorage.getItem('tripRequest')!)).toEqual(sampleRequest)
    wrapper.unmount()
  })
})
