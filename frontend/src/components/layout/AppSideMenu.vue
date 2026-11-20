<template>
  <div class="side-menu" :class="{ 'is-collapsed': collapsed, 'is-mobile': mobile }">
    <p v-if="!collapsed" class="side-caption serif">{{ t('nav.caption') }}</p>

    <nav class="side-nav" :aria-label="t('nav.aria')">
      <div v-for="group in SIDE_MENU_GROUPS" :key="group.labelKey" class="side-group">
        <p v-if="!collapsed" class="side-group-label" aria-hidden="true">{{ t(group.labelKey) }}</p>
        <ul class="side-list" :aria-label="t(group.labelKey)">
          <li v-for="item in group.items" :key="item.routeName">
            <a-tooltip :title="collapsed ? t(item.labelKey) : ''" placement="right" :trigger="['hover', 'focus']">
              <router-link v-slot="{ href, navigate }" :to="targetFor(item.routeName)" custom>
                <a
                  :href="href"
                  class="side-link"
                  :data-route="item.routeName"
                  :aria-current="route.name === item.routeName ? 'page' : undefined"
                  :aria-disabled="blocked ? 'true' : undefined"
                  @click="onLinkClick($event, item.routeName, navigate)"
                >
                  <SideMenuIcon :name="item.icon" />
                  <span class="side-label" :class="{ 'sr-only': collapsed }">{{ t(item.labelKey) }}</span>
                </a>
              </router-link>
            </a-tooltip>
          </li>
        </ul>
      </div>
    </nav>

    <div class="side-bottom">
      <p v-if="!collapsed" class="side-note">{{ t('nav.note') }}</p>
      <a-tooltip v-if="!mobile" :title="collapsed ? t('nav.expand') : ''" placement="right" :trigger="['hover', 'focus']">
        <button
          type="button"
          class="side-collapse"
          :aria-expanded="collapsed ? 'false' : 'true'"
          :aria-label="collapsed ? t('nav.expand') : t('nav.collapse')"
          :disabled="blocked"
          @click="emit('toggle-collapse')"
        >
          <SideMenuIcon :name="collapsed ? 'expand' : 'collapse'" />
          <span v-if="!collapsed" aria-hidden="true">{{ t('nav.collapse') }}</span>
        </button>
      </a-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute, type RouteLocationRaw } from 'vue-router'
import { t } from '@/i18n'
import { SIDE_MENU_GROUPS, type SideMenuRouteName } from '@/data/navigation'
import SideMenuIcon from './SideMenuIcon.vue'

const props = defineProps<{ collapsed: boolean; mobile: boolean; blocked: boolean }>()
const emit = defineEmits<{ 'toggle-collapse': []; select: [routeName: SideMenuRouteName] }>()

const route = useRoute()

/** The current entry links to the current URL, so re-selecting "My itinerary" keeps ?day. */
function targetFor(name: SideMenuRouteName): RouteLocationRaw {
  return route.name === name ? route.fullPath : { name }
}

function onLinkClick(event: MouseEvent, name: SideMenuRouteName, navigate: (e?: MouseEvent) => unknown) {
  if (props.blocked) {
    event.preventDefault()
    return
  }
  // Modified clicks (new tab / window) are left to the browser.
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return
  emit('select', name)
  void navigate(event)
}
</script>

<style scoped>
.side-menu {
  display: flex;
  flex-direction: column;
  gap: 24px;
  box-sizing: border-box;
  /* Room on the right for the bookmark tail that pokes past the edge. */
  padding: 28px 10px 18px 16px;
  font-family: var(--sans);
}

.side-caption {
  margin: 0;
  padding: 0 16px 0 0;
  color: var(--pine);
  font-size: 23px;
  line-height: 1.7;
  white-space: pre-line;
}

.side-nav {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.side-group-label {
  margin: 0 0 7px 16px;
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 1px;
}

.side-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.side-link {
  position: relative;
  display: flex;
  align-items: center;
  gap: 13px;
  min-height: 48px;
  padding: 8px 12px 8px 16px;
  box-sizing: border-box;
  color: var(--ink);
  font-size: 14px;
  font-weight: 500;
  line-height: 1.35;
  text-decoration: none;
  transition: background-color 150ms ease, color 150ms ease;
}

.side-link:hover {
  background: rgba(49, 83, 72, 0.08);
  color: var(--pine-dark);
}

.side-link[aria-current='page'] {
  background: var(--pine);
  color: #fff;
  font-weight: 600;
}

.side-link[aria-current='page']:hover {
  background: var(--pine-dark);
  color: #fff;
}

/* Bookmark tail: same height as the row, with a shallow V notch. */
.side-link[aria-current='page']::after {
  content: '';
  position: absolute;
  top: 0;
  right: -9px;
  bottom: 0;
  width: 10px;
  background: inherit;
  clip-path: polygon(0 0, 100% 0, 65% 50%, 100% 100%, 0 100%);
  pointer-events: none;
}

/* Focus is a ring inside the row, so it never reads as the selected fill. */
.side-link:focus-visible {
  outline: 2px solid var(--pine);
  outline-offset: -4px;
}

.side-link[aria-current='page']:focus-visible {
  outline-color: #fff;
}

.side-link[aria-disabled='true'] {
  cursor: not-allowed;
}

.side-bottom {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: auto;
  padding-right: 6px;
}

.side-note {
  margin: 0 0 0 16px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
  white-space: pre-line;
}

.side-collapse {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 12px 12px 0 16px;
  border: 0;
  border-top: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: color 150ms ease;
}

.side-collapse:hover:not(:disabled) {
  color: var(--pine);
}

.side-collapse:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

/* Collapsed rail: icons only, a shorter tail. */
.is-collapsed {
  padding-left: 12px;
}

.is-collapsed .side-link {
  justify-content: center;
  padding: 8px 0;
}

.is-collapsed .side-link[aria-current='page']::after {
  right: -6px;
  width: 7px;
}

.is-collapsed .side-collapse {
  justify-content: center;
  padding: 12px 0 0;
}

.is-collapsed .side-bottom {
  padding-right: 0;
}

@media (prefers-reduced-motion: reduce) {
  .side-link,
  .side-collapse {
    transition: none;
  }
}
</style>
