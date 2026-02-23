<template>
  <div
    v-if="visible"
    style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center;"
    @click.self="$emit('close')"
    @keydown.escape.window="$emit('close')"
  >
    <div class="card" style="width: 740px; max-height: 80vh; overflow-y: auto;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <div style="font-size: 14px; font-weight: 500;">
          Select Source Image
          <span v-if="currentShotType" style="font-size: 11px; color: var(--text-muted); margin-left: 6px;">
            ({{ currentShotType }} shot)
          </span>
        </div>
        <button class="btn" style="font-size: 11px; padding: 2px 8px;" @click="$emit('close')">Close</button>
      </div>

      <!-- Filter hint -->
      <div v-if="charactersPresent && charactersPresent.length > 0" style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px; display: flex; align-items: center; gap: 6px;">
        <span>Filtered for:</span>
        <span v-for="c in charactersPresent" :key="c" style="padding: 1px 6px; background: rgba(122,162,247,0.15); color: var(--accent-primary); border-radius: 10px; font-size: 10px;">{{ c }}</span>
        <button style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 11px; font-family: var(--font-primary);" @click="showAll = !showAll">
          {{ showAll ? 'Show matching only' : 'Show all' }}
        </button>
      </div>

      <div v-if="loading" style="color: var(--text-muted); font-size: 13px;">Loading approved images...</div>
      <div v-else>
        <!-- Recommended section -->
        <div v-if="recommendations && recommendations.length > 0" style="margin-bottom: 20px;">
          <div style="font-size: 12px; font-weight: 500; color: var(--status-warning); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
            Recommended for this shot
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 10px;">
            <div
              v-for="rec in recommendations"
              :key="rec.image_name + rec.slug"
              class="rec-card"
              @click="$emit('select', rec.slug, rec.image_name)"
            >
              <div style="position: relative;">
                <img
                  :src="imageUrl(rec.slug, rec.image_name)"
                  style="width: 120px; height: 120px; object-fit: cover; border-radius: 3px;"
                  @error="($event.target as HTMLImageElement).style.display = 'none'"
                />
                <span :class="qualityBadgeClass(rec.quality_score)" class="quality-badge"></span>
              </div>
              <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ rec.pose || 'unknown pose' }}
              </div>
              <div style="font-size: 10px; color: var(--text-muted);">
                {{ Math.round(rec.score * 100) }}% match
              </div>
            </div>
          </div>
        </div>

        <!-- Character grids -->
        <div v-for="(charData, slug) in sortedImages" :key="slug" style="margin-bottom: 16px;">
          <div style="font-size: 13px; font-weight: 500; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
            <span :style="{ color: isMatchingCharacter(slug as string) ? 'var(--accent-primary)' : 'var(--text-secondary)' }">
              {{ charData.character_name }}
            </span>
            <span v-if="isMatchingCharacter(slug as string)" style="font-size: 10px; color: var(--status-success);">match</span>
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            <div
              v-for="img in sortedCharImages(charData.images)"
              :key="getImageName(img)"
              :class="{ 'img-recommended': isRecommended(slug as string, getImageName(img)) }"
              style="cursor: pointer; border: 2px solid transparent; border-radius: 4px; text-align: center;"
              @click="$emit('select', slug as string, getImageName(img))"
            >
              <div style="position: relative; display: inline-block;">
                <img
                  :src="imageUrl(slug as string, getImageName(img))"
                  style="width: 120px; height: 120px; object-fit: cover; border-radius: 3px;"
                  @error="($event.target as HTMLImageElement).style.display = 'none'"
                />
                <span
                  v-if="getImageQuality(img) !== null"
                  :class="qualityBadgeClass(getImageQuality(img)!)"
                  class="quality-badge"
                ></span>
              </div>
              <div v-if="getImagePose(img)" style="font-size: 10px; color: var(--text-muted); margin-top: 2px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ getImagePose(img) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ImageWithMetadata, ShotRecommendation } from '@/types'

type ImageEntry = string | ImageWithMetadata

const props = defineProps<{
  visible: boolean
  loading: boolean
  approvedImages: Record<string, { character_name: string; images: ImageEntry[] }>
  imageUrl: (slug: string, imageName: string) => string
  charactersPresent?: string[]
  recommendations?: ShotRecommendation[]
  currentShotType?: string
}>()

defineEmits<{
  close: []
  select: [slug: string, imageName: string]
}>()

const showAll = ref(false)

// --- Polymorphic helpers for string[] vs ImageWithMetadata[] ---

function isMetadataEntry(img: ImageEntry): img is ImageWithMetadata {
  return typeof img === 'object' && img !== null && 'name' in img
}

function getImageName(img: ImageEntry): string {
  return isMetadataEntry(img) ? img.name : img
}

function getImagePose(img: ImageEntry): string | null {
  return isMetadataEntry(img) ? img.pose : null
}

function getImageQuality(img: ImageEntry): number | null {
  return isMetadataEntry(img) ? img.quality_score : null
}

function sortedCharImages(images: ImageEntry[]): ImageEntry[] {
  if (images.length === 0) return images
  if (!isMetadataEntry(images[0])) return images
  return [...images].sort((a, b) => {
    const qa = (a as ImageWithMetadata).quality_score ?? 0.5
    const qb = (b as ImageWithMetadata).quality_score ?? 0.5
    return qb - qa
  })
}

// --- Recommendation helpers ---

function isRecommended(slug: string, imageName: string): boolean {
  if (!props.recommendations) return false
  return props.recommendations.some(r => r.slug === slug && r.image_name === imageName)
}

function qualityBadgeClass(score: number): string {
  if (score >= 0.8) return 'quality-high'
  if (score >= 0.5) return 'quality-mid'
  return 'quality-low'
}

// --- Character filtering/sorting ---

function isMatchingCharacter(slug: string): boolean {
  if (!props.charactersPresent || props.charactersPresent.length === 0) return false
  return props.charactersPresent.includes(slug)
}

const sortedImages = computed(() => {
  const entries = Object.entries(props.approvedImages)
  if (!props.charactersPresent || props.charactersPresent.length === 0 || showAll.value) {
    return Object.fromEntries(
      entries.sort(([a], [b]) => {
        const aMatch = isMatchingCharacter(a) ? 0 : 1
        const bMatch = isMatchingCharacter(b) ? 0 : 1
        return aMatch - bMatch
      })
    )
  }
  const filtered = entries.filter(([slug]) => isMatchingCharacter(slug))
  if (filtered.length === 0) {
    showAll.value = true
    return props.approvedImages
  }
  return Object.fromEntries(filtered)
})
</script>

<style scoped>
.rec-card {
  cursor: pointer;
  border: 2px solid rgba(224, 175, 68, 0.4);
  border-radius: 6px;
  padding: 6px;
  background: rgba(224, 175, 68, 0.05);
  transition: border-color 0.15s;
}
.rec-card:hover {
  border-color: rgba(224, 175, 68, 0.8);
}

.img-recommended {
  border-color: rgba(224, 175, 68, 0.25) !important;
}

.quality-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.quality-high {
  background: var(--status-success);
  box-shadow: 0 0 4px rgba(80, 160, 80, 0.6);
}
.quality-mid {
  background: var(--status-warning);
  box-shadow: 0 0 4px rgba(200, 160, 60, 0.6);
}
.quality-low {
  background: var(--status-error);
  box-shadow: 0 0 4px rgba(160, 80, 80, 0.6);
}
</style>
