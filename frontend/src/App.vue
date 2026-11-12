<template>
  <a-config-provider :locale="antdLocale" :theme="antdTheme">
    <div class="app">
      <a class="skip-link" href="#main">{{ locale === 'zh' ? '跳到主要内容' : 'Skip to content' }}</a>
      <header class="shell app-header">
        <router-link to="/" class="brand">
          <span class="brand-mark" aria-hidden="true">H</span>
          <span>{{ t('app.brand') }}</span>
        </router-link>
        <nav class="product-nav" :aria-label="t('app.navAria')">
          <router-link to="/" :aria-current="route.name === 'Home' ? 'page' : undefined">
            {{ t('app.navHome') }}
          </router-link>
          <router-link to="/result" :aria-current="route.name === 'Result' ? 'page' : undefined">
            {{ t('app.navTrip') }}
          </router-link>
        </nav>
        <div class="header-end">
          <span class="header-note">{{ t('app.tagline') }}</span>
          <div class="lang-switch" role="group" :aria-label="t('app.langAria')">
            <button
              v-for="option in langOptions"
              :key="option.value"
              type="button"
              :lang="option.lang"
              :aria-pressed="locale === option.value"
              @click="setLocale(option.value)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
      </header>

      <main id="main" class="app-main" tabindex="-1">
        <router-view v-slot="{ Component }">
          <!-- Only the planning hand-off sets a transition name; other navigation stays instant. -->
          <transition :name="routeTransition || 'route-none'" mode="out-in" @after-enter="clearRouteTransition">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>

      <footer class="shell page-foot">
        <span>{{ t('app.footer') }}</span>
        <router-link to="/credits">{{ t('app.credits') }}</router-link>
      </footer>
    </div>
  </a-config-provider>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { antdLocale, locale, setLocale, t, type Locale } from '@/i18n'
import { antdTheme } from '@/styles/theme'
import { clearRouteTransition, routeTransition } from '@/services/routeTransition'

const route = useRoute()

const langOptions: { label: string; value: Locale; lang: string }[] = [
  { label: '中文', value: 'zh', lang: 'zh-CN' },
  { label: 'EN', value: 'en', lang: 'en' }
]
</script>

<style>
@import './styles/base.css';

/* Planning overlay → result page: the ticket screen fades out, the itinerary rises in. */
.trip-reveal-leave-active {
  transition: opacity 0.32s ease;
}

.trip-reveal-leave-to {
  opacity: 0;
}

.trip-reveal-enter-active {
  transition: opacity 0.45s ease, transform 0.55s cubic-bezier(0.2, 0.75, 0.25, 1);
}

.trip-reveal-enter-from {
  opacity: 0;
  transform: translateY(12px);
}

@media (prefers-reduced-motion: reduce) {
  .trip-reveal-enter-active,
  .trip-reveal-leave-active {
    transition: opacity 0.15s linear;
  }

  .trip-reveal-enter-from {
    transform: none;
  }
}
</style>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--paper);
}

.skip-link {
  position: absolute;
  left: 12px;
  top: -48px;
  z-index: 20;
  padding: 8px 14px;
  background: var(--pine);
  color: #fff;
}

.skip-link:focus {
  top: 12px;
}

.app-header {
  width: 100%;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  height: 84px;
  border-bottom: 1px solid var(--line);
}

.brand {
  display: flex;
  align-items: center;
  gap: 11px;
  color: var(--ink);
  font-size: 18px;
  font-weight: 630;
  letter-spacing: -0.4px;
  text-decoration: none;
  white-space: nowrap;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--pine);
  color: #fff;
  font-size: 16px;
  font-weight: 800;
}

.product-nav {
  display: flex;
  align-self: stretch;
  gap: 36px;
}

.product-nav a {
  display: flex;
  align-items: center;
  border-bottom: 2px solid transparent;
  color: var(--muted);
  text-decoration: none;
  white-space: nowrap;
}

.product-nav a[aria-current='page'] {
  border-color: var(--pine);
  color: var(--pine);
}

.header-end {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-note {
  font-size: 12px;
  color: var(--muted);
}

.lang-switch {
  display: inline-flex;
  border: 1px solid #c2cec0;
}

.lang-switch button {
  min-width: 44px;
  min-height: 30px;
  padding: 0 10px;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}

.lang-switch button[aria-pressed='true'] {
  background: var(--pine);
  color: #fff;
}

.app-main {
  flex: 1;
  outline: none;
}

.page-foot {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  width: 100%;
  box-sizing: border-box;
  padding-top: 16px;
  padding-bottom: 25px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 11px;
}

.page-foot a {
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid #aab9ad;
}

@media (max-width: 1100px) {
  .header-note {
    display: none;
  }
}

@media (max-width: 760px) {
  .app-header {
    height: auto;
    min-height: 64px;
    flex-wrap: wrap;
    gap: 6px 14px;
    padding-top: 10px;
    padding-bottom: 10px;
  }

  .brand {
    font-size: 16px;
    gap: 9px;
  }

  .brand-mark {
    width: 28px;
    height: 28px;
    border-radius: 7px;
  }

  .product-nav {
    order: 3;
    width: 100%;
    gap: 22px;
    font-size: 13px;
  }

  .product-nav a {
    min-height: 34px;
  }

  .page-foot {
    flex-direction: column;
    gap: 6px;
  }
}
</style>
