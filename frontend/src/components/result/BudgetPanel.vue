<template>
  <section class="budget" aria-labelledby="budget-heading">
    <div class="budget-title">
      <h2 id="budget-heading">{{ t('result.budgetHeading') }}</h2>
      <div v-if="hasBudget" class="budget-total">
        {{ totalText }}
        <small v-if="capText">{{ t('result.budgetCap', { v: capText }) }}</small>
      </div>
    </div>

    <template v-if="hasBudget">
      <div class="budget-bar" role="img" :aria-label="barAria">
        <span
          v-for="item in items"
          :key="item.key"
          :class="`seg-${item.key}`"
          :style="{ width: `${item.share}%` }"
        ></span>
      </div>
      <p v-if="capNote" class="budget-cap-note" :class="{ over: isOver }">{{ capNote }}</p>
      <dl class="budget-items">
        <div v-for="item in items" :key="item.key">
          <dt><span class="swatch" :class="`seg-${item.key}`" aria-hidden="true"></span>{{ item.label }}</dt>
          <dd>{{ item.text }}</dd>
        </div>
      </dl>
      <p class="budget-note">{{ t('result.budgetNote') }}</p>
    </template>
    <p v-else class="budget-empty">{{ t('result.budgetMissing') }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Budget } from '@/types'
import { locale, t } from '@/i18n'
import { formatMoney, isAmount } from '@/utils/trip'

// Shows the plan's own budget numbers. Nothing here re-prices anything.
const props = defineProps<{ budget?: Budget | null; cap?: number | null }>()

const money = (value: unknown) => (isAmount(value) ? formatMoney(value, locale.value) : '—')

const hasBudget = computed(() => {
  const b = props.budget
  if (!b) return false
  return [b.total, b.total_hotels, b.total_meals, b.total_transportation, b.total_attractions].some(isAmount)
})

const total = computed(() => (props.budget && isAmount(props.budget.total) ? props.budget.total : null))
const totalText = computed(() => money(total.value))
const cap = computed(() => (isAmount(props.cap) && props.cap > 0 ? props.cap : null))
const capText = computed(() => (cap.value === null ? '' : formatMoney(cap.value, locale.value)))
const isOver = computed(() => cap.value !== null && total.value !== null && total.value > cap.value)

const capNote = computed(() => {
  if (cap.value === null || total.value === null) return ''
  if (isOver.value) return t('result.budgetOver', { v: formatMoney(total.value - cap.value, locale.value) })
  return t('result.budgetShare', { p: Math.round((total.value / cap.value) * 100) })
})

const items = computed(() => {
  const b = props.budget
  const raw = [
    { key: 'hotels', label: t('result.budgetHotels'), value: b?.total_hotels },
    { key: 'meals', label: t('result.budgetMeals'), value: b?.total_meals },
    { key: 'transportation', label: t('result.budgetTransportation'), value: b?.total_transportation },
    { key: 'attractions', label: t('result.budgetAttractions'), value: b?.total_attractions }
  ]
  const sum = raw.reduce((acc, item) => acc + (isAmount(item.value) ? Math.max(0, item.value) : 0), 0)
  // Bar is relative to the cap when the plan fits under it, otherwise to the plan total.
  const base = cap.value !== null && !isOver.value ? cap.value : Math.max(sum, total.value ?? 0)
  return raw.map(item => ({
    key: item.key,
    label: item.label,
    text: money(item.value),
    share: base > 0 && isAmount(item.value) ? Math.max(0, (item.value / base) * 100) : 0
  }))
})

const barAria = computed(() => {
  const byKey = Object.fromEntries(items.value.map(item => [item.key, item.text]))
  return t('result.budgetBarAria', {
    h: byKey.hotels,
    m: byKey.meals,
    t: byKey.transportation,
    a: byKey.attractions,
    total: totalText.value
  })
})
</script>

<style scoped>
.budget {
  padding-top: 23px;
}

.budget-title {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.budget-title h2 {
  margin: 0;
  color: var(--ink);
  font-size: 14px;
  font-weight: 500;
}

.budget-total {
  color: var(--ink);
  font-size: 25px;
  line-height: 1.2;
  letter-spacing: -0.7px;
  font-variant-numeric: tabular-nums;
}

.budget-total small {
  margin-left: 4px;
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0;
}

.budget-bar {
  display: flex;
  height: 5px;
  margin: 16px 0 8px;
  overflow: hidden;
  background: #dce3dd;
}

.seg-hotels {
  background: #294b3e;
}

.seg-meals {
  background: #63816d;
}

.seg-transportation {
  background: #8ba28d;
}

.seg-attractions {
  background: #afc0ad;
}

.budget-cap-note {
  margin: 0 0 12px;
  color: var(--muted);
  font-size: 11px;
}

.budget-cap-note.over {
  color: #8a3d2e;
}

.budget-items {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
}

.budget-items div {
  min-width: 0;
}

.budget-items dt {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  font-size: 11px;
}

.swatch {
  width: 7px;
  height: 7px;
}

.budget-items dd {
  margin: 4px 0 0;
  color: var(--ink);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.budget-note,
.budget-empty {
  margin: 18px 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 11px;
  line-height: 1.8;
}

@media (max-width: 420px) {
  .budget-items {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
