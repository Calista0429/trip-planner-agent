<template>
  <nav class="day-navigation" :aria-label="t('result.dayNavAria')">
    <button
      ref="prevButton"
      type="button"
      class="day-direction"
      :aria-label="t('result.prevDay')"
      aria-controls="day-panel"
      :disabled="current <= 0"
      @click="go(current - 1)"
    >
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true" focusable="false">
        <path d="m12 5-5 5 5 5" />
      </svg>
    </button>
    <div class="day-current">
      <div class="day-picker-wrap">
        <label :for="pickerId" class="sr-only">{{ t('result.dayNavAria') }}</label>
        <select
          :id="pickerId"
          ref="picker"
          :value="current"
          :aria-describedby="`${pickerId}-counter`"
          aria-controls="day-panel"
          @change="go(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <svg class="day-picker-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true" focusable="false">
          <path d="m4 6 4 4 4-4" />
        </svg>
      </div>
      <p :id="`${pickerId}-counter`" class="day-counter" role="status" aria-live="polite">
        {{ t('result.dayCounter', { n: current + 1, total: total }) }}
      </p>
    </div>
    <button
      ref="nextButton"
      type="button"
      class="day-direction"
      :aria-label="t('result.nextDay')"
      aria-controls="day-panel"
      :disabled="current >= total - 1"
      @click="go(current + 1)"
    >
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true" focusable="false">
        <path d="m8 5 5 5-5 5" />
      </svg>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { DayPlan } from '@/types'
import { locale, t } from '@/i18n'
import { splitDate } from '@/utils/trip'

const props = defineProps<{ days: DayPlan[]; current: number }>()
const emit = defineEmits<{ (e: 'change', index: number): void }>()

const pickerId = 'day-picker'
const picker = ref<HTMLSelectElement | null>(null)
const prevButton = ref<HTMLButtonElement | null>(null)
const nextButton = ref<HTMLButtonElement | null>(null)

const total = computed(() => props.days.length)

const options = computed(() =>
  props.days.map((day, index) => {
    const parts = splitDate(day.date)
    const date = !parts
      ? ''
      : locale.value === 'en'
        ? new Date(parts.year, parts.month - 1, parts.day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        : `${parts.month}月${parts.day}日`
    return {
      value: index,
      label: date ? t('result.dayOptionDate', { n: index + 1, date }) : t('result.dayOption', { n: index + 1 })
    }
  })
)

function go(index: number) {
  if (!Number.isInteger(index) || index < 0 || index >= total.value || index === props.current) return
  const focusedEdge = document.activeElement === prevButton.value || document.activeElement === nextButton.value
  emit('change', index)
  // Reaching the first/last day disables the button under focus; keep focus on the picker.
  if (focusedEdge) {
    nextTick(() => {
      const active = document.activeElement as HTMLButtonElement | null
      if (!active || active.disabled || active === document.body) picker.value?.focus({ preventScroll: true })
    })
  }
}
</script>

<style scoped>
.day-navigation {
  position: sticky;
  top: 0;
  z-index: 5;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 34px;
  align-items: center;
  gap: 14px;
  min-width: 0;
  padding: 11px 0;
  border-bottom: 1px solid var(--line);
  background: var(--paper);
}

.day-direction {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid #c2cec0;
  border-radius: 50%;
  background: var(--paper);
  color: var(--pine);
  cursor: pointer;
}

.day-direction svg {
  width: 14px;
  height: 14px;
}

.day-direction:hover:not(:disabled) {
  background: #e8eee5;
}

.day-direction:disabled {
  border-color: #dce3d9;
  color: #aeb9aa;
  cursor: default;
}

.day-current {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 11px;
  min-width: 0;
}

.day-picker-wrap {
  position: relative;
  flex: 1;
  min-width: 0;
  max-width: 255px;
}

.day-picker-wrap select {
  display: block;
  width: 100%;
  min-width: 0;
  min-height: 34px;
  padding: 6px 22px 6px 2px;
  border: 0;
  background: transparent;
  color: var(--ink);
  font: inherit;
  font-size: 13px;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
  appearance: none;
  -webkit-appearance: none;
  cursor: pointer;
}

.day-picker-chevron {
  position: absolute;
  right: 3px;
  top: 50%;
  width: 12px;
  height: 12px;
  margin-top: -6px;
  color: #7b8b79;
  pointer-events: none;
}

.day-counter {
  flex: none;
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 760px) {
  .day-navigation {
    grid-template-columns: 32px minmax(0, 1fr) 32px;
    gap: 10px;
    padding: 9px 0;
  }

  .day-direction {
    width: 32px;
    height: 32px;
  }

  .day-current {
    gap: 8px;
  }

  .day-picker-wrap select {
    font-size: 12px;
  }
}
</style>
