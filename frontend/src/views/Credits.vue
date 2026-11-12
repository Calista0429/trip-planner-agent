<template>
  <section class="shell credits" aria-labelledby="credits-title">
    <router-link to="/" class="back">← {{ t('credits.back') }}</router-link>
    <h1 id="credits-title" class="serif">{{ t('credits.title') }}</h1>
    <p class="intro">{{ t('credits.intro') }}</p>
    <ol class="list">
      <li v-for="item in items" :key="item.id" class="item">
        <img
          :src="item.image"
          :alt="item.alt"
          :style="{ objectPosition: item.objectPosition || 'center' }"
          loading="lazy"
          width="160"
          height="110"
        />
        <div class="text">
          <h2>{{ item.heading }}</h2>
          <dl>
            <div>
              <dt>{{ t('credits.author') }}</dt>
              <dd>{{ item.credit }}</dd>
            </div>
            <div>
              <dt>{{ t('credits.license') }}</dt>
              <dd>
                <a v-if="item.licenseUrl" :href="item.licenseUrl" target="_blank" rel="noopener noreferrer">
                  {{ item.licenseName }}
                </a>
                <span v-else>{{ item.licenseName }}</span>
                <span v-if="item.licenseNote" class="note">{{ item.licenseNote }}</span>
              </dd>
            </div>
            <div v-if="item.objectPosition">
              <dt>{{ t('credits.crop') }}</dt>
              <dd>{{ item.objectPosition }}</dd>
            </div>
          </dl>
          <a class="source" :href="item.source" target="_blank" rel="noopener noreferrer">
            {{ t('credits.source') }}
          </a>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { locale, t } from '@/i18n'
import { DESTINATIONS, licenseLabel, licenseUrl } from '@/data/destinations'

const items = computed(() =>
  DESTINATIONS.map(d => {
    const url = licenseUrl(d)
    // Everything after the license name/URL is a resize or edit note; keep it verbatim.
    const note = d.license
      .replace(licenseLabel(d), '')
      .replace(url ?? '', '')
      .replace(/^[\s—；;]+|[\s—；;]+$/g, '')
    const en = locale.value === 'en'
    return {
      id: d.id,
      image: d.image,
      objectPosition: d.objectPosition,
      heading: en ? `${d.en.province} · ${d.en.title}` : `${d.province} · ${d.landmark}`,
      alt: en ? d.en.title : d.landmark,
      credit: d.credit,
      licenseName: licenseLabel(d),
      licenseUrl: url,
      licenseNote: note,
      source: d.source
    }
  })
)
</script>

<style scoped>
.credits {
  padding-top: 36px;
  padding-bottom: 48px;
}

.back {
  color: var(--pine);
  font-size: 13px;
  text-decoration: none;
  border-bottom: 1px solid #aebdaf;
}

h1 {
  margin: 28px 0 10px;
  font-size: 32px;
  color: var(--ink);
}

.intro {
  max-width: 720px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.85;
}

.list {
  list-style: none;
  margin: 24px 0 0;
  padding: 0;
}

.item {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 25px;
  padding: 22px 0;
  border-bottom: 1px solid var(--line);
}

.item img {
  width: 160px;
  height: 110px;
  object-fit: cover;
  background: #e5eae4;
}

h2 {
  margin: 0 0 6px;
  font-size: 17px;
  font-weight: 500;
  color: var(--ink);
}

dl {
  margin: 0;
}

dl div {
  display: flex;
  gap: 10px;
  font-size: 12px;
  line-height: 1.8;
}

dt {
  flex: none;
  min-width: 64px;
  color: var(--muted);
}

dd {
  margin: 0;
  overflow-wrap: anywhere;
}

dd a,
.source {
  color: var(--pine);
  text-underline-offset: 4px;
}

.note {
  display: block;
  color: var(--muted);
}

.source {
  display: inline-block;
  margin-top: 6px;
  font-size: 12px;
}

@media (max-width: 600px) {
  .item {
    grid-template-columns: 96px minmax(0, 1fr);
    gap: 14px;
  }

  .item img {
    width: 96px;
    height: 96px;
  }

  h1 {
    font-size: 26px;
  }

  h2 {
    font-size: 15px;
  }

  dl div {
    flex-direction: column;
    gap: 0;
  }
}
</style>
