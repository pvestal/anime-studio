# Tower Anime Production API - Working Endpoints Documentation

## Service Status: ✅ FULLY OPERATIONAL
- **Port**: 8328
- **Database**: PostgreSQL `anime_production` (19 projects, 113+ jobs)
- **ComfyUI Integration**: ✅ Connected (port 8188)
- **Last Updated**: November 5, 2025

## Issues Fixed ✅
1. **Job Status Tracking 404s**: Fixed - endpoints now properly track both database job IDs and ComfyUI request IDs
2. **Project Creation**: Fixed - actually triggers generation using working ComfyUI workflows
3. **ComfyUI Integration**: Working - submits real workflows and tracks progress
4. **Database Storage**: Fixed - all parameters properly serialized as JSON strings
5. **Missing Routes**: Added `/api/anime-enhanced/health` and `/api/anime/status` for compatibility

## Core Working Endpoints

### Health Check Endpoints
```bash
# Basic health check
curl http://localhost:8328/api/anime/health
# Response: {"status":"healthy","service":"tower-anime-production"}

# Enhanced health check (for compatibility)
curl http://localhost:8328/api/anime-enhanced/health
# Response: {"status":"healthy","service":"tower-anime-production","enhanced":true}

# Comprehensive status
curl http://localhost:8328/api/anime/status
# Response includes database stats, ComfyUI connection, available endpoints
```

### Project Management
```bash
# Get all projects
curl http://localhost:8328/api/anime/projects

# Create new project
curl -X POST http://localhost:8328/api/anime/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "My Anime Project", "description": "Test project"}'
# Response: {"name":"My Anime Project","id":21,"status":"draft",...}

# Update project
curl -X PATCH http://localhost:8328/api/anime/projects/21 \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated description"}'

# Delete project
curl -X DELETE http://localhost:8328/api/anime/projects/21
```

### Video Generation Endpoints

#### 1. Direct Generation (Recommended)
```bash
curl -X POST http://localhost:8328/api/anime/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "cyberpunk detective walking in neon city",
    "character": "kai",
    "duration": 5,
    "style": "anime"
  }'
# Response: {"job_id":109,"comfyui_job_id":"uuid","status":"processing",...}
```

#### 2. Fast Segmented Generation
```bash
curl -X POST http://localhost:8328/api/anime/generate-fast \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "samurai battle scene",
    "character": "original",
    "duration": 3
  }'
# Response: {"job_id":113,"batch_id":"uuid","total_segments":3,"segment_tasks":[...],...}
```

#### 3. Project-Specific Generation
```bash
curl -X POST http://localhost:8328/api/anime/generate/project/20 \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "epic anime scene",
    "character": "kai",
    "duration": 5
  }'
# Response: {"request_id":"uuid","job_id":111,"status":"processing",...}
```

### Job Status Tracking ✅ FIXED

#### Track by Job ID
```bash
curl http://localhost:8328/api/anime/generation/111/status
# Response: {
#   "id": "111",
#   "job_id": 111,
#   "status": "processing",
#   "progress": 0.5,
#   "created_at": "2025-11-05T05:32:54.087480",
#   "quality_score": null,
#   "output_path": "/mnt/1TB-storage/ComfyUI/output/...",
#   "job_type": "video_generation"
# }
```

#### Track by ComfyUI Request ID
```bash
curl http://localhost:8328/api/anime/generation/3ba15105-024f-4212-9e42-9d6ba963ec4e/status
# Response includes real ComfyUI progress monitoring
```

#### Track Fast Generation (with segment status)
```bash
curl http://localhost:8328/api/anime/generation/113/status
# Response: {
#   "id": 113,
#   "status": "segments_queued",
#   "progress": 0.0,
#   "segments_completed": [],
#   "segments_failed": [],
#   "segments_processing": [1, 2],
#   "total_segments": 2,
#   "batch_id": "uuid",
#   "estimated_completion": "4 minutes"
# }
```

### Project Bible System
```bash
# Create project bible
curl -X POST http://localhost:8328/api/anime/projects/20/bible \
  -H "Content-Type: application/json" \
  -d '{
    "title": "My Anime Bible",
    "description": "Character and world definitions",
    "visual_style": {"theme": "cyberpunk"},
    "world_setting": {"era": "2077"}
  }'

# Add character to bible
curl -X POST http://localhost:8328/api/anime/projects/20/bible/characters \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Kai Nakamura",
    "description": "Cyberpunk detective",
    "visual_traits": {"hair": "black", "eyes": "augmented"},
    "personality_traits": {"determined": true}
  }'

# Get project bible
curl http://localhost:8328/api/anime/projects/20/bible

# Get characters
curl http://localhost:8328/api/anime/projects/20/bible/characters
```

### Available Models and Quality Presets
```bash
# Get available AI models (scans actual filesystem)
curl http://localhost:8328/api/anime/models
# Response includes model quality ratings, file sizes, recommendations

# Get quality presets
curl http://localhost:8328/api/anime/quality-presets
# Response includes ultra_production, current_workflow, fast_preview

# Update configuration
curl -X POST http://localhost:8328/api/anime/config \
  -H "Content-Type: application/json" \
  -d '{
    "model": "counterfeit_v3.safetensors",
    "quality_preset": "ultra_production"
  }'
```

## Generation Parameters

### Request Format
```json
{
  "prompt": "your anime scene description",
  "character": "original|kai|custom_character_name",
  "scene_type": "dialogue|action|emotional|epic",
  "duration": 3-10,
  "style": "anime|realistic|artistic",
  "type": "professional|personal|creative"
}
```

### Response Statuses
- `processing`: ComfyUI is generating
- `completed`: Generation finished successfully
- `failed`: Generation failed
- `segments_queued`: Fast generation segments submitted
- `merge_failed`: Segment merging failed

## Real ComfyUI Integration ✅

### Working Workflow
- **Model**: counterfeit_v3.safetensors (4.2GB)
- **Resolution**: 1024x1024
- **Frames**: 120 frames for 5-second videos
- **Context Window**: 24-frame chunks with 4-frame overlap
- **VAE**: Dedicated vae-ft-mse-840000-ema-pruned.safetensors
- **Sampling**: 40 steps, CFG 8.5, dpmpp_2m karras

### Output Location
- **Path**: `/mnt/1TB-storage/ComfyUI/output/`
- **Format**: MP4 (H.264, yuv420p, CRF 12)
- **Naming**: `animatediff_5sec_120frames_[timestamp].mp4`

## Database Schema ✅

### Tables
- `anime_projects`: Project metadata
- `production_jobs`: Job tracking with real status
- `project_bibles`: Character and world definitions
- `bible_characters`: Character definitions

### Job Types
- `video_generation`: Standard generation
- `fast_video_generation`: Segmented parallel generation
- `integrated_generation`: Pipeline with quality controls
- `professional_generation`: Character-enhanced generation
- `personal_generation`: Mood-based generation

## Error Handling ✅

### Common Issues Fixed
1. **404 on status check**: Now handles both job ID and ComfyUI request ID lookup
2. **Database serialization**: All parameters properly JSON-encoded
3. **Missing functions**: `generate_with_echo_service` replaced with working `generate_with_fixed_workflow`
4. **Compatibility routes**: Added `/api/anime-enhanced/*` endpoints

### Testing Commands
```bash
# Test health
curl http://localhost:8328/api/anime/health

# Test generation
curl -X POST http://localhost:8328/api/anime/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test", "duration": 3}'

# Test status tracking (use returned job_id)
curl http://localhost:8328/api/anime/generation/[job_id]/status

# Test fast generation
curl -X POST http://localhost:8328/api/anime/generate-fast \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test fast", "duration": 2}'
```

## Performance Metrics

### Generation Times
- **Standard**: 6-7 minutes for 5-second 1024x1024 video
- **Fast Segmented**: Parallel processing reduces total time
- **Database Operations**: Sub-second response times

### Resource Usage
- **NVIDIA RTX 3060**: 8-10GB VRAM during generation
- **Database**: PostgreSQL with 110+ jobs, optimized queries
- **Storage**: Videos ~13MB each (1024x1024 @ 24fps)

## Status: All Major Issues Resolved ✅

1. ✅ **Job status tracking works** - handles both ID types properly
2. ✅ **Project creation triggers generation** - uses working ComfyUI workflows
3. ✅ **ComfyUI integration functional** - real workflow submission and monitoring
4. ✅ **Database persistence working** - proper JSON serialization
5. ✅ **No more 404 errors** - all endpoints responding correctly
6. ✅ **Real progress tracking** - monitors actual ComfyUI queue and history

The Tower Anime Production API is now fully operational with working generation, status tracking, and database persistence.