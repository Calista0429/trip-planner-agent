<template>
  <section class="ticket-wrap" :data-status="state.status" :aria-label="t('progress.ticketAria')">
    <article class="journey-ticket">
      <div class="ticket-content">
        <div class="ticket-identity">
          <span class="ticket-brand"><i class="ticket-brand-symbol" aria-hidden="true"></i>{{ t('app.brand') }}</span>
          <span>{{ t('progress.docLabel') }}</span>
        </div>

        <p v-if="summary.length" class="ticket-summary">
          <span v-for="(item, index) in summary" :key="index">{{ item }}</span>
        </p>

        <div class="ticket-main-copy">
          <h2 class="ticket-title">{{ title }}</h2>
          <div v-if="state.status === 'error'" class="ticket-detail ticket-error" role="alert">
            <p>{{ errorText }}</p>
            <p class="ticket-error-hint">{{ t('progress.errKept') }}</p>
          </div>
          <p v-else class="ticket-detail">{{ detail }}</p>
        </div>

        <ol class="ticket-checks" :aria-label="t('progress.stepsLabel')">
          <li
            v-for="step in steps"
            :key="step.key"
            class="ticket-checkpoint"
            :data-state="step.state"
            :aria-current="step.state === 'active' ? 'step' : undefined"
          >
            <div class="ticket-seal" aria-hidden="true">
              <div class="ticket-seal-center">
                <span class="ticket-seal-word">{{ step.seal }}</span>
                <span class="ticket-seal-state">{{ step.stateLabel }}</span>
                <i class="ticket-scan"></i>
              </div>
              <span class="ticket-seal-check">
                <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" focusable="false">
                  <path d="m2.5 6 2.2 2.2 4.8-4.7" />
                </svg>
              </span>
            </div>
            <strong aria-hidden="true">{{ step.name }}</strong>
            <span class="sr-only">{{ t('progress.stepAria', { step: step.name, state: step.stateLabel }) }}</span>
          </li>
        </ol>
      </div>

      <div class="ticket-perforation" aria-hidden="true"><i class="ticket-cut"></i><i class="ticket-cut"></i></div>

      <div class="ticket-stub">
        <div class="ticket-stage-meta">
          <span>{{ terminalOk ? t('progress.finalStage') : t('progress.currentStage') }}</span>
          <b>{{ stubLabel }}</b>
        </div>
        <div class="ticket-status-meta">
          <span v-if="!terminalOk" class="ticket-status">{{ statusText }}</span>
          <span class="ticket-elapsed">{{ elapsedText }}</span>
        </div>
      </div>

      <div v-if="state.status === 'error'" class="ticket-actions">
        <button type="button" class="ticket-retry" @click="emit('retry')">{{ t('progress.retry') }}</button>
      </div>
    </article>

    <!-- Announces step changes only; the elapsed clock is deliberately not live. -->
    <p class="sr-only" role="status" aria-live="polite">{{ announcement }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { locale, t } from '@/i18n'
import {
  STEP_KEYS,
  elapsedMs,
  formatElapsed,
  isQuiet,
  stepStates,
  type ProgressState,
  type StepState
} from '@/services/tripProgress'

const props = withDefaults(
  defineProps<{
    state: ProgressState
    /** Wall clock (ms) for the elapsed display only. */
    now: number
    /** Short facts from the submitted request, e.g. city / dates / days / party. */
    summary?: string[]
  }>(),
  { summary: () => [] }
)

const emit = defineEmits<{ retry: [] }>()

const NAME_KEYS = ['stepResearch', 'stepRoute', 'stepItinerary', 'stepReview'] as const
const SEAL_KEYS = ['sealResearch', 'sealRoute', 'sealItinerary', 'sealReview'] as const
const TITLE_KEYS = ['titleResearch', 'titleRoute', 'titleItinerary', 'titleReview'] as const
const STATE_KEYS: Record<StepState, string> = {
  pending: 'statePending',
  active: 'stateActive',
  complete: 'stateComplete',
  skipped: 'stateSkipped',
  error: 'stateError'
}

const terminalOk = computed(() => props.state.status === 'success' || props.state.status === 'fallback')

const steps = computed(() => {
  const states = stepStates(props.state)
  return STEP_KEYS.map((key, index) => {
    const state = states[index]
    const label =
      state === 'active' && props.state.fallbackPreparing
        ? t('progress.stateFallback')
        : t(`progress.${STATE_KEYS[state]}`)
    return {
      key,
      state,
      name: t(`progress.${NAME_KEYS[index]}`),
      seal: t(`progress.${SEAL_KEYS[index]}`),
      stateLabel: label
    }
  })
})

const title = computed(() => {
  const s = props.state
  if (s.status === 'success') return t('progress.titleSuccess')
  if (s.status === 'fallback') return t('progress.titleFallback')
  if (s.status === 'error') return t('progress.titleError')
  if (s.fallbackPreparing) return t('progress.titleFallbackPreparing')
  return t(`progress.${TITLE_KEYS[s.stage]}`)
})

const detail = computed(() => {
  const s = props.state
  if (s.status === 'success') return t('progress.detailSuccess')
  if (s.status === 'fallback') return t('progress.detailFallback')
  if (!s.phase) return t('progress.starting')
  if (s.phase === 'generating') {
    if (s.switchedModel) return t('progress.generatingSwitched')
    return (s.attempt ?? 1) > 1 ? t('progress.generatingMore') : t('progress.generating')
  }
  return t(`progress.${s.phase}`)
})

const errorText = computed(() => {
  const s = props.state
  switch (s.errorKind) {
    case 'http':
      return t('progress.errHttp', { status: s.errorStatus ?? '—' })
    case 'no_result':
      return t('progress.errNoResult')
    case 'failed':
      return t('progress.errFailed')
    case 'sse':
      return t('progress.errSse', { message: s.errorMessage || '—' })
    case 'aborted':
      return t('progress.errAborted')
    default:
      return t('progress.errNetwork')
  }
})

const statusText = computed(() => {
  const s = props.state
  if (s.status === 'error') return t('progress.statusError')
  return isQuiet(s, props.now) ? t('progress.statusQuiet') : t('progress.statusRunning')
})

const stubLabel = computed(() => {
  const s = props.state
  if (s.status === 'success') return t('progress.statusSuccess')
  if (s.status === 'fallback') return t('progress.statusFallback')
  return t(`progress.${NAME_KEYS[s.stage]}`)
})

const elapsedText = computed(() => {
  const time = formatElapsed(elapsedMs(props.state, props.now))
  return props.state.finishedAt != null ? t('progress.elapsedFinal', { time }) : t('progress.elapsed', { time })
})

const announcement = computed(() => {
  const s = props.state
  if (s.status === 'error') return ''
  if (terminalOk.value) return `${title.value}${locale.value === 'en' ? '. ' : '。'}${detail.value}`
  return title.value
})
</script>

<style scoped>
.ticket-wrap {
  --ticket-paper: #f6f7f5;
  --ticket-table: var(--paper, #f6f7f5);
  --ticket-ink: var(--pine, #315348);
  --ticket-line: #d9e0d5;
  --ticket-muted: #6f7e71;
  --ticket-seal: var(--pine, #315348);
  container-type: inline-size;
  margin-top: 22px;
  padding: 6px 8px 4px;
}

.ticket-wrap[data-status='fallback'] {
  --ticket-seal: #8a754e;
}

.journey-ticket {
  position: relative;
  width: 100%;
  max-width: 560px;
  box-sizing: border-box;
  color: var(--ticket-ink);
  background: var(--ticket-paper);
  border: 1px solid #cfd8ca;
  border-radius: 12px;
  box-shadow: 0 5px 9px #29453408, 0 22px 40px #29453407;
  transform: rotate(-1deg);
}

.ticket-content {
  padding: 25px 29px 19px;
  background-image: repeating-linear-gradient(0deg, transparent, transparent 3px, #31534803 3px, #31534803 4px);
  border-radius: 12px 12px 0 0;
}

.ticket-identity {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--ticket-line);
  color: var(--ticket-muted);
  font-size: 11px;
  line-height: 1.7;
  letter-spacing: 0.3px;
}

.ticket-brand {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--ticket-ink);
  font-size: 11px;
}

.ticket-brand-symbol {
  position: relative;
  flex: none;
  width: 15px;
  height: 15px;
  border: 1px solid currentColor;
  border-radius: 50%;
}

.ticket-brand-symbol::before,
.ticket-brand-symbol::after {
  content: '';
  position: absolute;
  left: 3px;
  right: 3px;
  height: 1px;
  background: currentColor;
  transform: rotate(-35deg);
}

.ticket-brand-symbol::before {
  top: 5px;
}

.ticket-brand-symbol::after {
  top: 8px;
}

.ticket-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 0;
  margin: 12px 0 0;
  color: var(--ticket-muted);
  font-size: 12px;
  line-height: 1.7;
}

.ticket-summary span {
  overflow-wrap: anywhere;
}

.ticket-summary span + span::before {
  content: '·';
  margin: 0 8px;
  color: #a9b5a6;
}

.ticket-main-copy {
  padding: 14px 0 16px;
}

.ticket-title {
  margin: 0;
  color: var(--ticket-ink);
  font-family: 'Songti SC', 'Noto Serif CJK SC', STSong, SimSun, serif;
  font-size: clamp(22px, 3vw, 28px);
  font-weight: 400;
  line-height: 1.5;
  letter-spacing: 1px;
  overflow-wrap: anywhere;
}

.ticket-wrap[data-status='error'] .ticket-title {
  color: #8a4f42;
}

.ticket-wrap[data-status='fallback'] .ticket-title {
  color: #7d653e;
}

.ticket-detail {
  min-height: 42px;
  max-width: 440px;
  margin: 8px 0 0;
  color: #66756a;
  font-size: 12px;
  line-height: 1.85;
  overflow-wrap: anywhere;
}

.ticket-error p {
  margin: 0;
  color: #7a3f33;
}

.ticket-error .ticket-error-hint {
  margin-top: 2px;
  color: #8a5a50;
}

.ticket-checks {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 10px 0 6px;
  list-style: none;
}

.ticket-checkpoint {
  min-width: 0;
  color: var(--ticket-muted);
  text-align: center;
}

.ticket-seal {
  position: relative;
  display: grid;
  place-items: center;
  width: 78px;
  height: 78px;
  margin: 0 auto 13px;
  border: 1px dashed #cfd8ca;
  border-radius: 50%;
  color: #a4afa0;
  background: var(--ticket-paper);
  isolation: isolate;
}

.ticket-seal::before {
  content: '';
  position: absolute;
  inset: 5px;
  border: 1px solid #e5eae1;
  border-radius: 50%;
  pointer-events: none;
}

.ticket-seal-center {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 58px;
  height: 58px;
  border-radius: 50%;
  overflow: hidden;
}

.ticket-seal-word {
  padding-left: 3px;
  font-family: 'Songti SC', 'Noto Serif CJK SC', STSong, SimSun, serif;
  font-size: 20px;
  line-height: 1.2;
  letter-spacing: 3px;
  white-space: nowrap;
}

:lang(en) .ticket-seal-word {
  padding-left: 0;
  font-size: 14px;
  letter-spacing: 0.5px;
}

.ticket-seal-state {
  max-width: 54px;
  overflow: hidden;
  font-size: 9px;
  line-height: 1.3;
  letter-spacing: 0.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ticket-scan {
  position: absolute;
  z-index: 2;
  top: 0;
  left: 2px;
  right: 2px;
  height: 1px;
  opacity: 0;
  background: var(--ticket-seal);
  box-shadow: 0 -4px 12px #31534812;
  pointer-events: none;
}

.ticket-seal-check {
  position: absolute;
  right: -1px;
  bottom: 4px;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 3px solid var(--ticket-paper);
  border-radius: 50%;
  color: #fff;
  background: var(--ticket-seal);
  opacity: 0;
  transform: scale(0.6);
}

.ticket-seal-check svg {
  display: block;
  width: 10px;
  height: 10px;
}

.ticket-checkpoint strong {
  display: block;
  color: inherit;
  font-size: 12px;
  font-weight: 400;
  line-height: 1.6;
  letter-spacing: 0.5px;
  overflow-wrap: anywhere;
}

.ticket-checkpoint[data-state='active'],
.ticket-checkpoint[data-state='complete'] {
  color: var(--ticket-ink);
}

.ticket-checkpoint[data-state='active'] .ticket-seal {
  border-style: solid;
  border-color: var(--ticket-seal);
  color: var(--ticket-seal);
}

.ticket-checkpoint[data-state='active'] .ticket-seal::before {
  border-color: #a5b8a1;
}

.ticket-checkpoint[data-state='active'] .ticket-scan {
  animation: ticket-scan 2.7s ease-in-out infinite;
}

/* Lands once when the step turns complete; the element is reused, so ticks never replay it. */
.ticket-checkpoint[data-state='complete'] .ticket-seal {
  border: 1.5px solid var(--ticket-seal);
  color: var(--ticket-seal);
  transform: rotate(-9deg);
  animation: ticket-imprint 0.5s cubic-bezier(0.2, 0.75, 0.25, 1) both;
}

.ticket-checkpoint[data-state='complete'] .ticket-seal::before {
  border-color: var(--ticket-seal);
  opacity: 0.65;
}

.ticket-checkpoint[data-state='complete'] .ticket-seal-check {
  opacity: 1;
  transform: scale(1);
}

.ticket-checkpoint[data-state='skipped'] .ticket-seal {
  border-style: dashed;
  border-color: #bcc6b8;
  color: #8f9a8c;
}

.ticket-checkpoint[data-state='error'] {
  color: #93655c;
}

.ticket-checkpoint[data-state='error'] .ticket-seal {
  border-style: solid;
  border-color: #aa7a6d;
  color: #93655c;
}

.ticket-checkpoint[data-state='error'] .ticket-seal::before {
  border-color: #d8c1b9;
}

.ticket-perforation {
  position: relative;
  display: flex;
  align-items: center;
  height: 25px;
  margin: 0 20px;
}

.ticket-perforation::before {
  content: '';
  width: 100%;
  border-top: 1px dashed #c6d2c2;
}

.ticket-cut {
  position: absolute;
  top: 50%;
  z-index: 2;
  width: 17px;
  height: 17px;
  margin-top: -8.5px;
  border: 1px solid #cfd8ca;
  border-radius: 50%;
  background: var(--ticket-table);
}

.ticket-cut:first-child {
  left: -29px;
  border-left-color: transparent;
  transform: rotate(-45deg);
}

.ticket-cut:last-child {
  right: -29px;
  border-right-color: transparent;
  transform: rotate(-45deg);
}

.ticket-stub {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 64px;
  padding: 10px 28px 20px;
}

.ticket-stage-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  color: var(--ticket-muted);
  font-size: 10px;
  line-height: 1.6;
}

.ticket-stage-meta b {
  color: var(--ticket-ink);
  font-size: 12px;
  font-weight: 400;
  overflow-wrap: anywhere;
}

.ticket-status-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  min-width: 0;
  text-align: right;
}

.ticket-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ticket-seal);
  font-size: 11px;
  line-height: 1.65;
}

.ticket-status::before {
  content: '';
  flex: none;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
}

.ticket-wrap[data-status='error'] .ticket-status {
  color: #93655c;
}

.ticket-elapsed {
  color: var(--ticket-muted);
  font-size: 10px;
  line-height: 1.6;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.ticket-actions {
  display: flex;
  justify-content: flex-end;
  padding: 0 28px 20px;
  margin-top: -6px;
}

.ticket-retry {
  min-height: 36px;
  padding: 0 16px;
  border: 1px solid var(--pine, #315348);
  background: transparent;
  color: var(--pine, #315348);
  font-size: 12px;
  cursor: pointer;
}

.ticket-retry:hover {
  background: #edf2eb;
}

.ticket-retry:focus-visible {
  outline: 2px solid var(--pine, #315348);
  outline-offset: 3px;
}

/* No looping animation once the run is over: seals sit in their final frame. */
.ticket-wrap[data-status='error'] .ticket-scan,
.ticket-wrap[data-status='error'] .ticket-seal {
  animation: none;
}

@keyframes ticket-scan {
  0%,
  12% {
    transform: translateY(4px);
    opacity: 0;
  }
  22%,
  75% {
    opacity: 0.65;
  }
  90%,
  100% {
    transform: translateY(54px);
    opacity: 0;
  }
}

@keyframes ticket-imprint {
  0% {
    opacity: 0.4;
    transform: translateY(-5px) scale(1.13) rotate(-14deg);
  }
  65% {
    opacity: 1;
    transform: translateY(1px) scale(0.97) rotate(-8deg);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1) rotate(-9deg);
  }
}

@container (max-width: 520px) {
  .ticket-content {
    padding: 22px 22px 15px;
  }

  .ticket-checks {
    gap: 6px;
  }

  .ticket-seal {
    width: 66px;
    height: 66px;
  }

  .ticket-seal-center {
    width: 50px;
    height: 50px;
  }

  .ticket-seal-word {
    font-size: 18px;
  }

  .ticket-seal-check {
    right: -2px;
    bottom: 1px;
  }

  .ticket-checkpoint strong {
    font-size: 11px;
  }

  .ticket-stub,
  .ticket-actions {
    padding-left: 22px;
    padding-right: 22px;
  }
}

@container (max-width: 400px) {
  .journey-ticket {
    transform: rotate(-0.7deg);
  }

  .ticket-content {
    padding: 20px 18px 12px;
  }

  .ticket-identity {
    gap: 9px;
    padding-bottom: 12px;
    font-size: 10px;
  }

  .ticket-title {
    font-size: 22px;
    letter-spacing: 0.5px;
  }

  .ticket-detail {
    min-height: 0;
    font-size: 12px;
  }

  .ticket-checks {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px 12px;
    padding: 8px 6px 12px;
  }

  .ticket-seal {
    width: 72px;
    height: 72px;
    margin-bottom: 8px;
  }

  .ticket-seal-center {
    width: 54px;
    height: 54px;
  }

  .ticket-seal-word {
    font-size: 20px;
  }

  .ticket-stub {
    gap: 12px;
    padding: 10px 18px 18px;
  }

  .ticket-actions {
    padding: 0 18px 18px;
  }

  .ticket-perforation {
    margin: 0 14px;
  }

  .ticket-cut:first-child {
    left: -23px;
  }

  .ticket-cut:last-child {
    right: -23px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ticket-checkpoint .ticket-seal,
  .ticket-checkpoint .ticket-scan {
    animation: none !important;
  }

  .ticket-checkpoint[data-state='active'] .ticket-scan {
    top: 27px;
    opacity: 0.45;
  }

  .journey-ticket {
    transform: none;
  }
}
</style>
