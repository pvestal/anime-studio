# Anime Studio v3.3

End-to-end anime production pipeline: project management, character design, dataset approval, LoRA training, image/video generation, scene assembly, episode composition, and Jellyfin publishing.

**Stack**: FastAPI (Python) + Vue 3 (TypeScript) + PostgreSQL + ComfyUI + Qdrant + Ollama
**Port**: 8401 (systemd: `tower-anime-studio.service`)
**URL**: `http://192.168.50.135/anime-studio/`
**API**: 109 endpoints under `/api/lora/*`
**Entry**: `src/app.py` (modular router mounts)

## Tabs

| # | Tab | Purpose |
|---|-----|---------|
| 1 | **Project** | Create/select projects, configure checkpoint models, generation styles |
| 2 | **Story & World** | Storyline, world settings, art direction, cinematography, Echo Brain narration assist |
| 3 | **Characters** | Character roster, design prompts, YouTube/video/image ingestion |
| 4 | **Approve** | Human-in-the-loop image approval with Gemma3 auto-triage, species validation, replenishment loop controls |
| 5 | **Train** | Launch LoRA training jobs, monitor epochs/loss |
| 6 | **Generate** | Generate images (Stable Diffusion) or videos (FramePack I2V) per character |
| 7 | **Scenes** | Scene Builder + Episodes: compose multi-shot scenes with motion presets, dialogue, continuity chaining; assemble into episodes; publish to Jellyfin |
| 8 | **Gallery** | Browse generated outputs |
| — | **Echo Brain** | AI chat with project context, prompt enhancement |

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for system diagrams and data flow.

## Key Paths

| Path | Purpose |
|------|---------|
| `src/app.py` | FastAPI entry point — mounts all package routers |
| `packages/core/` | DB pool, auth middleware, config, GPU status, models, events, learning, replenishment |
| `packages/story/` | Story & world settings, project CRUD (15 routes) |
| `packages/visual_pipeline/` | Vision review, classification, ComfyUI workflows (5 routes) |
| `packages/scene_generation/` | Scene builder, FramePack/LTX-Video, progressive-gate generation, crossfade assembly, music gen, motion presets, story-to-scenes AI (21 routes) |
| `packages/episode_assembly/` | Episode CRUD, multi-scene assembly, Jellyfin publishing (10 routes) |
| `packages/lora_training/` | Training, ingestion, regeneration, feedback (32 routes) |
| `packages/audio_composition/` | Voice ingestion/transcription, ACE-Step music generation, music cache (8 routes) |
| `packages/echo_integration/` | Echo Brain chat, prompt enhancement (4 routes) |
| `src/components/` | Vue 3 tab components with sub-component directories |
| `src/api/` | TypeScript API client split by domain (base, story, training, visual, scenes, episodes, echo) |
| `src/generate_training_images.py` | Standalone generation script (per-character negatives, IP-Adapter) |
| `datasets/{slug}/images/` | Character training images |
| `datasets/{slug}/reference_images/` | IP-Adapter reference images per character |
| `datasets/{slug}/approval_status.json` | Per-character approval state |
| `output/scenes/` | Assembled scene videos |
| `output/episodes/` | Assembled episode videos |

## Database

PostgreSQL `anime_production` database. Key tables:

- `projects` - Project definitions with default generation style
- `generation_styles` - Checkpoint, CFG, steps, sampler, resolution
- `characters` - Character names, design prompts, appearance_data (species, key_colors, key_features, common_errors)
- `storylines` - Story metadata per project
- `world_settings` - Art direction, cinematography, color palettes, negative_prompt_guidance
- `scenes` - Scene metadata, generation status, output paths, dialogue audio
- `shots` - Individual shots within scenes, FramePack generation state, dialogue text/character
- `episodes` - Episode metadata, assembly status, Jellyfin publish path
- `episode_scenes` - Junction table linking scenes to episodes with position ordering

## SSOT Principle

All generation parameters are project-level (Single Source of Truth):
- Projects reference a `generation_style` (checkpoint, CFG, steps, sampler, resolution)
- Characters only store `design_prompt` and `appearance_data` - no per-character generation overrides
- The design prompt IS the main prompt; style templates add quality tags only
- Per-character negative prompts are built dynamically from `appearance_data.species` and `appearance_data.common_errors`

## Character Quality Pipeline

### Per-Character Negatives
Non-human characters (species containing "NOT human") automatically get negative prompt terms:
`human, human face, human skin, realistic person, humanoid body, human proportions`
Plus species-specific terms from `common_errors` (e.g., Luigi gets `letter M on cap, child, teenager`).

### IP-Adapter Reference Images
Each character's `datasets/{slug}/reference_images/` directory is checked during generation.
If references exist + IP-Adapter models are installed, reference conditioning is injected into the ComfyUI workflow (weight 0.7, end_at 0.85).

### Vision Review (Gemma3)
- Scores character_match, clarity, training_value (0-10), solo detection, completeness
- Feature checklist built from `appearance_data` (species, key_colors, key_features, common_errors)
- Species verification step for non-human characters (focused binary check)
- **Non-human characters never auto-approve** — always require manual review
- Auto-reject threshold: quality_score < 0.4
- Human characters auto-approve at quality_score >= 0.8 + solo

## Scene Builder

The Scene Builder (tab 7) enables multi-shot video scene composition:

1. **Define** scenes with metadata (location, time, weather, mood)
2. **Add shots** with source images, motion prompts (with preset library), shot types, camera angles, per-shot dialogue, and transition settings (dissolve/fade/wipe)
3. **Generate** shots via progressive quality gates — each shot is generated, quality-checked by vision AI, and retried up to 3x with loosening thresholds (0.6→0.45→0.3) and more steps per retry
4. **Chain** continuity: each shot's last frame becomes the next shot's first frame
5. **Assemble** completed shots with crossfade transitions (ffmpeg xfade filter, 0.3s dissolve overlap)
6. **Music**: auto-generates AI music from scene mood via ACE-Step (3.5B model, AMD GPU), or uses assigned Apple Music tracks
7. **Audio mixing**: dialogue WAVs (100%) + music (30% with fade) mixed into final scene video

Generation runs as a background async task with one-at-a-time ComfyUI queueing (no queue flooding). The monitor view polls status every 5 seconds.

### Motion Presets
6 shot types with curated motion prompts: `establishing`, `wide`, `medium`, `close-up`, `extreme_close-up`, `action`. Presets appear as clickable chips in the shot editor; selecting one populates the motion prompt textarea.

### Story-to-Scenes AI
`POST /scenes/generate-from-story` sends the project storyline + world settings + character list to Ollama (gemma3:12b) and returns structured scene breakdowns with suggested shots, locations, moods, and motion prompts. The frontend shows a "Generate Scenes from Story" button when no scenes exist.

## Episodes & Publishing

Episodes group scenes into ordered sequences for final video assembly:

1. **Create** episodes with number, title, description, story arc
2. **Add scenes** to episodes in position order (drag-and-drop reordering)
3. **Assemble** episode via ffmpeg concat of all scene videos
4. **Publish** to Jellyfin with proper naming convention:
   ```
   /mnt/1TB-storage/media/anime/{Project Name}/Season 01/S01E01 - {Title}.mp4
   ```
5. **Auto-scan** triggers Jellyfin library refresh via API

### Episode Endpoints
- `GET/POST /episodes` — list/create episodes per project
- `GET/PATCH/DELETE /episodes/{id}` — CRUD
- `POST/DELETE /episodes/{id}/scenes/{scene_id}` — add/remove scenes
- `PUT /episodes/{id}/reorder` — reorder scene positions
- `POST /episodes/{id}/assemble` — ffmpeg concat + thumbnail
- `GET /episodes/{id}/video` — serve assembled MP4
- `POST /episodes/{id}/publish` — Jellyfin publish with library scan

## Autonomy System

### EventBus
In-process async event emitter (`packages/core/events.py`) for cross-package coordination. Events: `image.approved`, `image.rejected`, `generation.submitted`, `generation.completed`, `feedback.recorded`, `regeneration.queued`.

### Learning System
SQL-based pattern analysis from generation history, rejections, and approvals. Learns success/failure patterns per character, suggests optimal params, detects quality drift.

### Replenishment Loop
Autonomous image generation to reach target approved counts per character (`packages/core/replenishment.py`). Off by default — enable via Approve tab toggle or `POST /api/lora/replenishment/toggle`.

**Flow**: `IMAGE_APPROVED → check count vs target → generate batch → copy to datasets → register pending → vision review → auto-approve/reject → learn → repeat if still below target → STOP at target`

**Safety mechanisms**:
| Guard | Default | Purpose |
|-------|---------|---------|
| Enable flag | OFF | Must explicitly enable |
| Cooldown | 60s/char | Prevents burst from simultaneous approvals |
| Daily limit | 10/char | Caps daily GPU usage |
| Consecutive rejects | 5 max | Stops if model can't generate well |
| Pending buffer | 3 max | Won't generate if review backlog exists |
| Max concurrent | 2 | Limits parallel GPU load |
| Batch size | 3/round | Small batches for faster feedback |

**Endpoints**:
- `GET /api/lora/replenishment/status` — loop status, active tasks, daily counts
- `POST /api/lora/replenishment/toggle?enabled=true` — enable/disable
- `POST /api/lora/replenishment/target?target=20&character_slug=luigi` — set target count
- `GET /api/lora/replenishment/readiness?project_name=...` — per-character progress

### Auto-Correction
7 fix strategies for rejected images (`packages/core/auto_correction.py`). Off by default. Strategies: fix_quality, fix_resolution, fix_blur, fix_brightness, fix_contrast, fix_appearance, fix_solo.

### Quality Gates
Configurable DB-stored thresholds for auto-approve (0.8), auto-reject (0.4), and scene shot minimum (0.4). Managed via `GET/PUT /api/lora/quality/gates`.

## Generation Pipeline

### Image Generation
Character design prompt + style template + per-character negatives -> ComfyUI checkpoint workflow (+ IP-Adapter if refs exist) -> output image -> vision review -> approval queue

### FramePack Video (I2V)
Source image + motion prompt -> FramePack model -> sampling (sections) -> VAE decode tiled -> MP4

### Scene Generation (Progressive Gates)
```
For each shot (ordered):
  1. First frame = previous shot's last frame (or source image for shot 1)
  2. Copy to ComfyUI/input/
  3. Build FramePack workflow (one at a time — no queue flooding)
  4. Submit to ComfyUI, poll until complete
  5. Extract last frame, quality-check via Ollama vision (score 0-1)
  6. If score < threshold: RETRY with new seed + more steps (up to 3 attempts)
     Gate 1: threshold=0.6, Gate 2: 0.45, Gate 3: 0.3
  7. Accept best result, chain last frame to next shot
After all shots:
  8. ffmpeg xfade crossfade between shots (dissolve/fade/wipe, 0.3s overlap)
  9. Build dialogue audio (TTS per shot, concat)
  10. Get music: ACE-Step generated > Apple Music preview > auto-generate from mood
  11. Mix: video + dialogue (100%) + music (30%) -> final scene video
```

### Episode Assembly
```
For each episode:
  1. Gather scene videos in position order
  2. ffmpeg concat demuxer -> episode video
  3. Extract thumbnail from first frame
  4. Optional: publish to Jellyfin (symlink + library scan)
```

## Development

```bash
# Frontend
cd /opt/tower-anime-production
npm install
npm run dev    # Dev server with HMR
npm run build  # Production build to dist/

# Backend
source venv/bin/activate
python -m uvicorn src.app:app --host 0.0.0.0 --port 8401  # Dev run

# Service
sudo systemctl restart tower-anime-studio
sudo systemctl status tower-anime-studio
journalctl -u tower-anime-studio -f
```

## Dependencies

### Python
FastAPI, asyncpg, uvicorn, hvac (Vault), Pillow, yt-dlp

### Node
Vue 3, TypeScript, Vite, Pinia, vue-router, Tailwind CSS

### External Services
- **ComfyUI** (port 8188) - Image/video generation engine (NVIDIA RTX 3060, 12GB)
- **ACE-Step** (port 8440) - AI music generation, 3.5B model (AMD RX 9070 XT, 16GB, ROCm 7.2)
- **Qdrant** (port 6333) - Vector database for Echo Brain
- **Echo Brain** (port 8309) - Memory/context API (AMD RX 9070 XT)
- **Ollama** (port 11434) - Gemma3 vision model for auto-triage and quality gates
- **PostgreSQL** - Database backend
- **Vault** - Database credential management
- **Jellyfin** (port 8096) - Media server for published episodes
