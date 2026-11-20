import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import Antd from 'ant-design-vue'
import { defineComponent, h, provide, ref } from 'vue'
import type { Album } from '@/types'
import { SHELL_NAVIGATION_BLOCKED } from '@/services/shellNavigation'
import { ALBUM_LIBRARY_KEY, loadAlbums } from '@/services/albumLibrary'
import { setLocale } from '@/i18n'

const upload = vi.hoisted(() => ({ fn: null as unknown as ReturnType<typeof vi.fn> }))
vi.mock('@/services/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/api')>()
  upload.fn = vi.fn()
  return { ...actual, uploadAlbumPhotos: (...args: unknown[]) => upload.fn(...args) }
})

const { AlbumUploadError } = await import('@/services/api')
const { default: AlbumWorkspace } = await import('@/views/AlbumWorkspace.vue')
const { default: AlbumView } = await import('@/components/album/AlbumView.vue')

const album: Album = {
  tripId: 'k7Q',
  title: 'KUNMING IN BLOOM',
  style: 'watercolor-journal',
  pictures: [
    { imageUrl: 'https://storage.googleapis.com/b/1.png/0', description: 'Green Lake', location: 'Kunming', pointsOfInterest: '- **Yuantong Temple**: old temple' }
  ],
  failed: [{ file: 'blurry.png', reason: 'timeout' }],
  createdAt: '2026-11-20T08:00:00.000Z'
}

let urlCount = 0
const createObjectURL = vi.fn(() => `blob:thumb-${++urlCount}`)
const revokeObjectURL = vi.fn()

beforeAll(() => {
  Object.assign(URL, { createObjectURL, revokeObjectURL })
})

beforeEach(() => {
  localStorage.clear()
  urlCount = 0
  createObjectURL.mockClear()
  revokeObjectURL.mockClear()
  upload.fn.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
  setLocale('zh')
  document.body.innerHTML = ''
})

const photo = (name: string, type = 'image/png', size = 4) => {
  const file = new File(['x'.repeat(Math.min(size, 16))], name, { type })
  if (size > 16) Object.defineProperty(file, 'size', { value: size })
  return file
}

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)))
  return { promise, resolve, reject }
}

async function mountPage() {
  const Blank = defineComponent({ render: () => h('div', { class: 'blank' }) })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: Blank },
      { path: '/albums', name: 'AlbumWorkspace', component: AlbumWorkspace },
      { path: '/albums/library', name: 'AlbumLibrary', component: Blank }
    ]
  })
  const blocked = ref(false)
  const Shell = defineComponent({
    setup() {
      provide(SHELL_NAVIGATION_BLOCKED, blocked)
      return () => h(RouterView)
    }
  })
  router.push('/albums')
  await router.isReady()
  const wrapper = mount(Shell, { global: { plugins: [router, Antd] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router, blocked }
}

async function pick(wrapper: VueWrapper, files: File[]) {
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  await input.trigger('change')
  await flushPromises()
}

const thumbs = (wrapper: VueWrapper) => wrapper.findAll('.album-thumb')
const generateButton = (wrapper: VueWrapper) => wrapper.find('button.album-generate')

describe('AlbumWorkspace (/albums)', () => {
  it('keeps the page title id the shell relies on', async () => {
    const { wrapper } = await mountPage()
    expect(wrapper.find('#album-workspace-title').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows a thumbnail per picked photo and revokes the URL of a removed one', async () => {
    const { wrapper } = await mountPage()
    await pick(wrapper, [photo('a.png'), photo('b.jpg', 'image/jpeg')])
    expect(thumbs(wrapper)).toHaveLength(2)

    await thumbs(wrapper)[0].find('button.album-thumb-remove').trigger('click')

    expect(thumbs(wrapper)).toHaveLength(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:thumb-1')
    wrapper.unmount()
  })

  it('refuses non-images (including a typeless .heic), oversized photos and an eleventh photo', async () => {
    const { wrapper } = await mountPage()
    await pick(wrapper, [photo('IMG_1.heic', ''), photo('notes.txt', 'text/plain')])
    expect(thumbs(wrapper)).toHaveLength(0)
    expect(wrapper.find('.album-notice').text()).toContain('只能选择图片')

    await pick(wrapper, [photo('huge.png', 'image/png', 15 * 1024 * 1024 + 1)])
    expect(thumbs(wrapper)).toHaveLength(0)
    expect(wrapper.find('.album-notice').text()).toContain('15MB')

    await pick(wrapper, Array.from({ length: 11 }, (_, i) => photo(`p${i}.png`)))
    expect(thumbs(wrapper)).toHaveLength(10)
    expect(wrapper.find('.album-notice').text()).toContain('10')
    wrapper.unmount()
  })

  it('refuses a photo that would take the album past 95MB in total', async () => {
    const { wrapper } = await mountPage()
    const big = (i: number) => photo(`big${i}.jpg`, 'image/jpeg', 14 * 1024 * 1024)

    await pick(wrapper, Array.from({ length: 7 }, (_, i) => big(i)))

    expect(thumbs(wrapper)).toHaveLength(6)
    expect(wrapper.find('.album-notice').text()).toContain('95MB')
    expect(wrapper.find('.album-notice').text()).toContain('big6.jpg')
    wrapper.unmount()
  })

  it('explains a request that was too large in total', async () => {
    upload.fn.mockRejectedValueOnce(new AlbumUploadError('total_too_large'))
    const { wrapper } = await mountPage()
    await pick(wrapper, [photo('a.png')])

    await generateButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.find('.album-error').text()).toContain('95MB')
    wrapper.unmount()
  })

  it('clears the file input so the same photo can be picked again', async () => {
    const { wrapper } = await mountPage()
    await pick(wrapper, [photo('a.png')])
    expect((wrapper.find('input[type="file"]').element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it('cannot generate without photos', async () => {
    const { wrapper } = await mountPage()
    expect(generateButton(wrapper).attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('locks the shell and blocks leaving while the album is generated, then shows and saves it', async () => {
    const pending = deferred<Album>()
    upload.fn.mockReturnValue(pending.promise)
    const { wrapper, router, blocked } = await mountPage()
    const files = [photo('a.png'), photo('b.png')]
    await pick(wrapper, files)
    await wrapper.find('input[type="radio"][value="watercolor-journal"]').setValue(true)

    await generateButton(wrapper).trigger('click')
    await flushPromises()

    expect(upload.fn).toHaveBeenCalledWith(files, 'watercolor-journal')
    expect(generateButton(wrapper).attributes('aria-busy')).toBe('true')
    expect(wrapper.find('.album-generating').exists()).toBe(true)
    expect(blocked.value).toBe(true)
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('AlbumWorkspace')

    pending.resolve(album)
    await flushPromises()

    expect(blocked.value).toBe(false)
    expect(wrapper.find('.album-generating').exists()).toBe(false)
    expect(wrapper.findComponent(AlbumView).exists()).toBe(true)
    expect(wrapper.find('.album-view img').attributes('src')).toBe(album.pictures[0].imageUrl)
    expect(loadAlbums().map(a => a.tripId)).toEqual(['k7Q'])
    expect(wrapper.find('a.album-open-library').attributes('href')).toBe('/albums/library?album=k7Q')
    expect(wrapper.find('.album-partial').text()).toContain('blurry.png')
    expect(wrapper.find('.album-partial').text()).toContain('超时')

    await router.push('/')
    expect(router.currentRoute.value.name).toBe('Home')
    wrapper.unmount()
  })

  it('still shows the album when this browser cannot keep it', async () => {
    upload.fn.mockResolvedValue(album)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })
    const { wrapper } = await mountPage()
    await pick(wrapper, [photo('a.png')])

    await generateButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(AlbumView).exists()).toBe(true)
    expect(wrapper.find('.album-save-failed').exists()).toBe(true)
    expect(localStorage.getItem(ALBUM_LIBRARY_KEY)).toBeNull()
    wrapper.unmount()
  })

  it('explains a failure, keeps the photos and lets the user try again', async () => {
    upload.fn.mockRejectedValueOnce(new AlbumUploadError('comic_timeout'))
    const { wrapper, blocked } = await mountPage()
    await pick(wrapper, [photo('a.png')])

    await generateButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.find('.album-error').text()).toContain('超时')
    expect(thumbs(wrapper)).toHaveLength(1)
    expect(blocked.value).toBe(false)
    expect(generateButton(wrapper).attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('lists every photo that failed when none could be drawn', async () => {
    upload.fn.mockRejectedValueOnce(new AlbumUploadError('all_failed', [{ file: 'a.png', reason: 'billing' }]))
    const { wrapper } = await mountPage()
    await pick(wrapper, [photo('a.png')])

    await generateButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.find('.album-error').text()).toContain('a.png')
    expect(wrapper.find('.album-error').text()).toContain('额度')
    wrapper.unmount()
  })

  it('revokes every thumbnail URL when the page goes away', async () => {
    const { wrapper } = await mountPage()
    await pick(wrapper, [photo('a.png'), photo('b.png')])

    wrapper.unmount()

    expect(revokeObjectURL).toHaveBeenCalledWith('blob:thumb-1')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:thumb-2')
  })

  it('switches its labels with the locale', async () => {
    const { wrapper } = await mountPage()
    setLocale('en')
    await flushPromises()
    expect(generateButton(wrapper).text()).toBe('Create album')
    wrapper.unmount()
  })
})

describe('AlbumView', () => {
  it('renders model text as text, never as HTML', () => {
    const wrapper = mount(AlbumView, {
      props: { album: { ...album, pictures: [{ ...album.pictures[0], description: '<b>bold</b>' }] } }
    })
    expect(wrapper.find('.album-picture').text()).toContain('<b>bold</b>')
    expect(wrapper.find('.album-picture b').exists()).toBe(false)
    expect(wrapper.find('.album-poi').text()).toContain('Yuantong Temple')
  })
})
