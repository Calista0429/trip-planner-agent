<template>
  <Transition name="trip-overlay" appear>
    <div
      v-if="open"
      ref="dialogEl"
      class="trip-overlay"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      :data-status="state.status"
      tabindex="-1"
      @keydown="onKeydown"
    >
      <div class="trip-overlay-stage">
        <TripTicketProgress
          :state="state"
          :now="now"
          :summary="summary"
          :title-id="titleId"
          @retry="emit('retry')"
          @edit="emit('close')"
        />
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import TripTicketProgress from './TripTicketProgress.vue'
import type { ProgressState } from '@/services/tripProgress'

const props = withDefaults(
  defineProps<{
    open: boolean
    state: ProgressState
    now: number
    summary?: string[]
  }>(),
  { summary: () => [] }
)

const emit = defineEmits<{ retry: []; close: [] }>()

const titleId = 'trip-overlay-title'
const dialogEl = ref<HTMLElement | null>(null)
let previousOverflow: string | null = null

function lockScroll() {
  if (previousOverflow !== null) return
  previousOverflow = document.documentElement.style.overflow
  document.documentElement.style.overflow = 'hidden'
}

function unlockScroll() {
  if (previousOverflow === null) return
  document.documentElement.style.overflow = previousOverflow
  previousOverflow = null
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Keep Tab inside the dialog; Escape only closes once the run has stopped with an error. */
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.state.status === 'error') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key !== 'Tab' || !dialogEl.value) return
  const items = [...dialogEl.value.querySelectorAll<HTMLElement>(FOCUSABLE)]
  if (items.length === 0) {
    event.preventDefault()
    dialogEl.value.focus()
    return
  }
  const first = items[0]
  const last = items[items.length - 1]
  const active = document.activeElement
  if (event.shiftKey && (active === first || active === dialogEl.value)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      lockScroll()
      await nextTick()
      dialogEl.value?.focus({ preventScroll: true })
    } else {
      unlockScroll()
    }
  },
  { immediate: true }
)

// When a run fails, move focus to the retry action so keyboard users can act.
watch(
  () => props.state.status,
  async (status) => {
    if (status !== 'error' || !props.open) return
    await nextTick()
    dialogEl.value?.querySelector<HTMLElement>('.ticket-retry')?.focus({ preventScroll: true })
  }
)

onBeforeUnmount(unlockScroll)
</script>

<style scoped>
.trip-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  overflow-y: auto;
  overscroll-behavior: contain;
  background:
    radial-gradient(ellipse at 50% 38%, #f6f7f5 0%, #eef2ec 62%, #e8ede6 100%);
  outline: none;
}

.trip-overlay-stage {
  display: grid;
  place-items: center;
  width: 100%;
  max-width: 640px;
  min-height: 100%;
  box-sizing: border-box;
  margin: 0 auto;
  padding: 40px 20px;
}

.trip-overlay-stage :deep(.ticket-wrap) {
  --ticket-table: #eef2ec;
  width: 100%;
  margin-top: 0;
}

.trip-overlay-stage :deep(.journey-ticket) {
  margin: 0 auto;
}

/* Entrance: the paper fades in, the ticket rises slightly. */
.trip-overlay-enter-active {
  transition: opacity 0.32s ease;
}

.trip-overlay-enter-active .trip-overlay-stage {
  transition: transform 0.5s cubic-bezier(0.2, 0.75, 0.25, 1), opacity 0.5s ease;
}

.trip-overlay-leave-active {
  transition: opacity 0.24s ease;
}

.trip-overlay-enter-from,
.trip-overlay-leave-to {
  opacity: 0;
}

.trip-overlay-enter-from .trip-overlay-stage {
  opacity: 0;
  transform: translateY(18px);
}

@media (max-width: 420px) {
  .trip-overlay-stage {
    padding: 24px 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .trip-overlay-enter-active,
  .trip-overlay-leave-active,
  .trip-overlay-enter-active .trip-overlay-stage {
    transition: opacity 0.15s linear;
  }

  .trip-overlay-enter-from .trip-overlay-stage {
    transform: none;
  }
}
</style>
