<template>
  <button
    v-if="mapped"
    type="button"
    class="map-link"
    :aria-pressed="selected"
    @click="emit('view', pointKey)"
  >
    {{ selected ? t('result.viewingOnMap') : t('result.viewOnMap') }}
  </button>
  <p v-else class="map-link-missing">{{ t('result.noCoordinate') }}</p>
</template>

<script setup lang="ts">
import { t } from '@/i18n'

defineProps<{ pointKey: string; mapped: boolean; selected: boolean }>()
const emit = defineEmits<{ (e: 'view', key: string): void }>()
</script>

<style scoped>
.map-link {
  max-width: 100%;
  min-height: 30px;
  margin-top: 8px;
  padding: 3px 0;
  border: 0;
  border-bottom: 1px solid #aebdaf;
  background: transparent;
  color: var(--pine);
  font-size: 12px;
  line-height: 1.6;
  text-align: left;
  cursor: pointer;
}

.map-link:hover,
.map-link[aria-pressed='true'] {
  border-color: var(--pine);
  background: #e5ece3;
}

.map-link-missing {
  margin: 8px 0 0;
  color: #8a8f86;
  font-size: 11px;
}
</style>
