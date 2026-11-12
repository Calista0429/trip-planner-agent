<template>
  <!-- Off-screen, export-only rendering of the WHOLE plan (every day), so the
       PNG/PDF never shrinks to the single day shown on screen. -->
  <div class="export-sheet" aria-hidden="true">
    <header class="sheet-head">
      <p class="caption">{{ t('result.caption') }}</p>
      <h1 class="serif">{{ title }}</h1>
      <p class="meta">{{ meta }}</p>
      <p v-if="notice" class="notice">{{ notice }}</p>
      <p v-if="plan.overall_suggestions" class="suggestions">
        <strong>{{ t('result.suggestions') }}</strong>{{ plan.overall_suggestions }}
      </p>
    </header>

    <section class="sheet-row">
      <div class="sheet-map">
        <h2>{{ t('result.exportMapCaption') }}</h2>
        <img v-if="mapSnapshot" :src="mapSnapshot" alt="" />
        <p v-else class="muted">{{ t('result.exportMapMissing') }}</p>
      </div>
      <div class="sheet-budget">
        <BudgetPanel :budget="plan.budget" :cap="cap" />
      </div>
    </section>

    <section class="sheet-weather">
      <h2>{{ t('weather.heading') }}</h2>
      <table>
        <tbody>
          <tr v-for="row in weatherRows" :key="row.key">
            <th>{{ t('result.dayTitle', { n: row.index + 1 }) }} · {{ row.date }}</th>
            <td>{{ t('weather.day') }} {{ row.day }} {{ row.high }}°C</td>
            <td>{{ t('weather.night') }} {{ row.night }} {{ row.low }}°C</td>
            <td>{{ row.wind }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-for="(day, dayIndex) in plan.days" :key="dayIndex" class="sheet-day">
      <h2 class="serif">{{ t('result.dayTitle', { n: dayIndex + 1 }) }} · {{ day.date }}</h2>
      <p v-if="day.description" class="muted">{{ day.description }}</p>
      <p v-if="day.transportation" class="muted">{{ t('result.transport') }}：{{ day.transportation }}</p>

      <h3>{{ t('result.routeHeading') }}</h3>
      <ol v-if="day.attractions?.length" class="sheet-list">
        <li v-for="(item, index) in day.attractions" :key="index">
          <strong>{{ index + 1 }}. {{ item.name }}</strong>
          <span v-if="item.address"> · {{ item.address }}</span>
          <span class="facts">{{ attractionFacts(item) }}</span>
          <span v-if="item.description" class="desc">{{ item.description }}</span>
        </li>
      </ol>
      <p v-else class="muted">{{ t('result.noAttractions') }}</p>

      <h3>{{ t('result.hotelHeading') }}</h3>
      <template v-if="hotels[dayIndex]">
        <p>
          <strong>{{ hotels[dayIndex]!.hotel.name }}</strong>
          <span v-if="hotels[dayIndex]!.isCarriedOver"> · {{ t('result.carriedOver') }}</span>
        </p>
        <p class="muted">{{ hotelFacts(hotels[dayIndex]!.hotel, hotels[dayIndex]!.isCarriedOver) }}</p>
      </template>
      <p v-else class="muted">{{ t('result.noHotel') }}</p>

      <h3>{{ t('result.mealHeading') }}</h3>
      <ul v-if="day.meals?.length" class="sheet-list">
        <li v-for="(meal, index) in day.meals" :key="index">
          <strong>{{ mealLabel(meal.type) }} · {{ meal.name }}</strong>
          <span v-if="isAmount(meal.estimated_cost)"> · {{ t('result.mealCost', { v: money(meal.estimated_cost) }) }}</span>
          <span v-if="meal.address" class="desc">{{ meal.address }}</span>
          <span v-if="meal.description" class="desc">{{ meal.description }}</span>
        </li>
      </ul>
      <p v-else class="muted">{{ t('result.noMeals') }}</p>
    </section>

    <footer class="sheet-foot">{{ t('result.exportGenerated', { v: generatedAt }) }}</footer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Attraction, Hotel, TripPlan } from '@/types'
import { locale, t } from '@/i18n'
import { formatMoney, getDisplayHotel, isAmount } from '@/utils/trip'
import { formatTemperature, knownText, parseTemperature, weatherForDate } from '@/utils/weather'
import BudgetPanel from './BudgetPanel.vue'

const props = defineProps<{
  plan: TripPlan
  title: string
  meta: string
  notice?: string
  cap?: number | null
  mapSnapshot: string | null
}>()

const generatedAt = new Date().toLocaleString(locale.value === 'zh' ? 'zh-CN' : 'en-US')
const money = (value: number) => formatMoney(value, locale.value)

const hotels = computed(() => (props.plan.days || []).map((_, index) => getDisplayHotel(props.plan, index)))

const weatherRows = computed(() =>
  (props.plan.days || []).map((day, index) => {
    const w = weatherForDate(props.plan.weather_info, day.date)
    const direction = knownText(w?.wind_direction)
    const power = knownText(w?.wind_power)
    return {
      key: `${index}-${day.date}`,
      index,
      date: day.date,
      day: knownText(w?.day_weather) || t('weather.noForecast'),
      night: knownText(w?.night_weather) || t('weather.noForecast'),
      high: formatTemperature(parseTemperature(w?.day_temp)),
      low: formatTemperature(parseTemperature(w?.night_temp)),
      wind: direction || power ? `${direction || t('weather.directionPending')} · ${power || t('weather.powerPending')}` : t('weather.windPending')
    }
  })
)

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
    isAmount(item.ticket_price) ? t('result.ticket', { v: money(item.ticket_price) }) : '',
    item.rating !== undefined && item.rating !== null && String(item.rating) !== '' ? t('result.rating', { v: item.rating }) : ''
  ]
    .filter(Boolean)
    .join(' · ')

const hotelFacts = (hotel: Hotel, carriedOver = false) =>
  [
    hotel.address,
    hotel.type ? `${t('result.hotelType')} ${hotel.type}` : '',
    hotel.price_range ? `${t('result.hotelPrice')} ${hotel.price_range}` : '',
    isAmount(hotel.estimated_cost) && !carriedOver ? `${t('result.hotelCost')} ${money(hotel.estimated_cost)}` : '',
    hotel.rating ? `${t('result.hotelRating')} ${hotel.rating}` : '',
    hotel.distance ? `${t('result.hotelDistance')} ${hotel.distance}` : ''
  ]
    .filter(Boolean)
    .join(' · ')
</script>

<style scoped>
.export-sheet {
  position: absolute;
  left: -12000px;
  top: 0;
  width: 960px;
  padding: 40px 44px;
  background: #f6f7f5;
  color: #2a3d35;
  font-size: 13px;
  line-height: 1.75;
}

.caption {
  margin: 0;
  color: #6d7971;
  font-size: 12px;
}

h1 {
  margin: 4px 0 6px;
  font-size: 34px;
}

h2 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 500;
}

h3 {
  margin: 14px 0 4px;
  font-size: 14px;
  font-weight: 600;
}

p {
  margin: 4px 0;
}

.meta,
.muted {
  color: #6d7971;
}

.notice {
  padding: 8px 12px;
  border-left: 2px solid #98614f;
  background: #f3ebe6;
}

.suggestions strong {
  margin-right: 8px;
}

.sheet-row {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 28px;
  margin-top: 22px;
}

.sheet-map img {
  display: block;
  width: 100%;
  border: 1px solid #dce2dc;
}

.sheet-weather {
  margin-top: 22px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

th,
td {
  padding: 6px 8px;
  border-bottom: 1px solid #dce2dc;
  text-align: left;
  font-weight: 400;
}

.sheet-day {
  margin-top: 26px;
  padding-top: 18px;
  border-top: 1px solid #c9d2ca;
}

.sheet-list {
  margin: 0;
  padding-left: 0;
  list-style: none;
}

.sheet-list li {
  margin: 6px 0;
}

.facts,
.desc {
  display: block;
  color: #6d7971;
}

.sheet-foot {
  margin-top: 30px;
  color: #6d7971;
  font-size: 11px;
}
</style>
