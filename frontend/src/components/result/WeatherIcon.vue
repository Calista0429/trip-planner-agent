<template>
  <svg
    class="weather-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.3"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-if="kind === 'sun'">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5" />
    </template>
    <path v-else-if="kind === 'storm'" d="M7 15a5 5 0 1 1 1-9 6 6 0 0 1 11 3 3 3 0 0 1-1 6M13 12l-3 5h4l-3 5" />
    <path v-else-if="kind === 'rain'" d="M7 15a5 5 0 1 1 1-9 6 6 0 0 1 11 3 3 3 0 0 1-1 6M8 18l-1 3M13 18l-1 3M18 18l-1 3" />
    <path v-else-if="kind === 'snow'" d="M7 15a5 5 0 1 1 1-9 6 6 0 0 1 11 3 3 3 0 0 1-1 6M8 18v4M6 20h4M17 18v4M15 20h4" />
    <path v-else-if="kind === 'fog'" d="M7 13a5 5 0 1 1 1-9 6 6 0 0 1 11 3 3 3 0 0 1-1 6M4 17h16M6 21h12" />
    <template v-else-if="kind === 'unknown'">
      <path d="M7 18a5 5 0 1 1 1-9 6 6 0 0 1 11 3 3 3 0 0 1-1 6Z" />
      <path d="M10.5 12a1.6 1.6 0 0 1 3 .8c0 1.2-1.5 1.2-1.5 2.2M12 17h.01" />
    </template>
    <path v-else d="M7 18a5 5 0 1 1 1-9 6 6 0 0 1 11 3 3 3 0 0 1-1 6Z" />
  </svg>
</template>

<script setup lang="ts">
import type { WeatherIconKind } from '@/utils/weather'

defineProps<{ kind: WeatherIconKind }>()
</script>

<style scoped>
.weather-icon {
  display: block;
  flex: none;
  width: 26px;
  height: 26px;
}
</style>
