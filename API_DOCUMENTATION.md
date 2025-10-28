# Tower Anime Production API Documentation

## Service Information
- **Location**: /opt/tower-anime-production/anime_api.py
- **Port**: 8321 (localhost only)
- **Service**: tower-anime-api.service (systemd)
- **Database**: SQLite at /opt/tower-anime-production/anime.db
- **Status**: ✅ Running

## Service Management
```bash
# Start service
systemctl --user start tower-anime-api.service

# Stop service
systemctl --user stop tower-anime-api.service

# Restart service
systemctl --user restart tower-anime-api.service

# Check status
systemctl --user status tower-anime-api.service

# View logs
journalctl --user -u tower-anime-api.service -f
```

## Available Endpoints

### Health Check
**GET** /api/anime/health
- Returns service health status and database connection info

Example:
```bash
curl http://127.0.0.1:8321/api/anime/health
```

Response:
```json
{
  "status": "healthy",
  "service": "tower-anime-production",
  "database": "connected",
  "project_count": 1,
  "timestamp": "2025-10-05T04:57:46.802250"
}
```

### Projects

#### Create Project
**POST** /api/anime/projects
- Create a new anime project

Example:
```bash
curl -X POST http://127.0.0.1:8321/api/anime/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Anime Project",
    "description": "An epic adventure",
    "metadata": {"genre": "action", "target_length": "24min"}
  }'
```

#### List Projects
**GET** /api/anime/projects?status=active&limit=100
- List all projects with optional filters

Example:
```bash
curl http://127.0.0.1:8321/api/anime/projects
curl http://127.0.0.1:8321/api/anime/projects?status=active
```

#### Get Project Details
**GET** /api/anime/projects/{project_id}
- Get specific project by ID

Example:
```bash
curl http://127.0.0.1:8321/api/anime/projects/1
```

### Characters

#### Create Character
**POST** /api/anime/characters
- Create a new character for a project

Example:
```bash
curl -X POST http://127.0.0.1:8321/api/anime/characters \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "name": "Hero",
    "description": "Main protagonist",
    "image_path": "/path/to/character.png",
    "comfyui_workflow": "{workflow_json}"
  }'
```

#### List Characters
**GET** /api/anime/characters?project_id=1&limit=100
- List characters with optional project filter

Example:
```bash
curl http://127.0.0.1:8321/api/anime/characters
curl http://127.0.0.1:8321/api/anime/characters?project_id=1
```

#### Update Character
**PUT** /api/anime/characters/{character_id}
- Update character (automatically increments version)

Example:
```bash
curl -X PUT http://127.0.0.1:8321/api/anime/characters/1 \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Updated description",
    "image_path": "/new/path.png"
  }'
```

### Scenes

#### Create Scene
**POST** /api/anime/scenes
- Create a new scene in a project

Example:
```bash
curl -X POST http://127.0.0.1:8321/api/anime/scenes \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "branch_name": "main",
    "scene_number": 1,
    "description": "Opening scene with hero introduction",
    "characters": ["Hero", "Sidekick"]
  }'
```

#### List Scenes
**GET** /api/anime/scenes?project_id=1&branch_name=main&limit=100
- List scenes with optional filters

Example:
```bash
curl http://127.0.0.1:8321/api/anime/scenes
curl http://127.0.0.1:8321/api/anime/scenes?project_id=1
curl http://127.0.0.1:8321/api/anime/scenes?project_id=1&branch_name=main
```

#### Update Scene
**PUT** /api/anime/scenes/{scene_id}
- Update scene details

Example:
```bash
curl -X PUT http://127.0.0.1:8321/api/anime/scenes/1 \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Updated scene description",
    "status": "completed",
    "video_path": "/videos/scene1.mp4"
  }'
```

## Data Models

### ProjectCreate
```json
{
  "name": "string (required)",
  "description": "string (optional)",
  "metadata": {"key": "value"} // optional JSON object
}
```

### CharacterCreate
```json
{
  "project_id": 1,
  "name": "string (required)",
  "description": "string (optional)",
  "image_path": "string (optional)",
  "comfyui_workflow": "string (optional)"
}
```

### SceneCreate
```json
{
  "project_id": 1,
  "branch_name": "main",
  "scene_number": 1,
  "description": "string (required)",
  "characters": ["character names"]
}
```

## Database Schema

### projects
- id (INTEGER PRIMARY KEY)
- name (TEXT NOT NULL)
- description (TEXT)
- status (TEXT DEFAULT 'active')
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
- metadata (TEXT - JSON)

### characters
- id (INTEGER PRIMARY KEY)
- project_id (INTEGER FOREIGN KEY)
- name (TEXT NOT NULL)
- description (TEXT)
- version (INTEGER DEFAULT 1)
- image_path (TEXT)
- comfyui_workflow (TEXT)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)

### scenes
- id (INTEGER PRIMARY KEY)
- project_id (INTEGER FOREIGN KEY)
- branch_name (TEXT DEFAULT 'main')
- scene_number (INTEGER NOT NULL)
- description (TEXT)
- characters (TEXT - JSON array)
- video_path (TEXT)
- status (TEXT DEFAULT 'pending')
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)

## Interactive API Documentation

FastAPI provides automatic interactive documentation:

- **Swagger UI**: http://127.0.0.1:8321/docs
- **ReDoc**: http://127.0.0.1:8321/redoc
- **OpenAPI JSON**: http://127.0.0.1:8321/openapi.json

## CORS Configuration

CORS is enabled for all origins (*) to allow dashboard access. In production, update this to specific origins:

```python
allow_origins=["https://***REMOVED***"]
```

## Error Handling

All endpoints return standard HTTP status codes:
- 200: Success
- 404: Resource not found
- 500: Internal server error
- 503: Service unavailable

Error responses include detail messages:
```json
{
  "detail": "Project not found"
}
```
