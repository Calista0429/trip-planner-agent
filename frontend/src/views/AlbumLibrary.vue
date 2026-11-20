<template>
  <section class="shell album-page" aria-labelledby="album-library-title">
    <p class="album-caption">{{ t('album.caption') }}</p>
    <h1 id="album-library-title" class="serif">{{ t('album.libraryTitle') }}</h1>
    <p class="album-intro">{{ t('album.libraryIntro') }}</p>
    <p class="album-local-note">{{ t('album.libraryLocalNote') }}</p>

    <template v-if="selectedId">
      <div v-if="selected" class="album-detail">
        <div class="album-detail-bar">
          <router-link class="album-back" :to="{ path: '/albums/library' }">
            ← {{ t('album.backToLibrary') }}
          </router-link>
          <button type="button" class="album-remove" @click="confirmRemove(selected)">
            {{ t('album.removeLocal') }}
          </button>
        </div>
        <AlbumView :album="selected" />
      </div>
      <div v-else class="album-not-found" role="status">
        <p class="album-status-title">{{ t('album.notFound') }}</p>
        <p class="album-status-desc">{{ t('album.notFoundDesc') }}</p>
        <router-link :to="{ path: '/albums/library' }">{{ t('album.backToLibrary') }}</router-link>
      </div>
    </template>

    <div v-else-if="!albums.length" class="album-empty">
      <p class="album-status-title">{{ t('album.libraryEmpty') }}</p>
      <p class="album-status-desc">{{ t('album.libraryEmptyDesc') }}</p>
      <router-link to="/albums">{{ t('album.toWorkspace') }}</router-link>
    </div>

    <ul v-else class="album-grid">
      <li v-for="item in albums" :key="item.tripId" class="album-card">
        <router-link
          :to="{ path: '/albums/library', query: { album: item.tripId } }"
          :aria-label="t('album.openAlbum', { title: item.title })"
        >
          <img :src="item.pictures[0].imageUrl" alt="" loading="lazy" />
          <span class="album-card-body">
            <span class="album-card-title serif">{{ item.title }}</span>
            <span class="album-card-meta">
              {{ albumStyleLabel(item.style) }} · {{ formatAlbumDate(item.createdAt) }} ·
              {{ t('album.pictureCount', { n: item.pictures.length }) }}
            </span>
          </span>
        </router-link>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
// Albums saved in this browser (the comic service has no list endpoint). The
// detail view is `?album=<tripId>` on the same route, so the side menu keeps
// "My albums" selected.
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Modal } from 'ant-design-vue'
import AlbumView from '@/components/album/AlbumView.vue'
import { t } from '@/i18n'
import { loadAlbums, removeAlbum } from '@/services/albumLibrary'
import type { Album } from '@/types'
import { albumStyleLabel, formatAlbumDate } from '@/utils/albumMessages'

const route = useRoute()
const router = useRouter()
const albums = ref<Album[]>(loadAlbums())

const selectedId = computed(() => {
  const value = route.query.album
  return typeof value === 'string' && value ? value : null
})
const selected = computed(() => albums.value.find(album => album.tripId === selectedId.value) ?? null)

function confirmRemove(album: Album) {
  Modal.confirm({
    title: t('album.removeConfirmTitle'),
    content: t('album.removeConfirmDesc'),
    okText: t('album.removeConfirmOk'),
    okType: 'danger',
    cancelText: t('album.cancel'),
    onOk: async () => {
      removeAlbum(album.tripId)
      albums.value = loadAlbums()
      await router.replace({ path: '/albums/library' })
    }
  })
}
</script>

<style scoped>
.album-page {
  padding-top: 52px;
  padding-bottom: 96px;
}

.album-caption {
  margin: 0 0 15px;
  color: var(--muted);
  font-size: 12px;
}

h1 {
  margin: 0 0 14px;
  color: var(--ink);
  font-size: 44px;
  line-height: 1.4;
  letter-spacing: 1px;
}

.album-intro {
  max-width: 520px;
  margin: 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.85;
}

.album-local-note {
  max-width: 560px;
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}

.album-empty,
.album-not-found {
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
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.8;
}

.album-empty a,
.album-not-found a,
.album-back {
  border-bottom: 1px solid #aab9ad;
  color: var(--pine);
  font-size: 13px;
  text-decoration: none;
}

.album-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 24px;
  margin: 36px 0 0;
  padding: 0;
  list-style: none;
}

.album-card a {
  display: block;
  height: 100%;
  border: 1px solid var(--line);
  background: var(--card);
  color: inherit;
  text-decoration: none;
  transition: border-color 0.2s;
}

.album-card a:hover {
  border-color: var(--pine);
}

.album-card a:focus-visible {
  outline: 2px solid var(--pine);
  outline-offset: 2px;
}

.album-card img {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  background: var(--paper);
}

.album-card-body {
  display: grid;
  gap: 6px;
  padding: 14px 16px 16px;
}

.album-card-title {
  color: var(--ink);
  font-size: 17px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.album-card-meta {
  color: var(--muted);
  font-size: 12px;
}

.album-detail {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
}

.album-detail-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 28px;
}

.album-remove {
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid var(--field-line);
  background: transparent;
  color: #98614f;
  font-size: 12px;
  cursor: pointer;
}

.album-remove:hover {
  border-color: #98614f;
}

.album-remove:focus-visible {
  outline: 2px solid var(--pine);
  outline-offset: 2px;
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

  .album-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
