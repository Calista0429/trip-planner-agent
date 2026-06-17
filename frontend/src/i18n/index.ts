import { ref } from 'vue'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import 'dayjs/locale/en'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import enUS from 'ant-design-vue/es/locale/en_US'
import { messages, type Locale, type Messages } from './messages'

const STORAGE_KEY = 'app_locale'

function detectInitial(): Locale {
  const saved = localStorage.getItem(STORAGE_KEY)
  return saved === 'en' || saved === 'zh' ? saved : 'zh'
}

export const locale = ref<Locale>(detectInitial())

// Ant Design Vue locale pack for the active language (drives DatePicker, etc.).
export const antdLocale = ref(locale.value === 'en' ? enUS : zhCN)

function applyLocale(next: Locale) {
  document.documentElement.lang = next === 'zh' ? 'zh-CN' : 'en'
  dayjs.locale(next === 'zh' ? 'zh-cn' : 'en')
  antdLocale.value = next === 'en' ? enUS : zhCN
}

// Apply once on module load so refresh restores the persisted choice.
applyLocale(locale.value)

export function setLocale(next: Locale) {
  if (next !== 'zh' && next !== 'en') return
  locale.value = next
  localStorage.setItem(STORAGE_KEY, next)
  applyLocale(next)
}

function lookup(dict: Messages, path: string): string | undefined {
  const value = path.split('.').reduce<unknown>((acc, key) => {
    if (acc && typeof acc === 'object') return (acc as Record<string, unknown>)[key]
    return undefined
  }, dict)
  return typeof value === 'string' ? value : undefined
}

/**
 * Translate a dot-path key (e.g. "home.cardTitle"). Supports {name} placeholders
 * substituted from `params`. Falls back to Chinese, then to the raw key.
 */
export function t(path: string, params?: Record<string, string | number>): string {
  const raw = lookup(messages[locale.value], path) ?? lookup(messages.zh, path) ?? path
  if (!params) return raw
  return raw.replace(/\{(\w+)\}/g, (_, key: string) =>
    key in params ? String(params[key]) : `{${key}}`
  )
}

export function useI18n() {
  return { locale, setLocale, t }
}

export type { Locale }
