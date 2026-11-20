<template>
  <section class="shell album-page" aria-labelledby="album-workspace-title">
    <div class="album-compose" :inert="busy || undefined">
      <p class="album-caption">{{ t('album.caption') }}</p>
      <h1 id="album-workspace-title" class="serif">{{ t('album.workspaceTitle') }}</h1>
      <p class="album-intro">{{ t('album.workspaceIntro') }}</p>

      <div v-if="!result" class="album-form">
        <div class="album-field">
          <p class="album-label">{{ t('album.photosLabel') }}</p>
          <input
            ref="fileInput"
            class="sr-only"
            type="file"
            accept="image/*"
            multiple
            tabindex="-1"
            aria-hidden="true"
            @change="onPick"
          />
          <ul v-if="photos.length" class="album-thumbs">
            <li v-for="item in photos" :key="item.url" class="album-thumb">
              <img :src="item.url" alt="" />
              <button
                type="button"
                class="album-thumb-remove"
                :aria-label="t('album.removePhoto', { name: item.file.name })"
                :title="item.file.name"
                @click="removePhoto(item)"
              >
                ×
              </button>
            </li>
          </ul>
          <div class="album-pick-row">
            <button
              type="button"
              class="album-add"
              :disabled="photos.length >= MAX_ALBUM_PHOTOS"
              @click="fileInput?.click()"
            >
              {{ photos.length ? t('album.addMore') : t('album.pickPhotos') }}
            </button>
            <span class="album-hint">
              {{
                photos.length
                  ? t('album.photoCount', { n: photos.length, max: MAX_ALBUM_PHOTOS })
                  : t('album.pickHint', { max: MAX_ALBUM_PHOTOS })
              }}
            </span>
          </div>
          <p v-if="notice" class="album-notice" role="status">{{ notice }}</p>
        </div>

        <fieldset class="album-field album-styles">
          <legend class="album-label">{{ t('album.styleLabel') }}</legend>
          <label
            v-for="option in ALBUM_STYLES"
            :key="option"
            class="album-style"
            :class="{ 'is-active': style === option }"
          >
            <input v-model="style" type="radio" name="album-style" :value="option" />
            <span>{{ albumStyleLabel(option) }}</span>
          </label>
        </fieldset>

        <button
          type="button"
          class="album-generate"
          :disabled="!photos.length || busy"
          :aria-busy="busy ? 'true' : 'false'"
          @click="generate"
        >
          {{ busy ? t('album.generating') : t('album.generate') }}
        </button>

        <div v-if="error" class="album-error" role="alert">
          <p class="album-error-title">{{ t('album.errorTitle') }}</p>
          <p>{{ albumErrorText(error.code) }}</p>
          <ul v-if="error.failed.length">
            <li v-for="(item, index) in error.failed" :key="index">
              {{ item.file || '—' }}：{{ albumReasonText(item.reason) }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div v-if="busy" class="album-generating" role="status" aria-live="polite">
      <div class="album-generating-card">
        <span class="album-spinner" aria-hidden="true"></span>
        <p class="album-generating-title serif">{{ t('album.generating') }}</p>
        <p class="album-generating-desc">{{ t('album.generatingDesc') }}</p>
      </div>
    </div>

    <div v-if="result" class="album-result">
      <p v-if="saveFailed" class="album-save-failed" role="alert">{{ t('album.saveFailed') }}</p>
      <p v-else class="album-saved" role="status">{{ t('album.savedLocal') }}</p>

      <div v-if="result.failed.length" class="album-partial">
        <p>{{ t('album.partialFailed', { n: result.failed.length }) }}</p>
        <ul>
          <li v-for="(item, index) in result.failed" :key="index">
            {{ item.file || '—' }}：{{ albumReasonText(item.reason) }}
          </li>
        </ul>
      </div>

      <AlbumView :album="result" />

      <div class="album-result-actions">
        <router-link
          v-if="!saveFailed"
          class="album-open-library"
          :to="{ path: '/albums/library', query: { album: result.tripId } }"
        >
          {{ t('album.openInLibrary') }}
        </router-link>
        <button type="button" class="album-again" @click="startOver">{{ t('album.again') }}</button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// Upload photos, pick a style, get an album from the comic-trip service (via
// /api/comic/upload). The album is kept in this browser only (albumLibrary).
import { onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import AlbumView from '@/components/album/AlbumView.vue'
import { t } from '@/i18n'
import {
  AlbumUploadError,
  MAX_ALBUM_PHOTOS,
  MAX_ALBUM_PHOTO_BYTES,
  MAX_ALBUM_TOTAL_BYTES,
  uploadAlbumPhotos
} from '@/services/api'
import { saveAlbum } from '@/services/albumLibrary'
import { useShellNavigationLock } from '@/services/shellNavigation'
import { ALBUM_STYLES, type Album, type AlbumFailure, type AlbumStyle } from '@/types'
import { albumErrorText, albumReasonText, albumStyleLabel } from '@/utils/albumMessages'

interface PickedPhoto {
  file: File
  url: string
}

const fileInput = ref<HTMLInputElement | null>(null)
const photos = ref<PickedPhoto[]>([])
const style = ref<AlbumStyle>('comic')
const notice = ref('')
const busy = ref(false)
const error = ref<{ code: string; failed: AlbumFailure[] } | null>(null)
const result = ref<Album | null>(null)
const saveFailed = ref(false)

function onPick(event: Event) {
  const input = event.target as HTMLInputElement
  const picked = Array.from(input.files ?? [])
  // Cleared so picking the same photo again still fires `change`.
  input.value = ''

  const notImages = picked.filter(file => !file.type.startsWith('image/'))
  const tooBig = picked.filter(file => file.type.startsWith('image/') && file.size > MAX_ALBUM_PHOTO_BYTES)
  const accepted = picked.filter(file => !notImages.includes(file) && !tooBig.includes(file))
  const room = MAX_ALBUM_PHOTOS - photos.value.length
  const withinCount = accepted.slice(0, Math.max(room, 0))
  // Keep the whole album under the service's body limit, in pick order.
  let total = photos.value.reduce((sum, item) => sum + item.file.size, 0)
  const added: File[] = []
  const overTotal: File[] = []
  for (const file of withinCount) {
    if (total + file.size > MAX_ALBUM_TOTAL_BYTES) {
      overTotal.push(file)
    } else {
      total += file.size
      added.push(file)
    }
  }

  const messages: string[] = []
  const names = (files: File[]) => files.map(file => file.name).join('、')
  if (notImages.length) messages.push(t('album.rejectedType', { names: names(notImages) }))
  if (tooBig.length) messages.push(t('album.rejectedSize', { names: names(tooBig) }))
  if (overTotal.length) messages.push(t('album.rejectedTotal', { names: names(overTotal) }))
  if (withinCount.length < accepted.length) messages.push(t('album.rejectedCount', { max: MAX_ALBUM_PHOTOS }))
  notice.value = messages.join(' ')

  photos.value.push(...added.map(file => ({ file, url: URL.createObjectURL(file) })))
}

function removePhoto(item: PickedPhoto) {
  URL.revokeObjectURL(item.url)
  photos.value = photos.value.filter(photo => photo !== item)
  notice.value = ''
}

function clearPhotos() {
  photos.value.forEach(item => URL.revokeObjectURL(item.url))
  photos.value = []
}

async function generate() {
  if (busy.value || !photos.value.length) return
  busy.value = true
  error.value = null
  notice.value = ''
  try {
    const album = await uploadAlbumPhotos(
      photos.value.map(item => item.file),
      style.value
    )
    saveFailed.value = !saveAlbum(album)
    result.value = album
    clearPhotos()
  } catch (e) {
    error.value =
      e instanceof AlbumUploadError ? { code: e.code, failed: e.failed } : { code: 'comic_failed', failed: [] }
  } finally {
    busy.value = false
  }
}

function startOver() {
  result.value = null
  saveFailed.value = false
  error.value = null
}

// Generating takes minutes and cannot be resumed: keep the user here meanwhile.
useShellNavigationLock(() => busy.value)
onBeforeRouteLeave(() => !busy.value)
onBeforeUnmount(clearPhotos)
</script>

<style scoped>
.album-page {
  position: relative;
  padding-top: 52px;
  padding-bottom: 96px;
}

.album-caption {
  margin: 0 0 15px;
  color: var(--muted);
  font-size: 12px;
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
  max-width: 520px;
  margin: 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.85;
}

.album-form {
  display: grid;
  gap: 28px;
  max-width: 720px;
  margin-top: 36px;
  padding-top: 28px;
  border-top: 1px solid var(--line);
}

.album-field {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.album-label {
  margin: 0 0 12px;
  padding: 0;
  color: var(--ink);
  font-size: 14px;
  font-weight: 600;
}

.album-thumbs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 10px;
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
}

.album-thumb {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  border: 1px solid var(--line);
  background: var(--card);
}

.album-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.album-thumb-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 50%;
  background: rgb(42 61 53 / 78%);
  color: #fff;
  font-size: 16px;
  line-height: 26px;
  cursor: pointer;
}

.album-thumb-remove:focus-visible,
.album-add:focus-visible,
.album-generate:focus-visible,
.album-again:focus-visible,
.album-style:focus-within {
  outline: 2px solid var(--pine);
  outline-offset: 2px;
}

.album-pick-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
}

.album-add,
.album-again {
  min-height: 38px;
  padding: 0 18px;
  border: 1px solid var(--pine);
  background: transparent;
  color: var(--pine);
  font-size: 13px;
  cursor: pointer;
}

.album-add:disabled {
  border-color: var(--field-line);
  color: var(--muted);
  cursor: not-allowed;
}

.album-hint {
  color: var(--muted);
  font-size: 12px;
}

.album-notice {
  margin: 10px 0 0;
  color: #98614f;
  font-size: 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.album-styles {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.album-styles legend {
  width: 100%;
}

.album-style {
  position: relative;
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  padding: 0 16px;
  border: 1px solid var(--field-line);
  color: var(--ink);
  font-size: 13px;
  cursor: pointer;
}

.album-style input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.album-style.is-active {
  border-color: var(--pine);
  background: var(--pine);
  color: #fff;
}

.album-generate {
  justify-self: start;
  min-width: 168px;
  min-height: 46px;
  padding: 0 28px;
  border: 0;
  background: var(--pine);
  color: #fff;
  font-size: 15px;
  letter-spacing: 1px;
  cursor: pointer;
}

.album-generate:hover:not(:disabled) {
  background: var(--pine-dark);
}

.album-generate:disabled {
  background: #a9b8ad;
  cursor: not-allowed;
}

.album-error,
.album-partial,
.album-save-failed {
  padding: 14px 16px;
  border-left: 3px solid #98614f;
  background: #f6efeb;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.album-error p,
.album-partial p {
  margin: 0;
}

.album-error ul,
.album-partial ul {
  margin: 6px 0 0;
  padding-left: 18px;
}

.album-error-title {
  font-weight: 600;
}

.album-generating {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(246 247 245 / 88%);
}

.album-generating-card {
  max-width: 380px;
  text-align: center;
}

.album-spinner {
  display: inline-block;
  width: 34px;
  height: 34px;
  border: 2px solid var(--line);
  border-top-color: var(--pine);
  border-radius: 50%;
  animation: album-spin 1s linear infinite;
}

.album-generating-title {
  margin: 18px 0 8px;
  color: var(--ink);
  font-size: 22px;
}

.album-generating-desc {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.8;
}

.album-result {
  display: grid;
  gap: 24px;
  margin-top: 36px;
  padding-top: 28px;
  border-top: 1px solid var(--line);
}

.album-saved {
  margin: 0;
  color: var(--pine);
  font-size: 13px;
}

.album-save-failed {
  margin: 0;
}

.album-result-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 24px;
}

.album-open-library {
  border-bottom: 1px solid #aab9ad;
  color: var(--pine);
  font-size: 13px;
  text-decoration: none;
}

@keyframes album-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .album-spinner {
    animation: none;
  }
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

  .album-generate {
    justify-self: stretch;
  }
}
</style>
