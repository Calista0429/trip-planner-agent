import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Antd from 'ant-design-vue'
import { defineComponent, h, inject } from 'vue'
import App from '@/App.vue'
import { setLocale } from '@/i18n'
import { SHELL_NAVIGATION_BLOCKED } from '@/services/shellNavigation'
import { installMatchMedia } from './helpers/matchMedia'

const Blank = defineComponent({ render: () => h('div', { class: 'page' }) })
// A page that holds the shell lock, like Home while the plan is generated.
const Locking = defineComponent({
  setup() {
    const blocked = inject(SHELL_NAVIGATION_BLOCKED)
    if (blocked) blocked.value = true
    return () => h('div', { class: 'locking' })
  }
})

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: Blank },
      { path: '/albums', name: 'AlbumWorkspace', component: Blank },
      { path: '/albums/library', name: 'AlbumLibrary', component: Blank },
      { path: '/result', name: 'Result', component: Blank },
      { path: '/credits', name: 'Credits', component: Blank },
      { path: '/locking', name: 'Locking', component: Locking }
    ]
  })
}

async function mountApp(path: string, mobile = false) {
  const media = installMatchMedia(mobile)
  const router = makeRouter()
  router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router, Antd] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router, media }
}

const drawerMenu = () => document.querySelector('.app-drawer .side-menu')

beforeEach(() => localStorage.clear())
afterEach(() => {
  setLocale('zh')
  document.body.innerHTML = ''
})

describe('App shell', () => {
  it('shows the bookmark menu in a desktop sidebar instead of the old top nav', async () => {
    const { wrapper } = await mountApp('/')
    expect(wrapper.find('.product-nav').exists()).toBe(false)
    expect(wrapper.find('aside.app-sidebar .side-menu').exists()).toBe(true)
    expect(wrapper.find('button.menu-button').exists()).toBe(false)
    expect(wrapper.findAll('main#main')).toHaveLength(1)
    expect(wrapper.find('.brand').text()).toContain('Trip Planner')
    wrapper.unmount()
  })

  it('renders the next page after leaving a real album page (single-root views in the route transition)', async () => {
    const { default: AlbumWorkspace } = await import('@/views/AlbumWorkspace.vue')
    const { default: AlbumLibrary } = await import('@/views/AlbumLibrary.vue')
    installMatchMedia(false)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'Home', component: Blank },
        { path: '/albums', name: 'AlbumWorkspace', component: AlbumWorkspace },
        { path: '/albums/library', name: 'AlbumLibrary', component: AlbumLibrary },
        { path: '/result', name: 'Result', component: Blank },
        { path: '/credits', name: 'Credits', component: Blank }
      ]
    })
    router.push('/albums')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router, Antd] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('#album-workspace-title').exists()).toBe(true)

    await router.push('/albums/library')
    await flushPromises()
    expect(wrapper.find('#album-library-title').exists()).toBe(true)
    await router.push('/')
    await flushPromises()
    expect(wrapper.find('main .page').exists()).toBe(true)
    wrapper.unmount()
  })

  it('collapses the desktop sidebar and remembers it', async () => {
    const { wrapper } = await mountApp('/')
    await wrapper.find('button.side-collapse').trigger('click')
    expect(wrapper.find('.app-body').classes()).toContain('is-collapsed')
    expect(localStorage.getItem('tripPlanner.sidebarCollapsed.v1')).toBe('true')
    wrapper.unmount()
  })

  it('switches every shell label with the locale', async () => {
    const { wrapper } = await mountApp('/', true)
    const button = wrapper.find('button.menu-button')
    expect(button.attributes('aria-label')).toBe('打开菜单')
    await wrapper.find('.lang-switch button[lang="en"]').trigger('click')
    expect(button.attributes('aria-label')).toBe('Open menu')
    wrapper.unmount()
  })

  it('opens the mobile drawer and closes it only after a successful navigation', async () => {
    const { wrapper, router } = await mountApp('/', true)
    expect(wrapper.find('aside.app-sidebar').exists()).toBe(false)
    const button = wrapper.find('button.menu-button')
    expect(button.attributes('aria-expanded')).toBe('false')

    await button.trigger('click')
    await flushPromises()
    expect(button.attributes('aria-expanded')).toBe('true')
    expect(drawerMenu()).not.toBeNull()
    expect(document.querySelector('.app-drawer .side-collapse')).toBeNull()

    // A navigation that a guard cancels is not a success: the drawer stays open.
    const remove = router.beforeEach(to => to.name !== 'AlbumLibrary')
    ;(document.querySelector('.app-drawer a[data-route="AlbumLibrary"]') as HTMLElement).click()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Home')
    expect(button.attributes('aria-expanded')).toBe('true')
    remove()

    ;(document.querySelector('.app-drawer a[data-route="AlbumWorkspace"]') as HTMLElement).click()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('AlbumWorkspace')
    expect(button.attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })

  it('stacks the whole drawer (mask included) at 600, below the 1000 planning overlay', async () => {
    const { wrapper } = await mountApp('/', true)
    await wrapper.find('button.menu-button').trigger('click')
    await flushPromises()
    const root = document.querySelector<HTMLElement>('.app-drawer')!
    expect(root.style.zIndex).toBe('600')
    // A z-index on the panel alone would put it under its own mask (Ant Design's 1000).
    expect(document.querySelector<HTMLElement>('.app-drawer .ant-drawer-content-wrapper')!.style.zIndex).toBe('')
    wrapper.unmount()
  })

  it('re-selecting the current entry closes the drawer and keeps ?day', async () => {
    const { wrapper, router } = await mountApp('/result?day=2', true)
    await wrapper.find('button.menu-button').trigger('click')
    await flushPromises()
    ;(document.querySelector('.app-drawer a[data-route="Result"]') as HTMLElement).click()
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/result?day=2')
    expect(wrapper.find('button.menu-button').attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })

  it('closes the drawer when the viewport grows past the breakpoint', async () => {
    const { wrapper, media } = await mountApp('/', true)
    await wrapper.find('button.menu-button').trigger('click')
    await flushPromises()
    media.setMobile(false)
    await flushPromises()
    expect(wrapper.find('aside.app-sidebar').exists()).toBe(true)
    expect(wrapper.find('button.menu-button').exists()).toBe(false)
    wrapper.unmount()
    expect(media.mobileListeners()).toBe(0)
  })

  it('locks header, sidebar and footer while a page holds the shell lock, but not main', async () => {
    const { wrapper } = await mountApp('/locking')
    expect(wrapper.find('header.app-header').attributes('inert')).toBeDefined()
    expect(wrapper.find('aside.app-sidebar').attributes('inert')).toBeDefined()
    expect(wrapper.find('footer.page-foot').attributes('inert')).toBeDefined()
    expect(wrapper.find('main#main').attributes('inert')).toBeUndefined()
    expect(wrapper.find('a[data-route="Home"]').attributes('aria-disabled')).toBe('true')
    wrapper.unmount()
  })
})
