# Tower Anime Production System v2.0

## Overview

Progressive anime generation system with Echo Brain orchestration, moving from still images → animated loops → full video production. Built on ComfyUI (RTX 3060) with character consistency and quality gating.

## Current State (Per Dec 4, 2025 Status)

- **Generation Time**: 8-16 seconds per image ✅
- **Character Consistency**: 93% identity retention ✅  
- **Stress Test Pass Rate**: 83.3% (5/6 tests) ✅
- **Architecture**: FastAPI + PostgreSQL + Redis + ComfyUI

## Directory Structure

```
anime-system/
├── main.py                           # FastAPI application entry
├── migrations/
│   └── 001_character_consistency.sql # Database migrations
├── backend/
│   ├── models/
│   │   └── schemas.py                # Pydantic models
│   ├── routers/
│   │   └── anime.py                  # API endpoints
│   ├── services/
│   │   ├── character_consistency.py  # Face embedding & consistency
│   │   └── quality_metrics.py        # Quality gate evaluation
│   └── tests/
│       └── test_phases.py            # Phase gate test suites
├── echo-integration/
│   └── echo_client.py                # Echo Brain orchestrator client
└── comfyui-workflows/                # Workflow JSON files (add yours)
```

## Phase Implementation Roadmap

### Phase 1: Still Images (Weeks 1-3) - CURRENT
**Objective**: Reliable character generation with consistency anchors

| Task | Status | Success Metric |
|------|--------|----------------|
| Face embedding storage | To implement | ArcFace 512-dim vectors |
| Character attribute system | To implement | Prompt token management |
| Character variations | To implement | Outfit/expression modifiers |
| Quality metrics baseline | To implement | Face similarity >0.70 |
| Reproducibility tracking | To implement | Full param storage |

**Phase 1 Gate**: 80%+ of test generations pass quality thresholds

### Phase 2: Animation Loops (Weeks 4-7)
**Objective**: Smooth temporal animation while maintaining identity

| Task | Depends On | Success Metric |
|------|------------|----------------|
| AnimateDiff integration | Phase 1 gate | 16-frame loops |
| Temporal LPIPS evaluation | Phase 1 | Score <0.15 |
| Motion smoothness scoring | AnimateDiff | VBench >0.95 |
| Loop generation API | All above | Seamless loops |

**Phase 2 Gate**: Face similarity >0.70 across all frames + LPIPS <0.15

### Phase 3: Full Video (Weeks 8-12)
**Objective**: Complete scenes with multi-character support

| Task | Depends On | Success Metric |
|------|------------|----------------|
| Wan/CogVideoX integration | Phase 2 gate | 120+ frame videos |
| Multi-character consistency | Face embeddings | All chars >0.70 |
| Scene continuity scoring | DINO embeddings | Score >0.85 |
| Echo Brain full integration | All above | Orchestrated pipeline |

## API Endpoints Summary

### Character Consistency (New)
```
PUT  /api/anime/characters/{id}/embedding     # Store face embedding
POST /api/anime/characters/{id}/consistency-check  # Check image vs reference
PUT  /api/anime/characters/{id}/consistency   # Update consistency anchors
POST /api/anime/characters/{id}/attributes    # Add visual attribute
POST /api/anime/characters/{id}/variations    # Create variation
GET  /api/anime/characters/{id}/prompt        # Build full prompt
```

### Generation (Extended)
```
POST /api/anime/generate                      # Extended with quality options
POST /api/anime/jobs/{id}/reproduce           # Reproduce from stored params
GET  /api/anime/jobs/{id}/params              # Get generation parameters
```

### Quality Metrics (New)
```
POST /api/anime/quality/evaluate              # Evaluate output quality
GET  /api/anime/jobs/{id}/quality             # Get stored quality scores
POST /api/anime/quality/phase-gate/{phase}    # Evaluate phase gate
```

### Story Bible (New)
```
POST /api/anime/projects/{id}/story-bible     # Create story bible
GET  /api/anime/projects/{id}/story-bible     # Get story bible
PUT  /api/anime/projects/{id}/story-bible     # Update (auto-versions)
```

### Echo Brain (New)
```
POST /api/anime/echo/tasks                    # Handle Echo Brain dispatch
POST /api/anime/echo/webhook                  # Receive Echo callbacks
```

## Database Migrations

Run migrations against your existing PostgreSQL:

```bash
psql -h localhost -U anime -d anime_production -f migrations/001_character_consistency.sql
```

New tables created:
- `character_attributes` - Visual attribute tokens
- `character_variations` - Outfit/expression variations  
- `generation_params` - Full reproducibility storage
- `quality_scores` - Metric tracking
- `story_bibles` - Project style guides

## Dependencies to Add

```bash
# Face analysis
pip install insightface onnxruntime-gpu

# Quality metrics (optional, for full VBench)
pip install lpips torch torchvision

# Async PostgreSQL
pip install asyncpg

# HTTP client
pip install aiohttp
```

## Testing

Run phase tests:

```bash
# Phase 1 tests
python -m backend.tests.test_phases phase_1

# After Phase 1 gate passes
python -m backend.tests.test_phases phase_2

# After Phase 2 gate passes  
python -m backend.tests.test_phases phase_3
```

## Echo Brain Integration

Echo Brain (port 8309) serves as the orchestrator:

1. **Worker Registration**: Anime system registers as render worker on startup
2. **Task Dispatch**: Echo sends structured tasks via `/api/anime/echo/tasks`
3. **Quality Review**: Echo's quality agent reviews outputs and requests regeneration if needed
4. **Story Persistence**: Echo maintains story bible and character development state

### Echo Brain Task Types
- `generate_image` - Single image generation
- `generate_loop` - Animation loop
- `generate_video` - Full video production
- `character_design` - Interactive design session
- `scene_composition` - Multi-character staging
- `quality_review` - Output evaluation

## Hardware Considerations

Current setup (RTX 3060 12GB):
- Still images: 512x768 @ 8-16 seconds ✅
- AnimateDiff loops: 512x512 16 frames @ ~60 seconds
- Full video: May need VRAM optimizations (VAE tiling, GGUF quantization)

For your dual-GPU setup (RX 9070 XT + RTX 3060):
- Use NVIDIA for primary inference (CUDA ecosystem)
- AMD for secondary tasks or separate ComfyUI instance

## Integration with Existing Repos

This code is designed to extend your current anime system. Key integration points:

1. **Replace/extend your existing `generate` endpoint** with the new schema
2. **Add the new tables** via migration (non-breaking)
3. **Initialize services** in your startup code
4. **Configure Echo Brain URL** if Echo is already running

## Next Steps for Claude Code

1. Run database migration
2. Install InsightFace for face embeddings
3. Implement ComfyUI client integration in `_process_generation`
4. Run Phase 1 test suite
5. Iterate until 80%+ pass rate
6. Proceed to Phase 2

## Files to Review

- `backend/models/schemas.py` - All Pydantic models
- `backend/routers/anime.py` - All API endpoints
- `backend/services/character_consistency.py` - Face embedding logic
- `backend/services/quality_metrics.py` - Quality gate evaluation
- `backend/tests/test_phases.py` - Phase test suites
- `echo-integration/echo_client.py` - Echo Brain communication
