<template>
  <!-- Decorative: the heading text next to it carries the meaning. -->
  <svg
    class="section-icon"
    :class="`section-icon-${kind}`"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-if="kind === 'route'">
      <circle cx="5" cy="5" r="2.2" />
      <circle cx="19" cy="19" r="2.2" />
      <path d="M7.5 5H15a4 4 0 0 1 0 8H9a3 3 0 0 0 0 6h7.5" />
    </template>
    <path v-else-if="kind === 'hotel'" d="M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8M4 10V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4M12 4v6M2 17h20" />
    <path v-else d="M4 3v7a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2V3M7 3v18M20 3v18M20 3c-4 4-4 7-4 10h4" />
  </svg>
</template>

<script setup lang="ts">
defineProps<{ kind: 'route' | 'hotel' | 'meal' }>()
</script>

<style scoped>
.section-icon {
  display: block;
  flex: none;
  width: 22px;
  height: 22px;
  margin-top: 0.15em;
}

.section-icon-route {
  color: var(--attraction);
}

.section-icon-hotel {
  color: var(--hotel);
}

.section-icon-meal {
  color: var(--meal);
}

@media (max-width: 760px) {
  .section-icon {
    width: 21px;
    height: 21px;
  }
}
</style>
