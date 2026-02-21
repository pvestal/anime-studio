# Anime Studio v3.3 Architecture

## System Overview

```mermaid
graph TB
    subgraph Browser
        UI[Vue 3 Frontend<br/>7 tabs + Echo Brain panel]
    end

    subgraph "Anime Studio (port 8401)"
        APP[src/app.py<br/>FastAPI entry point]

        subgraph "packages/"
            CORE[core/<br/>DB, auth, config, GPU]
            STORY[story/<br/>15 routes]
            VIS[visual_pipeline/<br/>5 routes]
            SCENE[scene_generation/<br/>21 routes]
            EPISODE[episode_assembly/<br/>10 routes]
            TRAIN[lora_training/<br/>32 routes]
            AUDIO[audio_composition/<br/>8 routes]
            ECHO_PKG[echo_integration/<br/>4 routes]
        end

        APP --> CORE
        APP --> STORY
        APP --> VIS
        APP --> SCENE
        APP --> EPISODE
        APP --> TRAIN
        APP --> AUDIO
        APP --> ECHO_PKG
    end

    subgraph "External Services"
        ComfyUI[ComfyUI<br/>port 8188<br/>NVIDIA RTX 3060]
        Ollama[Ollama<br/>port 11434<br/>Gemma3:12b]
        Echo[Echo Brain<br/>port 8309<br/>AMD RX 9070 XT]
        ACEStep[ACE-Step<br/>port 8440<br/>AMD RX 9070 XT]
        Jellyfin[Jellyfin<br/>port 8096<br/>media server]
        Qdrant[Qdrant<br/>port 6333<br/>54K+ vectors]
        PG[(PostgreSQL<br/>anime_production)]
        Vault[Vault<br/>DB credentials]
    end

    UI -->|REST API| APP
    UI -->|WebSocket| ComfyUI
    VIS --> ComfyUI
    VIS --> Ollama
    SCENE --> ComfyUI
    SCENE --> Ollama
    SCENE --> ACEStep
    AUDIO --> ACEStep
    EPISODE --> Jellyfin
    ECHO_PKG --> Echo
    CORE --> PG
    CORE --> Vault
    Echo --> Qdrant
```

## Package Structure

```
packages/
  core/               # Shared infrastructure + autonomy
    __init__.py
    auth.py           # JWT auth middleware (local bypass, external JWT)
    config.py         # Paths, URLs, model names
    db.py             # asyncpg pool, migrations, character cache
    gpu_router.py     # GPU/Ollama status endpoint
    models.py         # Pydantic request/response models
    events.py         # EventBus — async event emitter
    learning.py       # Pattern analysis from gen history/rejections/approvals
    audit.py          # Autonomy decision logging
    model_selector.py # Param recommendations, drift detection, learned negatives
    auto_correction.py # 7 fix strategies for rejected images
    replenishment.py  # Autonomous generation loop (target-based)

  story/              # 15 routes
    router.py         # Project CRUD, storyline, world settings, generation styles

  visual_pipeline/    # 5 routes
    router.py         # Vision review endpoint (Gemma3 auto-triage)
    classification.py # Character identification, confusable pair verification
    vision.py         # Image quality assessment, species verification, perceptual hash
    comfyui.py        # Workflow building, submission, progress tracking

  scene_generation/   # 21 routes
    router.py         # Scene/shot CRUD, generate, assemble, video serve, motion presets, story-to-scenes, music
    builder.py        # Progressive-gate generation, crossfade assembly, continuity chaining, audio mixing
    framepack.py      # FramePack workflow building, I2V pipeline, motion presets
    ltx_video.py      # LTX-Video 2B workflow building, native LoRA support
    story_to_scenes.py # AI scene breakdown from storyline (Ollama gemma3:12b)

  episode_assembly/   # 10 routes
    router.py         # Episode CRUD, scene linking, assemble, video serve, publish
    builder.py        # ffmpeg concat for multi-scene episodes, thumbnail extraction
    publish.py        # Jellyfin directory structure, symlinks, library scan

  lora_training/      # 32 routes
    router.py         # Dataset browsing, approval, gallery, checkpoints
    training_router.py # Training jobs, regeneration
    ingest_router.py  # Image/video upload, ComfyUI scan, IP-Adapter refine
    feedback.py       # Rejection feedback loop, negative prompt building

  audio_composition/  # 8 routes
    router.py         # Voice ingestion, transcription, ACE-Step music generation, music cache

  echo_integration/   # 4 routes
    router.py         # Echo Brain chat, prompt enhancement
```

## Database Schema (Key Tables)

```mermaid
erDiagram
    projects ||--o{ characters : has
    projects ||--o| generation_styles : "default_style"
    projects ||--o| storylines : has
    projects ||--o| world_settings : has
    projects ||--o{ scenes : has
    projects ||--o{ episodes : has

    scenes ||--o{ shots : contains
    episodes ||--o{ episode_scenes : contains
    scenes ||--o{ episode_scenes : "referenced by"

    projects {
        int id PK
        string name
        string description
        string genre
        string default_style FK
        string premise
        string content_rating
    }

    generation_styles {
        string style_name PK
        string checkpoint_model
        float cfg_scale
        int steps
        string sampler
        int width
        int height
        string positive_prompt_template
        string negative_prompt_template
    }

    characters {
        int id PK
        string name
        text design_prompt
        int project_id FK
        jsonb appearance_data
    }

    scenes {
        uuid id PK
        int project_id FK
        int scene_number
        string title
        text description
        string location
        string time_of_day
        string weather
        string mood
        string generation_status
        int target_duration_seconds
        float actual_duration_seconds
        string final_video_path
        int total_shots
        int completed_shots
        string generated_music_path
        string generated_music_task_id
    }

    shots {
        uuid id PK
        uuid scene_id FK
        int shot_number
        string shot_type
        string camera_angle
        float duration_seconds
        text motion_prompt
        string source_image_path
        string first_frame_path
        string last_frame_path
        string output_video_path
        string status
        int seed
        int steps
        bool use_f1
        float generation_time_seconds
        float quality_score
        text dialogue_text
        string dialogue_character_slug
        string transition_type
        float transition_duration
    }

    episodes {
        uuid id PK
        int project_id FK
        int episode_number
        string title
        text description
        string story_arc
        string status
        string final_video_path
        string thumbnail_path
        float actual_duration_seconds
    }

    episode_scenes {
        uuid episode_id FK
        uuid scene_id FK
        int position
        string transition
    }
```

## Character Quality Pipeline

```mermaid
graph TD
    subgraph "Generation"
        DB_CHAR[DB: appearance_data] --> NEG_BUILD[build_character_negatives]
        NEG_BUILD --> |"human, human face..."| NEG[Per-Character Negative Prompt]
        DB_STYLE[DB: generation_style] --> STYLE_NEG[Style Negative Template]
        STYLE_NEG --> COMBINED[Combined Negative Prompt]
        NEG --> COMBINED

        REF[reference_images/] --> IPA[IP-Adapter Injection<br/>weight 0.7]
        DESIGN[design_prompt] --> POS[Positive Prompt]

        POS --> COMFY[ComfyUI Generation]
        COMBINED --> COMFY
        IPA --> COMFY
    end

    subgraph "Vision Review (Gemma3)"
        COMFY --> IMG[Generated Image]
        IMG --> REVIEW[vision_review_image]
        DB_CHAR --> |species, key_colors,<br/>common_errors| CHECKLIST[build_feature_checklist]
        CHECKLIST --> REVIEW

        REVIEW --> SCORE{quality_score}
        SCORE --> |"< 0.4"| REJECT[Auto-Reject]
        SCORE --> |">= 0.8 + solo"| HUMAN_CHECK{Is species human?}
        SCORE --> |"0.4 - 0.8"| MANUAL[Manual Review]

        HUMAN_CHECK --> |Yes| APPROVE[Auto-Approve]
        HUMAN_CHECK --> |"No (NOT human)"| MANUAL
    end

    subgraph "Feedback Loop"
        REJECT --> FEEDBACK[feedback.json]
        FEEDBACK --> REGEN[Regenerate with<br/>additional negatives]
        REGEN --> COMFY
    end

    APPROVE --> TRAIN[LoRA Training]
    MANUAL --> |Human approval| TRAIN
```

## Replenishment Loop (Autonomous)

```mermaid
graph TD
    subgraph "EventBus Trigger"
        APPROVE_EVT[IMAGE_APPROVED Event] --> CHECK{Approved count<br/>< target?}
        CHECK --> |Yes| GUARDS{Safety checks:<br/>cooldown, daily limit,<br/>concurrent, pending buffer}
        CHECK --> |"No (at target)"| DONE[Stop]
        GUARDS --> |Pass| GEN[Generate batch<br/>3 images via<br/>generate_training_images.py]
        GUARDS --> |"Fail (rate limited)"| WAIT[Wait for next event]
    end

    subgraph "Autonomous Pipeline"
        GEN --> COMFY[ComfyUI Generation]
        COMFY --> COPY[Copy to datasets/slug/images/]
        COPY --> REGISTER[Register as pending<br/>in approval_status.json]
        REGISTER --> VISION[Vision Review<br/>Gemma3 auto-triage]
        VISION --> SCORE{quality_score}
        SCORE --> |">= 0.8 + solo"| AUTO_APPROVE[Auto-Approve]
        SCORE --> |"< 0.4"| AUTO_REJECT[Auto-Reject]
        SCORE --> |"0.4 - 0.8"| MANUAL_Q[Pending Manual Review]
    end

    subgraph "Learning & Loop"
        AUTO_APPROVE --> LEARN_S[Record success pattern]
        AUTO_REJECT --> LEARN_F[Record failure pattern]
        LEARN_S --> APPROVE_EVT
        LEARN_F --> |"5+ consecutive"| PAUSE[Pause character]
    end

    subgraph "Audit"
        GEN --> LOG[autonomy_decisions table]
        AUTO_APPROVE --> LOG
        AUTO_REJECT --> LOG
    end
```

## Species Verification

Non-human characters (species contains "NOT human") get additional safeguards:

1. **Per-character negative prompts**: `human, human face, human skin, realistic person` added automatically
2. **Species-specific negatives**: star-shaped creatures get `child, boy, girl, humanoid`; mushroom creatures get `human child, boy wearing hat`
3. **Species verification step**: Focused binary question about creature-specific visual traits (shell, scales, fur, etc.)
4. **Auto-approve blocked**: Non-human characters always require manual approval regardless of vision scores

Species checks defined for: turtle, koopa, dinosaur, star-shaped, mushroom, mouse, dragon.

## Scene Builder Pipeline (Progressive Gates)

```mermaid
sequenceDiagram
    participant User
    participant Frontend as Vue Frontend
    participant API as FastAPI
    participant DB as PostgreSQL
    participant ComfyUI
    participant Ollama as Ollama (Vision)
    participant ACEStep as ACE-Step (Music)

    User->>Frontend: Create scene + add shots
    Frontend->>API: POST /scenes (create)
    API->>DB: INSERT scene
    Frontend->>API: POST /scenes/{id}/shots (per shot)
    API->>DB: INSERT shots

    User->>Frontend: Click "Generate"
    Frontend->>API: POST /scenes/{id}/generate
    API->>DB: Set status = "generating"
    API-->>Frontend: {total_shots, estimated_minutes}

    Note over API: Background asyncio task

    loop For each shot (ordered)
        API->>DB: Set shot status = "generating"

        alt First shot
            API->>API: Copy source_image to ComfyUI/input/
        else Subsequent shots
            API->>API: Use previous shot's last_frame (continuity chain)
        end

        rect rgb(255, 245, 230)
            Note over API,Ollama: Progressive Quality Gates (up to 3 attempts)
            loop Attempt 1→3 (loosening threshold: 0.6→0.45→0.3)
                API->>ComfyUI: POST /prompt (FramePack workflow, +5 steps per retry)
                ComfyUI-->>API: {prompt_id}

                loop Poll every 5s
                    API->>ComfyUI: GET /history/{prompt_id}
                end

                ComfyUI-->>API: Completed + output video
                API->>API: ffmpeg extract last frame
                API->>Ollama: Vision quality check (1-10 score)
                Ollama-->>API: quality_score

                alt Score >= threshold
                    Note over API: PASS — accept shot
                else Score < threshold AND retries left
                    Note over API: RETRY with new seed + more steps
                else Score < threshold AND no retries
                    Note over API: ACCEPT BEST — use highest-scoring attempt
                end
            end
        end

        API->>DB: Set shot completed + quality_score + paths
    end

    rect rgb(230, 245, 255)
        Note over API: Scene Assembly
        API->>API: ffmpeg xfade crossfade between shots (dissolve/fade/wipe)
        API->>API: build_scene_dialogue (TTS per shot)
        API->>ACEStep: Auto-generate music from scene mood (if no track assigned)
        ACEStep-->>API: Generated WAV (30s, 48kHz stereo)
        API->>API: ffmpeg amix (video + dialogue 100% + music 30%)
    end

    API->>DB: Set scene completed + final_video_path + duration

    User->>Frontend: Play assembled video
    Frontend->>API: GET /scenes/{id}/video
    API-->>Frontend: MP4 FileResponse
```

## Frontend Component Tree

```mermaid
graph TD
    APP[App.vue<br/>nav + router-view] --> PROJ[ProjectTab]
    APP --> CHAR[CharactersTab]
    APP --> CREATE[CreateTab]
    APP --> REVIEW[ReviewTab]
    APP --> TRAIN_TAB[TrainingTab]
    APP --> SCENE[SceneBuilderTab]
    APP --> ANALYTICS[AnalyticsTab]
    APP --> ECHO_PANEL[EchoFloatingPanel]

    PROJ --> PROJ_SUB[project/<br/>NewProjectForm<br/>StorylineSection<br/>WorldSettingsPanel<br/>GenerationStylePanel]
    CHAR --> CHAR_SUB[characters/<br/>CharacterCard<br/>CharacterFilters<br/>DesignPromptEditor]
    REVIEW --> PEND_SUB[pending/<br/>ImageApprovalModal<br/>ImageCard<br/>ImageReassignModal<br/>PendingFilters<br/>ProjectCharacterGrid<br/>ReplenishmentPanel]
    TRAIN_TAB --> TRAIN_SUB[training/<br/>ConfirmDialog]
    SCENE --> SCENE_SUB[scenes/<br/>SceneLibraryView<br/>SceneEditorView<br/>GenerationMonitorView<br/>ImagePickerModal<br/>ShotDetailsPanel<br/>EpisodeView]

    REVIEW --> IDP[ImageDetailPanel]
```

## API Endpoint Groups

| Package | Prefix | Routes | Key Files |
|---------|--------|--------|-----------|
| story | `/projects`, `/storyline`, `/world-settings`, `/generation-styles` | 15 | router.py |
| visual_pipeline | `/approval/vision-review` | 5 | router.py, classification.py, vision.py, comfyui.py |
| scene_generation | `/scenes`, `/scenes/motion-presets`, `/scenes/generate-from-story`, `/scenes/{id}/generate-music`, `/scenes/{id}/attach-music` | 21 | router.py, builder.py, framepack.py, ltx_video.py, story_to_scenes.py |
| episode_assembly | `/episodes`, `/episodes/{id}/scenes`, `/episodes/{id}/assemble`, `/episodes/{id}/publish` | 10 | router.py, builder.py, publish.py |
| lora_training | `/dataset`, `/approval`, `/training`, `/gallery`, `/ingest`, `/feedback` | 32 | router.py, training_router.py, ingest_router.py, feedback.py |
| audio_composition | `/audio`, `/audio/ingest/voice`, `/audio/voice/*`, `/audio/generate-music`, `/audio/music/*` | 8 | router.py |
| echo_integration | `/echo` | 4 | router.py |
| app.py | `/health`, `/gpu/status`, `/events/stats`, `/learning/*`, `/recommend/*`, `/drift`, `/quality/*`, `/correction/*`, `/replenishment/*` | 14 | — |
| **Total** | | **109** | |

## Hardware

| GPU | Service | Purpose |
|-----|---------|---------|
| NVIDIA RTX 3060 12GB | ComfyUI, Ollama | Image/video generation (FramePack, LTX-Video), Gemma3 vision review |
| AMD RX 9070 XT 16GB | Echo Brain, ACE-Step | Embedding generation, AI music generation (ROCm 7.2) |

## Ingestion → Production Pipeline (End-to-End)

```mermaid
graph TD
    subgraph "INGESTION SOURCES"
        YT_IMG[YouTube → Frames<br/>POST /ingest/youtube-project]
        YT_AUD[YouTube → Voice<br/>POST /audio/ingest/voice]
        UPLOAD[Manual Upload<br/>POST /ingest/image]
        COMFY_SCAN[ComfyUI Scan<br/>POST /ingest/scan-comfyui]
        AI_GEN[AI Generation<br/>POST /visual/generate]
        MOVIE[Movie Upload<br/>POST /ingest/movie-upload]
    end

    subgraph "REGISTRATION"
        YT_IMG --> REG[Register to<br/>datasets/slug/images/]
        UPLOAD --> REG
        COMFY_SCAN --> REG
        AI_GEN --> REG
        MOVIE --> |extract frames| REG
        REG --> DEDUP[Dedup + classify]
        DEDUP --> PENDING[approval_status.json<br/>status: pending]
    end

    subgraph "QUALITY REVIEW"
        PENDING --> VISION[Vision Review<br/>Gemma3 auto-triage]
        VISION --> GATE{Quality Score}
        GATE --> |"≥ 0.65 + solo"| AUTO_APP[Auto-Approve]
        GATE --> |"< 0.4"| AUTO_REJ[Auto-Reject]
        GATE --> |"0.4 - 0.65"| MANUAL[Manual Review]
        AUTO_REJ --> FEEDBACK[feedback.json<br/>categories + negatives]
        FEEDBACK --> |regenerate| AI_GEN
    end

    subgraph "TRAINING"
        AUTO_APP --> APPROVED[Approved Dataset]
        MANUAL --> |human approve| APPROVED
        APPROVED --> LORA[LoRA Training<br/>POST /training/start]
    end

    subgraph "VOICE PIPELINE"
        YT_AUD --> SEGMENTS[Speech segments]
        SEGMENTS --> WHISPER[Whisper transcription]
        WHISPER --> VOICE_DATA[Voice samples<br/>+ transcriptions]
    end

    subgraph "SCENE PRODUCTION"
        APPROVED --> |source images| SHOTS[Scene Shots<br/>POST /scenes/{id}/shots]
        VOICE_DATA --> |dialogue| SHOTS
        SHOTS --> PROG_GEN[Progressive Gate Generation<br/>FramePack I2V]
        PROG_GEN --> |quality check + retry| PROG_GEN
        PROG_GEN --> XFADE[Crossfade Assembly<br/>ffmpeg xfade dissolve]
        XFADE --> AUDIO_MIX[Audio Mix<br/>dialogue + ACE-Step music]
    end

    subgraph "DISTRIBUTION"
        AUDIO_MIX --> SCENE_VIDEO[Scene MP4]
        SCENE_VIDEO --> EPISODE[Episode Assembly<br/>multi-scene concat]
        EPISODE --> JELLYFIN[Jellyfin Publish<br/>S01E01 naming]
    end
```

## Episode Assembly Pipeline

```mermaid
sequenceDiagram
    participant User
    participant Frontend as Vue Frontend
    participant API as Episode Router
    participant DB as PostgreSQL
    participant FFmpeg
    participant Jellyfin

    User->>Frontend: Create episode + add scenes
    Frontend->>API: POST /episodes
    API->>DB: INSERT episode

    loop Add scenes in order
        Frontend->>API: POST /episodes/{id}/scenes
        API->>DB: INSERT episode_scenes (position)
    end

    User->>Frontend: Click "Assemble"
    Frontend->>API: POST /episodes/{id}/assemble
    API->>DB: Query scene videos in position order
    API->>FFmpeg: concat demuxer (all scene MP4s)
    FFmpeg-->>API: episode_{id}.mp4
    API->>FFmpeg: Extract thumbnail (first frame)
    API->>DB: Update status=assembled, video_path, duration

    User->>Frontend: Click "Publish"
    Frontend->>API: POST /episodes/{id}/publish
    API->>API: Create Jellyfin directory structure
    API->>API: Symlink S01E01 - {Title}.mp4
    API->>Jellyfin: POST /Library/Refresh
    API->>DB: Update status=published
```

## Audio Mixing Pipeline

```mermaid
graph LR
    subgraph "Per Shot"
        DT[dialogue_text] --> TTS[Voice Synthesis<br/>per character]
    end

    subgraph "Music Source (priority order)"
        ACE[ACE-Step generated<br/>generated_music_path] --> MUSIC_SRC{Music<br/>available?}
        APPLE[Apple Music preview<br/>audio_preview_url] --> MUSIC_SRC
        AUTO[Auto-generate from<br/>scene mood via ACE-Step] --> MUSIC_SRC
    end

    subgraph "Per Scene"
        TTS --> CONCAT_D[Concat dialogue WAVs]
        MUSIC_SRC --> MUSIC_FILE[Music file<br/>WAV/M4A]
    end

    subgraph "Mix (ffmpeg amix)"
        VIDEO[Scene video<br/>with crossfade transitions] --> MIX[ffmpeg 3-input mix]
        CONCAT_D --> |100% volume| MIX
        MUSIC_FILE --> |30% volume<br/>fade in/out| MIX
        MIX --> FINAL[Final scene MP4<br/>with audio]
    end
```

## Voice Pipeline

```mermaid
graph TD
    subgraph "Ingestion"
        YT[YouTube URL] --> DL[yt-dlp download]
        DL --> EXTRACT[ffmpeg extract audio<br/>22050Hz mono WAV]
        EXTRACT --> FILTER[Bandpass filter<br/>200-3000Hz voice]
        FILTER --> SILENCE[ffmpeg silencedetect]
        SILENCE --> SEGMENTS[Speech segments<br/>segment_001.wav...]
    end

    subgraph "Processing"
        SEGMENTS --> WHISPER[Whisper transcription]
        WHISPER --> MATCH[Character name matching]
        MATCH --> META[extraction_meta.json<br/>transcriptions + character links]
    end

    subgraph "Usage in Scenes"
        META --> DIALOGUE[Shot dialogue_text]
        DIALOGUE --> SYNTH[Voice synthesis per character]
        SYNTH --> SCENE_MIX[Scene audio mix]
    end
```

## ACE-Step Music Generation

```mermaid
graph LR
    subgraph "Trigger"
        SCENE_MOOD[Scene mood<br/>tense/romantic/action...] --> CAPTION[Build music caption<br/>from MOOD_PROMPTS]
        MANUAL[Manual caption<br/>free-form text] --> CAPTION
    end

    subgraph "ACE-Step (port 8440, AMD GPU)"
        CAPTION --> SUBMIT[POST /generate<br/>task_id returned]
        SUBMIT --> GEN[3.5B model inference<br/>~20s for 30s audio]
        GEN --> OUTPUT[48kHz stereo WAV]
    end

    subgraph "Integration"
        OUTPUT --> CACHE[music_cache/]
        CACHE --> ATTACH[POST /scenes/{id}/attach-music]
        ATTACH --> DB_STORE[(scenes.generated_music_path)]
        DB_STORE --> ASSEMBLY[Scene assembly<br/>auto-picks during mix]
    end
```

## Key Design Decisions

- **Modular packages**: 6 domain packages under `packages/`, each with own router. Entry point `src/app.py` mounts all routers.
- **Auth middleware**: Local network bypass (192.168.x.x, 127.0.0.1), JWT required for external access via `X-Real-IP` header from nginx
- **Species-aware generation**: `appearance_data` in DB drives per-character negative prompts and vision review checklist
- **Non-human manual review**: Auto-approve disabled for non-human characters because vision models can't reliably distinguish stylized cartoon humans from non-human creatures
- **IP-Adapter integration**: Reference images automatically injected into ComfyUI workflow during generation
- **Background tasks**: Scene generation uses `asyncio.create_task()`, tracked in `_scene_generation_tasks` dict
- **Vault for credentials**: DB password loaded from HashiCorp Vault at startup, env var fallback
- **Character cache**: `_get_char_project_map()` cached 60 seconds to reduce DB queries
- **Ollama KEEP_ALIVE=5m**: Models auto-unload after 5 minutes to free GPU memory for ComfyUI generation
- **FramePack memory**: `gpu_memory_preservation=6.0` required for RTX 3060 (3.5 causes OOM)
- **FramePack + LoRA incompatibility**: FramePack uses HunyuanVideo architecture, NOT Stable Diffusion — SD-based character LoRAs cannot be injected into video generation
- **Progressive quality gates**: Shot generation retries up to 3x with loosening thresholds (0.6→0.45→0.3), +5 steps per retry, new seed each attempt, keeps best result
- **Crossfade transitions**: Shots joined via ffmpeg `xfade` filter (dissolve/fade/fadeblack/wipeleft, 0.3s default overlap) — requires re-encoding but produces seamless results. Falls back to hard-cut if xfade fails
- **ACE-Step music generation**: AI music (3.5B model) on AMD RX 9070 XT via ROCm 7.2 nightly. ~20s for 30s of 48kHz stereo WAV. Scene assembly auto-generates from mood if no track assigned
- **Dual GPU architecture**: NVIDIA RTX 3060 for ComfyUI (image/video gen), AMD RX 9070 XT for ACE-Step (music gen) + Echo Brain (embeddings). No GPU conflicts, parallel execution
- **Episode assembly**: ffmpeg concat demuxer (no re-encoding) for fast multi-scene joins
- **Jellyfin publishing**: Symlinks (not copies) to avoid doubling disk usage; S01E01 naming convention
- **Audio mixing**: Non-fatal — if TTS or music download fails, scene video is kept without audio
- **Story-to-scenes AI**: Uses Ollama gemma3:12b for scene breakdowns; structured JSON output with retry parsing
- **Motion presets**: Curated per shot type, served via API so frontend stays in sync without hardcoding
- **FastAPI route ordering**: Static paths (`/scenes/motion-presets`, `/scenes/generate-from-story`) must be registered BEFORE dynamic `{scene_id}` routes
