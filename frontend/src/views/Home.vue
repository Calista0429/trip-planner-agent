<template>
  <div class="home-container">
    <div class="planner-page">
      <div class="top-banner">
        <div class="top-banner-content">
          <div class="banner-kicker">AI Trip Planner</div>
          <h1>{{ t('home.bannerTitle') }}</h1>
          <p>{{ t('home.bannerSubtitle') }}</p>
        </div>
        <div class="banner-summary">
          <div>
            <span class="summary-label">{{ t('home.summaryTrip') }}</span>
            <strong>{{ formData.travel_days }} {{ t('home.unitDays') }}</strong>
          </div>
          <div>
            <span class="summary-label">{{ t('home.summaryParty') }}</span>
            <strong>{{ formData.party.total }} {{ t('home.unitPeople') }}</strong>
          </div>
          <div>
            <span class="summary-label">{{ t('home.summaryProtocol') }}</span>
            <strong>Planner</strong>
          </div>
        </div>
      </div>

      <a-card class="form-card" :bordered="false">
        <div class="form-card-header">
          <div>
            <div class="form-eyebrow">Plan Request</div>
            <h2>{{ t('home.cardTitle') }}</h2>
          </div>
          <div class="header-status">
            <span>{{ formData.city || t('home.noCity') }}</span>
            <span>{{ formData.travel_days }} {{ t('home.unitDays') }}</span>
            <span>{{ formData.party.total }} {{ t('home.unitPeople') }}</span>
          </div>
        </div>

        <a-form
          :model="formData"
          layout="vertical"
          @finish="handleSubmit"
        >
          <div class="form-section">
            <div class="section-header">
              <EnvironmentOutlined />
              <span class="section-title">{{ t('home.sectionWhere') }}</span>
            </div>

            <a-row :gutter="[20, 16]">
              <a-col :xs="{ span: 24 }" :lg="{ span: 10 }">
                <a-form-item name="city" :rules="[{ required: true, message: t('home.ruleCity') }]">
                  <template #label>
                    <span class="form-label">{{ t('home.labelCity') }}</span>
                  </template>
                  <a-input
                    v-model:value="formData.city"
                    :placeholder="t('home.placeholderCity')"
                    size="large"
                    class="custom-input"
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="{ span: 24 }" :sm="{ span: 12 }" :lg="{ span: 7 }">
                <a-form-item name="start_date" :rules="[{ required: true, message: t('home.ruleStartDate') }]">
                  <template #label>
                    <span class="form-label">{{ t('home.labelStartDate') }}</span>
                  </template>
                  <a-date-picker
                    v-model:value="formData.start_date"
                    style="width: 100%"
                    size="large"
                    class="custom-input"
                    :placeholder="t('home.placeholderDate')"
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="{ span: 24 }" :sm="{ span: 12 }" :lg="{ span: 7 }">
                <a-form-item name="end_date" :rules="[{ required: true, message: t('home.ruleEndDate') }]">
                  <template #label>
                    <span class="form-label">{{ t('home.labelEndDate') }}</span>
                  </template>
                  <a-date-picker
                    v-model:value="formData.end_date"
                    style="width: 100%"
                    size="large"
                    class="custom-input"
                    :placeholder="t('home.placeholderDate')"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <TeamOutlined />
              <span class="section-title">{{ t('home.sectionParty') }}</span>
            </div>

            <a-row :gutter="[20, 16]">
              <a-col :xs="{ span: 8 }" :md="{ span: 4 }">
                <a-form-item name="adults">
                  <template #label>
                    <span class="form-label">{{ t('home.labelAdults') }}</span>
                  </template>
                  <a-input-number v-model:value="formData.party.adults" :min="0" :max="20" size="large" class="custom-input" style="width: 100%" />
                </a-form-item>
              </a-col>
              <a-col :xs="{ span: 8 }" :md="{ span: 4 }">
                <a-form-item name="children">
                  <template #label>
                    <span class="form-label">{{ t('home.labelChildren') }}</span>
                  </template>
                  <a-input-number v-model:value="formData.party.children" :min="0" :max="20" size="large" class="custom-input" style="width: 100%" />
                </a-form-item>
              </a-col>
              <a-col :xs="{ span: 8 }" :md="{ span: 4 }">
                <a-form-item name="elders">
                  <template #label>
                    <span class="form-label">{{ t('home.labelElders') }}</span>
                  </template>
                  <a-input-number v-model:value="formData.party.elders" :min="0" :max="20" size="large" class="custom-input" style="width: 100%" />
                </a-form-item>
              </a-col>
              <a-col :xs="{ span: 24 }" :md="{ span: 4 }">
                <a-form-item name="companion_type">
                  <template #label>
                  <span class="form-label">{{ t('home.labelCompanion') }}</span>
                </template>
                <a-select v-model:value="formData.party.companion_type" size="large" class="custom-select">
                    <a-select-option
                      v-for="option in companionTypeOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :xs="{ span: 24 }" :md="{ span: 4 }">
                <a-form-item name="budget_amount">
                  <template #label>
                    <span class="form-label">{{ t('home.labelBudget') }}</span>
                  </template>
                  <a-input-number
                    v-model:value="formData.budget_constraint.amount"
                    :min="0"
                    :step="100"
                    size="large"
                    class="custom-input"
                    style="width: 100%"
                    :placeholder="t('home.placeholderBudget')"
                  />
                  <!-- Strict (hard) budget: only meaningful once an amount is entered. -->
                  <a-checkbox
                    v-model:checked="strictBudget"
                    :disabled="formData.budget_constraint.amount === null || formData.budget_constraint.amount === undefined"
                    style="margin-top: 8px"
                  >
                    {{ t('home.noOverspend') }}
                  </a-checkbox>
                </a-form-item>
              </a-col>
              <a-col :xs="{ span: 24 }" :md="{ span: 4 }">
                <a-form-item name="budget_level">
                  <template #label>
                  <span class="form-label">{{ t('home.labelBudgetLevel') }}</span>
                </template>
                <a-select v-model:value="formData.budget_constraint.budget_level" size="large" class="custom-select">
                    <a-select-option
                      v-for="option in budgetLevelOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <CarOutlined />
              <span class="section-title">{{ t('home.sectionPrefs') }}</span>
            </div>

            <a-row :gutter="[20, 16]">
              <a-col :xs="{ span: 24 }" :lg="{ span: 8 }">
                <a-form-item name="transportation">
                  <template #label>
                  <span class="form-label">{{ t('home.labelTransportation') }}</span>
                </template>
                <a-select v-model:value="formData.transportation" size="large" class="custom-select">
                    <a-select-option
                      v-for="option in transportationOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :xs="{ span: 24 }" :lg="{ span: 8 }">
                <a-form-item name="accommodation">
                  <template #label>
                  <span class="form-label">{{ t('home.labelAccommodation') }}</span>
                </template>
                <a-select v-model:value="formData.accommodation" size="large" class="custom-select">
                    <a-select-option
                      v-for="option in accommodationOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :xs="{ span: 24 }" :lg="{ span: 8 }">
                <a-form-item name="preferences">
                  <template #label>
                    <span class="form-label">{{ t('home.labelPreferences') }}</span>
                  </template>
                  <div class="preference-tags">
                    <a-checkbox-group v-model:value="formData.preferences" class="custom-checkbox-group">
                      <a-checkbox
                        v-for="option in preferenceOptions"
                        :key="option.value"
                        :value="option.value"
                        class="preference-tag"
                      >
                        <span class="preference-icon">{{ option.icon }}</span>
                        <span>{{ option.label }}</span>
                      </a-checkbox>
                    </a-checkbox-group>
                  </div>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <EditOutlined />
              <span class="section-title">{{ t('home.sectionExtra') }}</span>
            </div>

            <a-form-item name="free_text_input">
              <a-textarea
                v-model:value="formData.free_text_input"
                :placeholder="t('home.placeholderExtra')"
                :rows="3"
                size="large"
                class="custom-textarea"
              />
            </a-form-item>
          </div>

          <a-form-item>
            <a-button
              type="primary"
              html-type="submit"
              :loading="loading"
              size="large"
              block
              class="submit-button"
            >
              <template v-if="!loading">
                <RocketOutlined />
                <span>{{ t('home.submit') }}</span>
              </template>
              <template v-else>
                <span>{{ t('home.submitting') }}</span>
              </template>
            </a-button>
          </a-form-item>

          <a-form-item v-if="loading">
            <div class="loading-container">
              <a-progress
                :percent="loadingProgress"
                status="active"
                :stroke-color="{
                  '0%': '#0f766e',
                  '100%': '#2563eb',
                }"
                :stroke-width="8"
              />
              <p class="loading-status">
                {{ loadingStatus }}
              </p>
            </div>
          </a-form-item>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  CarOutlined,
  EditOutlined,
  EnvironmentOutlined,
  RocketOutlined,
  TeamOutlined
} from '@ant-design/icons-vue'
import { streamTripPlan } from '@/services/api'
import type { TripFormData } from '@/types'
import type { Dayjs } from 'dayjs'
import { t } from '@/i18n'
import {
  accommodationOptions,
  budgetLevelOptions,
  companionTypeOptions,
  preferenceOptions,
  transportationOptions
} from '@/i18n/options'

const router = useRouter()
const loading = ref(false)
const loadingProgress = ref(0)
const loadingStatus = ref('')
// Hard budget toggle: when checked (and an amount is set) strictness becomes 'hard'.
const strictBudget = ref(false)

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
  loadingProgress.value = 0
  loadingStatus.value = t('home.starting')

  try {
    const budgetAmount = formData.budget_constraint.amount
    // No amount -> 'none'; amount + strict toggle -> 'hard'; amount only -> 'soft'.
    const budgetStrictness =
      budgetAmount === null || budgetAmount === undefined
        ? 'none'
        : strictBudget.value
          ? 'hard'
          : 'soft'
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
        strictness: budgetStrictness
      }
    }

    const plan = await streamTripPlan(requestData, (event) => {
      if (event.type === 'progress') {
        if (event.message) loadingStatus.value = event.message
        loadingProgress.value = nextProgress(event.phase, event.attempt, loadingProgress.value)
      }
    })

    loadingProgress.value = 100
    loadingStatus.value = t('home.done')

    // Persist the plan and navigate to the result page.
    sessionStorage.setItem('tripPlan', JSON.stringify(plan))
    message.success(t('home.successGenerated'))
    setTimeout(() => {
      router.push('/result')
    }, 500)
  } catch (error: any) {
    message.error(error.message || t('home.errGenerate'))
  } finally {
    setTimeout(() => {
      loading.value = false
      loadingProgress.value = 0
      loadingStatus.value = ''
    }, 1000)
  }
}
</script>

<style scoped>
.home-container {
  min-height: 100vh;
  padding: 28px 24px 48px;
  width: 100%;
  background: #f5f7fa;
}

.planner-page {
  max-width: 1280px;
  margin: 0 auto;
}

.top-banner {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  min-height: 220px;
  margin-bottom: -28px;
  padding: 34px 38px 58px;
  border-radius: 8px;
  background:
    linear-gradient(90deg, rgba(15, 23, 42, 0.92), rgba(15, 23, 42, 0.62)),
    url('https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1600&q=80') center/cover;
  color: #ffffff;
}

.top-banner-content {
  max-width: 620px;
}

.banner-kicker {
  margin-bottom: 12px;
  color: rgba(255, 255, 255, 0.76);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.top-banner h1 {
  margin: 0;
  font-size: 36px;
  font-weight: 760;
  line-height: 1.18;
}

.top-banner p {
  margin: 14px 0 0;
  color: rgba(255, 255, 255, 0.84);
  font-size: 16px;
  line-height: 1.7;
}

.banner-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  min-width: 340px;
  overflow: hidden;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(10px);
}

.banner-summary > div {
  padding: 16px 18px;
  background: rgba(255, 255, 255, 0.12);
}

.summary-label {
  display: block;
  margin-bottom: 8px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
}

.banner-summary strong {
  color: #ffffff;
  font-size: 20px;
}

.form-card {
  position: relative;
  z-index: 1;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: #ffffff !important;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.12);
}

.form-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
  padding-bottom: 20px;
  border-bottom: 1px solid #edf0f5;
}

.form-eyebrow {
  color: #1677ff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.form-card-header h2 {
  margin: 6px 0 0;
  color: #0f172a;
  font-size: 24px;
  font-weight: 700;
}

.header-status {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.header-status span {
  padding: 6px 10px;
  border-radius: 999px;
  background: #f3f6fb;
  color: #475569;
  font-size: 13px;
}

.form-section {
  margin-bottom: 24px;
  padding-bottom: 22px;
  border-bottom: 1px solid #eef2f7;
}

.form-section:last-of-type {
  border-bottom: none;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  color: #1677ff;
}

.section-header :deep(.anticon) {
  font-size: 17px;
}

.section-title {
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
}

.form-label {
  color: #475569;
  font-size: 13px;
  font-weight: 650;
}

.custom-input :deep(.ant-input) {
  border-radius: 8px;
}

.custom-input :deep(.ant-input),
.custom-textarea :deep(.ant-input),
.custom-select :deep(.ant-select-selector),
.custom-input :deep(.ant-picker) {
  border-color: #d9dee8 !important;
  border-radius: 8px !important;
  box-shadow: none !important;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.custom-input :deep(.ant-input:hover),
.custom-textarea :deep(.ant-input:hover),
.custom-select:hover :deep(.ant-select-selector),
.custom-input :deep(.ant-picker:hover) {
  border-color: #1677ff !important;
}

.custom-input :deep(.ant-input:focus),
.custom-textarea :deep(.ant-input:focus),
.custom-select :deep(.ant-select-focused .ant-select-selector),
.custom-input :deep(.ant-picker-focused) {
  border-color: #1677ff !important;
  box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.12) !important;
}

.preference-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.custom-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  width: 100%;
}

.preference-tag :deep(.ant-checkbox-wrapper) {
  margin: 0 !important;
  padding: 7px 12px 7px 10px;
  border: 1px solid #d9dee8;
  border-radius: 999px;
  transition: all 0.3s ease;
  background: #ffffff;
  font-size: 14px;
}

.preference-tag :deep(.ant-checkbox-wrapper:hover) {
  border-color: #1677ff;
  background: #f0f6ff;
}

.preference-tag :deep(.ant-checkbox-wrapper-checked) {
  border-color: #1677ff;
  background: #eaf3ff;
  color: #0958d9;
}

.preference-tag :deep(.ant-checkbox + span) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.preference-icon {
  display: inline-flex;
  width: 18px;
  justify-content: center;
}

.submit-button {
  height: 52px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 700;
  background: #1677ff;
  border: none;
  box-shadow: 0 10px 22px rgba(22, 119, 255, 0.24);
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.submit-button :deep(.anticon) {
  margin-right: 8px;
}

.submit-button:hover {
  background: #0958d9 !important;
  transform: translateY(-2px);
  box-shadow: 0 14px 30px rgba(22, 119, 255, 0.3);
}

.submit-button:active {
  transform: translateY(0);
}

.loading-container {
  text-align: center;
  padding: 20px;
  border: 1px dashed #1677ff;
  border-radius: 8px;
  background: #f7fbff;
}

.loading-status {
  margin: 14px 0 0;
  color: #0958d9;
  font-size: 15px;
  font-weight: 650;
}

@media (max-width: 960px) {
  .top-banner {
    display: block;
    min-height: auto;
    padding: 28px 24px 52px;
  }

  .banner-summary {
    min-width: 0;
    margin-top: 22px;
  }
}

@media (max-width: 720px) {
  .home-container {
    padding: 16px 12px 32px;
  }

  .top-banner {
    margin-bottom: -18px;
    padding: 24px 18px 42px;
  }

  .top-banner h1 {
    font-size: 28px;
  }

  .form-card :deep(.ant-card-body) {
    padding: 20px;
  }

  .banner-summary {
    grid-template-columns: 1fr;
  }

  .form-card-header {
    flex-direction: column;
  }

  .header-status {
    justify-content: flex-start;
  }
}
</style>
