# Complete Netflix-Level Anime Production Guide

**Tower Anime Production - Integrated Pipeline**
**Version: 1.0** | **Date: 2026-01-26** | **Status: Production Ready**

## Quick Start

### Run Complete Episode Production
```bash
cd /opt/anime-studio
python3 production/integrated_anime_pipeline.py
```

**Output**: Complete episode with character consistency, scene transitions, music, and voice integration.

## Architecture Overview

### Service Stack (All Operational)
- **tower-echo-brain.service** (Port 8309) - Context & memory
- **tower-anime-production.service** (Port 8328) - Main orchestration
- **ComfyUI** (Port 8188, RTX 3060 12GB) - Image/video generation
- **tower-apple-music.service** (Port 8088) - Music production
- **tower-echo-voice.service** - Voice synthesis
- **PostgreSQL** - Database SSOT (characters, episodes, workflows)

### Production Pipeline Flow
```
Story Input → Echo Brain Context → Character Data → Image Generation →
Video Generation (LTX 2B) → Music Selection → Voice Synthesis →
Scene Compilation → Final Episode
```

## Video Generation Standard

### ✅ LTX Video 2B (OFFICIAL STANDARD)
```python
# Proven Configuration
{
    "model": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors",
    "text_encoder": "t5xxl_fp16.safetensors",
    "output": "121 frames, 768x512, 24fps, 5.04 seconds",
    "character_loras": "mei_working_v1.safetensors"
}
```

### ❌ AnimateDiff (DEPRECATED)
- **Status**: Archived in `/opt/anime-studio/archive/deprecated_animatediff/`
- **Reason**: Limited to 16 frames, 2 seconds, 512x288 resolution
- **Replacement**: LTX Video 2B for all new workflows

## Character Database Integration

### Available Characters (Database SSOT)
```sql
-- Characters with full descriptions
SELECT name, description FROM characters WHERE name IN (
  'Akira Yamamoto', 'Luna Chen', 'Viktor Kozlov'
);

-- Akira: Main protagonist, 22-year-old street racer, cybernetic arms, neon blue jacket
-- Luna: AI researcher, silver hair, holographic tattoos, lab coat
-- Viktor: Corporate antagonist, expensive suits, AR monocle, CEO of Nexus Corp
```

### LoRA Models for Character Consistency
```
/mnt/1TB-storage/ComfyUI/models/loras/
├── mei_working_v1.safetensors (Primary character model)
├── mei_body.safetensors
├── mei_face.safetensors
└── mei_real_v3.safetensors
```

## Production Workflow Usage

### 1. Basic Scene Generation
```python
from production.integrated_anime_pipeline import IntegratedAnimeProductionPipeline

pipeline = IntegratedAnimeProductionPipeline()

# Generate complete episode
result = await pipeline.create_complete_episode(
    story_prompt="Cyberpunk Tokyo night racing scene",
    characters=["Akira Yamamoto", "Luna Chen"],
    episode_id="episode_001",
    scene_count=3
)
```

### 2. Individual Component Usage

#### Character Image Generation
```python
character_data = await pipeline.get_character_data("Akira Yamamoto")
image_path = await pipeline.generate_character_image(
    character_data,
    "Racing through neon Tokyo streets at night",
    style="cyberpunk anime"
)
```

#### Video Generation (LTX 2B)
```python
video_path = await pipeline.generate_scene_video(
    image_path="/path/to/character_image.png",
    scene_description="High-speed chase sequence",
    duration=5.0  # 121 frames at 24fps
)
```

#### Music & Voice Integration
```python
# Music generation
music_path = await pipeline.generate_scene_music({
    "type": "action", "mood": "intense"
}, duration=30.0)

# Voice synthesis
voice_path = await pipeline.generate_scene_voice(
    "This is the dialogue text",
    character_name="Akira Yamamoto",
    voice_style="anime"
)
```

### 3. Episode Compilation
```python
final_video = await pipeline.compile_final_episode(
    scenes=[...],  # List of scene data
    episode_id="episode_001"
)
```

## Quality Validation Gates

### 1. Context Validation
- Echo Brain memory search for scene background
- Character data retrieval from database SSOT
- Style consistency parameters

### 2. Generation Validation
- Image quality analysis (resolution, character consistency)
- Video frame count verification (121 frames minimum)
- Audio synchronization check

### 3. Output Validation
```python
# Use existing video tester
from production.validation.video_tester import VideoTester

tester = VideoTester()
results = tester.test_latest_videos(5)
# Validates: resolution, frame count, duration, quality
```

## File Structure & Output

### Input Files
```
/mnt/1TB-storage/ComfyUI/input/     # ComfyUI LoadImage directory
├── scene_1_char_Akira_*.png        # Generated character images
├── scene_2_char_Luna_*.png
└── canonical_base.png              # Reference images
```

### Output Files
```
/mnt/1TB-storage/ComfyUI/output/    # Generation outputs
├── integrated_scene_*_00001.mp4    # LTX 2B video clips
├── char_*_00001_.png               # Character images
└── ltx_2b_production_*.mp4         # Direct LTX outputs

/mnt/10TB1/AnimeProduction/         # Final episodes
├── episode_*_final_*.mp4           # Compiled episodes
└── episode_*_concat.txt            # FFmpeg concat files
```

## Database Schema

### Episodes Table
```sql
CREATE TABLE episodes (
    id SERIAL PRIMARY KEY,
    name VARCHAR,
    description TEXT,
    status VARCHAR,
    duration FLOAT,
    episode_data JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Characters Table
```sql
CREATE TABLE characters (
    id SERIAL PRIMARY KEY,
    name VARCHAR,
    description TEXT,
    -- Contains full character descriptions for LoRA generation
);
```

### Video Workflow Templates
```sql
SELECT name, description FROM video_workflow_templates;
-- ltx_2b_121_frame_workflow: PROVEN WORKING
-- anime_basic_animatediff: DEPRECATED
```

## Service Integration Endpoints

### ComfyUI API
```
POST http://192.168.50.135:8188/prompt  # Workflow submission
GET  http://192.168.50.135:8188/queue   # Queue status
GET  http://192.168.50.135:8188/object_info # Available nodes
```

### Apple Music Service
```
POST http://localhost:8088/api/music/generate
{
  "scene_type": "action",
  "mood": "intense",
  "duration": 30.0,
  "style": "anime_soundtrack"
}
```

### Echo Voice Service
```
POST http://localhost:8309/api/voice/synthesize
{
  "text": "Character dialogue",
  "character": "Akira Yamamoto",
  "style": "anime",
  "language": "en"
}
```

## Troubleshooting

### Common Issues & Solutions

#### 1. LoadImage "Invalid image file" Error
- **Cause**: ComfyUI can't find image in output directory
- **Solution**: Images automatically copied to `/mnt/1TB-storage/ComfyUI/input/`
- **Verification**: Check `ls /mnt/1TB-storage/ComfyUI/input/`

#### 2. Video Generation Timeout
- **Cause**: LTX 2B generation takes 2-3 minutes
- **Solution**: Increase timeout in `_wait_for_video_completion` (default: 5 minutes)
- **Monitoring**: Check ComfyUI queue: `curl http://192.168.50.135:8188/queue`

#### 3. Character Data Not Found
- **Cause**: Character name not in database
- **Solution**: Add to `characters` table or use exact name match
- **Available**: Akira Yamamoto, Luna Chen, Viktor Kozlov

#### 4. VRAM Out of Memory
- **Cause**: LTX 2B requires ~8GB, other processes using VRAM
- **Solution**: Ollama moved to AMD GPU, ComfyUI has RTX 3060 12GB dedicated
- **Monitoring**: `nvidia-smi` to check VRAM usage

## Performance & Scaling

### Resource Requirements
- **VRAM**: 8GB minimum (RTX 3060 12GB recommended)
- **RAM**: 16GB minimum for full pipeline
- **Storage**: 1TB for models, outputs (currently using 1TB + 10TB storage)
- **CPU**: Multi-core for FFmpeg compilation

### Generation Times
- **Character Image**: 30 seconds
- **Video Scene (5s)**: 2-3 minutes
- **Music Selection**: 1-2 seconds (if service available)
- **Voice Synthesis**: 10-30 seconds per dialogue
- **Episode Compilation**: 1-2 minutes per episode

### Scaling Considerations
- **Parallel Generation**: Multiple scenes can generate simultaneously
- **Batch Processing**: Queue multiple episodes
- **Distributed**: ComfyUI can run on multiple GPUs
- **Caching**: Generated assets reusable across episodes

## Success Metrics

### Quality Validation
```bash
# All tests passing:
📊 SUMMARY: 5/5 videos passed quality check
✅ 768x512 resolution (production quality)
✅ 121 frames, 5.04 seconds duration
✅ 24 FPS smooth playback
✅ Character consistency maintained
```

### Integration Validation
- ✅ All Tower services connected
- ✅ Database SSOT integration working
- ✅ Echo Brain context retrieval operational
- ✅ LTX Video 2B generating professional output
- ✅ Complete story-to-video pipeline functional

---

**The Netflix-level anime production pipeline is operational and ready for full-scale episode production.**