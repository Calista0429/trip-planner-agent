<template>
  <section class="shell album-page" :aria-labelledby="titleId">
    <p class="album-caption">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
        <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5v-13Z" />
        <path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5v-13Z" />
      </svg>
      {{ t('album.caption') }}
    </p>
    <h1 :id="titleId" class="serif">{{ title }}</h1>
    <p v-if="intro" class="album-intro">{{ intro }}</p>

    <div class="album-status">
      <p class="album-status-title">{{ status }}</p>
      <p class="album-status-desc">{{ description }}</p>
    </div>

    <ul class="album-links">
      <li v-for="link in links" :key="link.to">
        <router-link :to="link.to">{{ link.label }}</router-link>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
// An honest placeholder: album features are not built yet, so there is nothing
// to click except real links to other pages. Keep a single root element (no
// leading template comment): App's out-in route transition needs one.
import { t } from '@/i18n'

defineProps<{
  titleId: string
  title: string
  intro?: string
  status: string
  description: string
  links: { to: string; label: string }[]
}>()
</script>

<style scoped>
.album-page {
  padding-top: 52px;
  padding-bottom: 96px;
}

.album-caption {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0 0 15px;
  color: var(--muted);
  font-size: 12px;
}

.album-caption svg {
  width: 18px;
  height: 18px;
}

h1 {
  max-width: 640px;
  margin: 0 0 14px;
  color: var(--ink);
  font-size: 44px;
  line-height: 1.4;
  letter-spacing: 1px;
  white-space: pre-line;
}

.album-intro {
  max-width: 470px;
  margin: 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.85;
}

.album-status {
  max-width: 560px;
  margin-top: 34px;
  padding: 20px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

.album-status-title {
  margin: 0 0 6px;
  color: var(--pine);
  font-size: 15px;
  font-weight: 600;
}

.album-status-desc {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.8;
}

.album-links {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 28px;
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
}

.album-links a {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  border-bottom: 1px solid #aab9ad;
  color: var(--pine);
  font-size: 13px;
  text-decoration: none;
}

.album-links a:hover {
  border-color: var(--pine);
  color: var(--pine-dark);
}

@media (max-width: 760px) {
  .album-page {
    padding-top: 28px;
    padding-bottom: 64px;
  }

  h1 {
    font-size: 32px;
    letter-spacing: 0.5px;
  }

  .album-intro {
    font-size: 13px;
  }
}
</style>
