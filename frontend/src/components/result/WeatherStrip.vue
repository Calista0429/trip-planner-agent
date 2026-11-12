<template>
  <section class="weather-overview" aria-labelledby="weather-heading">
    <div class="weather-heading">
      <h2 id="weather-heading" class="serif">{{ t('weather.heading') }}</h2>
      <p>{{ hasForecast ? t('weather.noteForecast') : t('weather.noteNone') }}</p>
    </div>
    <div ref="row" class="weather-strip" role="group" :aria-label="t('weather.groupAria')">
      <button
        v-for="card in cards"
        :key="card.key"
        :ref="el => setCardRef(el, card.index)"
        type="button"
        class="weather-card"
        :aria-pressed="card.index === selected"
        aria-controls="day-panel"
        :aria-label="card.aria"
        @click="emit('select', card.index)"
      >
        <span class="card-top">
          <strong>{{ card.dateLabel }}</strong>
          <span>{{ t('weather.dayN', { n: card.index + 1 }) }}</span>
        </span>
        <span class="card-main">
          <WeatherIcon :kind="card.icon" />
          <span class="card-temp">
            {{ card.high }}<span class="card-low"> / {{ card.low }}</span><small>°C</small>
          </span>
        </span>
        <span class="card-conditions">
          <span>{{ t('weather.day') }} {{ card.dayText }}</span>
          <span>{{ t('weather.night') }} {{ card.nightText }}</span>
        </span>
        <span class="card-wind">{{ card.wind }}</span>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, type ComponentPublicInstance } from 'vue'
import type { TripPlan } from '@/types'
import { locale, t } from '@/i18n'
import { splitDate } from '@/utils/trip'
import { formatTemperature, knownText, parseTemperature, weatherForDate, weatherIconKind } from '@/utils/weather'
import WeatherIcon from './WeatherIcon.vue'

const props = defineProps<{ plan: TripPlan; selected: number }>()
const emit = defineEmits<{ (e: 'select', index: number): void }>()

const row = ref<HTMLElement | null>(null)
const cardEls = new Map<number, HTMLElement>()
const setCardRef = (el: Element | ComponentPublicInstance | null, index: number) => {
  if (el instanceof HTMLElement) cardEls.set(index, el)
  else cardEls.delete(index)
}

const formatDateLabel = (date: string, index: number) => {
  const parts = splitDate(date)
  if (!parts) return t('weather.dayN', { n: index + 1 })
  if (locale.value === 'en') {
    return new Date(parts.year, parts.month - 1, parts.day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }
  return `${parts.month}月${parts.day}日`
}

const windText = (direction: string, power: string) => {
  if (!direction && !power) return t('weather.windPending')
  const unit = t('weather.powerUnit')
  const strength = power && unit && /\d/.test(power) && !/级|m\/s|km\/h/i.test(power) ? `${power}${unit}` : power
  return `${direction || t('weather.directionPending')} · ${strength || t('weather.powerPending')}`
}

const cards = computed(() =>
  (props.plan.days || []).map((day, index) => {
    // Matched strictly by date: a day without a forecast entry stays "—".
    const weather = weatherForDate(props.plan.weather_info, day.date)
    const dayText = knownText(weather?.day_weather)
    const nightText = knownText(weather?.night_weather)
    const high = parseTemperature(weather?.day_temp)
    const low = parseTemperature(weather?.night_temp)
    const wind = windText(knownText(weather?.wind_direction), knownText(weather?.wind_power))
    const dateLabel = formatDateLabel(day.date, index)
    const tempAria = (v: number | null) => (v === null ? t('weather.tempPending') : t('weather.tempAria', { v }))
    return {
      key: `${index}-${day.date}`,
      index,
      dateLabel,
      icon: weatherIconKind(dayText),
      high: formatTemperature(high),
      low: formatTemperature(low),
      dayText: dayText || t('weather.noForecast'),
      nightText: nightText || t('weather.noForecast'),
      wind,
      hasForecast: !!(dayText || nightText || high !== null || low !== null),
      aria: t('weather.cardAria', {
        date: dateLabel,
        n: index + 1,
        day: dayText || t('weather.noForecast'),
        high: tempAria(high),
        night: nightText || t('weather.noForecast'),
        low: tempAria(low),
        wind
      })
    }
  })
)

const hasForecast = computed(() => cards.value.some(card => card.hasForecast))

/** Keep the selected card visible inside the horizontal strip. */
function revealSelected() {
  const strip = row.value
  const card = cardEls.get(props.selected)
  if (!strip || !card || strip.clientWidth <= 0) return
  const cardBox = card.getBoundingClientRect()
  const rowBox = strip.getBoundingClientRect()
  if (cardBox.left >= rowBox.left && cardBox.right <= rowBox.right) return
  const left = strip.scrollLeft + cardBox.left - rowBox.left - (strip.clientWidth - cardBox.width) / 2
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  strip.scrollTo({ left: Math.max(0, left), behavior: reduce ? 'auto' : 'smooth' })
}

watch(() => props.selected, () => nextTick(revealSelected), { immediate: true })
</script>

<style scoped>
.weather-overview {
  min-width: 0;
  margin: 0 0 26px;
}

.weather-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 11px;
}

.weather-heading h2 {
  margin: 0;
  color: var(--ink);
  font-size: 22px;
  line-height: 1.5;
  letter-spacing: 0.5px;
}

.weather-heading p {
  margin: 0;
  color: #596c56;
  font-size: 11px;
  line-height: 1.8;
}

.weather-strip {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(180px, 1fr);
  gap: 12px;
  min-width: 0;
  max-width: 100%;
  padding: 2px 2px 8px;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scroll-snap-type: x proximity;
  scrollbar-width: thin;
  scrollbar-color: #c6d2c3 transparent;
}

/* More than four days: fixed-width cards that scroll instead of shrinking. */
.weather-strip:has(> :nth-child(5)) {
  grid-auto-columns: 200px;
}

.weather-card {
  display: block;
  min-width: 0;
  min-height: 140px;
  padding: 13px 16px;
  border: 1px solid #d7dfd2;
  border-radius: 0;
  background: #fbfcf9;
  color: var(--ink);
  font: inherit;
  text-align: left;
  scroll-snap-align: start;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.weather-card:hover {
  border-color: #94a58d;
}

.weather-card[aria-pressed='true'] {
  border-color: var(--pine);
  background: #edf3e9;
}

.weather-card:focus-visible {
  outline: 2px solid var(--pine);
  outline-offset: -3px;
}

.card-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  line-height: 1.7;
}

.card-top strong {
  font-size: 12px;
  font-weight: 500;
}

.card-top span {
  color: #596c56;
  font-size: 10px;
}

.card-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin: 9px 0 8px;
  color: #6b8063;
}

.card-temp {
  min-width: 0;
  color: var(--ink);
  font-size: 24px;
  line-height: 1.15;
  letter-spacing: -0.5px;
  font-variant-numeric: tabular-nums;
}

.card-low {
  font-size: 18px;
}

.card-temp small {
  margin-left: 3px;
  color: #596c56;
  font-size: 11px;
  letter-spacing: 0;
}

.card-conditions {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 12px;
  min-height: 18px;
  color: #62735e;
  font-size: 11px;
  line-height: 1.8;
}

.card-wind {
  display: block;
  margin-top: 4px;
  color: #596c56;
  font-size: 11px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

@media (max-width: 760px) {
  .weather-overview {
    margin-bottom: 21px;
  }

  .weather-heading {
    display: block;
    margin-bottom: 9px;
  }

  .weather-heading p {
    margin-top: 4px;
  }

  .weather-strip,
  .weather-strip:has(> :nth-child(5)) {
    grid-auto-columns: 158px;
    gap: 10px;
    scroll-snap-type: x mandatory;
  }

  .weather-card {
    padding: 12px 13px;
  }

  .card-temp {
    font-size: 23px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .weather-card {
    transition: none;
  }
}
</style>
