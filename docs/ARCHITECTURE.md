# Tower Anime Production - Architecture

## Overview

GPU-accelerated anime generation platform integrating ComfyUI, Echo Brain AI, and FramePack for movie-length video production.

## Directory Structure

```
tower-anime-production/
├── api/                          # FastAPI backend
│   ├── main.py                   # Entry point (port 8328)
│   ├── echo_brain/               # Echo Brain AI integration
│   │   ├── assist.py             # AI assistance
│   │   ├── routes.py             # API routes
│   │   └── workflow_orchestrator.py
│   ├── auth_middleware.py        # Authentication
│   ├── websocket_manager.py      # Real-time connections
│   └── websocket_endpoints.py    # WebSocket routes
├── services/                     # Business logic
│   ├── framepack/                # FramePack video generation
│   │   ├── echo_brain_memory.py  # State persistence
│   │   ├── scene_generator.py    # Segment chaining
│   │   └── quality_analyzer.py   # SSIM/optical flow
│   └── generation/               # Image generation
│       └── simple_generator.py   # ComfyUI integration
├── config/                       # Configuration
│   └── settings.py               # Environment-based config
├── database/                     # SQL schemas
│   ├── anime_schema.sql          # Core tables
│   ├── framepack_schema.sql      # FramePack tables (8 tables)
│   └── migrations/
├── frontend/                     # Vue.js 3 UI
│   └── src/
│       ├── components/
│       │   └── EchoBrainChat.vue
│       └── App.vue
├── workflows/                    # ComfyUI templates
│   └── comfyui/
├── tests/                        # Test suites
│   ├── unit/
│   └── integration/
└── docs/                         # Documentation
    └── archive/                  # Historical docs
```

## Core Components

### API Layer (`api/`)
- **main.py**: FastAPI app with endpoints for generation, status, health
- **echo_brain/**: Echo Brain AI integration for creative assistance
- **WebSocket**: Real-time progress updates during generation

### Services Layer (`services/`)
- **framepack/**: FramePack video generation with memory persistence
  - Maintains character/story/visual state across scenes
  - Quality feedback learning loop
  - Segment chaining via last-frame extraction
- **generation/**: Direct ComfyUI integration for images/video

### Database Layer (`database/`)
Core tables:
- `production_jobs` - Job tracking
- `anime_characters` - Character definitions
- `workflow_configs` - ComfyUI workflow templates

FramePack tables:
- `movie_projects`, `movie_episodes`, `movie_scenes`
- `generation_segments` - Per-segment tracking
- `character_scene_memory` - Character state per scene
- `story_state_memory` - Plot/tension per scene
- `visual_style_memory` - Lighting/camera per scene
- `generation_quality_feedback` - Learning data

## Data Flow

```
User Request
    ↓
API (main.py)
    ↓
Echo Brain (optional AI assistance)
    ↓
Services Layer
    ├── FramePack (video) → Scene Generator → Quality Analyzer
    └── Generation (image) → Simple Generator
    ↓
ComfyUI (localhost:8188)
    ↓
Output → /mnt/1TB-storage/ComfyUI/output/
```

## Integration Points

| Service | Port | Purpose |
|---------|------|---------|
| Anime API | 8328 | Main API |
| ComfyUI | 8188 | Generation backend |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Job queue |
| Echo Brain | 8309 | AI orchestration |

## Configuration

All config via environment variables with Tower server defaults:
- `DB_*` - Database connection
- `COMFYUI_*` - ComfyUI connection
- `API_*` - API server settings

See `config/settings.py` for full list.
