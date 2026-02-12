# Tower Anime Production

Anime video production system with ComfyUI generation, LoRA character training, and Echo Brain AI integration.

## Services

| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| **LoRA Studio API** | 8401 | `https://<host>/api/lora/` | All anime production: generation, approval, training, gallery, Echo Brain |
| **LoRA Studio Frontend** | 443 | `https://<host>/lora-studio/` | 7-tab production UI |
| ComfyUI | 8188 | `http://<host>:8188` | Image/video generation backend |
| Echo Brain | 8309 | `http://<host>:8309` | AI memory & context (54,000+ vectors) |
| PostgreSQL | 5432 | - | Database (`anime_production`) |

> **Consolidation note (2026-02-12):** The standalone Anime Production API (port 8328) has been archived. All functionality is now in LoRA Studio. The `/anime/` route redirects to `/lora-studio/`.

## Quick Start

```bash
# Check service status
sudo systemctl status tower-lora-studio nginx

# Restart LoRA Studio
sudo systemctl restart tower-lora-studio

# View logs
journalctl -u tower-lora-studio -f

# Database
psql -h localhost -U patrick -d anime_production
```

API docs: `http://localhost:8401/docs`

## Architecture

```
User Browser (HTTPS :443)
    |
    nginx reverse proxy
    ├── /lora-studio/    → static dist (Vue.js frontend)
    ├── /api/lora/*      → proxy_pass http://127.0.0.1:8401 (LoRA Studio API)
    └── /anime/          → 301 redirect → /lora-studio/

LoRA Studio API (:8401)
    ├── Character management + SSOT design prompts
    ├── Dataset approval workflow (pending/approved/rejected)
    ├── ComfyUI generation (image + video) → :8188
    ├── Gallery browsing (ComfyUI output)
    ├── Training job management
    ├── Feedback loop (rejection → negative prompt refinement)
    ├── YouTube/video/image ingestion with llava classification
    ├── Echo Brain AI integration → :8309
    └── Database credentials from Vault

ComfyUI (:8188)
    ├── Stable Diffusion image generation
    ├── FramePack video generation
    └── Output → /opt/ComfyUI/output/
```

## Projects

5 active anime projects in the database:

| ID | Project | Status | Characters |
|----|---------|--------|------------|
| 24 | Tokyo Debt Desire | generating | Mei Kobayashi, Rina Suzuki, Yuki Tanaka, Takeshi Sato |
| 29 | Cyberpunk Goblin Slayer | generating | Goblin Slayer, Kai Nakamura, Hiroshi, Kai, Ryuu |
| 41 | Super Mario Galaxy Anime Adventure | planning | Mario, Luigi, Princess Peach, Bowser Jr., Rosalina, +8 more |
| 42 | CGS: Neon Shadows | active | 13 characters |
| 43 | Echo Chamber | active | Patrick, Claude, DeepSeek, Echo, Claude Code |

## Pipeline: ComfyUI → LoRA Studio

```
1. User triggers generation from LoRA Studio Generate tab
2. API builds ComfyUI workflow JSON (SSOT: project checkpoint, CFG, steps)
3. ComfyUI generates images → /opt/ComfyUI/output/
4. Gallery tab shows recent output
5. Ingestion (YouTube, upload, ComfyUI scan) → character datasets with llava classification
6. Approve tab: user approves/rejects with feedback loop
7. Rejections → negative prompt refinement → auto-regeneration
8. 10+ approved images → Start LoRA training
9. Trained LoRA → /opt/ComfyUI/models/loras/*.safetensors
```

## API Endpoints (`/api/lora/`)

### Characters & Datasets
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/lora/characters` | List characters with image counts and project info |
| POST | `/api/lora/characters` | Create character dataset |
| PATCH | `/api/lora/characters/{slug}` | Update design_prompt |
| GET | `/api/lora/dataset/{name}` | Get character's images |
| POST | `/api/lora/dataset/{name}/images` | Add image to dataset |
| GET | `/api/lora/dataset/{name}/image/{file}` | Serve image file |
| GET | `/api/lora/dataset/{name}/image/{file}/metadata` | Image generation metadata |

### Approval & Feedback
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/lora/approval/pending` | All pending approval images |
| POST | `/api/lora/approval/approve` | Approve/reject image (with feedback loop) |
| GET | `/api/lora/feedback/{slug}` | Rejection feedback analysis |
| DELETE | `/api/lora/feedback/{slug}` | Clear rejection feedback |

### Generation (ComfyUI)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/lora/generate/{slug}` | Generate image/video for character |
| GET | `/api/lora/generate/{prompt_id}/status` | Check generation progress |
| POST | `/api/lora/generate/clear-stuck` | Clear stuck ComfyUI jobs |
| POST | `/api/lora/regenerate/{slug}` | Manual regeneration with seed/prompt override |
| POST | `/api/lora/refine` | IPAdapter refinement from approved reference |

### Gallery
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/lora/gallery` | Recent images from ComfyUI output |
| GET | `/api/lora/gallery/image/{filename}` | Serve gallery image |

### Training
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/lora/training/jobs` | List training jobs |
| POST | `/api/lora/training/start` | Start LoRA training |
| GET | `/api/lora/training/jobs/{id}` | Job status |
| GET | `/api/lora/training/jobs/{id}/log` | Tail training log |

### Ingestion
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/lora/ingest/youtube` | YouTube frames → single character |
| POST | `/api/lora/ingest/youtube-project` | YouTube frames → all project characters (llava classified) |
| POST | `/api/lora/ingest/image` | Upload image with llava classification |
| POST | `/api/lora/ingest/video` | Upload video, extract + classify frames |
| POST | `/api/lora/ingest/scan-comfyui` | Scan ComfyUI output for new images |

### Echo Brain
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/lora/echo/status` | Echo Brain connection status |
| POST | `/api/lora/echo/chat` | Chat with Echo Brain (optional character context) |
| POST | `/api/lora/echo/enhance-prompt` | AI-enhanced prompt suggestions |

### Other
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/lora/health` | Health check |
| GET | `/api/lora/projects` | List projects with character counts |

## Frontend: LoRA Studio (`/lora-studio/`)

7-tab layout:

- **Ingest** — YouTube/video/image ingestion with single-character or project-wide modes
- **Approve** — Image grid for approve/reject with metadata, feedback categories, prompt editing
- **Characters** — Character list with dataset counts, project info, training readiness
- **Train** — LoRA training job management (start, monitor, download)
- **Generate** — ComfyUI generation with SSOT profiles (image/video)
- **Gallery** — Browse recent ComfyUI output
- **Echo Brain** — AI chat for character context and prompt enhancement

**Tech:** Vue 3 + TypeScript, Tailwind CSS, Pinia, Vite
**Source:** `training/lora-studio/src/`
**Build:** `training/lora-studio/dist/`

## Database

**Database:** `anime_production` on PostgreSQL (localhost:5432, user: patrick)

Key tables:

| Table | Purpose |
|-------|---------|
| `projects` | Anime projects with default_style |
| `characters` | Characters with design_prompt, project association |
| `generation_styles` | Checkpoint, CFG, steps, sampler per style |
| `production_jobs` | Generation job tracking |
| `generated_assets` | Cataloged output files |
| `lora_models` | Registered LoRA models |
| `lora_training_jobs` | Training job history |

## Hardware

Tower server (192.168.50.135):
- **GPU:** NVIDIA RTX 3060 12GB (ComfyUI/FramePack) + AMD RX 9070 XT (Echo Brain)
- **CPU:** AMD Ryzen 9 24-core
- **RAM:** 96GB DDR5
- **Storage:** 1TB NVMe

## Directory Structure

```
/opt/tower-anime-production/
├── training/lora-studio/         # THE anime production system
│   ├── src/
│   │   ├── dataset_approval_api.py   # FastAPI entry point (:8401)
│   │   ├── generate_training_images.py
│   │   ├── components/               # Vue.js components (7 tabs)
│   │   ├── api/client.ts             # Frontend API client
│   │   └── types/index.ts            # TypeScript interfaces
│   ├── tests/                        # pytest test suite
│   ├── datasets/                     # Character training datasets
│   ├── dist/                         # Built frontend (served by nginx)
│   └── venv/                         # Python virtualenv
├── api/                              # Archived reference (was port 8328)
├── frontend.archived/                # Archived anime frontend
├── services/                         # FramePack, generation services
├── workflows/comfyui/                # Workflow templates
├── archive/                          # Historical archives
└── docs/

/opt/ComfyUI/
├── output/                           # Generated images/videos
├── models/loras/                     # LoRA model files
└── models/checkpoints/               # Base SD models
```

## Development

```bash
# Rebuild LoRA Studio frontend
cd /opt/tower-anime-production/training/lora-studio && npm run build

# Run backend tests
cd /opt/tower-anime-production/training/lora-studio && venv/bin/python -m pytest tests/ -v

# Run frontend tests
cd /opt/tower-anime-production/training/lora-studio && npx vitest run

# Smoke test
curl -s http://localhost:8401/api/lora/health
```

## Systemd Service

```bash
# Service file
/etc/systemd/system/tower-lora-studio.service  # API on :8401

# Management
sudo systemctl {start|stop|restart|status} tower-lora-studio
sudo systemctl reload nginx
```
