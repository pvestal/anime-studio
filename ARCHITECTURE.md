# Anime Studio v0.4.0 Architecture

## System Overview

```mermaid
graph TB
    subgraph Browser
        UI[Vue 3 Frontend<br/>6 tabs + Echo Brain panel]
    end

    subgraph "Anime Studio (port 8401)"
        APP[src/app.py<br/>FastAPI entry point]

        subgraph "packages/"
            CORE[core/<br/>DB, auth, config, GPU,<br/>model profiles]
            STORY[story/<br/>15 routes]
            VIS[visual_pipeline/<br/>5 routes]
            SCENE[scene_generation/<br/>23 routes]
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
        Ollama[Ollama<br/>port 11434<br/>AMD RX 9070 XT<br/>Gemma3:12b]
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
    model_profiles.py # Checkpoint-aware prompt translation + param defaults
    generation.py     # Model-aware image generation pipeline
    orchestrator.py   # Production pipeline coordinator (training → video → publish)
    orchestrator_router.py # Orchestrator API endpoints (8 routes)
    graph_sync.py     # Apache AGE graph sync (EventBus-driven)
    graph_queries.py  # Cypher query helpers
    graph_router.py   # Graph analytics endpoints (11 routes)

  story/              # 18 routes
    router.py         # Project CRUD, storyline, world settings, generation styles
    story_characters.py # Character CRUD, PATCH with bool/jsonb, archive/unarchive

  visual_pipeline/    # 5 routes
    router.py         # Vision review endpoint (Gemma3 auto-triage)
    classification.py # Character identification, confusable pair verification
    vision.py         # Image quality assessment, species verification, perceptual hash
    comfyui.py        # Workflow building, submission, progress tracking

  scene_generation/   # 23 routes
    router.py         # Scene/shot CRUD, generate, assemble, video serve, motion presets, story-to-scenes, music, Wan endpoints
    builder.py        # Progressive-gate generation, crossfade assembly, intra-scene + cross-scene continuity chaining, audio ducking, frame interpolation, video upscaling
    framepack.py      # FramePack workflow building, I2V pipeline, motion presets
    ltx_video.py      # LTX-Video 2B workflow building, native LoRA support
    wan_video.py      # Wan 2.1 T2V workflow, GGUF support, environment/establishing shots
    framepack_refine.py # FramePack vid2vid refinement for Wan output (V2V: Wan 480p → FramePack 544x704, optional HunyuanVideo LoRA)
    engine_selector.py # Auto engine selection: shot type + LoRA availability + blacklist → wan/ltx/framepack
    scene_crud.py     # Scene/shot CRUD, episode-aware generation, continuity frames API, manual engine override
    scene_review.py   # Shot review + engine blacklist management
    scene_audio.py    # Dialogue synthesis, music mixing, audio ducking
    scene_video_utils.py # Crossfade concat, frame interpolation, upscaling
    scene_comparison.py # Multi-engine video comparison
    video_qc.py       # QC loop with vision review, prompt refinement, progressive gates
    video_vision.py   # Video frame quality assessment via Ollama
    story_to_scenes.py # AI scene breakdown from storyline (Ollama gemma3:12b), episode-scoped prompts
    image_recommender.py # Approved image scoring for auto source-image assignment

  episode_assembly/   # 10 routes
    router.py         # Episode CRUD, scene linking, assemble, video serve, publish
    builder.py        # ffmpeg xfade crossfade for multi-scene episodes, thumbnail extraction
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
    projects ||--o{ character_continuity_frames : tracks

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
        string model_architecture "sd15 or sdxl override"
        string prompt_format "prose or booru_tags override"
    }

    characters {
        int id PK
        string name
        text design_prompt
        int project_id FK
        jsonb appearance_data
        bool archived "default false"
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
        int post_interpolate_fps "NULL or target fps"
        int post_upscale_factor "NULL or 2x"
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
        string video_engine "framepack|framepack_f1|ltx|wan"
        string lora_name "auto-set by engine selector"
        float lora_strength "default 0.8"
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
    subgraph "Generation (Model-Aware)"
        CKPT[checkpoint_model] --> PROFILE[get_model_profile<br/>architecture, prompt_format,<br/>quality tags, style hints]
        DB_CHAR[DB: appearance_data] --> NEG_BUILD[build_character_negatives]
        NEG_BUILD --> |"human, human face..."| NEG[Per-Character Negative Prompt]
        DB_STYLE[DB: generation_style] --> STYLE_NEG[Style Negative Template]
        STYLE_NEG --> COMBINED[Combined Negative Prompt]
        NEG --> COMBINED

        REF[reference_images/] --> IPA[IP-Adapter Injection<br/>weight 0.7<br/>gated by profile]
        DESIGN[design_prompt] --> TRANSLATE[translate_prompt<br/>strip style tags for booru,<br/>inject appearance_data]
        DB_CHAR --> |key_colors,<br/>key_features| TRANSLATE
        PROFILE --> TRANSLATE
        TRANSLATE --> POS[Positive Prompt]

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

        alt Same character as previous shot (intra-scene)
            API->>API: Use previous shot's last_frame
        else Different character — check cross-scene frame
            API->>DB: SELECT frame_path FROM character_continuity_frames
            alt Cross-scene frame exists
                API->>API: Use cross-scene continuity frame
            else No continuity frame
                API->>API: Use auto-assigned approved image
            end
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
        API->>DB: UPSERT character_continuity_frames<br/>(save last frame for cross-scene reuse)
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

## Cross-Scene Character Continuity

When a character appears in multiple shots or scenes, the system maintains visual
continuity by tracking the most recent generated frame per character.

```mermaid
graph TD
    subgraph "Scene 8: Takeshi's Morning Visit"
        S8_1[Shot 1: Yuki<br/>source: approved image] --> S8_1V[FramePack I2V<br/>→ video + last frame]
        S8_1V --> S8_1_SAVE["Save continuity frame<br/>character_continuity_frames<br/>(project_id, yuki_tanaka)"]
        S8_2[Shot 2: Yuki<br/>source: shot 1 last frame<br/>INTRA-SCENE CHAIN] --> S8_2V[FramePack I2V]
        S8_2V --> S8_2_SAVE["Update continuity frame<br/>(yuki_tanaka)"]
        S8_3[Shot 3: Takeshi<br/>source: approved image] --> S8_3V[FramePack I2V]
        S8_3V --> S8_3_SAVE["Save continuity frame<br/>(takeshi_sato)"]
        S8_4[Shot 4: Rina<br/>source: approved image] --> S8_4V[FramePack I2V]
        S8_4V --> S8_4_SAVE["Save continuity frame<br/>(rina_suzuki)"]
    end

    subgraph "Scene 9: Rina's Counter-Offer"
        S8_4_SAVE -.->|CROSS-SCENE CHAIN| S9_1[Shot 1: Rina<br/>source: scene 8 last frame]
        S8_2_SAVE -.->|CROSS-SCENE CHAIN| S9_2[Shot 2: Yuki<br/>source: scene 8 last frame]
        S8_3_SAVE -.->|CROSS-SCENE CHAIN| S9_3[Shot 3: Takeshi<br/>source: scene 8 last frame]
    end

    style S8_1_SAVE fill:#2d5,stroke:#1a3
    style S8_2_SAVE fill:#2d5,stroke:#1a3
    style S8_3_SAVE fill:#2d5,stroke:#1a3
    style S8_4_SAVE fill:#2d5,stroke:#1a3
```

### Source Image Priority

```mermaid
graph LR
    START[Shot needs<br/>source image] --> CHECK1{Same character<br/>as previous shot<br/>in this scene?}
    CHECK1 -->|Yes| P1["Priority 1<br/>INTRA-SCENE CHAIN<br/>prev shot's last frame"]
    CHECK1 -->|No| CHECK2{Cross-scene<br/>continuity frame<br/>exists?}
    CHECK2 -->|Yes| P2["Priority 2<br/>CROSS-SCENE CHAIN<br/>from character_continuity_frames"]
    CHECK2 -->|No| CHECK3{Auto-assigned<br/>source image?}
    CHECK3 -->|Yes| P3["Priority 3<br/>APPROVED IMAGE<br/>from approval pool"]
    CHECK3 -->|No| FAIL[FAIL<br/>no source available]

    style P1 fill:#2a5,stroke:#1a3
    style P2 fill:#28a,stroke:#159
    style P3 fill:#a72,stroke:#741
    style FAIL fill:#a22,stroke:#711
```

### Database

```mermaid
erDiagram
    character_continuity_frames {
        uuid id PK
        int project_id FK
        string character_slug
        uuid scene_id FK
        uuid shot_id FK
        string frame_path
        int scene_number
        int shot_number
        timestamp created_at
    }

    character_continuity_frames }o--|| projects : "one per char per project"
    character_continuity_frames }o--|| scenes : "source scene"
    character_continuity_frames }o--|| shots : "source shot"
```

## Episode-Aware Scene Generation

Scenes can now be generated per-episode, with AI continuity context from existing scenes.

```mermaid
sequenceDiagram
    participant User
    participant API as Scene CRUD
    participant Ollama as Ollama gemma3:12b
    participant DB as PostgreSQL

    User->>API: POST /scenes/generate-from-story<br/>?project_id=24&episode_id=UUID
    API->>DB: Fetch episode synopsis + characters + existing scenes
    API->>Ollama: Episode-scoped prompt<br/>(synopsis + cast + continuity context)
    Ollama-->>API: JSON scenes with shots + dialogue

    API->>DB: pg_advisory_xact_lock(project_id)
    API->>DB: INSERT scenes (atomic numbering)
    API->>DB: INSERT shots (with characters_present as slugs)
    API->>DB: INSERT episode_scenes (link to episode)
    API-->>User: {scenes: [...], episode_id: UUID}
```

### Name-to-Slug Resolution

AI returns character names ("Rina", "Takeshi") which must be resolved to DB slugs
(`rina_suzuki`, `takeshi_sato`) for source image auto-assignment.

```mermaid
graph LR
    AI[Ollama output:<br/>characters: Rina, Yuki] --> MAP{char_slug_map<br/>from DB}
    MAP -->|found| SLUG[rina_suzuki, yuki_tanaka]
    MAP -->|not found| FALLBACK["_name_to_slug(name)<br/>LOWER + REPLACE + REGEXP"]
    SLUG --> DB[shots.characters_present]
    FALLBACK --> DB
```

## Frontend Component Tree

```mermaid
graph TD
    APP[App.vue<br/>nav + router-view] --> STORY[StoryTab /story]
    APP --> CAST[CastTab /cast]
    APP --> SCRIPT[ScriptTab /script]
    APP --> PRODUCE[ProduceTab /produce]
    APP --> REVIEW[ReviewTab /review]
    APP --> PUBLISH[PublishTab /publish]
    APP --> ECHO_PANEL[EchoFloatingPanel]

    STORY --> PROJ_SUB[ProjectTab<br/>project carousel, storyline,<br/>world settings, generation style]
    CAST --> CAST_SUB[3 sub-tabs:<br/>Characters — CharactersTab<br/>Ingest — IngestTab<br/>Voice — VoiceTab]
    CAST_SUB --> CHAR_DETAIL[CharacterDetailPanel<br/>profile editor, test generation,<br/>ChipInput, KeyValueEditor]
    SCRIPT --> SCRIPT_SUB[2 sub-tabs:<br/>Scenes — SceneBuilderTab<br/>Screenplay — ScreenplayView]
    PRODUCE --> PRODUCE_SUB[3 sub-tabs:<br/>Status — ProductionStatusTab<br/>Training — TrainingTab<br/>Analytics — AnalyticsTab]
    PRODUCE_SUB --> STATUS[ProductionStatusTab<br/>GPU status, active jobs,<br/>per-project pipeline cards,<br/>model lineage warnings]
    REVIEW --> PEND_SUB[pending/<br/>ImageApprovalModal<br/>ImageCard, PendingFilters<br/>ProjectCharacterGrid]
    PUBLISH --> PUB_SUB[2 sub-tabs:<br/>Episodes — EpisodeView<br/>Library — PublishedLibrary]

    REVIEW --> IDP[ImageDetailPanel]
```

## API Endpoint Groups

| Package | Prefix | Routes | Key Files |
|---------|--------|--------|-----------|
| story | `/projects`, `/storyline`, `/world-settings`, `/generation-styles` | 15 | router.py |
| visual_pipeline | `/approval/vision-review` | 5 | router.py, classification.py, vision.py, comfyui.py |
| scene_generation | `/scenes`, `/scenes/motion-presets`, `/scenes/generate-from-story`, `/scenes/{id}/generate-music`, `/scenes/{id}/attach-music`, `/generate/wan`, `/generate/wan/models`, `/continuity-frames` | 25 | router.py, builder.py, framepack.py, ltx_video.py, wan_video.py, story_to_scenes.py, scene_crud.py |
| episode_assembly | `/episodes`, `/episodes/{id}/scenes`, `/episodes/{id}/assemble`, `/episodes/{id}/publish` | 10 | router.py, builder.py, publish.py |
| lora_training | `/dataset`, `/approval`, `/training`, `/gallery`, `/ingest`, `/feedback` | 32 | router.py, training_router.py, ingest_router.py, feedback.py |
| audio_composition | `/audio`, `/audio/ingest/voice`, `/audio/voice/*`, `/audio/generate-music`, `/audio/music/*` | 8 | router.py |
| echo_integration | `/echo` | 4 | router.py |
| core (orchestrator) | `/orchestrator/status`, `/orchestrator/toggle`, `/orchestrator/initialize`, `/orchestrator/pipeline/{id}`, `/orchestrator/summary/{id}`, `/orchestrator/tick`, `/orchestrator/override`, `/orchestrator/training-target` | 8 | orchestrator.py, orchestrator_router.py |
| core (graph) | `/graph/sync`, `/graph/stats`, `/graph/lineage/*`, `/graph/co-occurrence/*`, `/graph/drift/*`, `/graph/ranking/*`, `/graph/health`, `/graph/feedback/*`, `/graph/cross-project/*` | 11 | graph_sync.py, graph_queries.py, graph_router.py |
| app.py | `/health`, `/gpu/status`, `/events/stats`, `/learning/*`, `/recommend/*`, `/drift`, `/quality/*`, `/correction/*`, `/replenishment/*` | 14 | — |
| **Total** | | **150+** | |

## Hardware

| GPU | Service | Purpose |
|-----|---------|---------|
| NVIDIA RTX 3060 12GB | ComfyUI | Image/video generation (FramePack, FramePack F1, LTX-Video, Wan 2.1 T2V) |
| AMD RX 9070 XT 16GB | Ollama, Echo Brain, ACE-Step | Vision review (Gemma3, Vulkan), embedding generation, AI music generation (ROCm 7.2) |

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

    subgraph "Mix (ffmpeg sidechaincompress + amix)"
        VIDEO[Scene video<br/>with crossfade transitions] --> MIX[ffmpeg 3-input mix]
        CONCAT_D --> |100% volume| MIX
        MUSIC_FILE --> |30% volume, auto-ducked<br/>fade in/out| MIX
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

## Video Engine Pipeline (Wan → FramePack V2V Refinement)

Multi-character shots use Wan T2V for composition, then optionally refine through FramePack vid2vid for improved anatomy/detail before post-processing.

```mermaid
graph TD
    subgraph "Engine Selection (engine_selector.py)"
        SHOT[Shot metadata] --> ES{select_engine}
        ES -->|establishing / no chars| WAN_E[wan]
        ES -->|multi-character| WAN_MC[wan]
        ES -->|solo + LoRA| LTX[ltx]
        ES -->|solo + source image| FP[framepack I2V]
        ES -->|no source image| WAN_NS[wan]
    end

    subgraph "Wan T2V Generation"
        WAN_E & WAN_MC & WAN_NS --> WAN_GEN[Wan 2.1 T2V 1.3B GGUF<br/>480x720 @ 16fps<br/>~4.5 min/clip]
        WAN_GEN --> WAN_OUT[Raw Wan MP4<br/>480x720 16fps]
    end

    subgraph "FramePack V2V Refinement (framepack_refine.py)"
        WAN_OUT --> LOAD_VID[VHS_LoadVideoPath<br/>resize to 544x704 @ 30fps]
        LOAD_VID --> VAE_ENC_ALL[VAEEncodeTiled<br/>all frames → LATENT]
        LOAD_VID --> FRAME0[ImageFromBatch<br/>extract frame 0]
        FRAME0 --> VAE_ENC_F0[VAEEncode<br/>frame 0 → start_latent]
        FRAME0 --> CLIP_VIS[CLIPVisionEncode<br/>frame 0 → image_embeds]

        LORA_CHECK{Character LoRA<br/>exists?}
        LORA_CHECK -->|Yes| LORA_SEL[FramePackLoraSelect<br/>HunyuanVideo LoRA]
        LORA_CHECK -->|No| MODEL_LOAD
        LORA_SEL --> MODEL_LOAD[LoadFramePackModel<br/>fp8 HunyuanVideo DiT]

        MODEL_LOAD --> SAMPLER[FramePackSampler<br/>denoise_strength=0.4<br/>preserves 60% Wan layout<br/>~10-13 min]
        VAE_ENC_ALL -->|initial_samples| SAMPLER
        VAE_ENC_F0 -->|start_latent| SAMPLER
        CLIP_VIS -->|image_embeds| SAMPLER

        SAMPLER --> DECODE[VAEDecodeTiled<br/>refined frames]
        DECODE --> V2V_OUT[Refined MP4<br/>544x704 @ 30fps]
    end

    subgraph "Post-Processing (video_postprocess.py)"
        V2V_OUT --> RIFE[RIFE 4.7<br/>frame interpolation<br/>30fps → 32fps]
        RIFE --> ESRGAN[RealESRGAN x4 anime<br/>upscale → downscale to 2x]
        ESRGAN --> COLOR[Color Grade<br/>contrast + saturation 1.15]
        COLOR --> FINAL[Final MP4<br/>960x1440 @ 32fps]
    end

    subgraph "Fallback"
        WAN_OUT -->|V2V fails or OOMs| RIFE_RAW[Post-process raw Wan<br/>480→960 upscale]
        RIFE_RAW --> FINAL_RAW[Final MP4<br/>960x1440 @ 32fps<br/>lower detail]
    end

    style WAN_GEN fill:#f96,stroke:#c60
    style SAMPLER fill:#69f,stroke:#36c
    style FINAL fill:#6c6,stroke:#393
    style FINAL_RAW fill:#cc6,stroke:#993
```

### LoRA Naming Convention

Character HunyuanVideo LoRAs in `/opt/ComfyUI/models/loras/`:
- Primary: `{slug}_framepack_lora.safetensors`
- Fallback: `{slug}_framepack.safetensors`

Auto-detected by `builder.py` during V2V refinement. Training via musubi-tuner at `/opt/musubi-tuner/`.

### Timing Impact

| Step | Without V2V | With V2V |
|------|-------------|----------|
| Wan generation | ~4.5 min | ~4.5 min |
| FramePack V2V | — | ~10-13 min |
| Post-processing | ~2 min | ~2 min |
| **Total per Wan shot** | **~6.5 min** | **~19 min** |

### Files

| File | Purpose |
|------|---------|
| `packages/scene_generation/framepack_refine.py` | V2V workflow builder + async orchestrator |
| `packages/scene_generation/builder.py` | Inserts V2V step after Wan completion, before post-processing |
| `packages/scene_generation/engine_selector.py` | Unchanged — Wan still handles multi-char; V2V is a post-generation step |
| `packages/scene_generation/framepack.py` | Original FramePack I2V (solo shots from source images) |

## Key Design Decisions

- **Modular packages**: 7 domain packages under `packages/` (+ core), each with own router. Entry point `src/app.py` mounts all routers.
- **Auth middleware**: Local network bypass (192.168.x.x, 127.0.0.1), JWT required for external access via `X-Real-IP` header from nginx
- **Species-aware generation**: `appearance_data` in DB drives per-character negative prompts and vision review checklist
- **Non-human manual review**: Auto-approve disabled for non-human characters because vision models can't reliably distinguish stylized cartoon humans from non-human creatures
- **IP-Adapter integration**: Reference images automatically injected into ComfyUI workflow during generation
- **Background tasks**: Scene generation uses `asyncio.create_task()`, tracked in `_scene_generation_tasks` dict
- **Vault for credentials**: DB password loaded from HashiCorp Vault at startup, env var fallback
- **Character cache**: `_get_char_project_map()` cached 60 seconds to reduce DB queries
- **Ollama KEEP_ALIVE=5m**: Models auto-unload after 5 minutes to free GPU memory for ComfyUI generation
- **FramePack memory**: `gpu_memory_preservation=6.0` required for RTX 3060 (3.5 causes OOM)
- **FramePack + SD LoRA incompatibility**: FramePack uses HunyuanVideo architecture, NOT Stable Diffusion — SD-based character LoRAs cannot be injected into video generation
- **Wan → FramePack V2V refinement**: Multi-character Wan T2V output (480x720) is refined through FramePack vid2vid (544x704) at denoise_strength=0.4, preserving 60% of Wan's composition/motion while sharpening anatomy/detail. Character HunyuanVideo LoRAs (trained via musubi-tuner) optionally injected during refinement via `FramePackLoraSelect`. Graceful fallback: if V2V fails or OOMs, raw Wan output proceeds to post-processing. Adds ~13 min per Wan shot
- **Progressive quality gates**: Shot generation retries up to 3x with loosening thresholds (0.6→0.45→0.3), +5 steps per retry, new seed each attempt, keeps best result
- **Crossfade transitions**: Shots joined via ffmpeg `xfade` filter (dissolve/fade/fadeblack/wipeleft, 0.3s default overlap) — requires re-encoding but produces seamless results. Falls back to hard-cut if xfade fails
- **Audio ducking**: ffmpeg sidechaincompress replaces flat amix — music volume (30%) automatically dips to ~5% when dialogue present, threshold=0.02, ratio=6:1, attack=200ms, release=1000ms
- **Frame interpolation**: Optional per-scene post-processing via ffmpeg minterpolate (MCI/AOBMC/bidirectional). `scenes.post_interpolate_fps` column controls target fps (NULL=disabled, 60=30→60fps doubling)
- **Video upscaling**: Optional per-scene upscale via ffmpeg lanczos filter. `scenes.post_upscale_factor` column (NULL=disabled, 2=2x resolution). Capped at 1920x1080
- **Multi-engine video**: Per-shot `video_engine` column selects generation engine — FramePack (I2V, highest quality), FramePack F1 (faster I2V), LTX-Video (I2V+T2V, LoRA support), Wan 2.1 T2V (environment shots, no source image needed, GGUF for low VRAM)
- **ACE-Step music generation**: AI music (3.5B model) on AMD RX 9070 XT via ROCm 7.2 nightly. ~20s for 30s of 48kHz stereo WAV. Scene assembly auto-generates from mood if no track assigned
- **Model-aware generation**: `model_profiles.py` maps checkpoint filenames to structured profiles (architecture, prompt_format, quality tags, style stripping, vision hints). `translate_prompt()` adapts design_prompts at generation time — booru tag models get score_9 prefixes and style tag stripping, prose models keep prompts as-is. DB design_prompts never modified. Param cascade: `recommend_params()` (medium+ confidence) > DB `generation_styles` > model profile defaults
- **Dual GPU architecture**: NVIDIA RTX 3060 for ComfyUI (image/video gen), AMD RX 9070 XT for Ollama (Vulkan) + ACE-Step (music gen, ROCm) + Echo Brain (embeddings). No GPU conflicts, parallel execution
- **Episode assembly**: ffmpeg xfade crossfade between scenes (fadeblack default, 0.5s overlap) with fallback to hard-cut concat
- **Jellyfin publishing**: Symlinks (not copies) to avoid doubling disk usage; S01E01 naming convention
- **Audio mixing**: Non-fatal — if TTS or music download fails, scene video is kept without audio
- **Story-to-scenes AI**: Uses Ollama gemma3:12b for scene breakdowns; structured JSON output with retry parsing. Episode-scoped generation includes episode synopsis + cast + existing scene continuity context
- **Cross-scene continuity**: `character_continuity_frames` table tracks most recent generated frame per character per project. Source image priority: intra-scene chain > cross-scene frame > approved image pool. UPSERT on every shot completion, backfilled from already-completed shots on service restart
- **Episode-aware generation**: `generate-from-story` accepts optional `episode_id` — AI generates scenes scoped to that episode with awareness of existing scenes. New scenes auto-linked to episode via `episode_scenes` junction table. Atomic scene numbering via `pg_advisory_xact_lock(project_id)`
- **Character name resolution**: AI returns human-readable names ("Rina"), pipeline resolves to DB slugs (`rina_suzuki`) via DB lookup with `_name_to_slug()` fallback. Critical for source image auto-assignment
- **Motion presets**: Curated per shot type, served via API so frontend stays in sync without hardcoding
- **Model lineage tracking**: dataset-stats API returns `model_breakdown` per character (which checkpoint generated each approved image), `dominant_model`, and `is_mixed_models` flag. LoRA listing includes `checkpoint`, `final_loss`, `trained_epochs`. Frontend surfaces mixed-model warnings and LoRA/image model mismatches
- **Character archiving**: `archived` boolean column on characters table, filtered from `get_char_project_map()` core query. Archive/unarchive via API without deleting data
- **FastAPI route ordering**: Static paths (`/scenes/motion-presets`, `/scenes/generate-from-story`) must be registered BEFORE dynamic `{scene_id}` routes
