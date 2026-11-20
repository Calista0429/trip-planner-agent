<template>
  <AlbumPlaceholder
    title-id="album-library-title"
    :title="t('album.libraryTitle')"
    :status="t('album.libraryEmpty')"
    :description="t('album.libraryDesc')"
    :links="[{ to: '/albums', label: t('album.toWorkspace') }]"
  />
</template>

<script setup lang="ts">
import AlbumPlaceholder from '@/components/album/AlbumPlaceholder.vue'
import { t } from '@/i18n'
</script>
