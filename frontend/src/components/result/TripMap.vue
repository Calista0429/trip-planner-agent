<template>
  <section class="map-panel" aria-labelledby="map-heading">
    <div class="map-head">
      <h2 id="map-heading">{{ t('map.heading') }}</h2>
      <div class="map-mode" role="group" :aria-label="t('map.modeAria')">
        <button type="button" :aria-pressed="mode === 'day'" @click="mode = 'day'">{{ t('map.modeDay') }}</button>
        <button type="button" :aria-pressed="mode === 'all'" @click="mode = 'all'">{{ t('map.modeAll') }}</button>
      </div>
    </div>

    <div class="map-filters" role="group" :aria-label="t('map.filtersAria')">
      <button
        v-for="category in CATEGORIES"
        :key="category"
        type="button"
        :class="`filter-${category}`"
        :aria-pressed="visible[category]"
        @click="visible[category] = !visible[category]"
      >
        <span class="legend-mark" :class="`legend-${category}`" aria-hidden="true"></span>
        {{ t(`map.${category}`) }}
        <span class="map-count">{{ counts[category] }}</span>
      </button>
    </div>
    <p class="map-status" role="status">
      {{ filterStatus }}
      <template v-if="missing > 0"> {{ t('map.missingCoords', { n: missing }) }}</template>
    </p>

    <div class="map-frame">
      <div
        ref="container"
        class="map-canvas"
        role="region"
        :aria-label="t('map.canvasAria', { scope: mode === 'day' ? t('result.dayTitle', { n: dayIndex + 1 }) : t('map.modeAll') })"
      ></div>
      <p v-if="overlayText" class="map-overlay">{{ overlayText }}</p>
    </div>
    <p class="map-note">{{ t('map.notNavigation') }}</p>

    <div class="map-detail" aria-live="polite">
      <template v-if="selectedPoint">
        <p class="detail-kind" :class="`kind-${selectedPoint.category}`">
          {{ t('map.detailDay', { n: selectedPoint.dayIndex + 1, type: t(`map.${selectedPoint.category}`) }) }}
        </p>
        <h3>{{ selectedPoint.name }}</h3>
        <p v-if="selectedPoint.address">{{ selectedPoint.address }}</p>
        <p v-if="selectedPoint.carriedOver">{{ t('result.carriedOverNote') }}</p>
        <p v-else-if="selectedPoint.description" class="detail-desc">{{ selectedPoint.description }}</p>
      </template>
      <p v-else class="detail-empty">{{ t('map.detailEmpty') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import html2canvas from 'html2canvas'
import type { TripPlan } from '@/types'
import { t } from '@/i18n'
import { COLORS } from '@/styles/theme'
import { buildDayPoints, routeOrder, type MapCategory, type MapPoint } from '@/utils/mapPoints'

const props = defineProps<{
  plan: TripPlan
  dayIndex: number
  selectedKey: string | null
  /** Bumped by the parent after saving edits so markers are rebuilt. */
  revision: number
}>()

const emit = defineEmits<{
  (e: 'select', key: string, dayIndex: number): void
}>()

const CATEGORIES: MapCategory[] = ['hotel', 'attraction', 'meal']
// Muted per-day line colors for the whole-trip view.
const DAY_COLORS = ['#315348', '#98614f', '#856435', '#4f6f8f', '#6d5a8a', '#5d7b4f']
const DEFAULT_CENTER: [number, number] = [116.397128, 39.916527]

const container = ref<HTMLElement | null>(null)
const mode = ref<'day' | 'all'>('day')
const visible = reactive<Record<MapCategory, boolean>>({ hotel: true, attraction: true, meal: true })
const status = ref<'loading' | 'ready' | 'nokey' | 'error'>('loading')

let map: any = null
let AMapApi: any = null
let disposed = false

// One loader promise per page load; AMapLoader itself must not load twice.
let loaderPromise: Promise<any> | null = null
const loadAMap = () => {
  if (!loaderPromise) {
    loaderPromise = AMapLoader.load({
      key: import.meta.env.VITE_AMAP_WEB_JS_KEY,
      version: '2.0',
      plugins: ['AMap.Marker', 'AMap.Polyline']
    }).catch((err: unknown) => {
      loaderPromise = null
      throw err
    })
  }
  return loaderPromise
}

const glyphs = computed(() => ({
  hotel: t('map.markerHotel'),
  breakfast: t('map.markerBreakfast'),
  lunch: t('map.markerLunch'),
  dinner: t('map.markerDinner'),
  snack: t('map.markerSnack')
}))

/** Points for every day (used for lookup, whole-trip view, and day jumps). */
const allDays = computed(() => {
  void props.revision
  return (props.plan.days || []).map((_, index) => buildDayPoints(props.plan, index, glyphs.value))
})

const scopePoints = computed<MapPoint[]>(() =>
  mode.value === 'day'
    ? allDays.value[props.dayIndex]?.points ?? []
    : allDays.value.flatMap(day => day.points)
)

const missing = computed(() =>
  mode.value === 'day'
    ? allDays.value[props.dayIndex]?.missing ?? 0
    : allDays.value.reduce((sum, day) => sum + day.missing, 0)
)

const counts = computed(() => {
  const result: Record<MapCategory, number> = { hotel: 0, attraction: 0, meal: 0 }
  const seenHotels = new Set<string>()
  scopePoints.value.forEach(point => {
    // A carried-over stay is the same hotel; count it once in the whole-trip view.
    if (point.category === 'hotel') {
      const id = `${point.name}@${point.longitude},${point.latitude}`
      if (seenHotels.has(id)) return
      seenHotels.add(id)
    }
    result[point.category] += 1
  })
  return result
})

const shownPoints = computed(() => scopePoints.value.filter(point => visible[point.category]))

const filterStatus = computed(() => {
  const shown = CATEGORIES.filter(c => visible[c]).map(c => t(`map.${c}`))
  const hidden = CATEGORIES.filter(c => !visible[c]).map(c => t(`map.${c}`))
  if (!shown.length) return t('map.statusNone')
  if (!hidden.length) {
    return t('map.statusAll', { hotel: t('map.hotel'), attraction: t('map.attraction'), meal: t('map.meal') })
  }
  return t('map.statusSome', { shown: shown.join('、'), hidden: hidden.join('、') })
})

const selectedPoint = computed(() => {
  if (!props.selectedKey) return null
  for (const day of allDays.value) {
    const hit = day.points.find(point => point.key === props.selectedKey)
    if (hit) return hit
  }
  return null
})

const overlayText = computed(() => {
  if (status.value === 'nokey') return t('map.noKey')
  if (status.value === 'error') return t('map.loadFailed')
  if (status.value === 'loading') return t('map.loading')
  if (!shownPoints.value.length) return t('map.noPoints')
  return ''
})

function markerElement(point: MapPoint): HTMLElement {
  const el = document.createElement('div')
  el.className = `tm-marker tm-${point.category}${point.key === props.selectedKey ? ' tm-selected' : ''}`
  el.setAttribute('role', 'button')
  el.setAttribute('tabindex', '0')
  el.setAttribute(
    'aria-label',
    `${t('map.detailDay', { n: point.dayIndex + 1, type: t(`map.${point.category}`) })}：${point.name}`
  )
  el.setAttribute('aria-pressed', String(point.key === props.selectedKey))
  const shape = document.createElement('span')
  shape.className = 'tm-shape'
  const glyph = document.createElement('span')
  glyph.className = 'tm-glyph'
  glyph.textContent = mode.value === 'all' && point.category === 'attraction' ? `${point.dayIndex + 1}·${point.glyph}` : point.glyph
  el.append(shape, glyph)
  const activate = (event: Event) => {
    event.stopPropagation()
    emit('select', point.key, point.dayIndex)
  }
  el.addEventListener('click', activate)
  el.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      activate(event)
    }
  })
  return el
}

function render(fit: boolean) {
  if (!map || !AMapApi || disposed) return
  map.clearMap()
  const AMap = AMapApi
  const points = shownPoints.value
  // Hotels repeat across days in the whole-trip view; draw each one once.
  const drawn = new Set<string>()
  const markers: any[] = []
  points.forEach(point => {
    if (point.category === 'hotel') {
      const id = `${point.name}@${point.longitude},${point.latitude}`
      if (drawn.has(id) && point.key !== props.selectedKey) return
      drawn.add(id)
    }
    markers.push(
      new AMap.Marker({
        position: [point.longitude, point.latitude],
        content: markerElement(point),
        anchor: 'center',
        zIndex: point.key === props.selectedKey ? 200 : point.category === 'hotel' ? 120 : 110,
        title: point.name
      })
    )
  })
  if (markers.length) map.add(markers)

  const days = mode.value === 'day' ? [props.dayIndex] : (props.plan.days || []).map((_, i) => i)
  days.forEach(day => {
    const route = routeOrder(points.filter(point => point.dayIndex === day))
    if (route.length < 2) return
    map.add(
      new AMap.Polyline({
        path: route.map(point => [point.longitude, point.latitude]),
        strokeColor: mode.value === 'day' ? COLORS.pine : DAY_COLORS[day % DAY_COLORS.length],
        strokeWeight: 3,
        strokeOpacity: 0.75,
        strokeStyle: 'dashed',
        strokeDasharray: [8, 6],
        zIndex: 50
      })
    )
  })

  if (fit) {
    if (markers.length > 1) map.setFitView(markers, false, [48, 48, 48, 48])
    else if (markers.length === 1) map.setZoomAndCenter(14, markers[0].getPosition())
  }
}

function focusSelected() {
  const point = selectedPoint.value
  if (!map || !point) return
  map.panTo([point.longitude, point.latitude])
}

watch(
  () => [props.revision, props.dayIndex, mode.value, visible.hotel, visible.attraction, visible.meal, props.plan],
  () => render(true)
)

watch(
  () => props.selectedKey,
  () => {
    const point = selectedPoint.value
    // Selecting a hidden category from the list turns that category back on.
    if (point && !visible[point.category]) visible[point.category] = true
    render(false)
    focusSelected()
  }
)

onMounted(async () => {
  if (!import.meta.env.VITE_AMAP_WEB_JS_KEY) {
    status.value = 'nokey'
    return
  }
  try {
    const AMap = await loadAMap()
    if (disposed || !container.value) return
    AMapApi = AMap
    map = new AMap.Map(container.value, {
      zoom: 12,
      center: DEFAULT_CENTER,
      viewMode: '2D',
      // Keeps the WebGL frame readable so export can snapshot the map.
      WebGLParams: { preserveDrawingBuffer: true }
    })
    trackInstance(1)
    status.value = 'ready'
    render(true)
    focusSelected()
  } catch (err) {
    console.error('Amap failed to load', err)
    if (!disposed) status.value = 'error'
  }
})

onBeforeUnmount(() => {
  disposed = true
  if (map) {
    map.destroy()
    map = null
    trackInstance(-1)
  }
})

/** Dev-only live-instance counter used to check for leaked maps. */
function trackInstance(delta: number) {
  if (!import.meta.env.DEV) return
  const w = window as unknown as { __tripMapInstances?: number }
  w.__tripMapInstances = (w.__tripMapInstances ?? 0) + delta
}

const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

/**
 * Snapshot the whole trip (all days, all categories) for export, then restore
 * the user's view. Returns null when there is no usable map.
 */
async function snapshotAll(): Promise<string | null> {
  if (!map || status.value !== 'ready' || !container.value) return null
  const previous = { mode: mode.value, ...visible }
  mode.value = 'all'
  visible.hotel = visible.attraction = visible.meal = true
  await nextTick()
  render(true)
  await new Promise<void>(resolve => {
    let done = false
    const finish = () => {
      if (done) return
      done = true
      map?.off('complete', finish)
      resolve()
    }
    map.on('complete', finish)
    setTimeout(finish, 1800)
  })
  await wait(400)
  let dataUrl: string | null = null
  try {
    const canvas = await html2canvas(container.value, { useCORS: true, backgroundColor: '#eaf0e9', scale: 2, logging: false })
    dataUrl = canvas.toDataURL('image/png')
  } catch (err) {
    console.warn('Map snapshot via html2canvas failed; trying the raw canvas', err)
    try {
      dataUrl = container.value.querySelector('canvas')?.toDataURL('image/png') ?? null
    } catch (inner) {
      console.warn('Raw map canvas snapshot failed', inner)
    }
  }
  mode.value = previous.mode
  visible.hotel = previous.hotel
  visible.attraction = previous.attraction
  visible.meal = previous.meal
  await nextTick()
  render(true)
  return dataUrl
}

defineExpose({ snapshotAll })
</script>

<style scoped>
.map-panel {
  border: 1px solid var(--line);
  background: #eef2ec;
}

.map-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 14px 18px 0;
}

.map-head h2 {
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  font-weight: 500;
}

.map-mode {
  display: inline-flex;
  border: 1px solid #b9c7b8;
}

.map-mode button {
  min-height: 30px;
  padding: 0 12px;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
}

.map-mode button[aria-pressed='true'] {
  background: var(--pine);
  color: #fff;
}

.map-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  padding: 12px 18px 0;
}

.map-filters button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 32px;
  padding: 4px 10px;
  border: 1px solid #b9c7b8;
  background: #f7f9f4;
  color: var(--ink);
  font-size: 11px;
  cursor: pointer;
}

.map-filters button[aria-pressed='false'] {
  border-style: dashed;
  background: transparent;
  color: #6c7867;
}

.legend-mark {
  display: inline-block;
  flex: none;
  width: 9px;
  height: 9px;
  border: 1px solid currentColor;
}

.legend-hotel {
  color: var(--hotel);
  background: var(--hotel);
}

.legend-attraction {
  color: var(--attraction);
  background: var(--attraction);
  border-radius: 50%;
}

.legend-meal {
  width: 8px;
  height: 8px;
  color: var(--meal);
  background: var(--meal);
  transform: rotate(45deg);
}

.map-filters button[aria-pressed='false'] .legend-mark {
  background: transparent;
}

.map-count {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.map-status {
  margin: 0;
  padding: 8px 18px 10px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
}

.map-frame {
  position: relative;
}

.map-canvas {
  width: 100%;
  height: 360px;
  background: #e2e9df;
}

.map-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  margin: 0;
  padding: 20px;
  background: rgba(234, 240, 233, 0.82);
  color: var(--ink);
  font-size: 12px;
  line-height: 1.8;
  text-align: center;
  pointer-events: none;
}

.map-note {
  margin: 0;
  padding: 6px 18px 0;
  color: #6b7a69;
  font-size: 10px;
}

.map-detail {
  min-height: 88px;
  margin-top: 8px;
  padding: 12px 18px 14px;
  border-top: 1px solid #d4dfd3;
  font-size: 12px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.map-detail h3 {
  margin: 0;
  color: var(--ink);
  font-size: 14px;
  font-weight: 500;
}

.map-detail p {
  margin: 3px 0 0;
  color: var(--muted);
  font-size: 11px;
}

.map-detail .detail-kind {
  margin: 0 0 2px;
  font-size: 10px;
}

.kind-hotel {
  color: var(--hotel) !important;
}

.kind-attraction {
  color: var(--attraction) !important;
}

.kind-meal {
  color: var(--meal) !important;
}

.detail-empty {
  margin: 0 !important;
}

@media (max-width: 760px) {
  .map-head,
  .map-filters,
  .map-status,
  .map-note,
  .map-detail {
    padding-left: 14px;
    padding-right: 14px;
  }

  .map-canvas {
    height: 280px;
  }
}
</style>

<!-- Marker DOM is created by Amap outside this component's scope. -->
<style>
.tm-marker {
  position: relative;
  display: grid;
  place-items: center;
  min-width: 22px;
  height: 22px;
  cursor: pointer;
  outline: none;
}

.tm-marker .tm-shape {
  position: absolute;
  inset: 0;
  border: 1.5px solid #fff;
  box-shadow: 0 1px 3px rgba(20, 35, 28, 0.35);
}

.tm-hotel .tm-shape {
  background: #98614f;
  border-radius: 3px;
}

.tm-attraction .tm-shape {
  background: #315348;
  border-radius: 50%;
}

.tm-meal .tm-shape {
  inset: 3px;
  background: #856435;
  transform: rotate(45deg);
}

.tm-glyph {
  position: relative;
  padding: 0 4px;
  color: #fff;
  font: 600 10px/1 -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
  white-space: nowrap;
}

.tm-attraction .tm-shape {
  border-radius: 11px;
}

.tm-selected .tm-shape,
.tm-marker:focus-visible .tm-shape {
  border-color: #1c2f27;
  border-width: 3px;
}

.tm-selected {
  transform: scale(1.25);
}

.tm-marker:focus-visible {
  outline: 2px solid #315348;
  outline-offset: 3px;
}
</style>
