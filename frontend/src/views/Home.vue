<template>
  <div class="home-page">
    <section class="shell home-layout" aria-labelledby="home-title" :inert="overlayOpen || undefined">
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

        </a-form>
      </div>

      <CameraCarousel />
    </section>

    <!-- Full-screen transition while the plan is generated; hands off to the result page. -->
    <TripTransitionOverlay
      :open="overlayOpen"
      :state="run.state.value"
      :now="run.clock.value"
      :summary="ticketSummary"
      @retry="retrySubmit"
      @close="closeOverlay"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import dayjs, { type Dayjs } from 'dayjs'
import CameraCarousel from '@/components/home/CameraCarousel.vue'
import TripTransitionOverlay from '@/components/home/TripTransitionOverlay.vue'
import { HANDOFF_DELAY_MS, HANDOFF_DELAY_REDUCED_MS, useTripPlanRun } from '@/composables/useTripPlanRun'
import { playNextRouteTransition } from '@/services/routeTransition'
import { loadRequest } from '@/services/tripSession'
import { clearPlannerDraft, loadPlannerDraft, savePlannerDraft, type PlannerDraft } from '@/services/plannerDraft'
import { useShellNavigationLock } from '@/services/shellNavigation'
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
const prefersReducedMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// One planning run at a time; the plan is saved once and the result page opens once.
// The leave guard below lets exactly this navigation through.
let handoffInProgress = false
const run = useTripPlanRun({
  navigate: () => {
    playNextRouteTransition('trip-reveal')
    handoffInProgress = true
    void router.push({ path: '/result', query: { day: '1' } }).finally(() => {
      handoffInProgress = false
    })
  },
  handoffDelay: () => (prefersReducedMotion() ? HANDOFF_DELAY_REDUCED_MS : HANDOFF_DELAY_MS),
  onSettled: (outcome) => {
    // The plan and its request are saved; this round's draft is done with.
    discardDraft()
    if (outcome === 'fallback') message.warning(t('home.fallbackNotice'))
    else message.success(t('home.successGenerated'))
  }
  // Errors are shown (and announced) by the ticket itself; a toast would cover it.
})
// Form stays locked while running and during the short hand-off to the result page.
const loading = run.busy
// The overlay stays up for every non-idle state; errors close it via "back to edit".
const overlayOpen = computed(() => run.state.value.status !== 'idle')
const optionsOpen = ref(false)
// Hard budget toggle: when checked (and an amount is set) strictness becomes 'hard'.
const strictBudget = ref(false)
// Prefill writes party fields in bulk; skip the companion auto-derivation once.
let suppressCompanionDerive = false

type TripFormState = Omit<TripFormData, 'start_date' | 'end_date' | 'party'> & {
  start_date: Dayjs | null
  end_date: Dayjs | null
  // A cleared number input holds null until the user types again.
  party: Omit<TripFormData['party'], 'adults' | 'children' | 'elders'> & {
    adults: number | null
    children: number | null
    elders: number | null
  }
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

// ---- Restoring the form: unsubmitted draft → last submitted request → defaults ----

/** The draft of the form exactly as shown, including half-filled fields. */
function snapshotDraft(): PlannerDraft {
  return {
    version: 1,
    provinceCode: provinceCode.value ?? null,
    form: {
      city: formData.city,
      start_date: formData.start_date ? formData.start_date.format('YYYY-MM-DD') : null,
      end_date: formData.end_date ? formData.end_date.format('YYYY-MM-DD') : null,
      transportation: formData.transportation,
      accommodation: formData.accommodation,
      preferences: [...formData.preferences],
      free_text_input: formData.free_text_input,
      party: {
        adults: formData.party.adults ?? null,
        children: formData.party.children ?? null,
        elders: formData.party.elders ?? null,
        companion_type: formData.party.companion_type
      },
      budget_constraint: {
        amount: formData.budget_constraint.amount ?? null,
        budget_level: formData.budget_constraint.budget_level
      }
    },
    strictBudget: strictBudget.value,
    optionsOpen: optionsOpen.value
  }
}

function applyDraft(draft: PlannerDraft) {
  const { form } = draft
  const province = PROVINCES.find(p => p.adcode === draft.provinceCode)
  provinceCode.value = province?.adcode
  const city = province?.cities.find(c => c.name === form.city)
  formData.city = province && city && citySupport(province, city) !== 'unsupported' ? city.name : ''
  formData.start_date = form.start_date ? dayjs(form.start_date) : null
  formData.end_date = form.end_date ? dayjs(form.end_date) : null
  formData.transportation = form.transportation
  formData.accommodation = form.accommodation
  formData.preferences = [...form.preferences]
  formData.free_text_input = form.free_text_input
  formData.party.adults = form.party.adults
  formData.party.children = form.party.children
  formData.party.elders = form.party.elders
  formData.party.companion_type = form.party.companion_type
  formData.budget_constraint.amount = form.budget_constraint.amount
  formData.budget_constraint.budget_level = form.budget_constraint.budget_level
  strictBudget.value = draft.strictBudget
  optionsOpen.value = draft.optionsOpen
}

// "Edit trip details" on the result page lands here with no draft: restore that
// request so the user edits it instead of starting over.
function applySubmittedRequest(saved: TripFormData) {
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
}

// ---- Draft writes: debounced while editing, flushed when leaving ----

const DRAFT_SAVE_DELAY_MS = 200
/** Off until the form has been restored, so the initial empty form never overwrites a draft. */
let draftWritable = false
let draftTimer: ReturnType<typeof setTimeout> | null = null

function cancelDraftTimer() {
  if (draftTimer !== null) {
    clearTimeout(draftTimer)
    draftTimer = null
  }
}

function flushDraft() {
  cancelDraftTimer()
  if (draftWritable) savePlannerDraft(snapshotDraft())
}

/** After a successful run: drop the draft and stop writing it for the rest of this page's life. */
function discardDraft() {
  cancelDraftTimer()
  draftWritable = false
  clearPlannerDraft()
}

watch(
  [formData, provinceCode, strictBudget, optionsOpen],
  () => {
    if (!draftWritable) return
    cancelDraftTimer()
    draftTimer = setTimeout(flushDraft, DRAFT_SAVE_DELAY_MS)
  },
  { deep: true }
)

onMounted(async () => {
  const draft = loadPlannerDraft()
  const saved = draft ? null : loadRequest()
  if (draft || saved) {
    suppressCompanionDerive = true
    if (draft) applyDraft(draft)
    else if (saved) applySubmittedRequest(saved)
    // Let the date / party watchers run on the restored values first.
    await nextTick()
    suppressCompanionDerive = false
  }
  draftWritable = true
})

// ---- Leaving: never in the middle of a run or its hand-off ----

// Header, side menu and footer stay locked while the planning overlay is up.
useShellNavigationLock(() => overlayOpen.value)

onBeforeRouteLeave(() => {
  if (run.busy.value && !handoffInProgress) return false
  flushDraft()
  return true
})

onBeforeUnmount(flushDraft)

const handleSubmit = async () => {
  if (loading.value) return
  if (!formData.start_date || !formData.end_date) {
    message.error(t('home.errPickDate'))
    return
  }

  if (formData.party.total <= 0) {
    message.error(t('home.errPartySize'))
    return
  }

  const budgetAmount = formData.budget_constraint.amount
  const requestData: TripFormData = {
    city: formData.city,
    start_date: formData.start_date.format('YYYY-MM-DD'),
    end_date: formData.end_date.format('YYYY-MM-DD'),
    travel_days: formData.travel_days,
    transportation: formData.transportation,
    accommodation: formData.accommodation,
    preferences: [...formData.preferences],
    free_text_input: formData.free_text_input,
    party: {
      adults: formData.party.adults ?? 0,
      children: formData.party.children ?? 0,
      elders: formData.party.elders ?? 0,
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

  await run.submit(requestData)
}

/** "Back to edit" after an error: close the overlay and return focus to the form. */
const closeOverlay = async () => {
  run.reset()
  await nextTick()
  document.querySelector<HTMLButtonElement>('.planner-form button.primary')?.focus()
}

/** Retry from the error ticket: re-run form validation, then submit once. */
const retrySubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  await handleSubmit()
}

/** Facts for the ticket, taken from the request this run was started with. */
const ticketSummary = computed(() => {
  const req = run.request.value
  if (!req) return []
  const match = findCity(req.city)
  const city = match ? (locale.value === 'en' ? match.city.en : match.city.name) : req.city
  const fmt = locale.value === 'en' ? 'MMM D' : 'M月D日'
  const start = dayjs(req.start_date)
  const end = dayjs(req.end_date)
  const dates = start.isValid() && end.isValid() ? `${start.format(fmt)} – ${end.format(fmt)}` : ''
  const days = req.travel_days === 1 ? t('progress.summaryDayOne') : t('progress.summaryDays', { n: req.travel_days })
  const people =
    req.party?.total === 1 ? t('progress.summaryPersonOne') : t('progress.summaryPeople', { n: req.party?.total ?? 0 })
  return [city, dates, days, people].filter(Boolean)
})
</script>

<style scoped>
.home-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.38fr) minmax(0, 0.82fr);
  gap: 32px;
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

/* With the side menu taking a column, two columns no longer fit here: stack
   the form above the photographs (same order as on desktop). */
@media (max-width: 1100px) {
  .home-layout {
    grid-template-columns: minmax(0, 1fr);
    gap: 32px;
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
