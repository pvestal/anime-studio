# Architecture

## System Overview

Tower Anime Production is a single-service system for generating anime images and videos, managing character training datasets, and LoRA training. It runs on a single server (192.168.50.135) with two GPUs, managed by systemd and fronted by nginx.

## Network Topology

```
Internet / LAN
    │
    ▼
nginx (HTTPS :443)
    ├── /lora-studio/        → /opt/.../training/lora-studio/dist/          [Vue.js SPA]
    ├── /api/lora/*          → proxy_pass http://127.0.0.1:8401             [FastAPI]
    └── /anime/              → 301 redirect → /lora-studio/
```

> The `/anime/` frontend and `/api/anime/*` proxy were removed 2026-02-12. The standalone Anime Production API (port 8328) has been archived. All functionality consolidated into LoRA Studio.

## Services

### LoRA Studio API (:8401)

**Entry point:** `/opt/tower-anime-production/training/lora-studio/src/dataset_approval_api.py`
**Service:** `tower-lora-studio.service`
**Venv:** `/opt/tower-anime-production/training/lora-studio/venv/`

Responsibilities:
- Character management with SSOT design prompts from DB
- Dataset image approval workflow (pending/approved/rejected)
- ComfyUI generation (image + video) with project-level settings
- Gallery browsing of ComfyUI output
- Training job management and LoRA training
- Feedback loop: structured rejection categories → negative prompt refinement
- Multi-source ingestion: YouTube, video upload, image upload, ComfyUI scan
- Llava vision classification for automatic character detection
- IPAdapter refinement from approved references
- Echo Brain AI integration for context and prompt enhancement

Database credentials loaded from HashiCorp Vault at startup.

### ComfyUI (:8188)

**Location:** `/opt/ComfyUI/`
**GPU:** NVIDIA RTX 3060 12GB

The generation backend. Receives workflow JSON via its API, runs Stable Diffusion or FramePack, writes output to `/opt/ComfyUI/output/`.

### Echo Brain (:8309)

**Location:** `/opt/tower-echo-brain/`
**GPU:** AMD RX 9070 XT

AI memory system with 54,000+ vectors. Provides semantic search over project history, conversation context, and structured facts via MCP protocol.

### PostgreSQL (:5432)

**Database:** `anime_production`
**User:** patrick

Key tables: projects, characters, generation_styles, production_jobs, generated_assets, lora_models, lora_training_jobs.

### HashiCorp Vault (:8200)

Stores database credentials and API keys. LoRA Studio loads credentials from Vault at startup via the `hvac` Python client.

## Data Flow

### Generation Pipeline

```
User selects character + params in Generate tab
    │
    ▼
LoRA Studio API builds ComfyUI workflow JSON
(SSOT: checkpoint, CFG, steps, sampler from project's generation_style)
    │
    ▼
Submits to ComfyUI via HTTP (:8188/prompt)
    │
    ▼
ComfyUI generates image/video → /opt/ComfyUI/output/
    │
    ▼
Gallery tab shows output, or ingestion copies to character datasets
```

### Training Pipeline

```
Ingestion (YouTube, upload, ComfyUI scan)
    │  llava classification identifies characters
    ▼
Character datasets: training/lora-studio/datasets/{slug}/images/
    │
    ▼  (LoRA Studio API scans directories)
    │
Pending Approval queue (Approve tab)
    │
    ▼  (User approves/rejects with structured feedback)
    │
Rejection → feedback loop → negative prompt additions → auto-regeneration
    │
    ▼  (10+ approved images)
    │
POST /api/lora/training/start → train_lora.py subprocess
    │
    ▼
LoRA .safetensors → /opt/ComfyUI/models/loras/
```

## Frontend Architecture

### LoRA Studio

**Source:** `/opt/tower-anime-production/training/lora-studio/src/`
**Framework:** Vue 3 + TypeScript + Tailwind CSS + Pinia
**Build output:** `/opt/tower-anime-production/training/lora-studio/dist/`
**Served at:** `/lora-studio/`

7-tab layout:
- `IngestTab.vue` — Multi-source ingestion with project-wide YouTube support
- `PendingTab.vue` — Approval queue with metadata, feedback categories, prompt editing
- `CharactersTab.vue` — Dataset overview with project info and training readiness
- `TrainingTab.vue` — Job monitoring and model download
- `GenerateTab.vue` — ComfyUI generation with SSOT character profiles
- `GalleryTab.vue` — Browse and manage ComfyUI output
- `EchoBrainTab.vue` — AI chat for character context and prompt enhancement

API client: `src/api/client.ts`
TypeScript interfaces: `src/types/index.ts`
Pinia stores: `src/stores/`

## File System Layout

```
/opt/tower-anime-production/          # Main project
    training/lora-studio/             # THE production system
        src/dataset_approval_api.py   # API server (:8401)
        src/generate_training_images.py
        src/components/               # Vue.js tab components
        src/api/client.ts             # Frontend API client
        src/types/index.ts            # TypeScript interfaces
        tests/                        # pytest test suite
        datasets/                     # Character training datasets
        dist/                         # Built frontend
        venv/                         # Python virtualenv
    api/                              # Archived reference (was port 8328)
    frontend.archived/                # Archived anime frontend (was /anime/)
    services/framepack/               # FramePack video generation
    services/generation/              # ComfyUI integration helpers
    workflows/comfyui/                # Workflow templates
    docs/                             # Documentation

/opt/ComfyUI/
    output/                           # Generated images/videos
    models/loras/                     # Trained LoRA files
    models/checkpoints/               # Base SD models

/etc/systemd/system/
    tower-lora-studio.service         # LoRA Studio API on :8401

/etc/nginx/sites-enabled/
    tower-https                       # HTTPS reverse proxy config
```

## Archived Services

- **Anime Production API (port 8328)** — Stopped and disabled 2026-02-12. Source kept at `api/` for reference.
- **Anime Director Studio frontend** — Archived to `frontend.archived/` on 2026-02-12. Was served at `/anime/`, now 301 redirects to `/lora-studio/`.
