import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import Antd from 'ant-design-vue'
import { defineComponent, h } from 'vue'
import type { Album } from '@/types'
import { getAlbum, saveAlbum } from '@/services/albumLibrary'
import AlbumLibrary from '@/views/AlbumLibrary.vue'
import AlbumView from '@/components/album/AlbumView.vue'

const album = (tripId: string, title: string, createdAt: string): Album => ({
  tripId,
  title,
  style: 'retro-film',
  pictures: [
    { imageUrl: `https://storage.googleapis.com/b/${tripId}-1.png/0`, description: 'd', location: 'Kunming', pointsOfInterest: '' },
    { imageUrl: `https://storage.googleapis.com/b/${tripId}-2.png/0`, description: 'd', location: 'Dali', pointsOfInterest: '' }
  ],
  failed: [],
  createdAt
})

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

beforeEach(() => localStorage.clear())
afterEach(() => {
  document.body.innerHTML = ''
})

async function mountLibrary(path = '/albums/library') {
  const Blank = defineComponent({ render: () => h('div', { class: 'blank' }) })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/albums', name: 'AlbumWorkspace', component: Blank },
      { path: '/albums/library', name: 'AlbumLibrary', component: AlbumLibrary }
    ]
  })
  router.push(path)
  await router.isReady()
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    global: { plugins: [router, Antd] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

async function settle() {
  for (let i = 0; i < 5; i++) await flushPromises()
}

const removeDialog = () =>
  [...document.querySelectorAll('.ant-modal-confirm')].filter(el => el.textContent?.includes('移除这本相册')).pop()
const dialogButton = (label: string) =>
  [...(removeDialog()?.querySelectorAll('button') ?? [])].find(b => b.textContent?.replace(/\s/g, '') === label) as HTMLButtonElement
const cards = (wrapper: VueWrapper) => wrapper.findAll('.album-card')

describe('AlbumLibrary (/albums/library)', () => {
  it('keeps the page title id the shell relies on and says albums live in this browser', async () => {
    const { wrapper } = await mountLibrary()
    expect(wrapper.find('#album-library-title').exists()).toBe(true)
    expect(wrapper.find('.album-local-note').text()).toContain('本浏览器')
    wrapper.unmount()
  })

  it('shows an empty state that links to the album workspace', async () => {
    const { wrapper } = await mountLibrary()
    expect(cards(wrapper)).toHaveLength(0)
    expect(wrapper.find('.album-empty').exists()).toBe(true)
    expect(wrapper.find('.album-empty a').attributes('href')).toBe('/albums')
    wrapper.unmount()
  })

  it('lists saved albums newest first with cover, title, style, date and picture count', async () => {
    saveAlbum(album('old', 'Old trip', '2026-10-01T08:00:00.000Z'))
    saveAlbum(album('new', 'New trip', '2026-11-20T08:00:00.000Z'))
    const { wrapper } = await mountLibrary()

    expect(cards(wrapper).map(c => c.find('.album-card-title').text())).toEqual(['New trip', 'Old trip'])
    const first = cards(wrapper)[0]
    expect(first.find('img').attributes('src')).toBe('https://storage.googleapis.com/b/new-1.png/0')
    expect(first.text()).toContain('复古胶片')
    expect(first.text()).toContain('2026年11月20日')
    expect(first.text()).toContain('2 张')
    wrapper.unmount()
  })

  it('opens an album from its card and goes back to the list', async () => {
    saveAlbum(album('k7Q', 'Kunming', '2026-11-20T08:00:00.000Z'))
    const { wrapper, router } = await mountLibrary()

    await cards(wrapper)[0].find('a').trigger('click')
    await settle()

    expect(router.currentRoute.value.fullPath).toBe('/albums/library?album=k7Q')
    expect(router.currentRoute.value.name).toBe('AlbumLibrary')
    expect(wrapper.findComponent(AlbumView).exists()).toBe(true)

    await wrapper.find('a.album-back').trigger('click')
    await settle()
    expect(router.currentRoute.value.fullPath).toBe('/albums/library')
    expect(cards(wrapper)).toHaveLength(1)
    wrapper.unmount()
  })

  it('says so when the album is not in this browser', async () => {
    const { wrapper } = await mountLibrary('/albums/library?album=missing')
    expect(wrapper.find('.album-not-found').exists()).toBe(true)
    expect(wrapper.find('.album-not-found a').attributes('href')).toBe('/albums/library')
    wrapper.unmount()
  })

  it('removes an album from this browser only after confirming, and keeps it on cancel', async () => {
    saveAlbum(album('k7Q', 'Kunming', '2026-11-20T08:00:00.000Z'))
    const { wrapper, router } = await mountLibrary('/albums/library?album=k7Q')

    await wrapper.find('button.album-remove').trigger('click')
    await settle()
    expect(removeDialog()?.textContent).toContain('服务器')
    dialogButton('取消').click()
    await settle()
    expect(getAlbum('k7Q')).not.toBeNull()

    await wrapper.find('button.album-remove').trigger('click')
    await settle()
    dialogButton('移除').click()
    await settle()

    expect(getAlbum('k7Q')).toBeNull()
    expect(router.currentRoute.value.fullPath).toBe('/albums/library')
    expect(wrapper.find('.album-empty').exists()).toBe(true)
    wrapper.unmount()
  })
})
