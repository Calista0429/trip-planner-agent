<template>
  <a-config-provider :locale="antdLocale" :theme="antdTheme">
    <div class="app">
      <a class="skip-link" href="#main">{{ locale === 'zh' ? '跳到主要内容' : 'Skip to content' }}</a>
      <header class="shell app-header" :inert="chromeInert || drawerVisible || undefined">
        <div class="header-start">
          <button
            v-if="isMobile"
            ref="menuButton"
            type="button"
            class="menu-button"
            :aria-label="t('nav.openMenu')"
            :aria-expanded="drawerVisible ? 'true' : 'false'"
            aria-controls="app-drawer-menu"
            :disabled="navBlocked"
            @click="openDrawer"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true" focusable="false">
              <path d="M4 7h16M4 12h16M4 17h10" />
            </svg>
          </button>
          <router-link to="/" class="brand">
            <span class="brand-mark" aria-hidden="true">H</span>
            <span>{{ t('app.brand') }}</span>
          </router-link>
        </div>
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

      <div class="app-body" :class="{ 'is-collapsed': collapsed && !isMobile, 'is-mobile': isMobile }">
        <aside v-if="!isMobile" class="app-sidebar" :inert="chromeInert || undefined">
          <div class="app-sidebar-inner">
            <AppSideMenu
              :collapsed="collapsed"
              :mobile="false"
              :blocked="navBlocked"
              @toggle-collapse="toggleCollapsed"
              @select="onSelect"
            />
          </div>
        </aside>

        <!-- Never inert while a page holds the lock: the planning overlay lives in here. -->
        <main id="main" class="app-main" tabindex="-1" :inert="drawerVisible || undefined">
          <router-view v-slot="{ Component }">
            <!-- Only the planning hand-off sets a transition name; other navigation stays instant. -->
            <transition :name="routeTransition || 'route-none'" mode="out-in" @after-enter="clearRouteTransition">
              <component :is="Component" />
            </transition>
          </router-view>
        </main>
      </div>

      <footer class="shell page-foot" :inert="chromeInert || drawerVisible || undefined">
        <span>{{ t('app.footer') }}</span>
        <router-link to="/credits">{{ t('app.credits') }}</router-link>
      </footer>

      <!-- z-index goes on the root: Ant Design's `z-index` prop only moves the panel,
           which would then sit under its own mask (1000). Planning overlay stays at 1000. -->
      <a-drawer
        v-if="isMobile"
        :open="drawerVisible"
        placement="left"
        width="min(280px, calc(100vw - 48px))"
        :root-style="{ zIndex: 600 }"
        :title="t('nav.drawerTitle')"
        :close-icon="null"
        root-class-name="app-drawer"
        :body-style="{ padding: 0 }"
        destroy-on-close
        @close="closeDrawer"
        @after-open-change="onDrawerAfterOpenChange"
      >
        <template #extra>
          <button type="button" class="drawer-close" :aria-label="t('nav.closeMenu')" @click="closeDrawer">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true" focusable="false">
              <path d="m6 6 12 12M18 6 6 18" />
            </svg>
          </button>
        </template>
        <div id="app-drawer-menu" ref="drawerMenu">
          <AppSideMenu :collapsed="false" :mobile="true" :blocked="navBlocked" @select="onSelect" />
        </div>
      </a-drawer>
    </div>
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppSideMenu from '@/components/layout/AppSideMenu.vue'
import { useSideMenu } from '@/composables/useSideMenu'
import type { SideMenuRouteName } from '@/data/navigation'
import { antdLocale, locale, setLocale, t, type Locale } from '@/i18n'
import { antdTheme } from '@/styles/theme'
import { clearRouteTransition, routeTransition } from '@/services/routeTransition'
import { SHELL_NAVIGATION_BLOCKED } from '@/services/shellNavigation'

const route = useRoute()
const router = useRouter()

const langOptions: { label: string; value: Locale; lang: string }[] = [
  { label: '中文', value: 'zh', lang: 'zh-CN' },
  { label: 'EN', value: 'en', lang: 'en' }
]

const { collapsed, isMobile, drawerOpen, toggleCollapsed, openDrawer, closeDrawer } = useSideMenu()

// Pages set this while leaving would break work in progress (generation, export).
const navBlocked = ref(false)
provide(SHELL_NAVIGATION_BLOCKED, navBlocked)
const chromeInert = computed(() => navBlocked.value)
const drawerVisible = computed(() => drawerOpen.value && isMobile.value && !navBlocked.value)

watch(navBlocked, blocked => {
  if (blocked) closeDrawer()
})

const menuButton = ref<HTMLButtonElement | null>(null)
const drawerMenu = ref<HTMLElement | null>(null)
/** Where focus goes once the drawer has closed. */
let focusAfterClose: 'menu' | 'main' = 'menu'

const focusMain = () => document.getElementById('main')?.focus({ preventScroll: true })

function onSelect(name: SideMenuRouteName) {
  // Re-selecting the current page navigates nowhere: just close the drawer.
  if (name === route.name) {
    focusAfterClose = 'menu'
    closeDrawer()
  }
}

function onDrawerAfterOpenChange(open: boolean) {
  if (open) {
    const menu = drawerMenu.value
    // Start on the current page's entry (a combined selector would pick the first link).
    ;(menu?.querySelector<HTMLElement>('a[aria-current="page"]') ?? menu?.querySelector<HTMLElement>('a'))?.focus()
    return
  }
  if (focusAfterClose === 'main') focusMain()
  else menuButton.value?.focus()
  focusAfterClose = 'menu'
}

/** Keep Tab / Shift+Tab inside the open drawer (its close button included). */
function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  const panel = drawerMenu.value?.closest<HTMLElement>('.ant-drawer-content')
  if (!panel) return
  const items = [...panel.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')]
  if (!items.length) return
  const first = items[0]
  const last = items[items.length - 1]
  const active = document.activeElement
  if (!panel.contains(active)) {
    event.preventDefault()
    first.focus()
  } else if (event.shiftKey && active === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(drawerVisible, open => {
  if (open) document.addEventListener('keydown', trapFocus)
  else document.removeEventListener('keydown', trapFocus)
})
onBeforeUnmount(() => document.removeEventListener('keydown', trapFocus))

// Only a navigation that actually happened closes the drawer and moves focus.
const removeAfterEach = router.afterEach((to, from, failure) => {
  if (failure || !from.matched.length) return
  if (to.path === from.path) {
    // Same page, new ?day: no scroll or focus change.
    closeDrawer()
    return
  }
  // The planning hand-off animates into the result page, which focuses its own title.
  const handoff = !!routeTransition.value
  if (drawerOpen.value) {
    focusAfterClose = handoff ? 'menu' : 'main'
    closeDrawer()
    return
  }
  if (!handoff) nextTick(focusMain)
})
onBeforeUnmount(removeAfterEach)
</script>

<style>
@import './styles/base.css';

/* Pages keep their `.shell` sections; inside the sidebar layout they fill the
   content column instead of centring a second 1360px box. Header, footer and
   the off-screen export sheet are outside .app-main and keep the global rule. */
.app-main .shell {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
  padding-left: 32px;
  padding-right: 32px;
}

@media (max-width: 760px) {
  .app-main .shell {
    padding-left: 20px;
    padding-right: 20px;
  }
}

/* Mobile drawer (teleported to <body>, so these rules are global). */
.app-drawer .ant-drawer-content {
  background: var(--sidebar-paper);
}

.app-drawer .ant-drawer-header {
  padding: 14px 20px 6px 16px;
  border-bottom: 0;
}

.app-drawer .ant-drawer-title {
  color: var(--muted);
  font-size: 12px;
  font-weight: 400;
  letter-spacing: 1px;
}

.app-drawer .side-menu {
  min-height: 100%;
  padding-top: 8px;
}

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

.header-start {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.menu-button,
.drawer-close {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  margin-left: -8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink);
  cursor: pointer;
}

.drawer-close {
  margin: 0 -8px 0 0;
  color: var(--muted);
}

.menu-button:hover:not(:disabled),
.drawer-close:hover {
  color: var(--pine);
}

.menu-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.menu-button svg,
.drawer-close svg {
  width: 22px;
  height: 22px;
}

/* Sidebar + page. The column width switches instantly (no width animation),
   so the map on the result page never redraws through a sliding frame. */
.app-body {
  flex: 1;
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  width: 100%;
  max-width: 1360px;
  margin: 0 auto;
  --sidebar-width: 188px;
}

.app-body.is-collapsed {
  --sidebar-width: 76px;
}

.app-body.is-mobile {
  display: block;
}

.app-sidebar {
  position: relative;
  min-width: 0;
  border-right: 1px solid var(--sidebar-edge);
  background: var(--sidebar-paper);
}

.app-sidebar-inner {
  position: sticky;
  top: 16px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  /* 10px wider than the column so the bookmark tail can poke past the edge. */
  width: calc(100% + 10px);
  /* Fits below the 84px header on first paint, so the collapse button is never
     below the fold; the menu scrolls itself in short windows. */
  height: calc(100vh - 100px);
  max-height: 100%;
  margin-right: -10px;
  overflow-x: hidden;
  overflow-y: auto;
}

.app-sidebar-inner > :deep(.side-menu) {
  flex: 1 0 auto;
}

.app-main {
  min-width: 0;
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

  .page-foot {
    flex-direction: column;
    gap: 6px;
  }
}
</style>
