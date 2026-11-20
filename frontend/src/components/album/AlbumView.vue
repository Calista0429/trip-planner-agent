<template>
  <article class="album-view">
    <header class="album-view-head">
      <p class="album-view-meta">
        {{ albumStyleLabel(album.style) }} · {{ formatAlbumDate(album.createdAt) }} ·
        {{ t('album.pictureCount', { n: album.pictures.length }) }}
      </p>
      <h2 class="serif album-view-title">{{ album.title }}</h2>
    </header>

    <ol class="album-pictures">
      <li v-for="(picture, index) in album.pictures" :key="picture.imageUrl + index" class="album-picture">
        <figure>
          <img
            :src="picture.imageUrl"
            :alt="t('album.pictureAlt', { location: picture.location || album.title })"
            loading="lazy"
          />
          <figcaption>
            <p v-if="picture.location" class="album-picture-location">{{ picture.location }}</p>
            <p v-if="picture.description" class="album-picture-desc">{{ picture.description }}</p>
            <div v-if="pointsOf(picture).length" class="album-poi">
              <p class="album-poi-title">{{ t('album.poiTitle') }}</p>
              <ul>
                <li v-for="poi in pointsOf(picture)" :key="poi.name">
                  <span class="album-poi-name">{{ poi.name }}</span>
                  <span v-if="poi.note" class="album-poi-note">{{ poi.note }}</span>
                </li>
              </ul>
            </div>
          </figcaption>
        </figure>
      </li>
    </ol>
  </article>
</template>

<script setup lang="ts">
// One album, as generated or as saved in this browser. Everything the model wrote
// is rendered with text interpolation only: never v-html.
import { t } from '@/i18n'
import type { Album, AlbumPicture } from '@/types'
import { albumStyleLabel, formatAlbumDate } from '@/utils/albumMessages'
import { parsePointsOfInterest } from '@/utils/pointsOfInterest'

defineProps<{ album: Album }>()

const pointsOf = (picture: AlbumPicture) => parsePointsOfInterest(picture.pointsOfInterest)
</script>

<style scoped>
.album-view-meta {
  margin: 0 0 8px;
  color: var(--muted);
  font-size: 12px;
}

.album-view-title {
  margin: 0 0 28px;
  color: var(--ink);
  font-size: 30px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.album-pictures {
  display: grid;
  gap: 40px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.album-picture figure {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 28px;
  align-items: start;
  margin: 0;
}

.album-picture img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid var(--line);
  background: var(--card);
}

.album-picture figcaption {
  min-width: 0;
  padding-top: 4px;
}

.album-picture-location {
  margin: 0 0 8px;
  color: var(--pine);
  font-family: var(--serif);
  font-size: 18px;
  overflow-wrap: anywhere;
}

.album-picture-desc {
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.85;
  overflow-wrap: anywhere;
}

.album-poi {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.album-poi-title {
  margin: 0 0 8px;
  color: var(--muted);
  font-size: 12px;
}

.album-poi ul {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
  line-height: 1.7;
}

.album-poi-name {
  color: var(--ink);
  font-weight: 600;
}

.album-poi-note {
  margin-left: 6px;
  color: var(--muted);
}

@media (max-width: 760px) {
  .album-view-title {
    font-size: 24px;
  }

  .album-picture figure {
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
}
</style>
