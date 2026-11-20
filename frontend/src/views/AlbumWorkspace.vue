<template>
  <AlbumPlaceholder
    title-id="album-workspace-title"
    :title="t('album.workspaceTitle')"
    :intro="t('album.workspaceIntro')"
    :status="t('album.status')"
    :description="t('album.statusDesc')"
    :links="[
      { to: '/albums/library', label: t('album.toLibrary') },
      { to: '/', label: t('album.toPlanner') }
    ]"
  />
</template>

<script setup lang="ts">
import AlbumPlaceholder from '@/components/album/AlbumPlaceholder.vue'
import { t } from '@/i18n'
</script>
