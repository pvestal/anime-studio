# Anime Production System - Actual Architecture (December 2, 2025)

## Current System Status

### Working Components ✅

#### 1. File Organization Service (anime-file-organizer)
- **Status**: RUNNING & WORKING
- **Function**: Monitors ComfyUI output and organizes files by date
- **Location**: `/mnt/1TB-storage/anime-projects/unorganized/images/YYYYMMDD/`
- **Database**: Records all files in `anime_api.anime_files` table
- **Files Processed**: 98 files organized and tracked
- **Fixed**: Database connection (was using ***REMOVED*** instead of localhost)

#### 2. Job Monitor Service (anime-job-monitor)
- **Status**: RUNNING
- **Function**: Monitors processing jobs and updates status from ComfyUI
- **Script**: `completion_tracking_fix.py`
- **Fixed**: Database connection to localhost

#### 3. Job Worker Service (anime-job-worker)
- **Status**: RUNNING
- **Function**: Processes jobs from Redis queue
- **Redis Queue**: Currently empty (0 jobs)
- **ComfyUI Integration**: Connected to http://***REMOVED***:8188

#### 4. WebSocket Progress Server (anime-websocket)
- **Status**: RUNNING & WORKING
- **Port**: 8765 (ws://localhost:8765)
- **Function**: Real-time progress updates via WebSocket
- **Fixed**: Method signature issue (removed 'path' parameter)
- **Redis Channel**: `anime:job:updates`

#### 5. Working API (Port 8330)
- **Status**: RUNNING & GENERATING
- **Location**: `/opt/tower-anime-production/api/working_api.py`
- **Features**:
  - VRAM management (ensures 8GB+ available)
  - Direct ComfyUI integration
  - 5-second average generation time
  - In-memory job tracking
  - Successfully generated 10+ images today

#### 6. Main API (Port 8328)
- **Status**: RUNNING (manually started)
- **Location**: `/opt/tower-anime-production/api/main.py`
- **Issues**:
  - Still has 500 errors for generation
  - Database integration issues
  - No real progress tracking

### Database Schema ✅

```sql
anime_api.anime_files
├── id (SERIAL PRIMARY KEY)
├── filename (VARCHAR)
├── project_id (UUID, nullable)
├── job_id (UUID, nullable)
├── file_type (VARCHAR)
├── file_path (TEXT)
├── file_size (BIGINT)
├── metadata (JSONB)
├── created_at (TIMESTAMP)
└── organized_at (TIMESTAMP)
```

### File Organization Structure

```
/mnt/1TB-storage/
├── ComfyUI/
│   └── output/           # Raw output from ComfyUI
└── anime-projects/
    └── unorganized/
        └── images/
            └── 20251202/  # Date-based organization
                ├── anime_*.png
                └── working_api_*.png
```

### Service Configuration Fixes Applied

1. **Database Connections**: Changed all services from `***REMOVED***` to `localhost`
2. **WebSocket Handler**: Fixed method signature for new websockets library
3. **File Organizer**: Added NULL handling for non-project files
4. **Systemd Service**: Updated to use existing `api/main.py`

### Discovered Issues

1. **No proper project association** - Files organized by date only
2. **No character integration** - Database has character data but APIs don't use it
3. **Progress tracking incomplete** - WebSocket server exists but not integrated
4. **Two separate APIs** - Working simple API (8330) vs complex broken API (8328)
5. **Missing hvac module** - Vault integration not working

### Next Steps Required

1. **Integrate WebSocket with generation API** - Connect progress updates
2. **Merge working API features into main API** - Combine best of both
3. **Implement proper project tracking** - Associate files with projects
4. **Add character support** - Use existing database character data
5. **Install missing dependencies** - hvac for Vault integration

## Service Management Commands

```bash
# Check all anime services
systemctl status anime-file-organizer anime-job-monitor anime-job-worker anime-websocket

# View logs
sudo journalctl -u anime-file-organizer -f
sudo journalctl -u anime-job-monitor -f
sudo journalctl -u anime-job-worker -f
sudo journalctl -u anime-websocket -f

# Test WebSocket
python3 /tmp/test_websocket.py

# Test generation (working API)
curl -X POST http://localhost:8330/api/anime/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "anime character", "type": "image"}'

# Check database
PGPASSWORD=***REMOVED*** psql -h localhost -U patrick -d anime_production \
  -c "SELECT * FROM anime_api.anime_files ORDER BY created_at DESC LIMIT 5;"
```

## Summary

The anime production system has multiple microservices that ARE running and partially working:
- File organization: ✅ WORKING (98 files organized)
- Job monitoring: ✅ RUNNING (monitoring ComfyUI)
- Job worker: ✅ RUNNING (processing Redis queue)
- WebSocket: ✅ FIXED (real-time updates ready)
- Generation: ✅ WORKING on port 8330 (5-second generations)

The main issue is integration - these services aren't properly connected to provide a cohesive workflow with progress tracking.