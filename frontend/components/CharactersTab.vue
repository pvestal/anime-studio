<template>
  <div>
    <!-- Training feedback toast -->
    <div v-if="trainingMessage" style="position: fixed; top: 16px; right: 16px; z-index: 1000; padding: 10px 16px; border-radius: 4px; font-size: 13px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); background: rgba(80,160,80,0.15); border: 1px solid var(--status-success); color: var(--status-success); min-width: 280px;">
      {{ trainingMessage }}
    </div>

    <!-- Sub-tab toggle (hidden when driven by CastTab) -->
    <div v-if="!hideSubTabs" style="display: flex; gap: 4px; margin-bottom: 20px;">
      <button
        :class="['sub-tab', activeSubTab === 'characters' ? 'sub-tab-active' : '']"
        @click="activeSubTab = 'characters'"
      >
        Characters
      </button>
      <button
        :class="['sub-tab', activeSubTab === 'ingest' ? 'sub-tab-active' : '']"
        @click="activeSubTab = 'ingest'"
      >
        Ingest Content
      </button>
      <button
        :class="['sub-tab', activeSubTab === 'workbench' ? 'sub-tab-active' : '']"
        @click="activeSubTab = 'workbench'"
      >
        Workbench
      </button>
    </div>

    <!-- ========== INGEST CONTENT SUB-TAB ========== -->
    <div v-if="activeSubTab === 'ingest'">
      <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 24px;">
        Bring in content from any source. Extracted frames go to the Approve tab for review.
      </p>

      <!-- Target selector -->
      <div style="margin-bottom: 24px; display: flex; gap: 16px; align-items: flex-end;">
        <div>
          <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Target</label>
          <div style="display: flex; gap: 4px;">
            <button :class="['btn', ingestTargetMode === 'character' ? 'btn-active' : '']" style="font-size: 12px; padding: 4px 12px;" @click="ingestTargetMode = 'character'">Single Character</button>
            <button :class="['btn', ingestTargetMode === 'project' ? 'btn-active' : '']" style="font-size: 12px; padding: 4px 12px;" @click="ingestTargetMode = 'project'">Entire Project</button>
          </div>
        </div>
        <div v-if="ingestTargetMode === 'character'" style="flex: 1;">
          <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Character</label>
          <select v-model="ingestSelectedCharacter" style="min-width: 280px;">
            <option value="">Select a character...</option>
            <option v-for="c in charactersStore.characters" :key="c.slug" :value="c.slug">{{ c.name }} ({{ c.project_name }})</option>
          </select>
        </div>
        <div v-else style="flex: 1;">
          <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Project <span style="font-size: 11px; color: var(--text-muted);">(frames distributed to all characters)</span></label>
          <select v-model="ingestSelectedProject" style="min-width: 280px;">
            <option value="">Select a project...</option>
            <option v-for="p in ingestProjects" :key="p.name" :value="p.name">{{ p.name }} ({{ p.character_count }} characters)</option>
          </select>
        </div>
      </div>

      <!-- Ingestion Progress Banner (always visible when active or recently completed) -->
      <div v-if="ingestProgress.active || ingestProgress.stage === 'complete' || ingestProgress.stage === 'error'" style="margin-bottom: 16px; padding: 14px 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 6px; border-left: 4px solid var(--accent-primary);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-weight: 600; font-size: 14px;">
            <template v-if="ingestProgress.stage === 'downloading'">Downloading Video</template>
            <template v-else-if="ingestProgress.stage === 'hashing'">Deduplicating Frames</template>
            <template v-else-if="ingestProgress.stage === 'classifying'">Classifying & Verifying</template>
            <template v-else-if="ingestProgress.stage === 'analyzing'">Building Source Analysis</template>
            <template v-else-if="ingestProgress.stage === 'registering'">Registering Images</template>
            <template v-else-if="ingestProgress.stage === 'complete'">Ingestion Complete</template>
            <template v-else-if="ingestProgress.stage === 'error'">Ingestion Failed</template>
            <template v-else>{{ ingestProgress.stage }}</template>
          </span>
          <span v-if="ingestProgress.frame_total" style="font-size: 13px; color: var(--text-muted);">
            {{ ingestProgress.frame_current }} / {{ ingestProgress.frame_total }} frames
          </span>
        </div>
        <div v-if="ingestProgress.frame_total && ingestProgress.active" style="width: 100%; height: 8px; background: var(--bg-primary); border-radius: 4px; overflow: hidden; margin-bottom: 8px;">
          <div :style="{ width: Math.round(100 * (ingestProgress.frame_current || 0) / ingestProgress.frame_total) + '%', height: '100%', background: 'var(--accent-primary)', transition: 'width 0.5s ease' }"></div>
        </div>
        <div style="font-size: 12px; color: var(--text-secondary);">{{ ingestProgress.message }}</div>
        <div v-if="ingestProgress.last_result && ingestProgress.active" style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">{{ ingestProgress.last_result }}</div>
        <div v-if="Object.keys(ingestProgress.per_character || {}).length" style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px;">
          <span v-for="(count, slug) in ingestProgress.per_character" :key="slug" style="padding: 3px 10px; background: var(--bg-primary); border-radius: 12px; font-size: 12px; font-weight: 500;">
            {{ slug }}: {{ count }}
          </span>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px;">
          <span v-if="ingestProgress.auto_approved" style="color: var(--status-success); font-weight: 500;">{{ ingestProgress.auto_approved }} auto-approved</span>
          <span v-if="ingestProgress.auto_approved && ingestProgress.verified_rejects"> · </span>
          <span v-if="ingestProgress.verified_rejects" style="color: var(--status-error);">{{ ingestProgress.verified_rejects }} rejected by quality gate</span>
          <span v-if="(ingestProgress.auto_approved || ingestProgress.verified_rejects) && ingestProgress.skipped"> · </span>
          <span v-if="ingestProgress.skipped">{{ ingestProgress.skipped }} no character</span>
          <span v-if="ingestProgress.skipped && ingestProgress.duplicates"> · </span>
          <span v-if="ingestProgress.duplicates">{{ ingestProgress.duplicates }} duplicates</span>
        </div>
        <!-- Synthesize Context button after completion -->
        <div v-if="ingestProgress.stage === 'complete'" style="margin-top: 10px; display: flex; gap: 8px;">
          <button class="btn" style="color: var(--accent-primary);" @click="synthesizeContext" :disabled="synthesizing">
            {{ synthesizing ? 'Synthesizing...' : 'Synthesize Context with Echo Brain' }}
          </button>
          <router-link v-if="ingestProgress.per_character" to="/review" class="btn" style="text-decoration: none;">
            Review in Review Tab
          </router-link>
        </div>
        <!-- Synthesis results -->
        <div v-if="synthesisResult" style="margin-top: 12px; padding: 12px; background: var(--bg-primary); border-radius: 4px; border: 1px solid var(--accent-primary);">
          <h5 style="font-size: 13px; font-weight: 600; color: var(--accent-primary); margin-bottom: 8px;">Source Analysis Synthesis</h5>
          <div v-if="synthesisResult.design_prompts" style="margin-bottom: 10px;">
            <span style="font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase;">Suggested Design Prompts:</span>
            <div v-for="(prompt, slug) in synthesisResult.design_prompts" :key="slug" style="margin-top: 4px; font-size: 12px; padding: 6px 8px; background: var(--bg-secondary); border-radius: 3px;">
              <strong>{{ slug }}:</strong> {{ prompt }}
            </div>
          </div>
          <div v-if="synthesisResult.style_preamble" style="margin-bottom: 10px;">
            <span style="font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase;">Suggested Style Preamble:</span>
            <div style="font-size: 12px; color: var(--accent-primary); padding: 6px 8px; background: var(--bg-secondary); border-radius: 3px; margin-top: 4px;">
              {{ synthesisResult.style_preamble }}
            </div>
          </div>
          <div v-if="synthesisResult.episode_themes?.length" style="margin-bottom: 10px;">
            <span style="font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase;">Episode Themes:</span>
            <div style="display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px;">
              <span v-for="theme in synthesisResult.episode_themes" :key="theme" style="padding: 2px 8px; background: var(--bg-secondary); border-radius: 10px; font-size: 11px;">{{ theme }}</span>
            </div>
          </div>
          <div v-if="synthesisResult.raw_response" style="font-size: 12px; white-space: pre-wrap; max-height: 300px; overflow-y: auto; color: var(--text-secondary);">
            {{ synthesisResult.raw_response }}
          </div>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px;">
        <!-- YouTube -->
        <div class="card">
          <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">YouTube Video</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
            {{ ingestTargetMode === 'project' ? 'Extract frames and distribute to ALL characters in the project.' : 'Paste a YouTube URL to extract frames from the video.' }}
          </p>
          <input v-model="youtubeUrl" type="url" placeholder="https://youtube.com/watch?v=..." style="width: 100%; padding: 6px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; margin-bottom: 8px;" />
          <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap;">
            <label style="font-size: 12px; color: var(--text-muted);">Max frames:</label>
            <input v-model.number="maxFrames" type="number" min="1" max="300" style="width: 70px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
            <label style="font-size: 12px; color: var(--text-muted);">FPS:</label>
            <input v-model.number="youtubeFps" type="number" min="0.5" max="10" step="0.5" style="width: 60px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
          </div>
          <button class="btn" style="width: 100%; color: var(--accent-primary);" @click="ingestYoutube" :disabled="!youtubeUrl || youtubeLoading || ingestProgress.active || (ingestTargetMode === 'character' && !ingestSelectedCharacter) || (ingestTargetMode === 'project' && !ingestSelectedProject)">
            {{ ingestProgress.active ? 'Ingestion running...' : ingestTargetMode === 'project' ? 'Extract to All Characters' : 'Extract Frames' }}
          </button>
        </div>

        <!-- Image Upload -->
        <div class="card">
          <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">Upload Image</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">Upload a single image directly to a character's dataset.</p>
          <div class="drop-zone" @drop.prevent="onImageDrop" @dragover.prevent @click="imageFileInput?.click()">
            <template v-if="imageFile">{{ imageFile.name }}</template>
            <template v-else>Drop an image here or click to browse</template>
          </div>
          <input ref="imageFileInput" type="file" accept="image/*" style="display: none;" @change="onImageSelect" />
          <button class="btn" style="width: 100%; margin-top: 8px; color: var(--accent-primary);" @click="ingestImage" :disabled="!imageFile || !ingestSelectedCharacter || imageLoading">
            {{ imageLoading ? 'Uploading...' : 'Upload' }}
          </button>
          <div v-if="imageResult" style="margin-top: 8px; font-size: 12px; color: var(--status-success);">Uploaded {{ imageResult.image }}. Check Approve tab.</div>
        </div>

        <!-- Video Upload -->
        <div class="card">
          <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">Video</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
            {{ ingestTargetMode === 'project' ? 'Extract frames from a video and distribute to all project characters.' : 'Upload a video or provide a server path to extract frames.' }}
          </p>
          <!-- Browser upload (small files) -->
          <div class="drop-zone" @drop.prevent="onVideoDrop" @dragover.prevent @click="videoFileInput?.click()">
            <template v-if="videoFile">{{ videoFile.name }}</template>
            <template v-else>Drop a video here or click to browse</template>
          </div>
          <input ref="videoFileInput" type="file" accept="video/*" style="display: none;" @change="onVideoSelect" />
          <!-- OR local path (large files already on server) -->
          <div style="margin-top: 8px; font-size: 11px; color: var(--text-muted); text-align: center;">— or server path for large files —</div>
          <input v-model="localVideoPath" type="text" placeholder="/home/patrick/Videos/movie.mp4" style="width: 100%; padding: 6px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; margin-top: 4px;" />
          <div style="display: flex; gap: 8px; align-items: center; margin-top: 8px;">
            <label style="font-size: 12px; color: var(--text-muted);">Max frames:</label>
            <input v-model.number="localVideoMaxFrames" type="number" min="1" max="500" style="width: 70px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
            <label style="font-size: 12px; color: var(--text-muted);">FPS:</label>
            <input v-model.number="videoFps" type="number" min="0.1" max="5" step="0.1" style="width: 70px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
          </div>
          <button
            class="btn"
            style="width: 100%; margin-top: 8px; color: var(--accent-primary);"
            @click="ingestVideoFile"
            :disabled="(!videoFile && !localVideoPath) || videoLoading || (ingestTargetMode === 'character' && !ingestSelectedCharacter) || (ingestTargetMode === 'project' && !ingestSelectedProject)"
          >
            {{ videoLoading ? 'Extracting frames...' : ingestTargetMode === 'project' ? 'Extract to All Characters' : 'Extract & Upload' }}
          </button>
          <div v-if="videoResult" style="margin-top: 8px; font-size: 12px; color: var(--status-success);">Extracted {{ videoResult.frames_extracted }} frames. Check Approve tab.</div>
        </div>

        <!-- ComfyUI Scan -->
        <div class="card">
          <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">Scan ComfyUI Output</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">Scan /opt/ComfyUI/output/ for new images and match them to characters.</p>
          <button class="btn" style="width: 100%; color: var(--accent-primary);" @click="scanComfyUI" :disabled="scanLoading">
            {{ scanLoading ? 'Scanning...' : 'Scan for New Images' }}
          </button>
          <div v-if="scanResult" style="margin-top: 8px; font-size: 12px;">
            <div style="color: var(--status-success);">{{ scanResult.new_images }} new images found</div>
            <div v-if="Object.keys(scanResult.matched).length > 0" style="margin-top: 4px; color: var(--text-secondary);">
              <div v-for="(count, slug) in scanResult.matched" :key="slug">{{ slug }}: {{ count }} images</div>
            </div>
          </div>
        </div>

        <!-- Movie Upload -->
        <div class="card" style="grid-column: span 2;">
          <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">Movie Upload</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
            Upload a full movie file (up to 4GB). Stored permanently for re-extraction with different params.
          </p>

          <!-- Step 1: Upload -->
          <div v-if="!movieUploaded" class="drop-zone" @drop.prevent="onMovieDrop" @dragover.prevent @click="movieFileInput?.click()" style="padding: 28px;">
            <template v-if="movieFile">
              {{ movieFile.name }} ({{ (movieFile.size / (1024 * 1024)).toFixed(0) }} MB)
            </template>
            <template v-else>Drop a movie file here or click to browse (.mp4, .mkv, .avi, .mov)</template>
          </div>
          <input ref="movieFileInput" type="file" accept="video/*,.mkv" style="display: none;" @change="onMovieSelect" />

          <!-- Upload progress -->
          <div v-if="movieUploading" style="margin-top: 10px;">
            <div style="display: flex; justify-content: space-between; font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">
              <span>Uploading {{ movieFile?.name }}...</span>
              <span>{{ movieUploadPct }}%</span>
            </div>
            <div style="width: 100%; height: 6px; background: var(--bg-primary); border-radius: 3px; overflow: hidden;">
              <div :style="{ width: movieUploadPct + '%', height: '100%', background: 'var(--accent-primary)', transition: 'width 0.3s ease' }"></div>
            </div>
          </div>

          <button
            v-if="movieFile && !movieUploaded"
            class="btn"
            style="width: 100%; margin-top: 8px; color: var(--accent-primary);"
            @click="uploadMovie"
            :disabled="movieUploading || !ingestSelectedProject"
          >
            {{ movieUploading ? 'Uploading...' : 'Upload Movie' }}
          </button>

          <!-- Step 2: Extract (after upload or from existing movies) -->
          <div v-if="movieUploaded || uploadedMovies.length > 0" style="margin-top: 12px; border-top: 1px solid var(--border-primary); padding-top: 12px;">
            <div style="font-size: 13px; font-weight: 500; margin-bottom: 8px;">Extract Frames</div>
            <select v-model="movieExtractPath" style="width: 100%; padding: 6px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; margin-bottom: 8px;">
              <option value="">Select a movie...</option>
              <option v-for="m in uploadedMovies" :key="m.path" :value="m.path">{{ m.filename }} ({{ m.size_mb }} MB)</option>
            </select>
            <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px;">
              <label style="font-size: 12px; color: var(--text-muted);">Max frames:</label>
              <input v-model.number="movieMaxFrames" type="number" min="50" max="2000" style="width: 80px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
            </div>
            <button
              class="btn"
              style="width: 100%; color: var(--accent-primary);"
              @click="extractMovie"
              :disabled="!movieExtractPath || !ingestSelectedProject || movieExtracting || ingestProgress.active"
            >
              {{ movieExtracting ? 'Starting extraction...' : ingestProgress.active ? 'Extraction running...' : 'Extract & Classify Frames' }}
            </button>
          </div>

          <!-- Success message -->
          <div v-if="movieUploadResult" style="margin-top: 8px; font-size: 12px; color: var(--status-success);">
            {{ movieUploadResult }}
          </div>
        </div>
      </div>

      <!-- Error display -->
      <div v-if="ingestError" class="card" style="margin-top: 16px; background: rgba(160,80,80,0.1); border-color: var(--status-error);">
        <p style="color: var(--status-error); font-size: 13px;">{{ ingestError }}</p>
        <button class="btn" @click="ingestError = ''" style="margin-top: 8px;">Dismiss</button>
      </div>
    </div>

    <!-- ========== CHARACTERS SUB-TAB ========== -->
    <template v-if="activeSubTab === 'characters'">

    <!-- New Character button -->
    <div v-if="!showNewCharForm" style="margin-bottom: 24px;">
      <button class="btn" style="white-space: nowrap; padding: 10px 20px; font-size: 14px; color: var(--accent-primary); border-color: var(--accent-primary);" @click="openNewCharForm">
        + New Character
      </button>
    </div>

    <!-- New Character Form (inline) -->
    <div v-if="showNewCharForm" class="card" style="margin-bottom: 24px; border-left: 3px solid var(--accent-primary);">
      <div style="font-size: 14px; font-weight: 500; margin-bottom: 12px;">New Character</div>
      <div style="display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 180px;">
          <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">Name *</label>
          <input v-model="newCharName" type="text" placeholder="Character name" style="width: 100%; padding: 6px 8px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
        </div>
        <div style="flex: 1; min-width: 200px;">
          <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">Project *</label>
          <select v-model="newCharProject" style="width: 100%; padding: 6px 8px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;">
            <option value="">Select project...</option>
            <option v-for="p in projectStore.projects" :key="p.id" :value="p.name">{{ p.name }}</option>
          </select>
        </div>
        <div style="flex: 2; min-width: 240px;">
          <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">Description (optional)</label>
          <input v-model="newCharDescription" type="text" placeholder="e.g., A dark-haired swordsman with a missing eye" style="width: 100%; padding: 6px 8px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
        </div>
      </div>
      <div style="margin-top: 10px;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
          <label style="font-size: 11px; color: var(--text-muted);">Design Prompt (optional)</label>
          <EchoAssistButton
            v-if="newCharProject"
            context-type="design_prompt"
            :context-payload="{
              project_name: newCharProject,
              character_name: newCharName,
              checkpoint_model: charactersStore.characters.find(c => c.project_name === newCharProject)?.checkpoint_model || undefined,
            }"
            :current-value="newCharDesignPrompt"
            compact
            @accept="newCharDesignPrompt = $event.suggestion"
          />
        </div>
        <textarea v-model="newCharDesignPrompt" rows="2" placeholder="1girl, silver hair, red eyes, dark armor, full body..." style="width: 100%; padding: 6px 8px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary);"></textarea>
      </div>
      <div style="display: flex; gap: 6px; margin-top: 10px;">
        <div style="display: flex; gap: 6px;">
          <button class="btn" style="color: var(--accent-primary); border-color: var(--accent-primary);" @click="createNewCharacter" :disabled="!newCharName.trim() || !newCharProject || creatingCharacter">
            {{ creatingCharacter ? 'Creating...' : 'Create' }}
          </button>
          <button class="btn" @click="showNewCharForm = false; newCharName = ''; newCharProject = ''; newCharDescription = ''; newCharDesignPrompt = ''">Cancel</button>
        </div>
      </div>
      <div v-if="newCharError" style="margin-top: 8px; font-size: 12px; color: var(--status-error);">{{ newCharError }}</div>
    </div>

    <!-- Filters -->
    <CharacterFilters
      :characters="charactersStore.characters"
      v-model:filter-project="filterProject"
      v-model:filter-character="filterCharacter"
      v-model:filter-model="filterModel"
      :loading="charactersStore.loading"
      @refresh="charactersStore.fetchCharacters()"
    />

    <!-- Loading -->
    <div v-if="charactersStore.loading" style="text-align: center; padding: 48px;">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
      <p style="color: var(--text-muted);">Loading characters...</p>
    </div>

    <!-- Error -->
    <div v-else-if="charactersStore.error" class="card" style="background: rgba(160,80,80,0.1); border-color: var(--status-error);">
      <p style="color: var(--status-error);">{{ charactersStore.error }}</p>
      <button class="btn" @click="charactersStore.clearError()" style="margin-top: 8px;">Dismiss</button>
    </div>

    <!-- Grouped by project -->
    <div v-else>
      <div v-for="(group, projectName) in projectGroups" :key="projectName" style="margin-bottom: 32px;">
        <!-- Project header -->
        <div style="margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border-primary);">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <h3 style="font-size: 17px; font-weight: 600;">{{ projectName }}</h3>
            <span style="font-size: 12px; color: var(--text-muted);">
              {{ group.characters.length }} characters
            </span>
          </div>
          <!-- Project generation settings -->
          <div v-if="group.style" style="display: flex; gap: 12px; margin-top: 6px; flex-wrap: wrap;">
            <span class="meta-tag">{{ group.style.default_style }}</span>
            <span class="meta-tag" style="color: var(--accent-primary);">{{ group.style.checkpoint_model }}</span>
            <span v-if="group.style.cfg_scale" class="meta-tag">CFG {{ group.style.cfg_scale }}</span>
            <span v-if="group.style.steps" class="meta-tag">{{ group.style.steps }} steps</span>
            <span v-if="group.style.resolution" class="meta-tag">{{ group.style.resolution }}</span>
          </div>
        </div>

        <!-- Characters grid within project -->
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px;">
          <CharacterCard
            v-for="character in group.characters"
            :key="character.slug"
            :character="character"
            :character-stats="stats(character.slug)"
            :min-training-images="MIN_TRAINING_IMAGES"
            :editing-slug="editingSlug"
            :edit-prompt-text="editPromptText"
            :saving-prompt="savingPrompt"
            :generating-slug="generatingSlug"
            :training-loading="trainingStore.loading"
            :dataset-images="getDatasetImages(character.slug)"
            :filter-model="filterModel"
            @start-edit="startEdit"
            @cancel-edit="cancelEdit"
            @save-prompt="onSavePrompt"
            @save-regenerate="onSaveRegenerate"
            @generate-more="generateMore"
            @open-detail="openDetailPanel"
          />
        </div>
      </div>
    </div>

    <!-- Empty -->
    <div v-if="!charactersStore.loading && charactersStore.characters.length === 0" style="text-align: center; padding: 48px;">
      <p style="color: var(--text-muted);">No characters found</p>
      <button class="btn" @click="charactersStore.fetchCharacters()" style="margin-top: 8px;">Refresh</button>
    </div>

    </template>

    <!-- ========== WORKBENCH SUB-TAB ========== -->
    <CreateTab v-if="activeSubTab === 'workbench'" />

    <!-- Character Detail Panel -->
    <CharacterDetailPanel
      v-if="detailCharacter"
      :character="detailCharacter"
      :dataset-images="getDatasetImages(detailCharacter.slug)"
      :character-stats="stats(detailCharacter.slug)"
      :min-training-images="MIN_TRAINING_IMAGES"
      @close="closeDetailPanel"
      @save-prompt="onSavePrompt"
      @generate-more="generateMore"
      @refresh="charactersStore.fetchCharacters()"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useCharactersStore } from '@/stores/characters'
import { useTrainingStore } from '@/stores/training'
import { useProjectStore } from '@/stores/project'
import { api } from '@/api/client'
import type { Character, DatasetImage } from '@/types'
import CharacterFilters from './characters/CharacterFilters.vue'
import CharacterCard from './characters/CharacterCard.vue'
import CharacterDetailPanel from './characters/CharacterDetailPanel.vue'
import EchoAssistButton from './EchoAssistButton.vue'
import CreateTab from './CreateTab.vue'

const props = withDefaults(defineProps<{
  hideSubTabs?: boolean
  initialSubTab?: 'characters' | 'ingest' | 'workbench'
}>(), {
  hideSubTabs: false,
  initialSubTab: 'characters',
})

const MIN_TRAINING_IMAGES = 100

const charactersStore = useCharactersStore()
const trainingStore = useTrainingStore()
const projectStore = useProjectStore()
const activeSubTab = ref<'characters' | 'ingest' | 'workbench'>(props.initialSubTab)
const filterProject = ref('')
const filterCharacter = ref('')
const filterModel = ref('')
const generatingSlug = ref<string | null>(null)
const editingSlug = ref<string | null>(null)
const editPromptText = ref('')
const savingPrompt = ref(false)
const trainingMessage = ref('')

// New character form state
const showNewCharForm = ref(false)
const newCharName = ref('')
const newCharProject = ref('')
const newCharDescription = ref('')
const newCharDesignPrompt = ref('')
const creatingCharacter = ref(false)
const newCharError = ref('')

// Detail panel state
const detailCharacter = ref<Character | null>(null)

// --- Ingest state ---
const ingestTargetMode = ref<'character' | 'project'>('project')
const ingestSelectedCharacter = ref('')
const ingestSelectedProject = ref('')
const ingestError = ref('')
const ingestProjects = ref<Array<{ id: number; name: string; default_style: string; character_count: number }>>([])
const youtubeUrl = ref('')
const maxFrames = ref(60)
const youtubeFps = ref(4)
const youtubeLoading = ref(false)
const youtubeResult = ref<{ frames_extracted: number; characters_seeded?: number } | null>(null)
const synthesizing = ref(false)
const synthesisResult = ref<Record<string, any> | null>(null)
const imageFile = ref<File | null>(null)
const imageFileInput = ref<HTMLInputElement | null>(null)
const imageLoading = ref(false)
const imageResult = ref<{ image: string } | null>(null)
const videoFile = ref<File | null>(null)
const videoFileInput = ref<HTMLInputElement | null>(null)
const videoFps = ref(0.5)
const videoLoading = ref(false)
const videoResult = ref<{ frames_extracted: number } | null>(null)
const localVideoPath = ref('')
const localVideoMaxFrames = ref(200)
const scanLoading = ref(false)
const scanResult = ref<{ new_images: number; matched: Record<string, number>; unmatched_count: number } | null>(null)
const ingestProgress = ref<Record<string, any>>({})
let progressPollTimer: ReturnType<typeof setInterval> | null = null

// Movie upload state
const movieFile = ref<File | null>(null)
const movieFileInput = ref<HTMLInputElement | null>(null)
const movieUploading = ref(false)
const movieUploadPct = ref(0)
const movieUploaded = ref(false)
const movieUploadResult = ref('')
const uploadedMovies = ref<Array<{ filename: string; path: string; size_mb: number }>>([])
const movieExtractPath = ref('')
const movieMaxFrames = ref(500)
const movieExtracting = ref(false)

function startProgressPolling() {
  stopProgressPolling()
  progressPollTimer = setInterval(async () => {
    try {
      const resp = await fetch('/api/training/ingest/progress')
      const data = await resp.json()
      ingestProgress.value = data
      // Auto-stop polling when job is done
      if (data.stage === 'complete' || data.stage === 'error') {
        if (data.stage === 'complete' && data.per_character) {
          youtubeResult.value = { frames_extracted: data.frame_total, characters_seeded: Object.keys(data.per_character).length }
        }
        // Keep showing result for 30s, then stop
        setTimeout(() => stopProgressPolling(), 30000)
      }
    } catch { /* ignore */ }
  }, 2000)
}

function stopProgressPolling() {
  if (progressPollTimer) {
    clearInterval(progressPollTimer)
    progressPollTimer = null
  }
}

onMounted(async () => {
  try {
    await projectStore.fetchProjects()
    ingestProjects.value = projectStore.projects
  } catch { /* ignore */ }
  // Load uploaded movies list
  await loadMoviesList()
  // Resume polling if an ingestion is already running (navigated away and back)
  try {
    const resp = await fetch('/api/training/ingest/progress')
    const data = await resp.json()
    if (data.active) {
      ingestProgress.value = data
      startProgressPolling()
    } else if (data.stage === 'complete' || data.stage === 'error') {
      ingestProgress.value = data
    }
  } catch { /* ignore */ }
})

onUnmounted(() => stopProgressPolling())

async function ingestYoutube() {
  youtubeLoading.value = true
  youtubeResult.value = null
  ingestError.value = ''
  try {
    if (ingestTargetMode.value === 'project') {
      await api.ingestYoutubeProject(youtubeUrl.value, ingestSelectedProject.value, maxFrames.value, youtubeFps.value)
    } else {
      await api.ingestYoutube(youtubeUrl.value, ingestSelectedCharacter.value, maxFrames.value, youtubeFps.value)
    }
    youtubeUrl.value = ''
    // POST returns immediately now -- polling handles the rest
    startProgressPolling()
  } catch (e: any) { ingestError.value = e.message || 'YouTube ingestion failed' }
  finally { youtubeLoading.value = false }
}

async function synthesizeContext() {
  if (!ingestSelectedProject.value) return
  synthesizing.value = true
  synthesisResult.value = null
  try {
    const result = await api.synthesizeContext(ingestSelectedProject.value)
    synthesisResult.value = result.synthesis || {}
  } catch (e: any) {
    ingestError.value = e.message || 'Context synthesis failed'
  } finally {
    synthesizing.value = false
  }
}

function onImageDrop(e: DragEvent) { const f = e.dataTransfer?.files[0]; if (f && f.type.startsWith('image/')) imageFile.value = f }
function onImageSelect(e: Event) { const f = (e.target as HTMLInputElement).files?.[0]; if (f) imageFile.value = f }
async function ingestImage() {
  if (!imageFile.value) return
  imageLoading.value = true; imageResult.value = null; ingestError.value = ''
  try { imageResult.value = await api.ingestImage(imageFile.value, ingestSelectedCharacter.value); imageFile.value = null }
  catch (e: any) { ingestError.value = e.message || 'Image upload failed' }
  finally { imageLoading.value = false }
}

function onVideoDrop(e: DragEvent) { const f = e.dataTransfer?.files[0]; if (f && f.type.startsWith('video/')) videoFile.value = f }
function onVideoSelect(e: Event) { const f = (e.target as HTMLInputElement).files?.[0]; if (f) videoFile.value = f }
async function ingestVideoFile() {
  if (!videoFile.value && !localVideoPath.value) return
  videoLoading.value = true; videoResult.value = null; ingestError.value = ''
  try {
    if (localVideoPath.value) {
      // Local server path — use local-video endpoint (supports project mode)
      const projectName = ingestTargetMode.value === 'project'
        ? ingestSelectedProject.value
        : charactersStore.characters.find(c => c.slug === ingestSelectedCharacter.value)?.project_name || ''
      videoResult.value = await api.ingestLocalVideo(
        localVideoPath.value, projectName, localVideoMaxFrames.value, videoFps.value
      )
      localVideoPath.value = ''
    } else if (videoFile.value) {
      // Browser upload — character mode only
      videoResult.value = await api.ingestVideo(videoFile.value, ingestSelectedCharacter.value, videoFps.value)
      videoFile.value = null
    }
  } catch (e: any) { ingestError.value = e.message || 'Video ingestion failed' }
  finally { videoLoading.value = false }
}

async function scanComfyUI() {
  scanLoading.value = true; scanResult.value = null; ingestError.value = ''
  try { scanResult.value = await api.scanComfyUI() }
  catch (e: any) { ingestError.value = e.message || 'ComfyUI scan failed' }
  finally { scanLoading.value = false }
}

function onMovieDrop(e: DragEvent) {
  const f = e.dataTransfer?.files[0]
  if (f) { movieFile.value = f; movieUploaded.value = false; movieUploadResult.value = '' }
}
function onMovieSelect(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) { movieFile.value = f; movieUploaded.value = false; movieUploadResult.value = '' }
}

async function uploadMovie() {
  if (!movieFile.value || !ingestSelectedProject.value) return
  movieUploading.value = true
  movieUploadPct.value = 0
  movieUploadResult.value = ''
  ingestError.value = ''
  try {
    const result = await api.uploadMovie(movieFile.value, ingestSelectedProject.value, (pct) => {
      movieUploadPct.value = pct
    })
    movieUploaded.value = true
    movieUploadResult.value = `Uploaded ${result.filename} (${result.size_mb} MB)`
    movieExtractPath.value = result.path
    // Refresh movies list
    await loadMoviesList()
  } catch (e: any) {
    ingestError.value = e.message || 'Movie upload failed'
  } finally {
    movieUploading.value = false
  }
}

async function extractMovie() {
  if (!movieExtractPath.value || !ingestSelectedProject.value) return
  movieExtracting.value = true
  ingestError.value = ''
  try {
    await api.extractMovie(movieExtractPath.value, ingestSelectedProject.value, movieMaxFrames.value)
    startProgressPolling()
  } catch (e: any) {
    ingestError.value = e.message || 'Movie extraction failed'
  } finally {
    movieExtracting.value = false
  }
}

async function loadMoviesList() {
  try {
    const result = await api.listMovies()
    uploadedMovies.value = result.movies
  } catch { /* ignore */ }
}

const approvedCount = computed(() => {
  let total = 0
  for (const images of charactersStore.datasets.values()) {
    total += images.filter(img => img.status === 'approved').length
  }
  return total
})

const readyCount = computed(() => {
  return charactersStore.characters.filter(c => stats(c.slug).canTrain).length
})

const needsMoreCount = computed(() => {
  return charactersStore.characters.filter(c => !stats(c.slug).canTrain && stats(c.slug).total > 0).length
})

interface ProjectGroup {
  characters: Character[]
  style: {
    default_style: string
    checkpoint_model: string
    cfg_scale: number | null
    steps: number | null
    resolution: string
  } | null
}

// Group characters by project, filtered by dropdowns
const projectGroups = computed(() => {
  const groups: Record<string, ProjectGroup> = {}
  for (const c of charactersStore.characters) {
    const proj = c.project_name || 'Unknown'
    if (filterProject.value && proj !== filterProject.value) continue
    if (filterCharacter.value && c.name !== filterCharacter.value) continue
    if (filterModel.value) {
      const hasModel = c.generation_checkpoints?.some(gc => gc.checkpoint === filterModel.value)
        || (!c.generation_checkpoints?.length && (c.checkpoint_model || 'unknown') === filterModel.value)
      if (!hasModel) continue
    }
    if (!groups[proj]) {
      groups[proj] = {
        characters: [],
        style: c.checkpoint_model ? {
          default_style: c.default_style,
          checkpoint_model: c.checkpoint_model,
          cfg_scale: c.cfg_scale,
          steps: c.steps,
          resolution: c.resolution,
        } : null,
      }
    }
    groups[proj].characters.push(c)
  }
  for (const group of Object.values(groups)) {
    group.characters.sort((a, b) => {
      const sa = stats(a.slug)
      const sb = stats(b.slug)
      if (sa.canTrain !== sb.canTrain) return sa.canTrain ? -1 : 1
      return sb.approved - sa.approved
    })
  }
  return groups
})

function stats(name: string) {
  const s = charactersStore.getCharacterStats(name)
  return { ...s, canTrain: s.approved >= MIN_TRAINING_IMAGES }
}

function startEdit(character: Character) {
  editingSlug.value = character.slug
  editPromptText.value = character.design_prompt || ''
}

function cancelEdit() {
  editingSlug.value = null
  editPromptText.value = ''
}

async function onSavePrompt(payload: { character: Character; text: string }) {
  if (!payload.text.trim()) return
  savingPrompt.value = true
  try {
    await api.updateCharacter(payload.character.slug, { design_prompt: payload.text.trim() })
    editingSlug.value = null
    await charactersStore.fetchCharacters()
  } catch (error) {
    console.error('Failed to update design prompt:', error)
  } finally {
    savingPrompt.value = false
  }
}

async function onSaveRegenerate(payload: { character: Character; text: string }) {
  if (!payload.text.trim()) return
  savingPrompt.value = true
  try {
    await api.updateCharacter(payload.character.slug, { design_prompt: payload.text.trim() })
    editingSlug.value = null
    const need = Math.max(1, MIN_TRAINING_IMAGES - stats(payload.character.slug).approved)
    await api.regenerate(payload.character.slug, need)
    await charactersStore.fetchCharacters()
  } catch (error) {
    console.error('Failed to save and regenerate:', error)
  } finally {
    savingPrompt.value = false
  }
}

async function generateMore(character: Character) {
  const slug = character.slug
  const need = MIN_TRAINING_IMAGES - stats(character.slug).approved
  if (need <= 0) return
  generatingSlug.value = slug
  try {
    await api.regenerate(slug, need)
  } catch (error) {
    console.error('Failed to generate:', error)
  } finally {
    setTimeout(() => { generatingSlug.value = null }, 2000)
  }
}

function getDatasetImages(slug: string): DatasetImage[] {
  return charactersStore.datasets.get(slug) || []
}

function openDetailPanel(character: Character) {
  detailCharacter.value = character
}

function closeDetailPanel() {
  detailCharacter.value = null
}

function openNewCharForm() {
  showNewCharForm.value = true
  newCharProject.value = filterProject.value || (projectStore.projects.length === 1 ? projectStore.projects[0].name : '')
}

async function createNewCharacter() {
  if (!newCharName.value.trim() || !newCharProject.value) return
  creatingCharacter.value = true
  newCharError.value = ''
  try {
    await api.createCharacter({
      name: newCharName.value.trim(),
      project_name: newCharProject.value,
      description: newCharDescription.value.trim() || undefined,
      design_prompt: newCharDesignPrompt.value.trim() || undefined,
    })
    showNewCharForm.value = false
    newCharName.value = ''
    newCharProject.value = ''
    newCharDescription.value = ''
    newCharDesignPrompt.value = ''
    await charactersStore.fetchCharacters()
  } catch (error: any) {
    newCharError.value = error.message || 'Failed to create character'
  } finally {
    creatingCharacter.value = false
  }
}

</script>

<style scoped>
.sub-tab {
  padding: 8px 20px;
  border: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-family: var(--font-primary);
  border-radius: 4px;
  transition: all 150ms ease;
}
.sub-tab:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.sub-tab-active {
  background: rgba(80, 120, 200, 0.15);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: 500;
}
.btn-active {
  background: rgba(80, 120, 200, 0.2) !important;
  border-color: var(--accent-primary) !important;
  color: var(--accent-primary) !important;
  font-weight: 500;
}
.drop-zone {
  border: 2px dashed var(--border-primary);
  border-radius: 4px;
  padding: 20px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  transition: border-color 150ms ease;
}
.drop-zone:hover {
  border-color: var(--accent-primary);
}
.meta-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
}
</style>
