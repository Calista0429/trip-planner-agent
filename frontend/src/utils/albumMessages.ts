import { locale, t } from '@/i18n'
import type { AlbumStyle } from '@/types'

// Codes the backend (/api/comic/upload) and uploadAlbumPhotos can produce.
const ERROR_CODES = [
  'comic_not_configured', 'no_files', 'too_many_files', 'not_an_image', 'unknown_style',
  'file_too_large', 'total_too_large', 'all_failed', 'comic_timeout', 'comic_unavailable', 'comic_failed', 'network'
]
// Per-photo reasons from the comic service, plus the proxy's bad_image_url.
const REASONS = ['timeout', 'no_image', 'billing', 'rate_limited', 'model_error', 'internal', 'bad_image_url']

export function albumErrorText(code: string): string {
  return t(ERROR_CODES.includes(code) ? `album.err_${code}` : 'album.err_unknown')
}

export function albumReasonText(reason: string): string {
  return t(REASONS.includes(reason) ? `album.reason_${reason}` : 'album.reason_unknown')
}

export function albumStyleLabel(style: AlbumStyle): string {
  return t(`album.style_${style}`)
}

export function formatAlbumDate(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value === 'en' ? 'en-US' : 'zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
}
