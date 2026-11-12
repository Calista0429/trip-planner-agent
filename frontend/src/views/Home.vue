<template>
  <section class="shell home-layout" aria-labelledby="home-title">
    <div class="home-copy">
      <div class="home-heading">
        <p class="trip-caption">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true" focusable="false">
            <path d="M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0Z" />
            <circle cx="12" cy="10" r="2.5" />
          </svg>
          {{ t('home.caption') }}
        </p>
        <h1 id="home-title" class="serif">{{ t('home.title') }}</h1>
        <p class="intro">{{ t('home.intro') }}</p>
      </div>

      <a-form
        ref="formRef"
        class="planner-form"
        layout="vertical"
        :model="formData"
        :required-mark="false"
        @finish="handleSubmit"
      >
        <div class="field-grid">
          <!-- Destination: province first, then a city limited to that province.
               The submitted `city` is always the official Chinese name. -->
          <a-form-item class="field" :label="t('home.labelProvince')" html-for="province-select">
            <a-select
              id="province-select"
              v-model:value="provinceCode"
              show-search
              :placeholder="t('home.placeholderProvince')"
              :options="provinceOptions"
              :filter-option="filterRegion"
              :disabled="loading"
              :not-found-content="t('home.noMatch')"
              @change="onProvinceChange"
            />
          </a-form-item>

          <a-form-item
            class="field"
            name="city"
            :label="t('home.labelCity')"
            :rules="[{ required: true, message: t('home.ruleCity') }]"
            :extra="regionNote"
          >
            <a-select
              v-model:value="cityValue"
              show-search
              :placeholder="selectedProvince ? t('home.placeholderCity') : t('home.pickProvinceFirst')"
              :options="cityOptions"
              :filter-option="filterRegion"
              :disabled="loading || !selectedProvince"
              :not-found-content="t('home.noMatch')"
            />
          </a-form-item>

          <a-form-item
            class="field"
            name="start_date"
            :label="t('home.labelStartDate')"
            :rules="[{ required: true, message: t('home.ruleStartDate') }]"
          >
            <a-date-picker
              v-model:value="formData.start_date"
              :placeholder="t('home.placeholderDate')"
              format="YYYY-MM-DD"
              :disabled="loading"
              style="width: 100%"
            />
          </a-form-item>

          <a-form-item
            class="field"
            name="end_date"
            :label="t('home.labelEndDate')"
            :rules="[{ required: true, message: t('home.ruleEndDate') }]"
            :extra="tripLengthText"
          >
            <a-date-picker
              v-model:value="formData.end_date"
              :placeholder="t('home.placeholderDate')"
              format="YYYY-MM-DD"
              :disabled-date="disabledEndDate"
              :disabled="loading"
              style="width: 100%"
            />
          </a-form-item>

          <a-form-item class="field" :name="['party', 'adults']" :label="t('home.labelAdults')" :extra="partyText">
            <a-input-number
              v-model:value="formData.party.adults"
              :min="0"
              :max="20"
              :precision="0"
              :disabled="loading"
              style="width: 100%"
            />
          </a-form-item>

          <a-form-item class="field" :name="['budget_constraint', 'amount']" :label="t('home.labelBudget')">
            <a-input-number
              v-model:value="formData.budget_constraint.amount"
              :min="0"
              :step="100"
              :precision="0"
              :placeholder="t('home.placeholderBudget')"
              :aria-label="t('home.budgetAria')"
              :disabled="loading"
              prefix="¥"
              style="width: 100%"
            />
          </a-form-item>
        </div>

        <div class="constraint">
          <a-checkbox v-model:checked="strictBudget" :disabled="loading || !hasBudgetAmount">
            {{ t('home.strictBudget') }}
          </a-checkbox>
          <span class="constraint-mode" aria-live="polite">
            {{ hasBudgetAmount ? budgetModeText : t('home.strictNeedsAmount') }}
          </span>
        </div>

        <div class="options">
          <button
            type="button"
            class="options-toggle"
            :aria-expanded="optionsOpen"
            aria-controls="more-options"
            @click="optionsOpen = !optionsOpen"
          >
            <span>{{ t('home.moreOptions') }}</span>
            <span class="options-sign" aria-hidden="true">{{ optionsOpen ? '−' : '＋' }}</span>
          </button>
          <!-- v-show keeps every field mounted so collapsed values are still submitted. -->
          <div v-show="optionsOpen" id="more-options" class="option-fields">
            <a-form-item class="field" :name="['party', 'children']" :label="t('home.labelChildren')">
              <a-input-number v-model:value="formData.party.children" :min="0" :max="20" :precision="0" :disabled="loading" style="width: 100%" />
            </a-form-item>
            <a-form-item class="field" :name="['party', 'elders']" :label="t('home.labelElders')">
              <a-input-number v-model:value="formData.party.elders" :min="0" :max="20" :precision="0" :disabled="loading" style="width: 100%" />
            </a-form-item>
            <a-form-item class="field" :name="['party', 'companion_type']" :label="t('home.labelCompanion')">
              <a-select v-model:value="formData.party.companion_type" :options="companionTypeOptions" :disabled="loading" />
            </a-form-item>
            <a-form-item class="field" :name="['budget_constraint', 'budget_level']" :label="t('home.labelBudgetLevel')">
              <a-select v-model:value="formData.budget_constraint.budget_level" :options="budgetLevelOptions" :disabled="loading" />
            </a-form-item>
            <a-form-item class="field" name="transportation" :label="t('home.labelTransportation')">
              <a-select v-model:value="formData.transportation" :options="transportationOptions" :disabled="loading" />
            </a-form-item>
            <a-form-item class="field" name="accommodation" :label="t('home.labelAccommodation')">
              <a-select v-model:value="formData.accommodation" :options="accommodationOptions" :disabled="loading" />
            </a-form-item>
            <a-form-item class="field wide" name="preferences" :label="t('home.labelPreferences')">
              <a-checkbox-group v-model:value="formData.preferences" class="preference" :disabled="loading">
                <a-checkbox v-for="option in preferenceOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </a-checkbox>
              </a-checkbox-group>
            </a-form-item>
            <a-form-item class="field wide" name="free_text_input" :label="t('home.labelExtra')">
              <a-textarea
                v-model:value="formData.free_text_input"
                :placeholder="t('home.placeholderExtra')"
                :auto-size="{ minRows: 2, maxRows: 5 }"
                :disabled="loading"
              />
            </a-form-item>
          </div>
        </div>

        <div class="submit-row">
          <button class="primary" type="submit" :disabled="loading" :aria-busy="loading ? 'true' : 'false'">
            <span>{{ loading ? t('home.submitting') : t('home.submit') }}</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true" focusable="false">
              <path d="M3 12h17m-6-6 6 6-6 6" />
            </svg>
          </button>
          <p class="submit-hint">{{ t('home.submitHint') }}</p>
        </div>

        <div class="progress" role="status" aria-live="polite">
          <template v-if="loading">
            <div
              class="progress-track"
              role="progressbar"
              :aria-valuenow="loadingProgress"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuetext="loadingStatus"
            >
              <span :style="{ width: `${loadingProgress}%` }"></span>
            </div>
            <p class="progress-text">
              <span>{{ loadingStatus }}</span>
              <span class="progress-value">{{ loadingProgress }}%</span>
            </p>
          </template>
        </div>

        <div v-if="errorText" class="form-error" role="alert">
          <strong>{{ t('home.errTitle') }}</strong>
          <p>{{ errorText }}</p>
          <p class="form-error-hint">{{ t('home.errRetry') }}</p>
        </div>
      </a-form>
    </div>

    <CameraCarousel />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import dayjs, { type Dayjs } from 'dayjs'
import CameraCarousel from '@/components/home/CameraCarousel.vue'
import { streamTripPlan } from '@/services/api'
import { loadRequest, saveMeta, savePlan, saveRequest, isFallbackStatus } from '@/services/tripSession'
import type { TripFormData } from '@/types'
import { PROVINCES, citySupport, findCity, type ProvinceOption } from '@/data/regions'
import { locale, t } from '@/i18n'
import {
  accommodationOptions,
  budgetLevelOptions,
  companionTypeOptions,
  preferenceOptions,
  transportationOptions
} from '@/i18n/options'

const router = useRouter()
const formRef = ref()
const loading = ref(false)
const loadingProgress = ref(0)
const loadingStatus = ref('')
const errorText = ref('')
const optionsOpen = ref(false)
// Hard budget toggle: when checked (and an amount is set) strictness becomes 'hard'.
const strictBudget = ref(false)
// Prefill writes party fields in bulk; skip the companion auto-derivation once.
let suppressCompanionDerive = false

type TripFormState = Omit<TripFormData, 'start_date' | 'end_date'> & {
  start_date: Dayjs | null
  end_date: Dayjs | null
}

const formData = reactive<TripFormState>({
  city: '',
  start_date: null,
  end_date: null,
  travel_days: 1,
  transportation: '公共交通',
  accommodation: '经济型酒店',
  preferences: [],
  free_text_input: '',
  party: {
    adults: 1,
    children: 0,
    elders: 0,
    total: 1,
    companion_type: 'solo'
  },
  budget_constraint: {
    amount: null,
    scope: 'total',
    currency: 'CNY',
    budget_level: 'standard',
    strictness: 'none'
  }
})

// ---- Destination: province -> city ----
const provinceCode = ref<string | undefined>(undefined)
const selectedProvince = computed<ProvinceOption | null>(
  () => PROVINCES.find(p => p.adcode === provinceCode.value) ?? null
)

/** Bilingual label so both "浙江" and "Zhejiang" are searchable in either UI language. */
const bilingual = (zh: string, en: string) => (locale.value === 'en' ? `${en} · ${zh}` : `${zh} · ${en}`)

const provinceOptions = computed(() =>
  PROVINCES.map(p => ({ value: p.adcode, label: bilingual(p.name, p.en), search: `${p.name} ${p.en}`.toLowerCase() }))
)

const cityOptions = computed(() => {
  const province = selectedProvince.value
  if (!province) return []
  return province.cities.map(c => ({
    value: c.name,
    label: bilingual(c.name, c.en),
    search: `${c.name} ${c.en}`.toLowerCase(),
    disabled: citySupport(province, c) === 'unsupported'
  }))
})

const filterRegion = (input: string, option?: { search?: string }) =>
  !!option?.search && option.search.includes(input.trim().toLowerCase())

// The select is bound to `cityValue`; only a city inside the chosen province is ever submitted.
const cityValue = computed<string | undefined>({
  get: () => formData.city || undefined,
  set: value => {
    formData.city = value ?? ''
  }
})

function onProvinceChange() {
  const province = selectedProvince.value
  if (!province || !province.cities.some(c => c.name === formData.city)) formData.city = ''
  // A municipality / Hong Kong / Macau is a single city: choose it for the user.
  const selectable = province?.cities.filter(c => citySupport(province, c) !== 'unsupported') ?? []
  if (province && province.cities.length === 1 && selectable.length === 1) formData.city = selectable[0].name
  formRef.value?.clearValidate?.(['city'])
}

const regionNote = computed(() => {
  const province = selectedProvince.value
  if (!province) return undefined
  if (province.support === 'unsupported') return t('home.regionUnsupported')
  const city = province.cities.find(c => c.name === formData.city)
  if (city && citySupport(province, city) === 'noWeather') return t('home.regionNoWeather')
  return undefined
})

const hasBudgetAmount = computed(() => {
  const amount = formData.budget_constraint.amount
  return amount !== null && amount !== undefined
})

// No amount -> 'none'; amount + strict toggle -> 'hard'; amount only -> 'soft'.
const budgetStrictness = computed<TripFormData['budget_constraint']['strictness']>(() =>
  !hasBudgetAmount.value ? 'none' : strictBudget.value ? 'hard' : 'soft'
)

const budgetModeText = computed(() => {
  const mode = budgetStrictness.value
  return mode === 'hard' ? t('home.budgetModeHard') : mode === 'soft' ? t('home.budgetModeSoft') : t('home.budgetModeNone')
})

const tripLengthText = computed(() =>
  formData.start_date && formData.end_date ? t('home.tripLength', { n: formData.travel_days }) : undefined
)

const partyText = computed(() =>
  formData.party.total === 1 ? t('home.partySummaryOne') : t('home.partySummary', { n: formData.party.total })
)

watch(hasBudgetAmount, has => {
  if (!has) strictBudget.value = false
})

const disabledEndDate = (current: Dayjs) =>
  !!formData.start_date && current.isBefore(formData.start_date, 'day')

// 监听日期变化,自动计算旅行天数
watch([() => formData.start_date, () => formData.end_date], ([start, end]) => {
  if (start && end) {
    const days = end.diff(start, 'day') + 1
    if (days > 0 && days <= 30) {
      formData.travel_days = days
    } else if (days > 30) {
      message.warning(t('home.warnMaxDays'))
      formData.end_date = null
    } else {
      message.warning(t('home.warnDateOrder'))
      formData.end_date = null
    }
  }
})

// planner协议要求party.total显式等于成人、儿童、老人之和
watch([() => formData.party.adults, () => formData.party.children, () => formData.party.elders], ([adults, children, elders]) => {
  const adultCount = Number(adults || 0)
  const childCount = Number(children || 0)
  const elderCount = Number(elders || 0)
  formData.party.total = adultCount + childCount + elderCount
  if (suppressCompanionDerive) return
  if (childCount > 0) {
    formData.party.companion_type = 'family_with_children'
  } else if (elderCount > 0) {
    formData.party.companion_type = 'family_with_elders'
  } else if (adultCount === 1) {
    formData.party.companion_type = 'solo'
  } else if (adultCount === 2) {
    formData.party.companion_type = 'couple'
  } else if (adultCount > 2) {
    formData.party.companion_type = 'friends'
  }
})

// "Edit trip details" on the result page lands here: restore that request so
// the user edits it instead of starting over. Only ever fills a fresh form.
onMounted(async () => {
  const saved = loadRequest()
  if (!saved) return
  suppressCompanionDerive = true
  // Older saved requests may hold a short or English name; map it onto the lists.
  const match = findCity(saved.city)
  provinceCode.value = match?.province.adcode
  formData.city = match && citySupport(match.province, match.city) !== 'unsupported' ? match.city.name : ''
  formData.start_date = saved.start_date ? dayjs(saved.start_date) : null
  formData.end_date = saved.end_date ? dayjs(saved.end_date) : null
  formData.transportation = saved.transportation || formData.transportation
  formData.accommodation = saved.accommodation || formData.accommodation
  formData.preferences = Array.isArray(saved.preferences) ? [...saved.preferences] : []
  formData.free_text_input = saved.free_text_input ?? ''
  if (saved.party) Object.assign(formData.party, saved.party)
  if (saved.budget_constraint) {
    formData.budget_constraint.amount = saved.budget_constraint.amount ?? null
    formData.budget_constraint.budget_level = saved.budget_constraint.budget_level || 'standard'
    strictBudget.value = saved.budget_constraint.strictness === 'hard'
  }
  await nextTick()
  suppressCompanionDerive = false
})

// Map a streamed planning phase to a monotonic progress value (never regresses).
const PHASE_PROGRESS: Record<string, number> = {
  collecting_attractions: 20,
  collecting_weather: 22,
  collecting_hotels: 24,
  collecting_context: 30,
  building_query: 35,
  switching_model: 75,
  reranking: 90,
  fallback: 90
}

function nextProgress(phase: string | undefined, attempt: number | undefined, current: number): number {
  if (phase === 'generating') {
    // Each generate attempt nudges progress forward but stays below rerank.
    return Math.min(85, Math.max(current, 40 + (attempt ?? 1) * 8))
  }
  const target = phase ? PHASE_PROGRESS[phase] ?? current : current
  return Math.max(current, target)
}

/** Localized copy for a phase; falls back to the server's own message. */
function phaseText(phase: string | undefined, attempt: number | undefined, fallback: string | undefined): string {
  if (phase === 'generating') {
    return attempt ? t('progress.generatingAttempt', { n: attempt }) : t('progress.generating')
  }
  if (phase) {
    const key = `progress.${phase}`
    const text = t(key)
    if (text !== key) return text
  }
  return fallback || loadingStatus.value
}

const handleSubmit = async () => {
  if (!formData.start_date || !formData.end_date) {
    message.error(t('home.errPickDate'))
    return
  }

  if (formData.party.total <= 0) {
    message.error(t('home.errPartySize'))
    return
  }

  loading.value = true
  errorText.value = ''
  loadingProgress.value = 0
  loadingStatus.value = t('progress.starting')

  let switchedModel = false

  try {
    const budgetAmount = formData.budget_constraint.amount
    const requestData: TripFormData = {
      city: formData.city,
      start_date: formData.start_date.format('YYYY-MM-DD'),
      end_date: formData.end_date.format('YYYY-MM-DD'),
      travel_days: formData.travel_days,
      transportation: formData.transportation,
      accommodation: formData.accommodation,
      preferences: formData.preferences,
      free_text_input: formData.free_text_input,
      party: {
        adults: formData.party.adults,
        children: formData.party.children,
        elders: formData.party.elders,
        total: formData.party.total,
        companion_type: formData.party.companion_type
      },
      budget_constraint: {
        amount: budgetAmount ?? null,
        scope: 'total',
        currency: 'CNY',
        budget_level: formData.budget_constraint.budget_level,
        strictness: budgetStrictness.value
      }
    }

    let resultStatus: string | undefined
    let resultMessage: string | undefined
    const plan = await streamTripPlan(requestData, (event) => {
      if (event.type === 'progress') {
        if (event.phase === 'switching_model') switchedModel = true
        loadingStatus.value = phaseText(event.phase, event.attempt, event.message)
        loadingProgress.value = nextProgress(event.phase, event.attempt, loadingProgress.value)
      } else if (event.type === 'result') {
        resultStatus = event.status
        resultMessage = event.message
      }
    })

    loadingProgress.value = 100
    loadingStatus.value = t('progress.done')

    // Persist the plan (existing key) plus this request and generation meta.
    savePlan(plan)
    saveRequest(requestData)
    saveMeta({ status: resultStatus, message: resultMessage, switchedModel })

    if (isFallbackStatus(resultStatus)) {
      message.warning(t('home.fallbackNotice'))
    } else {
      message.success(t('home.successGenerated'))
    }
    setTimeout(() => {
      router.push({ path: '/result', query: { day: '1' } })
    }, 400)
  } catch (error: any) {
    errorText.value = error?.message || t('home.errGenerate')
    message.error(t('home.errGenerate'))
  } finally {
    setTimeout(() => {
      loading.value = false
      loadingProgress.value = 0
      loadingStatus.value = ''
    }, 600)
  }
}
</script>

<style scoped>
.home-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.38fr) minmax(0, 0.82fr);
  gap: 76px;
  align-items: start;
  padding-top: 44px;
  padding-bottom: 35px;
}

.trip-caption {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0 0 15px;
  color: var(--muted);
  font-size: 12px;
}

.trip-caption svg {
  width: 17px;
  height: 17px;
}

h1 {
  margin: 0 0 17px;
  color: var(--ink);
  font-size: 51px;
  line-height: 1.4;
  letter-spacing: 1px;
  white-space: pre-line;
}

.intro {
  max-width: 470px;
  margin: 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.85;
}

.planner-form {
  max-width: 600px;
  margin-top: 27px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
}

.field-grid,
.option-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 24px;
}

.field {
  min-width: 0;
  margin-bottom: 14px;
}

.field.wide {
  grid-column: 1 / -1;
}

/* Underlined fields instead of boxed inputs. */
.planner-form :deep(.ant-form-item-label > label) {
  height: auto;
  color: var(--muted);
  font-size: 11px;
}

.planner-form :deep(.ant-form-item-label) {
  padding-bottom: 4px;
}

.planner-form :deep(.ant-form-item-extra) {
  min-height: 0;
  margin-top: 3px;
  color: #7d897f;
  font-size: 11px;
}

.planner-form :deep(.ant-input),
.planner-form :deep(.ant-picker),
.planner-form :deep(.ant-input-number),
.planner-form :deep(.ant-input-number-affix-wrapper),
.planner-form :deep(.ant-select-selector) {
  border-width: 0 0 1px !important;
  border-color: var(--field-line) !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  padding-left: 0 !important;
}

.planner-form :deep(.ant-input-number-affix-wrapper .ant-input-number) {
  border: 0 !important;
}

.planner-form :deep(.ant-input-number-input) {
  padding-left: 0;
}

.planner-form :deep(.ant-input),
.planner-form :deep(.ant-input-number-input),
.planner-form :deep(.ant-picker-input > input),
.planner-form :deep(.ant-select-selection-item) {
  font-size: 15px;
}

.planner-form :deep(textarea.ant-input) {
  font-size: 14px;
  resize: vertical;
}

.planner-form :deep(.ant-input:focus),
.planner-form :deep(.ant-picker-focused),
.planner-form :deep(.ant-input-number-focused),
.planner-form :deep(.ant-input-number-affix-wrapper-focused),
.planner-form :deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--pine) !important;
  box-shadow: 0 1px 0 0 var(--pine) !important;
}

.constraint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 14px;
  margin: 2px 0 14px;
  font-size: 12px;
}

.constraint-mode {
  color: var(--muted);
  font-size: 11px;
}

.options {
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
}

.options-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 40px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.options-sign {
  font-size: 17px;
}

.option-fields {
  margin-top: 12px;
}

.preference {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 4px;
}

.preference :deep(.ant-checkbox-wrapper) {
  margin-inline-start: 0;
  font-size: 12px;
}

.submit-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-top: 22px;
}

.primary {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  gap: 28px;
  min-width: 180px;
  min-height: 46px;
  padding: 12px 26px;
  border: 0;
  border-radius: 0;
  background: var(--pine);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.primary:hover:not(:disabled) {
  background: var(--pine-dark);
}

.primary:disabled {
  cursor: progress;
  opacity: 0.86;
}

.primary svg {
  width: 18px;
  height: 18px;
}

.submit-hint {
  max-width: 260px;
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
}

.progress {
  margin-top: 16px;
}

.progress-track {
  height: 3px;
  overflow: hidden;
  background: var(--line);
}

.progress-track span {
  display: block;
  height: 100%;
  background: var(--pine);
  transition: width 0.4s ease;
}

.progress-text {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin: 8px 0 0;
  color: var(--pine);
  font-size: 12px;
}

.progress-value {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.form-error {
  margin-top: 14px;
  padding: 12px 14px;
  border-left: 2px solid #a14a3b;
  background: #f8eeeb;
  color: #6b3026;
  font-size: 12px;
  line-height: 1.7;
}

.form-error p {
  margin: 4px 0 0;
  overflow-wrap: anywhere;
}

.form-error-hint {
  color: #8a5a50;
}

@media (max-width: 1100px) {
  .home-layout {
    grid-template-columns: minmax(0, 1.28fr) minmax(0, 0.9fr);
    gap: 42px;
  }

  h1 {
    font-size: 43px;
  }

  .primary {
    min-width: 170px;
  }
}

@media (max-width: 760px) {
  .home-layout {
    display: flex;
    flex-direction: column;
    gap: 24px;
    padding-top: 26px;
  }

  .home-copy {
    display: contents;
  }

  .home-heading {
    order: 0;
  }

  .home-layout > :deep(.inspiration) {
    order: 1;
  }

  .planner-form {
    order: 2;
    width: 100%;
    max-width: none;
    margin: 0;
  }

  h1 {
    max-width: 330px;
    margin-bottom: 13px;
    font-size: 34px;
    line-height: 1.45;
    letter-spacing: 0.5px;
  }

  .intro {
    font-size: 12px;
    line-height: 1.8;
  }

  .field-grid,
  .option-fields {
    gap: 0 16px;
  }

  .submit-row {
    flex-direction: column;
    align-items: stretch;
    gap: 9px;
  }

  .primary {
    width: 100%;
  }

  .submit-hint {
    max-width: none;
    text-align: center;
  }
}

@media (max-width: 360px) {
  .field-grid,
  .option-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
