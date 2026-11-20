import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Antd from 'ant-design-vue'
import { defineComponent, h } from 'vue'
import AppSideMenu from '@/components/layout/AppSideMenu.vue'
import { setLocale } from '@/i18n'

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
})

afterEach(() => {
  setLocale('zh')
  document.body.innerHTML = ''
})

const Blank = defineComponent({ render: () => h('div') })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: Blank },
      { path: '/albums', name: 'AlbumWorkspace', component: Blank },
      { path: '/albums/library', name: 'AlbumLibrary', component: Blank },
      { path: '/result', name: 'Result', component: Blank },
      { path: '/credits', name: 'Credits', component: Blank }
    ]
  })
}

async function mountMenu(path: string, props: Partial<{ collapsed: boolean; mobile: boolean; blocked: boolean }> = {}) {
  const router = makeRouter()
  router.push(path)
  await router.isReady()
  const wrapper = mount(AppSideMenu, {
    props: { collapsed: false, mobile: false, blocked: false, ...props },
    global: { plugins: [router, Antd] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

const current = (wrapper: Awaited<ReturnType<typeof mountMenu>>['wrapper']) =>
  wrapper.findAll('a[aria-current="page"]').map(a => a.attributes('data-route'))

describe('AppSideMenu', () => {
  it('links the four entries to their real paths', async () => {
    const { wrapper } = await mountMenu('/')
    const links = wrapper.findAll('a[data-route]')
    expect(links.map(a => [a.attributes('data-route'), a.attributes('href')])).toEqual([
      ['Home', '/'],
      ['AlbumWorkspace', '/albums'],
      ['Result', '/result'],
      ['AlbumLibrary', '/albums/library']
    ])
    expect(wrapper.text()).toContain('旅行创作')
    expect(wrapper.text()).toContain('我的旅行')
  })

  it.each([
    ['/', ['Home']],
    ['/albums', ['AlbumWorkspace']],
    ['/albums/library', ['AlbumLibrary']],
    ['/result?day=2', ['Result']],
    ['/credits', []]
  ])('marks exactly the current entry on %s', async (path, expected) => {
    const { wrapper } = await mountMenu(path)
    expect(current(wrapper)).toEqual(expected)
  })

  it('navigates on click and emits select', async () => {
    const { wrapper, router } = await mountMenu('/')
    await wrapper.find('a[data-route="AlbumWorkspace"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('AlbumWorkspace')
    expect(wrapper.emitted('select')).toEqual([['AlbumWorkspace']])
    expect(current(wrapper)).toEqual(['AlbumWorkspace'])
  })

  it('keeps ?day when the current itinerary entry is clicked again', async () => {
    const { wrapper, router } = await mountMenu('/result?day=2')
    const link = wrapper.find('a[data-route="Result"]')
    expect(link.attributes('href')).toBe('/result?day=2')
    await link.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/result?day=2')
    expect(wrapper.emitted('select')).toEqual([['Result']])
  })

  it('does not navigate while blocked', async () => {
    const { wrapper, router } = await mountMenu('/', { blocked: true })
    const link = wrapper.find('a[data-route="AlbumLibrary"]')
    expect(link.attributes('aria-disabled')).toBe('true')
    await link.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Home')
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('switches labels and accessible names with the locale, also when collapsed', async () => {
    const { wrapper } = await mountMenu('/', { collapsed: true })
    const name = () => wrapper.find('a[data-route="AlbumWorkspace"]').text()
    expect(name()).toBe('旅行相册')
    expect(wrapper.find('nav').attributes('aria-label')).toBe('功能导航')
    const toggle = wrapper.find('button.side-collapse')
    expect(toggle.attributes('aria-label')).toBe('展开侧栏')
    expect(toggle.attributes('aria-expanded')).toBe('false')

    setLocale('en')
    await flushPromises()
    expect(name()).toBe('Album studio')
    expect(wrapper.find('a[data-route="AlbumLibrary"]').text()).toBe('My albums')
    expect(wrapper.find('nav').attributes('aria-label')).toBe('Main navigation')
    expect(toggle.attributes('aria-label')).toBe('Expand sidebar')
  })

  it('emits toggle-collapse and hides the toggle in the mobile drawer', async () => {
    const { wrapper } = await mountMenu('/')
    await wrapper.find('button.side-collapse').trigger('click')
    expect(wrapper.emitted('toggle-collapse')).toHaveLength(1)

    const mobile = await mountMenu('/', { mobile: true })
    expect(mobile.wrapper.find('button.side-collapse').exists()).toBe(false)
  })
})
