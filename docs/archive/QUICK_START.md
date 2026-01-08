# Tower Anime Production API - Quick Start

## Service Status
- **Port**: 8321 (localhost only)
- **Service**: tower-anime-api.service
- **Database**: /opt/tower-anime-production/anime.db (SQLite)

## Quick Test
```bash
# Health check
curl http://127.0.0.1:8321/api/anime/health

# Create a project
curl -X POST http://127.0.0.1:8321/api/anime/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Project", "description": "My first anime"}'

# List projects
curl http://127.0.0.1:8321/api/anime/projects
```

## All Endpoints
- GET /api/anime/health
- POST /api/anime/projects
- GET /api/anime/projects
- GET /api/anime/projects/{id}
- POST /api/anime/characters
- GET /api/anime/characters
- PUT /api/anime/characters/{id}
- POST /api/anime/scenes
- GET /api/anime/scenes
- PUT /api/anime/scenes/{id}

## Interactive Docs
- Swagger UI: http://127.0.0.1:8321/docs
- ReDoc: http://127.0.0.1:8321/redoc

## Service Management
```bash
systemctl --user status tower-anime-api.service
systemctl --user restart tower-anime-api.service
journalctl --user -u tower-anime-api.service -f
```

For detailed documentation, see API_DOCUMENTATION.md
