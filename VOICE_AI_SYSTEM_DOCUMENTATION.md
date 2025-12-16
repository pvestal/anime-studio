# Voice AI System Documentation
## Complete Voice Generation and Integration for Anime Production

### 🎭 Overview

The Voice AI System is a comprehensive text-to-speech and voice integration solution designed specifically for anime production workflows. It provides high-quality voice generation, character voice consistency, multi-character dialogue processing, lip sync integration, and seamless video pipeline integration.

### 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Voice AI System                            │
├─────────────────┬─────────────────┬─────────────────┬──────────┤
│   Voice Service │ Dialogue Proc.  │ Video Integration│Echo Brain│
│   (Port 8319)   │                 │                 │  Quality │
├─────────────────┼─────────────────┼─────────────────┼──────────┤
│ • TTS Generation│ • Scene Dialogue│ • Video+Voice   │• Quality │
│ • Character     │ • Multi-Character│ • Lip Sync     │  Assessment│
│   Profiles      │ • Timing Calc.  │ • Audio Mixing  │• Settings│
│ • Eleven Labs   │ • Cache System  │ • FFmpeg        │  Optimization│
│   Integration   │                 │                 │          │
└─────────────────┴─────────────────┴─────────────────┴──────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Audio Manager   │
                    │ • File Storage    │
                    │ • Optimization    │
                    │ • Cache System    │
                    │ • Performance     │
                    └───────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │ PostgreSQL Database│
                    │ • Voice Profiles  │
                    │ • Generation Jobs │
                    │ • Dialogue Scenes │
                    │ • Quality Metrics │
                    └───────────────────┘
```

### 🚀 Quick Start

#### 1. Prerequisites
- PostgreSQL database running on 192.168.50.135
- Eleven Labs API key (optional, falls back to local TTS)
- Echo Brain service (optional, for quality assessment)
- FFmpeg installed for audio processing
- ComfyUI for video generation integration

#### 2. Environment Setup
```bash
# Set Eleven Labs API key (optional)
export ELEVENLABS_API_KEY="your_api_key_here"

# Create required directories
sudo mkdir -p /mnt/1TB-storage/ComfyUI/output/voice/{cache,temp,optimized}
sudo mkdir -p /mnt/1TB-storage/ComfyUI/output/dialogue
sudo mkdir -p /opt/tower-anime-production/logs
```

#### 3. Database Setup
```bash
# Initialize database schema
cd /opt/tower-anime-production
psql -h 192.168.50.135 -U patrick -d tower_consolidated -f database/voice_ai_schema.sql
```

#### 4. Start Service
```bash
# Start the complete voice AI system
python3 services/start_voice_ai.py

# Or run individual components
python3 services/voice_api_endpoints.py
```

#### 5. Health Check
```bash
curl http://localhost:8319/api/voice/health
```

### 📚 API Documentation

#### Base URL: `http://localhost:8319/api/voice`

#### Core Endpoints

##### 🎤 Voice Generation

**Quick Voice Generation**
```http
POST /generate/quick
{
    "text": "Hello, this is a test dialogue line.",
    "character_name": "Akira",
    "emotion": "neutral"
}
```

**Batch Voice Generation**
```http
POST /generate/batch
{
    "lines": [
        {
            "text": "First dialogue line",
            "character_name": "Akira",
            "emotion": "neutral"
        },
        {
            "text": "Second dialogue line",
            "character_name": "Yuki",
            "emotion": "excited"
        }
    ],
    "scene_name": "Scene1"
}
```

##### 👥 Character Management

**Create Character Voice Profile**
```http
POST /characters/profile
{
    "character_name": "Akira",
    "voice_id": "21m00Tcm4TlvDq8ikWAM",
    "voice_name": "Rachel",
    "voice_settings": {
        "stability": 0.4,
        "similarity_boost": 0.9,
        "style": 0.2
    },
    "description": "Young male protagonist"
}
```

**Get Character Analytics**
```http
GET /characters/{character_name}/analytics
```

**Optimize Character Voice Settings**
```http
POST /characters/{character_name}/optimize
{
    "target_quality": 0.8
}
```

##### 🎬 Scene Processing

**Process Complete Scene Dialogue**
```http
POST /scenes/process
{
    "scene_name": "OpeningScene",
    "project_id": "anime_project_1",
    "dialogue_lines": [
        {
            "character_name": "Akira",
            "dialogue_text": "The journey begins here.",
            "emotion": "determined",
            "timing_start": 0.0,
            "priority": 1
        }
    ],
    "auto_timing": true,
    "background_music_volume": 0.3
}
```

**Export Scene for Video Pipeline**
```http
GET /scenes/{scene_id}/export
```

##### 🎥 Complete Scene Integration

**Create Complete Scene with Video**
```http
POST /complete-scene
{
    "project_id": "anime_project_1",
    "scene_name": "OpeningScene",
    "video_prompt": "anime character in a peaceful garden",
    "characters": ["Akira", "Yuki"],
    "dialogue_lines": [
        {
            "character_name": "Akira",
            "dialogue_text": "Welcome to our story.",
            "emotion": "warm"
        }
    ],
    "video_settings": {
        "video_type": "video",
        "frames": 120,
        "fps": 24,
        "width": 512,
        "height": 512
    },
    "audio_settings": {
        "enable_lip_sync": true,
        "voice_audio_volume": 0.8,
        "background_music_volume": 0.3
    }
}
```

##### 🔍 Quality Assessment

**Assess Voice Quality**
```http
POST /assess
{
    "job_id": "voice_job_uuid",
    "audio_file_path": "/path/to/audio.mp3",
    "character_name": "Akira",
    "original_text": "Assessment test text",
    "emotion": "neutral",
    "compare_with_profile": true
}
```

##### 📊 Statistics & Monitoring

**Get System Statistics**
```http
GET /stats
```

**Get Audio File**
```http
GET /audio/{job_id}
```

**Get Generated Video**
```http
GET /video/{processing_id}
```

### 🎯 Key Features

#### 🎤 Voice Generation
- **Eleven Labs Integration**: High-quality TTS with 24+ voice options
- **Fallback TTS**: Local espeak/festival for offline operation
- **Character Voice Profiles**: Persistent voice mapping per character
- **Emotion Control**: Support for multiple emotional tones
- **Batch Processing**: Efficient multi-line generation

#### 👥 Character Management
- **Voice Profile System**: Persistent character-voice mapping
- **Usage Analytics**: Track generation metrics per character
- **Voice Consistency**: Character voice validation across scenes
- **Echo Brain Optimization**: AI-powered voice setting optimization

#### 🎬 Dialogue Processing
- **Multi-Character Scenes**: Handle complex dialogue scenarios
- **Automatic Timing**: Intelligent dialogue pacing calculation
- **Scene Organization**: Project-based dialogue management
- **Export Integration**: Seamless video pipeline handoff

#### 🎥 Video Integration
- **Lip Sync Generation**: Phoneme-based mouth movement data
- **Audio Mixing**: Voice + background music composition
- **Video Pipeline**: Integration with ComfyUI anime generation
- **Quality Control**: Echo Brain assessment integration

#### 🔧 Audio Management
- **File Optimization**: FFmpeg-based audio compression
- **Intelligent Caching**: Performance-optimized file storage
- **Storage Management**: Automatic cleanup and organization
- **Format Support**: MP3, WAV, OGG output formats

### 🧠 Echo Brain Integration

The system integrates with Echo Brain (port 8309) for advanced AI capabilities:

#### Quality Assessment
- **Voice Quality Analysis**: Comprehensive audio quality metrics
- **Character Consistency**: Compare with established voice profiles
- **Emotion Accuracy**: Validate emotional expression
- **Production Approval**: Automated quality gates

#### Voice Optimization
- **Setting Tuning**: AI-optimized voice parameters per character
- **Performance Learning**: Continuous improvement from usage data
- **Recommendation Engine**: Smart voice selection suggestions

#### Integration Endpoints
```python
# Echo Brain Query Example
{
    "query": "Assess voice quality for character Akira with metrics...",
    "conversation_id": "voice_assessment_session",
    "context": {
        "character_name": "Akira",
        "audio_metrics": {...},
        "consistency_metrics": {...}
    }
}
```

### 🗃️ Database Schema

#### Core Tables

**voice_profiles**
- Character voice mapping and settings
- Usage statistics and performance metrics
- Voice ID references to Eleven Labs

**voice_generation_jobs**
- Individual voice generation tracking
- Job status, timing, and error handling
- Audio file path references

**dialogue_scenes**
- Scene-level dialogue organization
- Project association and metadata
- Background music and timing data

**dialogue_lines**
- Individual dialogue line storage
- Character assignment and timing
- Audio and lip sync file references

**voice_quality_assessments**
- Echo Brain quality analysis results
- Approval status and recommendations
- Historical quality tracking

#### Performance Optimization
- Indexed queries for character lookups
- Efficient scene and project organization
- Automated cache cleanup and maintenance
- Connection pooling for concurrent operations

### 📁 File Organization

```
/opt/tower-anime-production/
├── services/
│   ├── voice_ai_service.py          # Core voice generation
│   ├── dialogue_pipeline.py         # Multi-character processing
│   ├── video_voice_integration.py   # Video pipeline integration
│   ├── echo_voice_integration.py    # Echo Brain quality assessment
│   ├── lip_sync_processor.py        # Lip sync generation
│   ├── audio_manager.py             # File management & optimization
│   ├── voice_api_endpoints.py       # Main API interface
│   └── start_voice_ai.py            # Service orchestration
├── database/
│   └── voice_ai_schema.sql          # Database schema
├── tests/
│   └── test_voice_ai_system.py      # Comprehensive test suite
└── logs/
    └── voice_ai.log                 # Service logs

/mnt/1TB-storage/ComfyUI/output/
├── voice/                           # Generated voice files
├── voice/cache/                     # Cached audio files
├── voice/optimized/                 # Optimized audio files
├── voice/temp/                      # Temporary processing files
└── dialogue/                        # Scene dialogue exports
```

### 🔧 Configuration

#### Environment Variables
```bash
# Eleven Labs Configuration
ELEVENLABS_API_KEY="your_api_key"

# Service Configuration
VOICE_AI_HOST="0.0.0.0"
VOICE_AI_PORT="8319"
VOICE_AI_LOG_LEVEL="info"

# Database Configuration
DB_HOST="192.168.50.135"
DB_NAME="tower_consolidated"
DB_USER="patrick"
DB_PASSWORD="tower_echo_brain_secret_key_2025"
```

#### Audio Settings
```python
# Default optimization settings
AUDIO_OPTIMIZATION = {
    "target_format": "mp3",
    "target_bitrate": 128,  # kbps
    "target_sample_rate": 22050,  # Hz
    "normalize_volume": True,
    "noise_reduction": False
}

# Cache configuration
CACHE_SETTINGS = {
    "max_cache_size_gb": 5.0,
    "default_cache_ttl_days": 7,
    "cleanup_interval_hours": 1
}
```

### 🧪 Testing

#### Run Complete Test Suite
```bash
cd /opt/tower-anime-production
python3 tests/test_voice_ai_system.py
```

#### Test Categories
1. **Service Health**: API availability and response
2. **Character Management**: Profile creation and management
3. **Voice Generation**: Single and batch generation
4. **Dialogue Processing**: Multi-character scene handling
5. **Echo Brain Integration**: Quality assessment functionality
6. **Audio Management**: File optimization and caching
7. **Video Integration**: Complete scene pipeline
8. **Performance**: Concurrent generation benchmarks

#### Test Output Example
```
🚀 Starting Voice AI System Test Suite
============================================================

🧪 Running test: Voice Service Health
----------------------------------------
✓ Voice service health check passed: healthy

🧪 Running test: Character Profile Management
----------------------------------------
✓ Character profile created: TestCharacter1
✓ Character profile listing: 2 characters found

📊 TEST SUMMARY
============================================================
✅ PASS      Voice Service Health
✅ PASS      Character Profile Management
✅ PASS      Voice Generation
✅ PASS      Batch Voice Generation
✅ PASS      Dialogue Scene Processing
✅ PASS      Echo Brain Integration
✅ PASS      Audio Management
✅ PASS      Character Analytics
✅ PASS      Complete Scene Integration
✅ PASS      Performance Benchmarks
------------------------------------------------------------
📈 OVERALL RESULT: 10/10 tests passed (100.0%)
🎉 ALL TESTS PASSED! Voice AI system is ready for production.
```

### 🔄 Integration with Anime Production

#### Workflow Integration
1. **Video Generation**: Request video via anime API (port 8328)
2. **Voice Processing**: Generate character dialogue with Voice AI
3. **Lip Sync Application**: Apply mouth movement data to video
4. **Audio Mixing**: Combine voice + background music
5. **Quality Assessment**: Echo Brain validation pipeline
6. **Final Output**: Complete video with synchronized audio

#### API Integration Example
```python
# Complete scene processing
async def create_anime_scene_with_voice():
    # 1. Generate video
    video_response = await anime_api.post("/api/anime/generate/video", {
        "prompt": "anime character in garden",
        "frames": 120,
        "fps": 24
    })

    # 2. Process dialogue
    dialogue_response = await voice_api.post("/api/voice/complete-scene", {
        "video_prompt": "anime character in garden",
        "dialogue_lines": dialogue_data,
        "enable_lip_sync": True
    })

    # 3. Get final video with voice
    final_video = dialogue_response["output_video_path"]
    return final_video
```

### 📊 Performance Metrics

#### Target Performance
- **Voice Generation**: <10 seconds per line
- **Scene Processing**: <60 seconds for 5-line scene
- **Video Integration**: <300 seconds complete pipeline
- **Quality Assessment**: <30 seconds Echo Brain analysis
- **System Availability**: 99.5% uptime target

#### Monitoring
- Real-time health checks every 60 seconds
- Automated performance logging and alerting
- Database performance optimization
- Cache hit rate tracking and optimization

### 🚨 Troubleshooting

#### Common Issues

**Voice Generation Fails**
```bash
# Check Eleven Labs API key
curl -H "xi-api-key: $ELEVENLABS_API_KEY" https://api.elevenlabs.io/v1/voices

# Check fallback TTS
espeak "test" -w /tmp/test.wav

# Check logs
tail -f /opt/tower-anime-production/logs/voice_ai.log
```

**Database Connection Issues**
```bash
# Test database connection
psql -h 192.168.50.135 -U patrick -d tower_consolidated -c "SELECT 1;"

# Check connection pool
curl http://localhost:8319/api/voice/health | jq '.services.database'
```

**Audio Processing Errors**
```bash
# Test FFmpeg
ffmpeg -version

# Check audio permissions
ls -la /mnt/1TB-storage/ComfyUI/output/voice/

# Clear cache
curl -X POST http://localhost:8319/api/voice/admin/clear-cache
```

**Echo Brain Integration Issues**
```bash
# Test Echo Brain connectivity
curl http://localhost:8309/api/echo/health

# Check Echo Brain logs
tail -f /opt/tower-echo-brain/logs/echo.log
```

#### Debug Mode
```bash
# Enable debug logging
export VOICE_AI_LOG_LEVEL="debug"
python3 services/start_voice_ai.py
```

### 🔐 Security

#### API Security
- CORS configuration for allowed origins
- Input validation and sanitization
- SQL injection prevention
- File path validation

#### Data Protection
- Secure credential storage in environment variables
- Database connection encryption
- Audio file access controls
- No sensitive data in logs

### 🚀 Production Deployment

#### SystemD Service
```bash
# Create systemd service
sudo cp tower-voice-ai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tower-voice-ai
sudo systemctl start tower-voice-ai
```

#### Nginx Proxy Configuration
```nginx
location /api/voice/ {
    proxy_pass http://localhost:8319/api/voice/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 300s;
}
```

#### Backup Strategy
- Daily database dumps
- Audio file backup to secondary storage
- Configuration backup
- Log rotation and archival

### 📈 Future Enhancements

#### Planned Features
- **Real-time Voice Cloning**: Custom voice training
- **Advanced Lip Sync**: ML-based mouth movement prediction
- **Voice Emotion Analysis**: Sentiment-based voice modulation
- **Multi-language Support**: International voice generation
- **Voice Effects**: Real-time audio processing effects

#### Performance Optimizations
- **GPU Acceleration**: CUDA-based audio processing
- **Distributed Processing**: Multi-node voice generation
- **Advanced Caching**: Predictive audio caching
- **WebSocket Streaming**: Real-time voice generation

---

## 📞 Support

For technical support, documentation updates, or feature requests, please refer to the Tower Anime Production system documentation or contact the development team.

**Service Status**: ✅ Production Ready
**Last Updated**: 2025-12-15
**Version**: 1.0.0
**Maintainer**: Tower AI Development Team