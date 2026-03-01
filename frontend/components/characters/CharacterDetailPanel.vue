<template>
  <div class="panel-overlay" @click.self="$emit('close')" @keydown.escape.window="$emit('close')">
    <div class="panel-slide">
      <!-- Header -->
      <div class="panel-header">
        <div style="display: flex; align-items: center; gap: 10px;">
          <div>
            <h2 style="font-size: 18px; font-weight: 500; margin: 0;">{{ character.name }}</h2>
            <span style="font-size: 12px; color: var(--text-muted);">{{ character.project_name }}</span>
          </div>
          <span v-if="profile.character_role" class="role-badge">{{ profile.character_role }}</span>
        </div>
        <button class="btn" style="font-size: 16px; padding: 4px 10px; line-height: 1;" @click="$emit('close')">&times;</button>
      </div>

      <!-- Training status bar -->
      <div class="panel-section" style="padding: 12px 20px; background: var(--bg-primary);">
        <div style="display: flex; gap: 24px; align-items: center; font-size: 13px;">
          <div>
            <span :style="{ color: characterStats.canTrain ? 'var(--status-success)' : 'var(--text-secondary)', fontWeight: 600 }">
              {{ characterStats.approved }}/{{ minTrainingImages }}
            </span>
            <span style="color: var(--text-muted);"> approved</span>
          </div>
          <div v-if="characterStats.pending > 0">
            <span style="font-weight: 600;">{{ characterStats.pending }}</span>
            <span style="color: var(--text-muted);"> pending</span>
          </div>
          <span
            v-if="characterStats.canTrain"
            class="badge badge-approved"
            style="font-size: 11px;"
          >Ready to Train</span>
        </div>
        <div class="progress-track" style="height: 6px; margin-top: 8px;">
          <div
            class="progress-bar"
            :class="{ ready: characterStats.canTrain }"
            :style="{ width: `${Math.min(100, (characterStats.approved / minTrainingImages) * 100)}%` }"
          ></div>
        </div>
      </div>

      <!-- Scrollable body -->
      <div class="panel-body">
        <!-- Build Character button -->
        <div class="panel-section" style="display: flex; align-items: center; gap: 8px;">
          <EchoAssistButton
            context-type="character_profile"
            :context-payload="{
              project_name: character.project_name,
              character_name: character.name,
              character_slug: character.slug,
              checkpoint_model: character.checkpoint_model,
              design_prompt: profile.design_prompt || character.design_prompt,
            }"
            label="Build Character"
            @accept="applyCharacterProfile"
          />
          <span v-if="loadingDetail" style="font-size: 11px; color: var(--text-muted);">Loading profile...</span>
        </div>

        <!-- Identity section -->
        <div class="panel-section">
          <button class="section-toggle" @click="sections.identity = !sections.identity">
            <span style="font-size: 10px;">{{ sections.identity ? '\u25BC' : '\u25B6' }}</span>
            Identity
          </button>
          <div v-if="sections.identity" class="section-body">
            <div class="field-row">
              <div class="field" style="flex: 1;">
                <label>Description</label>
                <textarea v-model="profile.description" rows="3" class="input" placeholder="2-3 sentence character summary..."></textarea>
              </div>
            </div>
            <div class="field-row">
              <div class="field" style="flex: 1;">
                <label>Role</label>
                <select v-model="profile.character_role" class="input">
                  <option value="">--</option>
                  <option value="protagonist">Protagonist</option>
                  <option value="antagonist">Antagonist</option>
                  <option value="supporting">Supporting</option>
                  <option value="mentor">Mentor</option>
                  <option value="comic_relief">Comic Relief</option>
                </select>
              </div>
              <div class="field" style="width: 80px;">
                <label>Age</label>
                <input v-model.number="profile.age" type="number" class="input" placeholder="--" />
              </div>
            </div>
            <div class="field">
              <label>Personality</label>
              <textarea v-model="profile.personality" rows="3" class="input" placeholder="Personality description..."></textarea>
            </div>
            <div class="field">
              <label>Background</label>
              <textarea v-model="profile.background" rows="3" class="input" placeholder="Backstory..."></textarea>
            </div>
            <div class="field">
              <label>Personality Tags</label>
              <ChipInput v-model="profile.personality_tags" placeholder="Add tag..." />
            </div>
          </div>
        </div>

        <!-- Appearance section -->
        <div class="panel-section">
          <button class="section-toggle" @click="sections.appearance = !sections.appearance">
            <span style="font-size: 10px;">{{ sections.appearance ? '\u25BC' : '\u25B6' }}</span>
            Appearance
          </button>
          <div v-if="sections.appearance" class="section-body">
            <div class="field-row">
              <div class="field" style="flex: 1;">
                <label>Species</label>
                <PillSelect v-model="appearance.species" :options="['human', 'elf', 'android', 'demon', 'catgirl', 'vampire', 'dragon']" placeholder="human, elf, android..." />
              </div>
              <div class="field" style="flex: 1;">
                <label>Body Type</label>
                <PillSelect v-model="appearance.body_type" :options="['slim', 'athletic', 'muscular', 'curvy', 'petite', 'lean']" placeholder="lean, muscular..." />
              </div>
            </div>

            <div class="sub-section-label">Hair</div>
            <div class="field-row">
              <div class="field" style="flex: 1;"><label>Color</label><PillSelect v-model="appearance.hair.color" :options="['black', 'brown', 'blonde', 'red', 'silver', 'white', 'pink', 'blue', 'purple', 'green']" /></div>
              <div class="field" style="flex: 1;"><label>Style</label><PillSelect v-model="appearance.hair.style" :options="['long', 'short', 'ponytail', 'twin tails', 'braids', 'bob', 'spiky', 'wavy', 'messy', 'straight']" /></div>
              <div class="field" style="flex: 1;"><label>Length</label><PillSelect v-model="appearance.hair.length" :options="['short', 'medium', 'long', 'very long']" /></div>
            </div>

            <div class="sub-section-label">Eyes</div>
            <div class="field-row">
              <div class="field" style="flex: 1;"><label>Color</label><PillSelect v-model="appearance.eyes.color" :options="['brown', 'blue', 'green', 'red', 'purple', 'gold', 'amber', 'heterochromia']" /></div>
              <div class="field" style="flex: 1;"><label>Shape</label><PillSelect v-model="appearance.eyes.shape" :options="['round', 'almond', 'narrow', 'large', 'sharp']" /></div>
              <div class="field" style="flex: 1;"><label>Special</label><PillSelect v-model="appearance.eyes.special" :options="['glowing', 'slit pupils', 'eye patch', 'blindfold', 'cybernetic', 'scarred', 'gradient iris']" /></div>
            </div>

            <div class="sub-section-label">Skin</div>
            <div class="field-row">
              <div class="field" style="flex: 1;"><label>Tone</label><PillSelect v-model="appearance.skin.tone" :options="['fair', 'light', 'tan', 'olive', 'brown', 'dark', 'pale', 'porcelain']" /></div>
              <div class="field" style="flex: 1;"><label>Markings</label><PillSelect v-model="appearance.skin.markings" :options="['scar', 'tattoo', 'freckles', 'birthmark', 'tribal markings', 'cybernetic lines', 'none']" /></div>
            </div>

            <div class="sub-section-label">Face</div>
            <div class="field-row">
              <div class="field" style="flex: 1;"><label>Shape</label><PillSelect v-model="appearance.face.shape" :options="['round', 'oval', 'angular', 'heart', 'square', 'sharp jawline', 'soft']" /></div>
              <div class="field" style="flex: 1;"><label>Features</label><PillSelect v-model="appearance.face.features" :options="['sharp features', 'soft features', 'high cheekbones', 'strong jaw', 'delicate', 'rugged', 'boyish', 'mature']" /></div>
            </div>

            <div class="sub-section-label">Body</div>
            <div class="field-row">
              <div class="field" style="flex: 1;"><label>Build</label><PillSelect v-model="appearance.body.build" :options="['slim', 'athletic', 'muscular', 'toned', 'stocky', 'broad', 'lithe', 'heavyset']" /></div>
              <div class="field" style="flex: 1;"><label>Height</label><PillSelect v-model="appearance.body.height" :options="['short', 'average', 'tall', 'very tall', 'petite', 'towering']" /></div>
            </div>
            <div class="field-row">
              <div class="field" style="flex: 1;"><label>Bust</label><PillSelect v-model="appearance.body.bust" :options="['flat', 'small', 'medium', 'large', 'huge']" /></div>
              <div class="field" style="flex: 1;"><label>Waist</label><PillSelect v-model="appearance.body.waist" :options="['narrow', 'slim', 'average', 'wide']" /></div>
              <div class="field" style="flex: 1;"><label>Hips</label><PillSelect v-model="appearance.body.hips" :options="['narrow', 'average', 'wide', 'thick']" /></div>
            </div>

            <div class="sub-section-label">Key Colors</div>
            <KeyValueEditor v-model="appearance.key_colors" key-placeholder="Part" value-placeholder="Color" />

            <div class="field">
              <label>Key Features</label>
              <ChipInput v-model="appearance.key_features" placeholder="Add feature..." />
            </div>
            <div class="field">
              <label>Common Errors</label>
              <ChipInput v-model="appearance.common_errors" placeholder="Add error..." />
            </div>
          </div>
        </div>

        <!-- Equipment section -->
        <div class="panel-section">
          <button class="section-toggle" @click="sections.equipment = !sections.equipment">
            <span style="font-size: 10px;">{{ sections.equipment ? '\u25BC' : '\u25B6' }}</span>
            Equipment
          </button>
          <div v-if="sections.equipment" class="section-body">
            <div class="field-row">
              <div class="field" style="flex: 1;">
                <label>Default Outfit</label>
                <PillSelect v-model="appearance.clothing.default_outfit" :options="['school uniform', 'armor', 'kimono', 'leather jacket', 'dress', 'suit', 'casual', 'military', 'maid outfit', 'hoodie', 'robes', 'swimsuit', 'bodysuit']" placeholder="leather jacket, ripped jeans..." />
              </div>
              <div class="field" style="flex: 1;">
                <label>Style</label>
                <PillSelect v-model="appearance.clothing.style" :options="['gothic', 'cyberpunk', 'fantasy', 'medieval', 'modern', 'punk', 'elegant', 'streetwear', 'steampunk', 'military', 'traditional']" placeholder="post-apocalyptic punk..." />
              </div>
            </div>

            <div class="sub-section-label" style="display: flex; align-items: center; gap: 8px;">
              Weapons
              <button class="btn" style="font-size: 10px; padding: 1px 6px;" @click="addWeapon">+ Add</button>
            </div>
            <div v-for="(w, i) in appearance.weapons" :key="i" class="field-row" style="align-items: flex-end;">
              <div class="field" style="flex: 1;"><label v-if="i === 0">Name</label><input v-model="w.name" class="input" /></div>
              <div class="field" style="flex: 1;"><label v-if="i === 0">Type</label><PillSelect v-model="w.type" :options="['sword', 'katana', 'axe', 'spear', 'bow', 'gun', 'staff', 'dagger', 'scythe', 'hammer', 'shield', 'magic']" /></div>
              <div class="field" style="flex: 2;"><label v-if="i === 0">Description</label><input v-model="w.description" class="input" /></div>
              <button class="btn" style="font-size: 10px; padding: 2px 6px; color: var(--status-error);" @click="appearance.weapons.splice(i, 1)">&times;</button>
            </div>

            <div class="field">
              <label>Accessories</label>
              <ChipInput v-model="appearance.accessories" placeholder="Add accessory..." />
            </div>
          </div>
        </div>

        <!-- Intimate section -->
        <div class="panel-section">
          <button class="section-toggle" @click="sections.intimate = !sections.intimate">
            <span style="font-size: 10px;">{{ sections.intimate ? '\u25BC' : '\u25B6' }}</span>
            Intimate
          </button>
          <div v-if="sections.intimate && appearance.sexual" class="section-body">
            <div class="field-row">
              <div class="field" style="flex: 1;"><label>Orientation</label><PillSelect v-model="appearance.sexual!.orientation" :options="['straight', 'gay', 'bisexual', 'asexual', 'pansexual']" /></div>
              <div class="field" style="flex: 1;"><label>Preferences</label><PillSelect v-model="appearance.sexual!.preferences" :options="['dominant', 'submissive', 'switch', 'romantic', 'playful', 'aggressive', 'gentle']" /></div>
            </div>
            <div class="field">
              <label>Physical Traits</label>
              <PillSelect v-model="appearance.sexual!.physical_traits" :options="['toned abs', 'athletic build', 'soft curves', 'muscular', 'slender', 'voluptuous', 'androgynous']" placeholder="athletic build, toned abs..." />
            </div>
          </div>
        </div>

        <!-- Design Prompt Editor -->
        <div class="panel-section">
          <button class="section-toggle" @click="sections.designPrompt = !sections.designPrompt">
            <span style="font-size: 10px;">{{ sections.designPrompt ? '\u25BC' : '\u25B6' }}</span>
            Design Prompt
          </button>
          <div v-if="sections.designPrompt" class="section-body">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
              <EchoAssistButton
                context-type="design_prompt"
                :context-payload="{
                  project_name: character.project_name,
                  character_name: character.name,
                  character_slug: character.slug,
                  checkpoint_model: character.checkpoint_model,
                }"
                :current-value="profile.design_prompt"
                compact
                @accept="profile.design_prompt = $event.suggestion"
              />
            </div>
            <textarea
              v-model="profile.design_prompt"
              rows="8"
              class="prompt-textarea"
              placeholder="Visual-only SD prompt for this character..."
            ></textarea>
            <div style="display: flex; gap: 6px; margin-top: 8px;">
              <button
                class="btn"
                style="font-size: 12px; color: var(--accent-primary);"
                @click="saveAndRegenerate"
                :disabled="!isDirty || saving"
              >
                Save & Regenerate
              </button>
            </div>
          </div>
        </div>

        <!-- Quick Actions -->
        <div class="panel-section" style="display: flex; gap: 8px; padding: 12px 20px;">
          <button
            v-if="!characterStats.canTrain"
            class="btn"
            style="font-size: 12px; color: var(--accent-primary); border-color: var(--accent-primary);"
            @click="$emit('generate-more', character)"
          >
            Generate {{ minTrainingImages - characterStats.approved }} More
          </button>
          <RouterLink
            v-if="characterStats.canTrain"
            to="/produce"
            class="btn"
            style="font-size: 12px; text-decoration: none; color: var(--status-success); border-color: var(--status-success);"
          >
            Start Training
          </RouterLink>
          <RouterLink
            to="/review"
            class="btn"
            style="font-size: 12px; text-decoration: none;"
          >
            Review Images
          </RouterLink>
        </div>

        <!-- Test Generation (collapsible) -->
        <div class="panel-section">
          <button class="section-toggle" @click="showTestGen = !showTestGen">
            <span style="font-size: 10px;">{{ showTestGen ? '\u25BC' : '\u25B6' }}</span>
            Test Generation
          </button>

          <div v-if="showTestGen" style="margin-top: 12px;">
            <!-- Type toggle + Seed -->
            <div style="display: flex; gap: 16px; margin-bottom: 12px; align-items: flex-end; flex-wrap: wrap;">
              <div>
                <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">Type</label>
                <div style="display: flex; gap: 4px;">
                  <button :class="['btn', genType === 'image' ? 'btn-active' : '']" style="font-size: 11px; padding: 3px 10px;" @click="genType = 'image'">Image</button>
                  <button :class="['btn', genType === 'video' ? 'btn-active' : '']" style="font-size: 11px; padding: 3px 10px;" @click="genType = 'video'">Video</button>
                  <button :class="['btn', genType === 'framepack' ? 'btn-active' : '']" style="font-size: 11px; padding: 3px 10px;" @click="genType = 'framepack'">FramePack</button>
                </div>
              </div>
              <div>
                <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">Seed</label>
                <input v-model.number="genSeed" type="number" placeholder="Random" style="width: 100px; padding: 3px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
              </div>
            </div>

            <!-- FramePack options -->
            <div v-if="genType === 'framepack'" style="display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; padding: 8px; background: var(--bg-primary); border-radius: 4px; border: 1px solid var(--border-primary); font-size: 11px;">
              <div style="min-width: 140px;">
                <label style="color: var(--text-muted); display: block; margin-bottom: 2px;">Duration: {{ fpSec }}s</label>
                <input v-model.number="fpSec" type="range" min="1" max="10" step="0.5" style="width: 100%;" />
              </div>
              <div>
                <label style="color: var(--text-muted); display: block; margin-bottom: 2px;">Steps</label>
                <div style="display: flex; gap: 3px;">
                  <button v-for="s in [15, 20, 25]" :key="s" :class="['btn', fpSteps === s ? 'btn-active' : '']" style="font-size: 10px; padding: 2px 8px;" @click="fpSteps = s">{{ s }}</button>
                </div>
              </div>
              <div>
                <label style="color: var(--text-muted); display: block; margin-bottom: 2px;">Model</label>
                <div style="display: flex; gap: 3px;">
                  <button :class="['btn', !fpF1 ? 'btn-active' : '']" style="font-size: 10px; padding: 2px 8px;" @click="fpF1 = false">I2V</button>
                  <button :class="['btn', fpF1 ? 'btn-active' : '']" style="font-size: 10px; padding: 2px 8px;" @click="fpF1 = true">F1</button>
                </div>
              </div>
            </div>

            <!-- Prompt override -->
            <div style="margin-bottom: 8px;">
              <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">
                Prompt Override <span style="font-size: 10px;">(empty = design_prompt)</span>
              </label>
              <textarea v-model="genPrompt" rows="2" :placeholder="character.design_prompt || 'Enter prompt...'" style="width: 100%; padding: 6px 8px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary);"></textarea>
            </div>

            <!-- Negative prompt -->
            <div style="margin-bottom: 12px;">
              <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">Negative Prompt</label>
              <input v-model="genNegative" type="text" placeholder="worst quality, low quality, blurry" style="width: 100%; padding: 4px 8px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
            </div>

            <!-- Generate button + status -->
            <div style="display: flex; gap: 8px; align-items: center;">
              <button class="btn btn-active" style="font-size: 12px; padding: 6px 16px;" @click="testGenerate" :disabled="genBusy">
                {{ genBusy ? 'Generating...' : 'Generate' }}
              </button>
              <span v-if="genStatus" style="font-size: 11px; color: var(--text-muted);">{{ genStatus }}</span>
            </div>

            <!-- Progress bar -->
            <div v-if="genProgress > 0" style="margin-top: 8px;">
              <div style="height: 4px; background: var(--bg-primary); border-radius: 2px; overflow: hidden;">
                <div :style="{ width: (genProgress * 100) + '%', height: '100%', background: genProgress >= 1 ? 'var(--status-success)' : 'var(--accent-primary)', transition: 'width 300ms ease' }"></div>
              </div>
            </div>

            <!-- Output -->
            <div v-if="genOutput.length" style="margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap;">
              <template v-for="file in genOutput" :key="file">
                <video v-if="/\\.(mp4|webm|gif)$/i.test(file)" :src="galleryUrl(file)" controls autoplay loop style="max-width: 220px; border-radius: 4px; border: 1px solid var(--border-primary);"></video>
                <img v-else :src="galleryUrl(file)" style="max-width: 160px; border-radius: 4px; cursor: pointer; border: 1px solid var(--border-primary);" @click="openGalleryImage(file)" />
              </template>
            </div>
          </div>
        </div>

        <!-- Image Gallery -->
        <div class="panel-section" style="flex: 1;">
          <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;">
            Approved Images ({{ approvedImages.length }})
          </div>
          <div v-if="approvedImages.length === 0" style="text-align: center; padding: 24px; color: var(--text-muted); font-size: 13px;">
            No approved images yet
          </div>
          <div v-else class="image-grid">
            <img
              v-for="img in approvedImages"
              :key="img.name"
              :src="imageUrl(img.name)"
              class="gallery-image"
              loading="lazy"
              @click="openImage(img.name)"
            />
          </div>
        </div>
      </div>

      <!-- Sticky footer -->
      <div class="panel-footer">
        <button
          class="btn"
          :class="{ 'btn-primary': isDirty }"
          @click="saveProfile"
          :disabled="!isDirty || saving"
        >
          {{ saving ? 'Saving...' : profileSaved ? 'Saved' : 'Save Profile' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import type { Character, DatasetImage, AppearanceData, CharacterUpdate } from '@/types'
import { api } from '@/api/client'
import EchoAssistButton from '../EchoAssistButton.vue'
import ChipInput from './ChipInput.vue'
import KeyValueEditor from './KeyValueEditor.vue'
import PillSelect from './PillSelect.vue'

interface CharacterStats {
  total: number
  approved: number
  pending: number
  canTrain: boolean
}

const props = defineProps<{
  character: Character
  datasetImages: DatasetImage[]
  characterStats: CharacterStats
  minTrainingImages: number
}>()

const emit = defineEmits<{
  close: []
  'save-prompt': [payload: { character: Character; text: string }]
  'generate-more': [character: Character]
  refresh: []
}>()

// --- Profile state ---
const loadingDetail = ref(false)
const saving = ref(false)
const profileSaved = ref(false)

const profile = reactive({
  design_prompt: props.character.design_prompt || '',
  description: '' as string,
  personality: '' as string,
  background: '' as string,
  age: null as number | null,
  character_role: '' as string,
  personality_tags: [] as string[],
})

function makeAppearance(data?: AppearanceData | null): AppearanceData {
  const d = data || {}
  return {
    species: d.species || '',
    body_type: d.body_type || '',
    key_colors: d.key_colors ? { ...d.key_colors } : {},
    key_features: d.key_features ? [...d.key_features] : [],
    common_errors: d.common_errors ? [...d.common_errors] : [],
    hair: { color: '', style: '', length: '', ...(d.hair || {}) },
    eyes: { color: '', shape: '', special: '', ...(d.eyes || {}) },
    skin: { tone: '', markings: '', ...(d.skin || {}) },
    face: { shape: '', features: '', ...(d.face || {}) },
    body: { build: '', height: '', bust: '', waist: '', hips: '', ...(d.body || {}) },
    clothing: { default_outfit: '', style: '', ...(d.clothing || {}) },
    weapons: d.weapons ? d.weapons.map(w => ({ ...w })) : [],
    accessories: d.accessories ? [...d.accessories] : [],
    sexual: { orientation: '', preferences: '', physical_traits: '', ...(d.sexual || {}) },
  }
}

const appearance = reactive<AppearanceData>(makeAppearance())

// Snapshot for dirty tracking — use deep watch to guarantee reactivity
const snapshot = ref('')
const currentState = ref('')

function serializeState() {
  return JSON.stringify({ profile, appearance })
}

function takeSnapshot() {
  const s = serializeState()
  snapshot.value = s
  currentState.value = s
}

// Deep watch both reactive objects to update currentState
watch([() => ({ ...profile }), () => JSON.stringify(appearance)], () => {
  currentState.value = serializeState()
}, { deep: true })

const isDirty = computed(() => {
  if (!snapshot.value) return false
  return currentState.value !== snapshot.value
})

// Section visibility
const sections = reactive({
  identity: true,
  appearance: true,
  equipment: false,
  intimate: false,
  designPrompt: true,
})

// --- Parse design_prompt into appearance fields when appearance_data is empty ---
const HAIR_COLORS = ['black', 'brown', 'blonde', 'red', 'silver', 'white', 'pink', 'blue', 'purple', 'green']
const HAIR_STYLES = ['long', 'short', 'medium', 'ponytail', 'twin tails', 'braids', 'bob', 'spiky', 'wavy', 'messy', 'straight']
const EYE_COLORS = ['brown', 'blue', 'green', 'red', 'purple', 'gold', 'amber']
const SPECIES_LIST = ['human', 'elf', 'android', 'demon', 'catgirl', 'vampire', 'dragon']
const BODY_TYPES = ['slim', 'athletic', 'muscular', 'curvy', 'petite', 'lean', 'tall']

function parseDesignPromptIntoAppearance(prompt: string, app: AppearanceData) {
  if (!prompt) return
  const tags = prompt.split(',').map(t => t.trim().toLowerCase()).filter(Boolean)
  for (const tag of tags) {
    const hc = HAIR_COLORS.find(c => tag.includes(`${c} hair`))
    if (hc && app.hair) { app.hair.color = app.hair.color || hc; continue }
    const hs = HAIR_STYLES.find(s => tag.includes(`${s} hair`))
    if (hs && app.hair) { app.hair.style = app.hair.style || hs; continue }
    const ec = EYE_COLORS.find(c => tag.includes(`${c} eyes`))
    if (ec && app.eyes) { app.eyes.color = app.eyes.color || ec; continue }
    const sp = SPECIES_LIST.find(s => tag === s)
    if (sp) { app.species = app.species || sp; continue }
    const bt = BODY_TYPES.find(b => tag === b || tag === `${b} body`)
    if (bt) { app.body_type = app.body_type || bt; continue }
  }
}

// --- Load full detail ---
async function loadDetail() {
  loadingDetail.value = true
  try {
    const detail = await api.getCharacterDetail(props.character.slug)
    profile.design_prompt = detail.design_prompt || ''
    profile.description = detail.description || ''
    profile.personality = detail.personality || ''
    profile.background = detail.background || ''
    profile.age = detail.age ?? null
    profile.character_role = detail.character_role || ''
    profile.personality_tags = detail.personality_tags || []

    Object.assign(appearance, makeAppearance(detail.appearance_data))
    // When appearance_data is empty, seed from design_prompt
    if (!detail.appearance_data && detail.design_prompt) {
      parseDesignPromptIntoAppearance(detail.design_prompt, appearance)
    }
    takeSnapshot()
  } catch (err) {
    console.error('Failed to load character detail:', err)
    takeSnapshot()
  } finally {
    loadingDetail.value = false
  }
}

onMounted(loadDetail)

watch(() => props.character.slug, () => {
  profile.design_prompt = props.character.design_prompt || ''
  profile.description = ''
  profile.personality = ''
  profile.background = ''
  profile.age = null
  profile.character_role = ''
  profile.personality_tags = []
  Object.assign(appearance, makeAppearance())
  profileSaved.value = false
  loadDetail()
})

// --- Build Character handler ---
function applyCharacterProfile(event: { suggestion: string; contextType: string; fields?: Record<string, any> }) {
  const f = event.fields
  if (!f) return

  if (f.description) profile.description = f.description
  if (f.personality) profile.personality = f.personality
  if (f.background) profile.background = f.background
  if (f.age != null) profile.age = typeof f.age === 'number' ? f.age : parseInt(f.age) || null
  if (f.character_role) profile.character_role = f.character_role
  if (f.personality_tags && Array.isArray(f.personality_tags)) profile.personality_tags = f.personality_tags
  if (f.design_prompt) profile.design_prompt = f.design_prompt

  // Appearance fields → merge into appearance reactive
  const appFields: (keyof AppearanceData)[] = [
    'species', 'body_type', 'key_colors', 'key_features', 'common_errors',
    'hair', 'eyes', 'skin', 'face', 'body', 'clothing', 'weapons', 'accessories', 'sexual',
  ]
  for (const key of appFields) {
    if (f[key] != null) {
      if (typeof f[key] === 'object' && !Array.isArray(f[key])) {
        // Merge sub-objects (hair, eyes, skin, etc.)
        const existing = (appearance as any)[key]
        if (existing && typeof existing === 'object') {
          Object.assign(existing, f[key])
        } else {
          (appearance as any)[key] = f[key]
        }
      } else {
        (appearance as any)[key] = f[key]
      }
    }
  }
}

// --- Save Profile ---
async function saveProfile() {
  if (!isDirty.value) return
  saving.value = true
  try {
    const payload: CharacterUpdate = {}

    // Always include text fields from profile
    payload.design_prompt = profile.design_prompt?.trim() || undefined
    payload.description = profile.description?.trim() || undefined
    payload.personality = profile.personality?.trim() || undefined
    payload.background = profile.background?.trim() || undefined
    payload.age = profile.age
    payload.character_role = profile.character_role || undefined
    payload.personality_tags = profile.personality_tags.length ? profile.personality_tags : undefined

    // Build merged appearance_data
    const appData: AppearanceData = {}
    if (appearance.species) appData.species = appearance.species
    if (appearance.body_type) appData.body_type = appearance.body_type
    if (appearance.key_colors && Object.keys(appearance.key_colors).length) appData.key_colors = appearance.key_colors
    if (appearance.key_features?.length) appData.key_features = appearance.key_features
    if (appearance.common_errors?.length) appData.common_errors = appearance.common_errors
    if (appearance.hair && Object.values(appearance.hair).some(v => v)) appData.hair = appearance.hair
    if (appearance.eyes && Object.values(appearance.eyes).some(v => v)) appData.eyes = appearance.eyes
    if (appearance.skin && Object.values(appearance.skin).some(v => v)) appData.skin = appearance.skin
    if (appearance.face && Object.values(appearance.face).some(v => v)) appData.face = appearance.face
    if (appearance.body && Object.values(appearance.body).some(v => v)) appData.body = appearance.body
    if (appearance.clothing && Object.values(appearance.clothing).some(v => v)) appData.clothing = appearance.clothing
    if (appearance.weapons?.length) appData.weapons = appearance.weapons
    if (appearance.accessories?.length) appData.accessories = appearance.accessories
    if (appearance.sexual && Object.values(appearance.sexual).some(v => v)) appData.sexual = appearance.sexual
    if (Object.keys(appData).length) payload.appearance_data = appData

    await api.updateCharacter(props.character.slug, payload)
    profileSaved.value = true
    takeSnapshot()
    setTimeout(() => { profileSaved.value = false }, 2000)
    emit('refresh')
  } catch (error) {
    console.error('Failed to save profile:', error)
  } finally {
    saving.value = false
  }
}

async function saveAndRegenerate() {
  await saveProfile()
  emit('generate-more', props.character)
}

function addWeapon() {
  if (!appearance.weapons) appearance.weapons = []
  appearance.weapons.push({ name: '', type: '', description: '' })
}

// --- Test Generation state ---
const showTestGen = ref(false)
const genType = ref<'image' | 'video' | 'framepack'>('image')
const genSeed = ref<number | undefined>(undefined)
const genPrompt = ref('')
const genNegative = ref('')
const genBusy = ref(false)
const genStatus = ref('')
const genProgress = ref(0)
const genOutput = ref<string[]>([])
const fpSec = ref(3)
const fpSteps = ref(25)
const fpF1 = ref(false)
let genPollTimer: ReturnType<typeof setInterval> | null = null

onUnmounted(() => {
  if (genPollTimer) { clearInterval(genPollTimer); genPollTimer = null }
})

function galleryUrl(filename: string): string {
  return api.galleryImageUrl(filename)
}

function openGalleryImage(filename: string) {
  window.open(galleryUrl(filename), '_blank')
}

async function testGenerate() {
  genBusy.value = true
  genStatus.value = ''
  genProgress.value = 0
  genOutput.value = []

  try {
    if (genType.value === 'framepack') {
      const result = await api.generateFramePack(props.character.slug, {
        prompt_override: genPrompt.value || undefined,
        negative_prompt: genNegative.value || undefined,
        seconds: fpSec.value,
        steps: fpSteps.value,
        use_f1: fpF1.value,
        seed: genSeed.value || undefined,
      })
      genStatus.value = `FramePack submitted (${result.total_sections} sections)`
      genProgress.value = 0.05
      startGenPoll(result.prompt_id)
    } else {
      const result = await api.generateForCharacter(props.character.slug, {
        generation_type: genType.value,
        prompt_override: genPrompt.value || undefined,
        negative_prompt: genNegative.value || undefined,
        seed: genSeed.value || undefined,
      })
      genStatus.value = 'Submitted to ComfyUI'
      genProgress.value = 0.05
      startGenPoll(result.prompt_id)
    }
  } catch (err: any) {
    genStatus.value = `Error: ${err.message}`
    genBusy.value = false
  }
}

function startGenPoll(promptId: string) {
  if (genPollTimer) clearInterval(genPollTimer)
  genPollTimer = setInterval(async () => {
    try {
      const status = await api.getGenerationStatus(promptId)
      genProgress.value = status.progress
      genStatus.value = status.status
      if (status.status === 'completed') {
        if (genPollTimer) clearInterval(genPollTimer)
        genPollTimer = null
        genOutput.value = status.images || []
        genBusy.value = false
      } else if (status.status === 'error') {
        if (genPollTimer) clearInterval(genPollTimer)
        genPollTimer = null
        genStatus.value = `Error: ${status.error || 'unknown'}`
        genBusy.value = false
      }
    } catch { /* ignore transient */ }
  }, 2000)
}

const approvedImages = computed(() =>
  props.datasetImages.filter(img => img.status === 'approved')
)

function imageUrl(name: string): string {
  return api.imageUrl(props.character.slug, name)
}

function openImage(name: string) {
  window.open(imageUrl(name), '_blank')
}
</script>

<style scoped>
.panel-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: flex-end;
}
.panel-slide {
  width: 560px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-primary);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: slideIn 200ms ease;
}
@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
}
.panel-body {
  flex: 1;
  overflow-y: auto;
}
.panel-section {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
}
.panel-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  display: flex;
  justify-content: flex-end;
}
.role-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--accent-primary);
  color: var(--bg-primary);
  text-transform: capitalize;
  font-weight: 600;
}
.section-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 0;
  font-family: var(--font-primary);
}
.section-toggle:hover {
  color: var(--text-primary);
}
.section-body {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.field label {
  font-size: 11px;
  color: var(--text-muted);
}
.field-row {
  display: flex;
  gap: 8px;
}
.sub-section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-top: 4px;
}
.input {
  width: 100%;
  padding: 5px 8px;
  font-size: 12px;
  font-family: var(--font-primary);
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
}
.input:focus {
  border-color: var(--accent-primary);
  outline: none;
}
select.input {
  appearance: auto;
}
textarea.input {
  resize: vertical;
  line-height: 1.5;
}
.prompt-textarea {
  width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  font-family: var(--font-primary);
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  resize: vertical;
  line-height: 1.5;
}
.prompt-textarea:focus {
  border-color: var(--accent-primary);
  outline: none;
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}
.gallery-image {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--border-primary);
  cursor: pointer;
  transition: border-color 150ms ease;
}
.gallery-image:hover {
  border-color: var(--accent-primary);
}
.btn-primary {
  background: var(--accent-primary);
  color: #fff;
  border-color: var(--accent-primary);
}
</style>
