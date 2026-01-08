# Tower Anime Production

Anime video production system with Echo Brain memory persistence and FramePack segment chaining for movie-length content.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up database
psql -U patrick -d anime_production < database/anime_schema.sql
psql -U patrick -d anime_production < database/framepack_schema.sql

# Run API server
python api/main.py
```

API runs at `http://localhost:8328/api/anime/docs`

## Architecture

```
tower-anime-production/
├── api/                    # FastAPI application
│   ├── main.py            # Entry point
│   ├── auth_middleware.py # Authentication
│   └── websocket_*.py     # Real-time updates
├── services/              # Business logic
│   ├── framepack/         # FramePack video generation
│   │   ├── echo_brain_memory.py  # Character/story/visual persistence
│   │   ├── scene_generator.py    # Segment generation & chaining
│   │   └── quality_analyzer.py   # SSIM & optical flow analysis
│   └── generation/        # Image/video generation
├── config/                # Environment-based configuration
│   └── settings.py
├── database/              # SQL schemas
│   ├── anime_schema.sql
│   └── framepack_schema.sql
├── tests/                 # Test suites
├── workflows/             # ComfyUI workflow templates
└── frontend/              # React UI
```

## FramePack Pipeline

Generates movie-length content by chaining 30-60 second segments:

```
Movie → Episodes → Scenes → Segments (30-60s each)
                              ↓
                    Echo Brain Memory
                    - Character state per scene
                    - Story context per scene
                    - Visual style per scene
                    - Quality feedback (learning)
                              ↓
                    FramePack Generation
                    - First/last frame anchoring
                    - Motion prompt from memory
                    - Chain via extracted last frames
                              ↓
                    Quality Analysis
                    - Frame consistency (SSIM)
                    - Motion smoothness (optical flow)
                    - Feed back into memory
```

### The Learning Loop

After each segment generation:
1. Quality analyzer measures frame consistency and motion smoothness
2. If score > 0.7: prompt elements marked as "successful"
3. If score < 0.4: prompt elements marked as "failed"
4. Next generation queries feedback to enhance/filter prompts

## Configuration

Environment variables (or defaults for Tower server):

```bash
# Database
DB_HOST=localhost
DB_NAME=anime_production
DB_USER=patrick

# ComfyUI
COMFYUI_HOST=localhost
COMFYUI_PORT=8188

# API
API_PORT=8328
```

## Hardware Requirements

Optimized for Tower server:
- **GPU**: RTX 3060 12GB (FramePack needs ~6GB VRAM)
- **CPU**: AMD Ryzen 9 24-core
- **RAM**: 96GB DDR6
- **Storage**: 1TB NVMe for models/output

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/anime/health` | GET | System health check |
| `/api/anime/generate` | POST | Generate anime image |
| `/api/anime/orchestrate` | POST | Full production pipeline |
| `/api/anime/generation/{id}/status` | GET | Job status with progress |
| `/api/anime/phases` | GET | Available production phases |

## Development

```bash
# Run tests
pytest tests/ -v

# Format code
black api/ services/ config/
isort api/ services/ config/

# Type check
mypy api/ services/ config/
```

## Documentation

Historical implementation notes archived in `docs/archive/`.
