<template>
  <!-- Decorative: the link text next to it carries the meaning. -->
  <svg
    class="side-menu-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-if="name === 'plan'">
      <circle cx="5.5" cy="5.5" r="2" />
      <circle cx="18.5" cy="18.5" r="2" />
      <path d="M7.5 5.5H15a3.5 3.5 0 0 1 0 7H9a3.5 3.5 0 0 0 0 7h7.5" />
    </template>
    <template v-else-if="name === 'album'">
      <rect x="3" y="5" width="18" height="14" rx="1.5" />
      <circle cx="8.5" cy="10" r="1.6" />
      <path d="m21 16-5-5-8 8" />
    </template>
    <template v-else-if="name === 'trip'">
      <path d="M9 4 3 6.5v13.5l6-2.5 6 2.5 6-2.5V4l-6 2.5L9 4Z" />
      <path d="M9 4v13.5M15 6.5V20" />
    </template>
    <template v-else-if="name === 'library'">
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5v-13Z" />
      <path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5v-13Z" />
    </template>
    <template v-else>
      <rect x="3.5" y="4" width="17" height="16" rx="1.5" />
      <path d="M9 4v16" />
      <path :d="name === 'collapse' ? 'm15.5 9.5-2.5 2.5 2.5 2.5' : 'm13 9.5 2.5 2.5-2.5 2.5'" />
    </template>
  </svg>
</template>

<script setup lang="ts">
import type { SideMenuIconName } from '@/data/navigation'

defineProps<{ name: SideMenuIconName }>()
</script>

<style scoped>
.side-menu-icon {
  display: block;
  flex: none;
  width: 19px;
  height: 19px;
}
</style>
