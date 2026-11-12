<template>
  <figure
    class="inspiration"
    role="region"
    :aria-roledescription="t('carousel.roleDescription')"
    :aria-label="t('carousel.region')"
  >
    <div class="camera-shell">
      <div class="camera-viewfinder" aria-hidden="true"></div>
      <span class="camera-shutter" aria-hidden="true"></span>
      <div class="camera-body">
        <div class="camera-screen">
          <div class="photo-window" :aria-busy="busy ? 'true' : 'false'">
            <img
              ref="layer0"
              class="destination-photo"
              alt=""
              width="1100"
              height="800"
              fetchpriority="high"
              decoding="async"
            />
            <img
              ref="layer1"
              class="destination-photo"
              alt=""
              width="1100"
              height="800"
              decoding="async"
            />
            <p v-if="status === 'failed'" class="photo-fallback">{{ t('carousel.unavailable') }}</p>
          </div>
        </div>
        <span class="camera-grip" aria-hidden="true"></span>
        <div class="camera-controls" aria-hidden="true">
          <span class="camera-dial"></span>
          <span class="camera-control-mark"></span>
          <span class="camera-control-dot"></span>
        </div>
        <span class="camera-thumb-rest" aria-hidden="true"></span>
      </div>
    </div>

    <figcaption
      ref="captionEl"
      class="photo-caption"
      @focusin="onCaptionFocus(true)"
      @focusout="onCaptionFocus(false)"
    >
      <template v-if="caption">
        <div class="photo-location">
          <span>{{ caption.province }}</span>
          <template v-if="caption.city">
            <i aria-hidden="true"></i>
            <span>{{ caption.city }}</span>
          </template>
        </div>
        <h2 class="serif">{{ caption.title }}</h2>
        <p class="photo-description">{{ caption.description }}</p>
        <p class="image-credit">
          {{ t('carousel.photoBy') }}<a
            :href="caption.source"
            :title="caption.creditFull"
            target="_blank"
            rel="noopener noreferrer"
          >{{ caption.credit }}</a>
          <a
            v-if="caption.licenseUrl"
            class="license"
            :href="caption.licenseUrl"
            :title="caption.licenseFull"
            target="_blank"
            rel="noopener noreferrer"
          >{{ caption.license }}</a>
          <router-link v-else class="license" to="/credits" :title="caption.licenseFull">
            {{ caption.license }}
          </router-link>
        </p>
      </template>
    </figcaption>
  </figure>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { locale, t } from '@/i18n'
import {
  DESTINATIONS,
  creditLabel,
  licenseLabel,
  licenseUrl,
  shortRegionName,
  type Destination
} from '@/data/destinations'

const HOLD_MS = 6000
const FADE_MS = 1400
const LOAD_TIMEOUT_MS = 12000

const slides = DESTINATIONS
const layer0 = ref<HTMLImageElement | null>(null)
const layer1 = ref<HTMLImageElement | null>(null)
const captionEl = ref<HTMLElement | null>(null)

/** Index of the slide whose caption is shown (null until the first photo loads). */
const captionIndex = ref<number | null>(null)
const status = ref<'loading' | 'ready' | 'failed'>('loading')
const busy = ref(false)

let current = 0
let activeLayer = 0
let timer: ReturnType<typeof setTimeout> | null = null
let epoch = 0
let disposed = false
let captionFocused = false
let animations: Animation[] = []
let warm: { index: number; ready: Promise<boolean> } | null = null
const motion = window.matchMedia('(prefers-reduced-motion: reduce)')

const caption = computed(() => {
  if (captionIndex.value === null) return null
  const slide = slides[captionIndex.value]
  const en = locale.value === 'en'
  const province = en ? slide.en.province : shortRegionName(slide.province)
  const city = en ? slide.en.city : slide.city
  return {
    province,
    city: shortRegionName(city) === shortRegionName(province) || city === province ? '' : city,
    title: en ? slide.en.title : slide.title || slide.landmark,
    description: en ? slide.en.description : slide.description,
    source: slide.source,
    credit: creditLabel(slide),
    creditFull: slide.credit,
    license: licenseLabel(slide),
    licenseUrl: licenseUrl(slide),
    licenseFull: slide.license
  }
})

const layers = () => [layer0.value, layer1.value] as const

function altFor(slide: Destination): string {
  return locale.value === 'en'
    ? t('carousel.photoAlt', { province: slide.en.province, landmark: slide.en.title })
    : t('carousel.photoAlt', { province: slide.province, landmark: slide.landmark })
}

function setPhoto(img: HTMLImageElement, index: number) {
  const slide = slides[index]
  img.src = slide.image
  img.alt = altFor(slide)
  img.dataset.slide = String(index)
  img.style.objectPosition = slide.objectPosition || 'center'
}

/** Resolve true when the image is decodable, false on error/timeout. Never rejects. */
function loadPhoto(index: number): Promise<boolean> {
  return new Promise(resolve => {
    const image = new Image()
    let settled = false
    const settle = (ok: boolean) => {
      if (settled) return
      settled = true
      clearTimeout(deadline)
      image.onload = image.onerror = null
      resolve(ok)
    }
    const deadline = setTimeout(() => settle(false), LOAD_TIMEOUT_MS)
    image.decoding = 'async'
    image.onload = async () => {
      if (typeof image.decode === 'function') {
        try {
          await image.decode()
        } catch {
          // onload already confirmed a readable image.
        }
      }
      settle(true)
    }
    image.onerror = () => settle(false)
    image.src = slides[index].image
  })
}

function warmNext() {
  const index = (current + 1) % slides.length
  warm = { index, ready: loadPhoto(index) }
}

const canPlay = () =>
  !disposed &&
  status.value === 'ready' &&
  slides.length > 1 &&
  !document.hidden &&
  !motion.matches &&
  !captionFocused

function schedule() {
  if (timer) clearTimeout(timer)
  timer = null
  if (canPlay() && !busy.value) timer = setTimeout(advance, HOLD_MS)
}

/** Find the next slide that loads, skipping broken images (at most one full lap). */
async function nextLoadable(from: number, runEpoch: number): Promise<number | null> {
  for (let step = 1; step < slides.length; step += 1) {
    const index = (from + step) % slides.length
    const ok = warm && warm.index === index ? await warm.ready : await loadPhoto(index)
    warm = null
    if (runEpoch !== epoch) return null
    if (ok) return index
  }
  return null
}

async function advance() {
  timer = null
  if (busy.value || !canPlay()) return
  busy.value = true
  const runEpoch = epoch
  try {
    const target = await nextLoadable(current, runEpoch)
    if (target === null || runEpoch !== epoch || !canPlay()) return
    const [a, b] = layers()
    if (!a || !b) return
    const incoming = activeLayer === 0 ? b : a
    const outgoing = activeLayer === 0 ? a : b
    setPhoto(incoming, target)
    incoming.style.zIndex = '2'
    incoming.style.opacity = '0'
    outgoing.style.zIndex = '1'
    // The outgoing photo stays fully opaque beneath the incoming layer, so the
    // total brightness never dips during the crossfade.
    outgoing.style.opacity = '1'
    let captionTimer: ReturnType<typeof setTimeout> | null = null
    const cap = captionEl.value
    if (typeof incoming.animate === 'function' && !motion.matches) {
      animations = [
        incoming.animate([{ opacity: 0 }, { opacity: 1 }], {
          duration: FADE_MS,
          easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
          fill: 'forwards'
        })
      ]
      if (cap) {
        animations.push(
          cap.animate(
            [
              { opacity: 1, offset: 0 },
              { opacity: 0, offset: 0.22 },
              { opacity: 0, offset: 0.5 },
              { opacity: 1, offset: 1 }
            ],
            { duration: FADE_MS, easing: 'ease-in-out', fill: 'forwards' }
          )
        )
      }
      captionTimer = setTimeout(() => {
        if (runEpoch === epoch) captionIndex.value = target
      }, FADE_MS / 2)
      await Promise.all(animations.map(animation => animation.finished.catch(() => undefined)))
    }
    if (captionTimer) clearTimeout(captionTimer)
    if (disposed) return
    // Commit the frame even if the run went stale mid-fade: never leave two
    // half-transparent layers.
    captionIndex.value = target
    incoming.style.opacity = '1'
    outgoing.style.opacity = '0'
    incoming.removeAttribute('aria-hidden')
    outgoing.setAttribute('aria-hidden', 'true')
    animations.forEach(animation => animation.cancel())
    animations = []
    activeLayer = activeLayer === 0 ? 1 : 0
    current = target
  } finally {
    busy.value = false
    if (!disposed) {
      warmNext()
      schedule()
    }
  }
}

function syncPlayback() {
  if (!canPlay()) epoch += 1
  if (motion.matches) animations.forEach(animation => animation.finish())
  schedule()
}

function onCaptionFocus(focused: boolean) {
  if (focused) {
    captionFocused = true
    syncPlayback()
    return
  }
  queueMicrotask(() => {
    captionFocused = !!captionEl.value?.contains(document.activeElement)
    syncPlayback()
  })
}

/** The first slide may be broken too: fall through until one loads. */
async function showFirst() {
  const runEpoch = epoch
  for (let index = 0; index < slides.length; index += 1) {
    const ok = await loadPhoto(index)
    if (disposed || runEpoch !== epoch) return
    if (!ok) continue
    const [a, b] = layers()
    if (!a || !b) return
    setPhoto(a, index)
    a.style.opacity = '1'
    a.style.zIndex = '2'
    b.style.opacity = '0'
    b.style.zIndex = '1'
    b.setAttribute('aria-hidden', 'true')
    current = index
    activeLayer = 0
    captionIndex.value = index
    status.value = 'ready'
    warmNext()
    schedule()
    return
  }
  status.value = 'failed'
}

onMounted(() => {
  document.addEventListener('visibilitychange', syncPlayback)
  motion.addEventListener('change', syncPlayback)
  void showFirst()
})

onBeforeUnmount(() => {
  disposed = true
  epoch += 1
  if (timer) clearTimeout(timer)
  timer = null
  animations.forEach(animation => animation.cancel())
  animations = []
  document.removeEventListener('visibilitychange', syncPlayback)
  motion.removeEventListener('change', syncPlayback)
})
</script>

<style scoped>
.inspiration {
  position: relative;
  min-width: 0;
  margin: 0;
  align-self: center;
}

.photo-window {
  position: relative;
  aspect-ratio: 5 / 4;
  overflow: hidden;
  background: #e5eae4;
}

.destination-photo {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  will-change: opacity;
}

.photo-window::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 3;
  border: 1px solid #00000007;
  pointer-events: none;
}

.photo-fallback {
  position: absolute;
  inset: 0;
  z-index: 4;
  display: grid;
  place-items: center;
  margin: 0;
  color: #dbe2d6;
  font-size: 12px;
}

.photo-caption {
  min-height: 205px;
  padding: 17px 4px 0;
  text-align: center;
}

.photo-location {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 11px;
}

.photo-location i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #9aa89d;
}

.photo-caption h2 {
  margin: 0 0 6px;
  font-size: 27px;
  line-height: 1.45;
  letter-spacing: 1px;
  color: var(--ink);
}

.photo-description {
  max-width: 355px;
  min-height: 44px;
  margin: 0 auto;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.85;
}

.image-credit {
  margin: 10px 0 0;
  color: #6f7c71;
  font-size: 10px;
  line-height: 1.8;
  text-align: center;
  overflow-wrap: anywhere;
}

.image-credit a {
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid #c8d2c8;
}

.image-credit .license {
  display: block;
  width: max-content;
  max-width: 100%;
  margin: 3px auto 0;
  font-size: 9px;
}

/* Camera back: the photo is the LCD; every part is static decoration. */
.camera-shell {
  position: relative;
  width: 100%;
  padding-top: 21px;
}

.camera-body {
  position: relative;
  min-width: 0;
  padding: 27px 48px 19px 17px;
  border: 1px solid #788375;
  border-radius: 13px;
  background: linear-gradient(155deg, #d0d6ca 0%, #c1cabc 58%, #b8c2b2 100%);
  box-shadow: inset 0 1px 0 #edf0e7, 0 5px 12px #3445310a;
}

.camera-body::before,
.camera-body::after {
  content: '';
  position: absolute;
  left: 8px;
  width: 3px;
  height: 3px;
  border: 1px solid #8a9584;
  border-radius: 50%;
  background: #b7c0af;
}

.camera-body::before {
  top: 10px;
}

.camera-body::after {
  bottom: 9px;
}

.camera-viewfinder {
  position: absolute;
  z-index: 1;
  left: 41%;
  top: 1px;
  width: 85px;
  max-width: 28%;
  height: 28px;
  border: 1px solid #788375;
  border-bottom: 0;
  border-radius: 8px 8px 0 0;
  background: linear-gradient(#c7d0bf, #b9c3b2);
  transform: translateX(-50%);
  pointer-events: none;
}

.camera-viewfinder::after {
  content: '';
  position: absolute;
  left: 23%;
  right: 23%;
  top: 7px;
  height: 11px;
  border: 2px solid #919e88;
  border-radius: 3px;
  background: #4c5948;
  box-shadow: inset 0 1px 2px #26352255;
}

.camera-shutter {
  position: absolute;
  z-index: 1;
  right: 35px;
  top: 12px;
  width: 27px;
  height: 10px;
  border: 1px solid #6f7b67;
  border-radius: 5px 5px 1px 1px;
  background: linear-gradient(#abb7a0, #86947c);
  pointer-events: none;
}

.camera-screen {
  position: relative;
  min-width: 0;
  padding: 5px;
  border: 1px solid #56614e;
  border-radius: 4px;
  background: #475340;
  box-shadow: inset 0 1px 2px #25321f33;
}

.camera-grip {
  position: absolute;
  right: 6px;
  top: 41px;
  bottom: 11px;
  width: 31px;
  border-left: 1px solid #a3af9a;
  border-radius: 6px 8px 8px 6px;
  background: repeating-linear-gradient(90deg, #a4b19820 0, #a4b19820 1px, #c8d0c020 1px, #c8d0c020 3px);
  pointer-events: none;
}

.camera-controls {
  position: absolute;
  right: 11px;
  top: 57px;
  width: 23px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  pointer-events: none;
}

.camera-dial {
  position: relative;
  width: 23px;
  height: 23px;
  border: 1px solid #7c896f;
  border-radius: 50%;
  background: linear-gradient(145deg, #d2d9c9, #aab89d);
  box-shadow: 0 1px 1px #64745325;
}

.camera-dial::after {
  content: '';
  position: absolute;
  inset: 6px;
  border: 1px solid #8d9d7f;
  border-radius: 50%;
  background: #bdc9b1;
}

.camera-control-mark {
  width: 13px;
  height: 3px;
  border: 1px solid #8e9e7e;
  border-radius: 2px;
  background: #b5c3a6;
}

.camera-control-dot {
  width: 5px;
  height: 5px;
  border: 1px solid #899b77;
  border-radius: 50%;
  background: #a3b58f;
}

.camera-thumb-rest {
  position: absolute;
  right: 9px;
  top: 12px;
  width: 28px;
  height: 19px;
  border: 1px solid #a7b49b;
  border-radius: 4px;
  background: repeating-linear-gradient(90deg, #a3b29340 0, #a3b29340 1px, #c6d0bc40 1px, #c6d0bc40 4px);
  pointer-events: none;
}

@media (max-width: 1100px) {
  .photo-caption h2 {
    font-size: 26px;
  }

  .photo-description {
    font-size: 11px;
  }
}

@media (max-width: 760px) {
  .inspiration {
    width: 100%;
    align-self: stretch;
  }

  .camera-shell {
    padding-top: 19px;
  }

  .camera-body {
    padding: 24px 40px 15px 13px;
    border-radius: 11px;
  }

  .camera-viewfinder {
    top: 0;
    width: 76px;
    height: 25px;
  }

  .camera-viewfinder::after {
    top: 6px;
    height: 10px;
  }

  .camera-shutter {
    top: 10px;
    right: 29px;
    width: 24px;
  }

  .camera-screen {
    padding: 4px;
  }

  .photo-window {
    aspect-ratio: auto;
    height: 205px;
  }

  .camera-grip {
    right: 5px;
    top: 38px;
    bottom: 9px;
    width: 26px;
  }

  .camera-controls {
    right: 8px;
    top: 53px;
    width: 21px;
    gap: 17px;
  }

  .camera-dial {
    width: 21px;
    height: 21px;
  }

  .camera-dial::after {
    inset: 5px;
  }

  .camera-thumb-rest {
    right: 7px;
    top: 10px;
    width: 24px;
    height: 17px;
  }

  .photo-caption {
    min-height: 196px;
    padding-top: 14px;
  }

  .photo-caption h2 {
    font-size: 24px;
  }

  .photo-description {
    min-height: 40px;
    font-size: 11px;
  }
}
</style>
