<template>
  <section v-if="!tripPlan" class="shell empty-state" aria-labelledby="empty-title">
    <h1 id="empty-title" class="serif">{{ t('result.emptyTitle') }}</h1>
    <p>{{ t('result.emptyDesc') }}</p>
    <router-link to="/" class="primary-link">{{ t('result.emptyAction') }}</router-link>
  </section>

  <section v-else class="shell result-page" aria-labelledby="result-title">
    <div class="result-heading">
      <div class="heading-text">
        <p class="trip-caption">{{ t('result.caption') }} / {{ displayCity }}</p>
        <h1 id="result-title" ref="titleEl" class="serif" tabindex="-1">{{ title }}</h1>
        <p class="trip-meta">{{ metaLine }}</p>
      </div>
      <div class="heading-actions">
        <template v-if="!editMode">
          <button type="button" class="ghost-button" @click="editConditions">{{ t('result.editConditions') }}</button>
          <button type="button" class="ghost-button" @click="toggleEditMode">{{ t('result.edit') }}</button>
          <a-dropdown :trigger="['click']" placement="bottomRight">
            <button type="button" class="ghost-button" :disabled="exporting" :aria-busy="exporting ? 'true' : 'false'">
              {{ t('result.exportMenu') }}
              <svg class="chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true" focusable="false"><path d="m4 6 4 4 4-4" /></svg>
            </button>
            <template #overlay>
              <a-menu @click="onExport">
                <a-menu-item key="image">{{ t('result.exportImage') }}</a-menu-item>
                <a-menu-item key="pdf">{{ t('result.exportPdf') }}</a-menu-item>
                <a-menu-item key="note" disabled>{{ t('result.exportNote', { n: tripPlan.days.length }) }}</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </template>
        <template v-else>
          <button type="button" class="solid-button" @click="saveChanges">{{ t('result.save') }}</button>
          <button type="button" class="ghost-button" @click="cancelEdit">{{ t('result.cancel') }}</button>
        </template>
      </div>
    </div>

    <div v-if="planNotice" class="plan-notice" role="status">
      <strong v-if="isFallback">{{ t('result.fallbackTitle') }}</strong>
      <p>{{ planNotice }}</p>
    </div>

    <p v-if="tripPlan.overall_suggestions" class="suggestions">
      <span class="suggestions-label">{{ t('result.suggestions') }}</span>
      {{ tripPlan.overall_suggestions }}
    </p>

    <WeatherStrip :plan="tripPlan" :selected="dayIndex" @select="index => setDay(index, false)" />

    <div class="result-layout">
      <div class="itinerary">
        <DayNavigation :days="tripPlan.days" :current="dayIndex" @change="index => setDay(index, true)" />

        <div
          v-if="currentDay"
          id="day-panel"
          ref="dayPanel"
          class="day-panel"
          role="region"
          :aria-label="t('result.dayPanel', { n: dayIndex + 1 })"
          tabindex="-1"
        >
          <div class="day-intro">
            <h2 class="serif section-heading">
              <SectionIcon kind="route" />
              <span>{{ dayHeading }}</span>
            </h2>
            <p v-if="currentDay.description">{{ currentDay.description }}</p>
            <p v-if="currentDay.transportation" class="day-transport">
              {{ t('result.transport') }} · {{ currentDay.transportation }}
            </p>
          </div>

          <p v-if="editMode" class="editing-hint" role="status">{{ t('result.editingHint') }}</p>

          <!-- Route & sights -->
          <section class="poi-section first" aria-labelledby="route-heading">
            <h2 id="route-heading" class="sr-only">{{ t('result.routeHeading') }}</h2>
            <ol v-if="currentDay.attractions?.length" class="timeline">
              <li
                v-for="(item, index) in currentDay.attractions"
                :key="`${dayIndex}-${index}-${item.name}`"
                class="stop"
                :class="{ selected: selectedKey === attractionKey(dayIndex, index) }"
                :data-key="attractionKey(dayIndex, index)"
              >
                <div class="stop-index" aria-hidden="true">{{ index + 1 }}</div>
                <div class="stop-body">
                  <div class="stop-media">
                    <template v-if="photoFor(item) && !failedPhotos.has(photoFor(item)!.url)">
                      <img
                        :src="photoFor(item)!.url"
                        :alt="photoFor(item)!.stock ? t('result.stockPhotoAlt', { name: item.name }) : item.name"
                        loading="lazy"
                        decoding="async"
                        @error="failedPhotos.add(photoFor(item)!.url)"
                      />
                      <span v-if="photoFor(item)!.stock" class="stock-tag">{{ t('result.stockPhoto') }}</span>
                    </template>
                    <div v-else class="photo-placeholder">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true" focusable="false">
                        <rect x="3" y="5" width="18" height="14" rx="1" />
                        <path d="m3 16 5-5 4 4 3-3 6 6" />
                        <circle cx="16" cy="9" r="1.5" />
                      </svg>
                      <span>{{ t('result.photoMissing') }}</span>
                    </div>
                  </div>
                  <div class="stop-text">
                    <h3>{{ item.name }}</h3>
                    <p v-if="attractionFacts(item)" class="facts">{{ attractionFacts(item) }}</p>

                    <template v-if="!editMode">
                      <p v-if="item.address" class="address">{{ item.address }}</p>
                      <p v-if="item.description" class="summary">{{ item.description }}</p>
                    </template>
                    <div v-else class="edit-fields">
                      <label>
                        <span>{{ t('result.editAddress') }}</span>
                        <a-input v-model:value="item.address" size="small" />
                      </label>
                      <label>
                        <span>{{ t('result.editDuration') }}</span>
                        <a-input-number v-model:value="item.visit_duration" :min="10" :max="480" size="small" style="width: 100%" />
                      </label>
                      <label>
                        <span>{{ t('result.editDescription') }}</span>
                        <a-textarea v-model:value="item.description" :auto-size="{ minRows: 2, maxRows: 5 }" size="small" />
                      </label>
                      <div class="edit-controls">
                        <button type="button" :disabled="index === 0" @click="moveAttraction(index, 'up')">
                          ↑ {{ t('result.moveUp') }}
                        </button>
                        <button type="button" :disabled="index === currentDay.attractions.length - 1" @click="moveAttraction(index, 'down')">
                          ↓ {{ t('result.moveDown') }}
                        </button>
                        <button type="button" class="danger" @click="deleteAttraction(index)">{{ t('result.remove') }}</button>
                      </div>
                    </div>

                    <MapLink
                      v-if="!editMode"
                      :point-key="attractionKey(dayIndex, index)"
                      :mapped="mappedKeys.has(attractionKey(dayIndex, index))"
                      :selected="selectedKey === attractionKey(dayIndex, index)"
                      @view="viewOnMap"
                    />
                  </div>
                </div>
              </li>
            </ol>
            <p v-else class="poi-empty">{{ t('result.noAttractions') }}</p>
          </section>

          <!-- Hotel -->
          <section class="poi-section" aria-labelledby="hotel-heading">
            <h2 id="hotel-heading" class="serif section-heading">
              <SectionIcon kind="hotel" />
              <span>{{ t('result.hotelHeading') }}</span>
            </h2>
            <article
              v-if="displayHotel"
              class="poi-card"
              :class="{ selected: selectedKey === hotelKey(dayIndex) }"
              :data-key="hotelKey(dayIndex)"
            >
              <div class="poi-topline">
                <h3 class="poi-title">{{ displayHotel.hotel.name }}</h3>
                <span v-if="displayHotel.isCarriedOver" class="poi-badge">{{ t('result.carriedOver') }}</span>
              </div>
              <p v-if="displayHotel.hotel.address" class="address">{{ displayHotel.hotel.address }}</p>
              <dl v-if="hotelFacts.length" class="poi-facts">
                <div v-for="fact in hotelFacts" :key="fact.label">
                  <dt>{{ fact.label }}</dt>
                  <dd>{{ fact.value }}</dd>
                </div>
              </dl>
              <p v-if="displayHotel.isCarriedOver" class="summary">{{ t('result.carriedOverNote') }}</p>
              <MapLink
                :point-key="hotelKey(dayIndex)"
                :mapped="mappedKeys.has(hotelKey(dayIndex))"
                :selected="selectedKey === hotelKey(dayIndex)"
                @view="viewOnMap"
              />
            </article>
            <p v-else class="poi-empty">{{ t('result.noHotel') }}</p>
          </section>

          <!-- Meals -->
          <section class="poi-section" aria-labelledby="meal-heading">
            <h2 id="meal-heading" class="serif section-heading">
              <SectionIcon kind="meal" />
              <span>{{ t('result.mealHeading') }}</span>
            </h2>
            <ul v-if="currentDay.meals?.length" class="meal-list">
              <li
                v-for="(meal, index) in currentDay.meals"
                :key="`${dayIndex}-m${index}-${meal.name}`"
                class="meal-row"
                :class="{ selected: selectedKey === mealKey(dayIndex, index) }"
                :data-key="mealKey(dayIndex, index)"
              >
                <span class="meal-type">{{ mealLabel(meal.type) }}</span>
                <div class="meal-body">
                  <div class="poi-topline">
                    <h3 class="poi-title">{{ meal.name || '—' }}</h3>
                    <span v-if="isAmount(meal.estimated_cost)" class="poi-cost">
                      {{ t('result.mealCost', { v: money(meal.estimated_cost) }) }}
                    </span>
                  </div>
                  <p v-if="meal.description" class="summary">{{ meal.description }}</p>
                  <p v-if="meal.address" class="address">{{ meal.address }}</p>
                  <p v-if="isLodgingBreakfastMeal(meal.type, meal.name)" class="map-note">{{ t('result.lodgingBreakfast') }}</p>
                  <MapLink
                    v-else
                    :point-key="mealKey(dayIndex, index)"
                    :mapped="mappedKeys.has(mealKey(dayIndex, index))"
                    :selected="selectedKey === mealKey(dayIndex, index)"
                    @view="viewOnMap"
                  />
                </div>
              </li>
            </ul>
            <p v-else class="poi-empty">{{ t('result.noMeals') }}</p>
          </section>
        </div>
      </div>

      <aside class="trip-sidebar" :aria-label="`${t('map.heading')} / ${t('result.budgetHeading')}`">
        <div ref="mapWrap">
          <TripMap
            ref="tripMap"
            :plan="tripPlan"
            :day-index="dayIndex"
            :selected-key="selectedKey"
            :revision="mapRevision"
            @select="onMapSelect"
          />
        </div>
        <BudgetPanel :budget="tripPlan.budget" :cap="budgetCap" />
      </aside>
    </div>

    <ExportSheet
      v-if="exporting"
      ref="exportSheet"
      :plan="tripPlan"
      :title="title"
      :meta="metaLine"
      :notice="planNotice"
      :cap="budgetCap"
      :map-snapshot="mapSnapshot"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import type { Attraction, TripFormData, TripPlan } from '@/types'
import { API_BASE_URL } from '@/services/api'
import { isFallbackStatus, loadMeta, loadPlan, loadRequest, savePlan, type TripPlanMeta } from '@/services/tripSession'
import { locale, t } from '@/i18n'
import { isLodgingBreakfastMeal, isValidLocation, normalizeLocation } from '@/utils/geo'
import { attractionKey, buildDayPoints, hotelKey, mealKey } from '@/utils/mapPoints'
import { findCity } from '@/data/regions'
import { formatMoney, getDisplayHotel, isAmount, splitDate } from '@/utils/trip'
import BudgetPanel from '@/components/result/BudgetPanel.vue'
import DayNavigation from '@/components/result/DayNavigation.vue'
import ExportSheet from '@/components/result/ExportSheet.vue'
import MapLink from '@/components/result/MapLink.vue'
import SectionIcon from '@/components/result/SectionIcon.vue'
import TripMap from '@/components/result/TripMap.vue'
import WeatherStrip from '@/components/result/WeatherStrip.vue'

const route = useRoute()
const router = useRouter()

const tripPlan = ref<TripPlan | null>(loadPlan())
const meta = ref<TripPlanMeta | null>(loadMeta())
const request = ref<TripFormData | null>(loadRequest())

const editMode = ref(false)
const originalPlan = ref<TripPlan | null>(null)
const selectedKey = ref<string | null>(null)
const mapRevision = ref(0)
const exporting = ref(false)
const mapSnapshot = ref<string | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const failedPhotos = reactive(new Set<string>())

const titleEl = ref<HTMLElement | null>(null)
const dayPanel = ref<HTMLElement | null>(null)
const mapWrap = ref<HTMLElement | null>(null)
const tripMap = ref<InstanceType<typeof TripMap> | null>(null)

const money = (value: number) => formatMoney(value, locale.value)

// ---- Day selection: `?day=N` (1-based) is the single source of truth. ----

const dayCount = computed(() => tripPlan.value?.days?.length ?? 0)

/** Parse ?day; null when absent or not a positive integer. */
const requestedDay = computed(() => {
  const raw = Array.isArray(route.query.day) ? route.query.day[0] : route.query.day
  if (raw === undefined || raw === null || raw === '') return null
  const value = Number(raw)
  return Number.isInteger(value) && value >= 1 ? value : NaN
})

const dayIndex = computed(() => {
  const count = dayCount.value
  if (!count) return 0
  const requested = requestedDay.value
  if (requested === null || Number.isNaN(requested)) return 0
  return Math.min(requested, count) - 1
})

// Normalize an invalid/out-of-range ?day in place (no extra history entry).
watch(
  [requestedDay, dayCount],
  ([requested, count]) => {
    if (!count) return
    const normalized = dayIndex.value + 1
    if (requested !== normalized) {
      router.replace({ query: { ...route.query, day: String(normalized) } })
    }
  },
  { immediate: true }
)

function setDay(index: number, fromNav: boolean) {
  if (index < 0 || index >= dayCount.value || index === dayIndex.value) return
  router.push({ query: { ...route.query, day: String(index + 1) } })
  if (fromNav) {
    nextTick(() => {
      // Only scroll when the day panel's top has scrolled out of view.
      const panel = dayPanel.value
      if (panel && panel.getBoundingClientRect().top < 0) {
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
        panel.scrollIntoView({ block: 'start', behavior: reduce ? 'auto' : 'smooth' })
      }
    })
  }
}

watch(dayIndex, () => {
  if (selectedKey.value && !selectedKey.value.startsWith(`d${dayIndex.value}-`)) selectedKey.value = null
})

const currentDay = computed(() => tripPlan.value?.days?.[dayIndex.value] ?? null)

// ---- Heading ----

/** Use the saved request only when it belongs to this plan. */
const matchingRequest = computed(() => {
  const req = request.value
  const plan = tripPlan.value
  if (!req || !plan) return null
  return req.city?.trim() === plan.city?.trim() && req.start_date === plan.start_date ? req : null
})

/** Plan city in the UI language (the plan itself always stores the Chinese name). */
const displayCity = computed(() => {
  const city = tripPlan.value?.city ?? ''
  return locale.value === 'en' ? findCity(city)?.city.en ?? city : city
})

const title = computed(() =>
  tripPlan.value
    ? t(dayCount.value === 1 ? 'result.titleDayOne' : 'result.titleDays', { city: displayCity.value, n: dayCount.value })
    : ''
)

const formatShortDate = (date: string | undefined) => {
  const parts = splitDate(date)
  if (!parts) return date || ''
  return locale.value === 'en'
    ? new Date(parts.year, parts.month - 1, parts.day).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : `${parts.year}.${String(parts.month).padStart(2, '0')}.${String(parts.day).padStart(2, '0')}`
}

const metaLine = computed(() => {
  const plan = tripPlan.value
  if (!plan) return ''
  const parts: string[] = []
  if (plan.start_date || plan.end_date) {
    parts.push(
      plan.end_date && plan.end_date !== plan.start_date
        ? `${formatShortDate(plan.start_date)} — ${formatShortDate(plan.end_date)}`
        : formatShortDate(plan.start_date)
    )
  }
  const n = dayCount.value
  if (n) parts.push(n === 1 ? t('result.metaDaysOne') : t('result.metaDays', { n, nights: n - 1 }))
  const party = matchingRequest.value?.party
  if (party) {
    const who: string[] = []
    if (party.adults) who.push(t('result.partyAdults', { n: party.adults }))
    if (party.children) who.push(t('result.partyChildren', { n: party.children }))
    if (party.elders) who.push(t('result.partyElders', { n: party.elders }))
    if (who.length) parts.push(who.join(locale.value === 'zh' ? '、' : ', '))
  }
  return parts.join('  /  ')
})

const dayHeading = computed(() => {
  const day = currentDay.value
  if (!day) return ''
  const parts = splitDate(day.date)
  const date = !parts
    ? ''
    : locale.value === 'en'
      ? new Date(parts.year, parts.month - 1, parts.day).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
      : `${parts.month}月${parts.day}日`
  return date ? `${t('result.dayTitle', { n: dayIndex.value + 1 })} · ${date}` : t('result.dayTitle', { n: dayIndex.value + 1 })
})

const isFallback = computed(() => isFallbackStatus(meta.value?.status))
const planNotice = computed(() => {
  if (isFallback.value) return t('result.fallbackDesc')
  if (meta.value?.switchedModel) return t('result.switchedDesc')
  return ''
})

const budgetCap = computed(() => {
  const amount = matchingRequest.value?.budget_constraint?.amount
  return isAmount(amount) ? amount : null
})

// ---- Day content ----

const displayHotel = computed(() => getDisplayHotel(tripPlan.value, dayIndex.value))

const hotelFacts = computed(() => {
  const hotel = displayHotel.value?.hotel
  if (!hotel) return []
  const facts: { label: string; value: string }[] = []
  if (hotel.type) facts.push({ label: t('result.hotelType'), value: hotel.type })
  if (hotel.price_range) facts.push({ label: t('result.hotelPrice'), value: hotel.price_range })
  // A carried-over stay adds no night, so its per-night cost is not repeated here.
  if (isAmount(hotel.estimated_cost) && !displayHotel.value?.isCarriedOver) facts.push({ label: t('result.hotelCost'), value: money(hotel.estimated_cost) })
  if (hotel.rating !== undefined && hotel.rating !== null && String(hotel.rating).trim() !== '') {
    facts.push({ label: t('result.hotelRating'), value: String(hotel.rating) })
  }
  if (hotel.distance && String(hotel.distance).trim()) facts.push({ label: t('result.hotelDistance'), value: hotel.distance })
  return facts
})

const mapGlyphs = computed(() => ({
  hotel: t('map.markerHotel'),
  breakfast: t('map.markerBreakfast'),
  lunch: t('map.markerLunch'),
  dinner: t('map.markerDinner'),
  snack: t('map.markerSnack')
}))

/** Keys on the current day that have valid coordinates (drives "view on map"). */
const mappedKeys = computed(() => {
  void mapRevision.value
  return new Set(buildDayPoints(tripPlan.value, dayIndex.value, mapGlyphs.value).points.map(point => point.key))
})

const mealLabel = (type: string) =>
  ({
    breakfast: t('result.mealBreakfast'),
    lunch: t('result.mealLunch'),
    dinner: t('result.mealDinner'),
    snack: t('result.mealSnack')
  })[type] || type

const attractionFacts = (item: Attraction) =>
  [
    isAmount(item.visit_duration) ? t('result.duration', { n: item.visit_duration }) : '',
    isAmount(item.ticket_price) ? (item.ticket_price === 0 ? t('result.ticketFree') : t('result.ticket', { v: money(item.ticket_price) })) : '',
    item.rating !== undefined && item.rating !== null && String(item.rating) !== '' ? t('result.rating', { v: item.rating }) : ''
  ]
    .filter(Boolean)
    .join(' · ')

/**
 * The plan's own image_url is shown as-is. The existing POI photo service is a
 * keyword search on a stock library, so its result may not depict this place:
 * it is always labelled as a stock reference image, never passed off as the POI.
 */
const photoFor = (item: Attraction): { url: string; stock: boolean } | null => {
  const own = typeof item.image_url === 'string' ? item.image_url.trim() : ''
  if (own) return { url: own, stock: false }
  const stock = attractionPhotos.value[item.name]
  // The same stock image returned for different places is not specific to any of them.
  if (!stock || genericStockUrls.value.has(stock)) return null
  return { url: stock, stock: true }
}

const genericStockUrls = computed(() => {
  const owners = new Map<string, Set<string>>()
  Object.entries(attractionPhotos.value).forEach(([name, url]) => {
    if (!owners.has(url)) owners.set(url, new Set())
    owners.get(url)!.add(name)
  })
  return new Set([...owners].filter(([, names]) => names.size > 1).map(([url]) => url))
})

// ---- List <-> map linking ----

function viewOnMap(key: string) {
  selectedKey.value = key
  // On the single-column layout the map sits below the list.
  if (window.matchMedia('(max-width: 760px)').matches) {
    nextTick(() => mapWrap.value?.scrollIntoView({ block: 'start', behavior: 'smooth' }))
  }
}

function onMapSelect(key: string, pointDay: number) {
  selectedKey.value = key
  if (pointDay !== dayIndex.value) {
    router.push({ query: { ...route.query, day: String(pointDay + 1) } })
  }
  nextTick(() => {
    const el = document.querySelector<HTMLElement>(`[data-key="${key}"]`)
    if (!el) return
    const box = el.getBoundingClientRect()
    if (box.top < 60 || box.bottom > window.innerHeight) {
      el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  })
}

// ---- Editing ----

const editConditions = () => router.push('/')

const toggleEditMode = () => {
  editMode.value = true
  originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))
  selectedKey.value = null
  message.info(t('result.toastEditMode'))
}

const saveChanges = () => {
  editMode.value = false
  if (tripPlan.value) savePlan(tripPlan.value)
  originalPlan.value = null
  mapRevision.value += 1
  message.success(t('result.toastSaved'))
}

const cancelEdit = () => {
  if (originalPlan.value) tripPlan.value = JSON.parse(JSON.stringify(originalPlan.value))
  originalPlan.value = null
  editMode.value = false
  mapRevision.value += 1
  message.info(t('result.toastCanceled'))
}

const deleteAttraction = (attrIndex: number) => {
  const day = currentDay.value
  if (!day) return
  if (day.attractions.length <= 1) {
    message.warning(t('result.toastKeepOne'))
    return
  }
  day.attractions.splice(attrIndex, 1)
  mapRevision.value += 1
  message.success(t('result.toastDeleted'))
}

const moveAttraction = (attrIndex: number, direction: 'up' | 'down') => {
  const list = currentDay.value?.attractions
  if (!list) return
  const target = direction === 'up' ? attrIndex - 1 : attrIndex + 1
  if (target < 0 || target >= list.length) return
  ;[list[attrIndex], list[target]] = [list[target], list[attrIndex]]
  mapRevision.value += 1
}

// ---- Data enrichment (existing services) ----

const loadAttractionPhotos = async () => {
  const plan = tripPlan.value
  if (!plan) return
  const names = new Set<string>()
  plan.days.forEach(day => (day.attractions || []).forEach(a => {
    if (!(typeof a.image_url === 'string' && a.image_url.trim()) && a.name) names.add(a.name)
  }))
  await Promise.all(
    [...names].map(name =>
      fetch(`${API_BASE_URL}/api/poi/photo?name=${encodeURIComponent(name)}`)
        .then(res => res.json())
        .then(data => {
          if (data?.success && data.data?.photo_url) attractionPhotos.value[name] = data.data.photo_url
        })
        .catch(err => console.warn(`POI photo unavailable: ${name}`, err))
    )
  )
}

/** Backfill meal coordinates from POI search; never invents a location. */
const loadMissingMealLocations = async () => {
  const plan = tripPlan.value
  if (!plan) return
  let updated = 0
  const jobs: Promise<void>[] = []
  plan.days.forEach(day => {
    ;(day.meals || []).forEach(meal => {
      if (isValidLocation(meal.location) || isLodgingBreakfastMeal(meal.type, meal.name) || !meal.name) return
      jobs.push(
        fetch(`${API_BASE_URL}/api/poi/search?keywords=${encodeURIComponent(meal.name)}&city=${encodeURIComponent(plan.city)}&source_role=food`)
          .then(res => res.json())
          .then(data => {
            const poi = Array.isArray(data?.data) ? data.data.find((item: any) => isValidLocation(item.location)) : null
            if (!poi) return
            if (!meal.address && poi.address) meal.address = poi.address
            meal.location = normalizeLocation(poi.location)
            updated += 1
          })
          .catch(err => console.warn(`Meal location backfill failed: ${meal.name}`, err))
      )
    })
  })
  await Promise.all(jobs)
  if (updated > 0 && tripPlan.value && !editMode.value) {
    savePlan(tripPlan.value)
    mapRevision.value += 1
  }
}

onMounted(() => {
  if (!tripPlan.value) return
  void loadAttractionPhotos()
  void loadMissingMealLocations()
})

// ---- Export: always the whole plan ----

const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

async function renderExportCanvas(): Promise<HTMLCanvasElement> {
  mapSnapshot.value = (await tripMap.value?.snapshotAll()) ?? null
  exporting.value = true
  await nextTick()
  await wait(150)
  const sheet = document.querySelector<HTMLElement>('.export-sheet')
  if (!sheet) throw new Error('export sheet missing')
  try {
    return await html2canvas(sheet, { backgroundColor: '#f6f7f5', scale: 2, logging: false, useCORS: true })
  } finally {
    exporting.value = false
  }
}

const fileStem = () => `${t('result.exportFilePrefix')}_${tripPlan.value?.city ?? ''}_${Date.now()}`

async function exportAsImage() {
  message.loading({ content: t('result.toastGenImage'), key: 'export', duration: 0 })
  try {
    const canvas = await renderExportCanvas()
    const link = document.createElement('a')
    link.download = `${fileStem()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
    message.success({ content: t('result.toastImageOk'), key: 'export' })
  } catch (error: any) {
    console.error('Image export failed', error)
    message.error({ content: t('result.toastImageFail', { msg: error?.message ?? '' }), key: 'export' })
  }
}

async function exportAsPDF() {
  message.loading({ content: t('result.toastGenPdf'), key: 'export', duration: 0 })
  try {
    const canvas = await renderExportCanvas()
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
    const pageWidth = 210
    const pageHeight = 297
    // Slice the tall canvas into A4-sized pieces so each page embeds only its
    // own strip (embedding the whole image on every page bloats the file).
    const sliceHeight = Math.floor((canvas.width * pageHeight) / pageWidth)
    const slice = document.createElement('canvas')
    slice.width = canvas.width
    const ctx = slice.getContext('2d')
    if (!ctx) throw new Error('canvas 2d context unavailable')
    for (let offset = 0, page = 0; offset < canvas.height; offset += sliceHeight, page += 1) {
      const height = Math.min(sliceHeight, canvas.height - offset)
      slice.height = height
      ctx.fillStyle = '#f6f7f5'
      ctx.fillRect(0, 0, slice.width, height)
      ctx.drawImage(canvas, 0, offset, canvas.width, height, 0, 0, canvas.width, height)
      if (page > 0) pdf.addPage()
      pdf.addImage(slice.toDataURL('image/jpeg', 0.9), 'JPEG', 0, 0, pageWidth, (height * pageWidth) / canvas.width)
    }
    pdf.save(`${fileStem()}.pdf`)
    message.success({ content: t('result.toastPdfOk'), key: 'export' })
  } catch (error: any) {
    console.error('PDF export failed', error)
    message.error({ content: t('result.toastPdfFail', { msg: error?.message ?? '' }), key: 'export' })
  }
}

function onExport({ key }: { key: string | number }) {
  if (exporting.value) return
  if (key === 'image') void exportAsImage()
  else if (key === 'pdf') void exportAsPDF()
}
</script>

<style scoped>
.empty-state {
  padding-top: 80px;
  padding-bottom: 120px;
  text-align: center;
}

.empty-state h1 {
  margin: 0 0 10px;
  font-size: 32px;
}

.empty-state p {
  color: var(--muted);
}

.primary-link {
  display: inline-block;
  margin-top: 14px;
  padding: 12px 26px;
  background: var(--pine);
  color: #fff;
  text-decoration: none;
}

.result-page {
  padding-top: 36px;
  padding-bottom: 30px;
}

.result-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
  margin-bottom: 18px;
}

.heading-text {
  min-width: 0;
}

.trip-caption {
  margin: 0 0 10px;
  color: var(--muted);
  font-size: 12px;
}

.result-heading h1 {
  margin: 0;
  color: var(--ink);
  font-size: 40px;
  line-height: 1.35;
  letter-spacing: 1px;
  outline: none;
  overflow-wrap: anywhere;
}

.trip-meta {
  margin: 9px 0 0;
  color: var(--muted);
  font-size: 12px;
  white-space: pre-wrap;
}

.heading-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.ghost-button,
.solid-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 8px 16px;
  border: 1px solid #b8c8bb;
  border-radius: 0;
  background: transparent;
  color: var(--ink);
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}

.ghost-button:hover:not(:disabled) {
  background: #e8eee8;
}

.ghost-button:disabled {
  cursor: progress;
  opacity: 0.7;
}

.solid-button {
  border-color: var(--pine);
  background: var(--pine);
  color: #fff;
}

.chevron {
  width: 12px;
  height: 12px;
}

.plan-notice {
  margin: 0 0 16px;
  padding: 10px 14px;
  border-left: 2px solid var(--hotel);
  background: #f3ebe6;
  color: #5d3a2f;
  font-size: 12px;
  line-height: 1.7;
}

.plan-notice p {
  margin: 2px 0 0;
}

.suggestions {
  max-width: 920px;
  margin: 0 0 24px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.85;
}

.suggestions-label {
  margin-right: 8px;
  color: var(--ink);
  font-weight: 500;
}

.result-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: 58px;
}

.itinerary,
.trip-sidebar {
  min-width: 0;
}

.trip-sidebar {
  align-self: start;
}

@media (min-width: 761px) and (min-height: 860px) {
  .trip-sidebar {
    position: sticky;
    top: 16px;
  }
}

.day-panel {
  scroll-margin-top: 70px;
  outline: none;
}

.day-intro {
  padding: 22px 0 8px;
}

.section-heading {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
  margin: 0;
  color: var(--ink);
}

.section-heading > span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.day-intro h2 {
  margin-bottom: 8px;
  font-size: 26px;
  letter-spacing: 1px;
}

.day-intro p {
  margin: 0 0 4px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.85;
}

.day-transport {
  font-size: 12px !important;
}

.editing-hint {
  margin: 8px 0 0;
  padding: 8px 12px;
  background: #e8eee5;
  color: var(--pine);
  font-size: 12px;
}

.poi-section {
  margin-top: 24px;
  padding-top: 21px;
  border-top: 1px solid var(--line);
}

.poi-section.first {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 0;
}

.poi-section > .section-heading {
  margin-bottom: 13px;
  font-size: 22px;
  letter-spacing: 0.5px;
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}

.stop {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid var(--line);
}

.stop:last-child {
  border-bottom: 0;
}

.stop-index {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  margin-top: 2px;
  border-radius: 50%;
  background: var(--attraction);
  color: #fff;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.stop-body {
  display: grid;
  grid-template-columns: 148px minmax(0, 1fr);
  gap: 16px;
  min-width: 0;
}

.stop.selected .stop-body,
.poi-card.selected,
.meal-row.selected {
  background: #edf2e9;
  box-shadow: 0 0 0 6px #edf2e9;
}

.stop-media {
  position: relative;
  width: 148px;
  height: 108px;
  overflow: hidden;
  background: #e5eae4;
}

.stop-media img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.stock-tag {
  position: absolute;
  left: 0;
  bottom: 0;
  padding: 1px 6px;
  background: rgba(36, 52, 44, 0.72);
  color: #fff;
  font-size: 10px;
  line-height: 1.6;
}

.photo-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 100%;
  color: #8a978c;
  font-size: 11px;
}

.photo-placeholder svg {
  width: 26px;
  height: 26px;
}

.stop-text {
  min-width: 0;
}

.stop-text h3,
.poi-title {
  margin: 0;
  color: var(--ink);
  font-size: 16px;
  font-weight: 500;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.facts {
  margin: 2px 0 0;
  color: #5b7560;
  font-size: 11px;
}

.address,
.summary {
  margin: 5px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.edit-fields {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}

.edit-fields label {
  display: grid;
  gap: 3px;
  color: var(--muted);
  font-size: 11px;
}

.edit-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.edit-controls button {
  min-height: 30px;
  padding: 3px 10px;
  border: 1px solid #b8c8bb;
  background: transparent;
  color: var(--ink);
  font-size: 11px;
  cursor: pointer;
}

.edit-controls button:disabled {
  color: #aab4ab;
  cursor: default;
}

.edit-controls .danger {
  border-color: #c9a59a;
  color: #8a3d2e;
}

.poi-card {
  min-width: 0;
  padding: 17px 18px;
  border: 1px solid var(--line);
  background: var(--card);
}

.poi-topline {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.poi-badge {
  padding: 1px 6px;
  border: 1px solid #c8c6b8;
  color: var(--hotel);
  font-size: 10px;
  line-height: 1.8;
}

.poi-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 18px;
  margin: 12px 0 4px;
  padding: 12px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

.poi-facts div {
  min-width: 0;
}

.poi-facts dt {
  color: var(--muted);
  font-size: 10px;
}

.poi-facts dd {
  margin: 3px 0 0;
  font-size: 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.poi-cost {
  color: #6e5543;
  font-size: 12px;
  white-space: nowrap;
}

.poi-empty,
.map-note {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
}

.map-note {
  font-size: 11px;
}

.meal-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--line);
}

.meal-row {
  display: grid;
  grid-template-columns: minmax(46px, max-content) minmax(0, 1fr);
  gap: 14px;
  padding: 16px 0;
  border-bottom: 1px solid var(--line);
}

.meal-type {
  padding-top: 3px;
  color: var(--meal);
  font-size: 12px;
}

.meal-body {
  min-width: 0;
}

.meal-body .poi-title {
  font-size: 15px;
}

@media (max-width: 1100px) {
  .result-layout {
    gap: 30px;
  }

  .result-heading h1 {
    font-size: 34px;
  }

  .stop-body {
    grid-template-columns: 112px minmax(0, 1fr);
  }

  .stop-media {
    width: 112px;
    height: 84px;
  }
}

@media (max-width: 760px) {
  .result-page {
    padding-top: 22px;
  }

  .result-heading {
    flex-direction: column;
    align-items: stretch;
    gap: 14px;
  }

  .heading-actions {
    justify-content: flex-start;
  }

  .result-heading h1 {
    font-size: 28px;
    letter-spacing: 0;
  }

  .trip-meta {
    font-size: 11px;
    line-height: 1.8;
  }

  .result-layout {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .trip-sidebar {
    position: static;
    width: 100%;
  }

  .day-intro h2 {
    font-size: 23px;
  }

  .poi-section > .section-heading {
    font-size: 20px;
  }

  .stop {
    grid-template-columns: 22px minmax(0, 1fr);
    gap: 10px;
  }

  .stop-index {
    width: 22px;
    height: 22px;
  }

  .stop-body {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }

  .stop-media {
    width: 100%;
    height: 150px;
  }

  .poi-card {
    padding: 14px;
  }

  .poi-facts {
    gap: 9px 14px;
  }

  .meal-row {
    grid-template-columns: minmax(38px, max-content) minmax(0, 1fr);
    gap: 10px;
  }
}
</style>
