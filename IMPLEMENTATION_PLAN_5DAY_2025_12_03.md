# Tower Anime Production - 5-Day Implementation Plan
## Based on Verified Testing - December 3, 2025
## Goal: Transform Broken Prototype into Working Production System

---

# Day 1: Fix Critical Infrastructure (Database & Job Tracking)

## Morning (4 hours): Database Persistence Fix
### Tasks:
1. **Fix job persistence in anime_generation_api.py**
   ```python
   # Add after line 89 (job creation)
   async def save_job_to_db(job_data):
       query = """
       INSERT INTO anime_api.production_jobs
       (comfyui_job_id, job_type, prompt, status, created_at)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING id
       """
       # Implement PostgreSQL connection
   ```

2. **Add database connection pool**
   - File: `/opt/tower-anime-production/database.py`
   - Use asyncpg for async PostgreSQL
   - Connection string: `postgresql://patrick:***REMOVED***@localhost/anime_production`

3. **Update job status tracking**
   - Modify: `update_job_status()` to write to DB
   - Add: Transaction support for consistency
   - Fix: Missing columns in production_jobs table

### Database Changes:
```sql
ALTER TABLE anime_api.production_jobs
ADD COLUMN IF NOT EXISTS total_time_seconds FLOAT,
ADD COLUMN IF NOT EXISTS file_path TEXT,
ADD COLUMN IF NOT EXISTS generation_params JSONB;
```

### Testing:
- Generate 5 test images
- Verify all persist to database
- Restart service and confirm jobs still exist

### Success Metrics:
- ✅ All jobs persist to PostgreSQL
- ✅ Jobs survive service restart
- ✅ Database queries return correct data

---

# Day 2: Performance Optimization (60s → <30s)

## Morning (4 hours): Profile & Optimize
### Tasks:
1. **Profile generation pipeline**
   ```python
   import cProfile
   import pstats

   # Add profiling to /generate endpoint
   profiler = cProfile.Profile()
   profiler.enable()
   # ... generation code ...
   profiler.disable()
   ```

2. **Optimize ComfyUI workflow**
   - File: `/opt/tower-anime-production/comfyui_client.py`
   - Reduce model loading time (cache models)
   - Optimize image resolution (512x768 → 512x512 for speed)
   - Use simpler workflows for quick generation

3. **Add caching layer**
   ```python
   from functools import lru_cache
   import redis

   redis_client = redis.Redis(host='localhost', port=6379)

   @lru_cache(maxsize=100)
   def get_cached_workflow(prompt_hash):
       # Cache frequently used workflows
   ```

### Code Files to Modify:
- `/opt/tower-anime-production/anime_generation_api.py`
- `/opt/tower-anime-production/comfyui_client.py`
- Create: `/opt/tower-anime-production/cache_manager.py`

### Testing:
- Benchmark 10 generations
- Measure time for each component
- Target: <30 seconds average

### Success Metrics:
- ✅ Generation time <30 seconds
- ✅ Cached operations skip redundant work
- ✅ Performance metrics logged

---

# Day 3: Implement Core Project Management APIs

## Full Day (8 hours): Build Missing APIs
### Tasks:
1. **Implement /api/anime/projects CRUD**
   ```python
   @app.post("/api/anime/projects")
   async def create_project(project: ProjectCreate):
       query = """
       INSERT INTO anime_api.projects
       (name, description, style, created_at)
       VALUES ($1, $2, $3, NOW())
       RETURNING id, name, description
       """
       # Full CRUD implementation

   @app.get("/api/anime/projects")
   @app.get("/api/anime/projects/{project_id}")
   @app.put("/api/anime/projects/{project_id}")
   @app.delete("/api/anime/projects/{project_id}")
   ```

2. **Implement /api/anime/characters**
   ```python
   @app.post("/api/anime/characters")
   async def create_character(character: CharacterCreate):
       # Store character bible
       # Link to project
       # Generate reference image

   @app.get("/api/anime/characters/{character_id}/bible")
   async def get_character_bible(character_id: str):
       # Return complete character details
   ```

3. **Implement /api/anime/workflows**
   ```python
   @app.post("/api/anime/workflows")
   async def create_workflow(workflow: WorkflowCreate):
       # Define generation pipeline
       # Store workflow configuration
   ```

### Database Schema Updates:
```sql
-- Projects table already exists, verify structure
-- Characters table exists, add indexes
CREATE INDEX IF NOT EXISTS idx_projects_created ON anime_api.projects(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_characters_project ON anime_api.characters(project_id);
```

### Testing:
- Create 3 test projects via API
- Add 2 characters per project
- Verify all CRUD operations work

### Success Metrics:
- ✅ All project endpoints return 200
- ✅ Characters persist with bible data
- ✅ Workflows can be saved and retrieved

---

# Day 4: WebSocket Progress & File Organization

## Morning (4 hours): Real-time Progress
### Tasks:
1. **Implement WebSocket progress tracking**
   ```python
   from fastapi import WebSocket
   import asyncio

   @app.websocket("/ws/progress/{job_id}")
   async def websocket_progress(websocket: WebSocket, job_id: str):
       await websocket.accept()
       while True:
           progress = await get_job_progress(job_id)
           await websocket.send_json({
               "job_id": job_id,
               "progress": progress,
               "eta": calculate_eta(progress)
           })
           if progress >= 100:
               break
           await asyncio.sleep(1)
   ```

2. **Add progress hooks to ComfyUI**
   - Monitor ComfyUI execution
   - Calculate percentage based on workflow steps
   - Send updates via WebSocket

## Afternoon (4 hours): File Organization
### Tasks:
1. **Implement project-based file structure**
   ```python
   def organize_output_file(job_id, project_id, character_id):
       # Move from: /output/working_api_timestamp.png
       # To: /output/projects/{project_id}/characters/{character_id}/
       source = f"/mnt/1TB-storage/ComfyUI/output/{old_filename}"
       dest = f"/mnt/1TB-storage/anime/projects/{project_id}/..."
       shutil.move(source, dest)
       return dest
   ```

2. **Update database with organized paths**
   - Store organized path in production_jobs
   - Link files to projects and characters

### Testing:
- Generate images for 2 projects
- Verify WebSocket sends progress
- Confirm files organized correctly

### Success Metrics:
- ✅ WebSocket reports 0-100% progress
- ✅ Files organized by project/character
- ✅ Database tracks file locations

---

# Day 5: Echo Integration & Production Hardening

## Morning (4 hours): Echo Brain Integration
### Tasks:
1. **Connect Echo memory to characters**
   ```python
   async def enhance_with_echo_memory(character_id, prompt):
       echo_response = await echo_client.post(
           "/api/echo/anime/enhance",
           json={
               "character_id": character_id,
               "prompt": prompt,
               "use_memory": True
           }
       )
       return echo_response.json()["enhanced_prompt"]
   ```

2. **Implement style learning**
   - Track user preferences
   - Store in echo_brain.anime_preferences
   - Apply learned styles to new generations

3. **Add character consistency scoring**
   - Compare new generations to character bible
   - Use Echo to maintain consistency
   - Score and flag inconsistencies

## Afternoon (4 hours): Testing & Documentation
### Tasks:
1. **End-to-end testing**
   - Create project → Add characters → Generate content
   - Test all API endpoints
   - Verify database integrity

2. **Performance testing**
   - Load test with 10 concurrent requests
   - Measure response times
   - Check resource usage

3. **Create API documentation**
   ```python
   from fastapi import FastAPI
   from fastapi.openapi.utils import get_openapi

   # Add OpenAPI documentation
   app.openapi_schema = get_openapi(
       title="Tower Anime Production API",
       version="1.0.0",
       description="Production-ready anime generation"
   )
   ```

### Testing Requirements:
- Full workflow test (project → character → generation)
- Stress test (10 concurrent generations)
- Data integrity check (all relations valid)

### Success Metrics:
- ✅ Echo enhances prompts intelligently
- ✅ Character consistency >90%
- ✅ All tests pass
- ✅ API documentation complete

---

# Daily Schedule & Accountability

## Day 1 Deliverables:
- [ ] Database persistence working
- [ ] Jobs survive restart
- [ ] Error handling improved

## Day 2 Deliverables:
- [ ] Generation <30 seconds
- [ ] Caching implemented
- [ ] Performance metrics logged

## Day 3 Deliverables:
- [ ] Project API working
- [ ] Character API working
- [ ] Workflow API working

## Day 4 Deliverables:
- [ ] WebSocket progress working
- [ ] Files organized by project
- [ ] Database tracks all files

## Day 5 Deliverables:
- [ ] Echo integration complete
- [ ] All tests passing
- [ ] System production-ready

---

# Post-Implementation Checklist

## Must Have (For Production):
- [x] Generation works
- [ ] Jobs persist to database
- [ ] Generation <30 seconds
- [ ] Project management APIs
- [ ] File organization
- [ ] Progress tracking
- [ ] Error handling

## Nice to Have (Future):
- [ ] Batch generation
- [ ] Video generation
- [ ] Advanced Echo learning
- [ ] Multi-user support
- [ ] Web UI improvements

---

# Conclusion

This plan transforms the current broken prototype into a working production system in 5 days by:
1. Fixing fundamental issues (persistence, performance)
2. Implementing missing core features (APIs, organization)
3. Adding production requirements (progress, integration)

Each day has specific, measurable goals. By following this plan, the anime production system will be ready for real use by December 8, 2025.