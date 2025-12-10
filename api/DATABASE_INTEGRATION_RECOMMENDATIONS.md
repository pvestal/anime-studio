# Database Integration Recommendations

## Overview

This document provides recommendations for integrating the new SQLAlchemy database layer into the existing Tower Anime Production system at `/opt/tower-anime-production/api/secured_api.py`.

## Files Created

### 1. Updated `models.py`
- **Location**: `/opt/tower-anime-production/api/models.py`
- **Description**: SQLAlchemy models matching the existing database schema
- **Key Changes**:
  - Uses `public` schema (not `anime_api`)
  - Fixed `metadata` column naming conflict with `metadata_`
  - Added comprehensive models for all 25 existing tables
  - Proper relationships between Project, Character, ProductionJob, and GeneratedAsset

### 2. New `database.py`
- **Location**: `/opt/tower-anime-production/api/database.py`
- **Description**: Database connection management and FastAPI integration
- **Features**:
  - SQLAlchemy engine with connection pooling
  - `get_db()` dependency for FastAPI route injection
  - `DatabaseHealth` class for monitoring
  - Startup/shutdown event handlers

### 3. Refactored API `secured_api_refactored.py`
- **Location**: `/opt/tower-anime-production/api/secured_api_refactored.py`
- **Description**: Example implementation using database models
- **Port**: 8331 (to avoid conflict with existing API on 8328)
- **Features**:
  - Database-driven CRUD operations for projects and characters
  - Real-time job progress tracking from database + ComfyUI
  - Proper error handling and transaction management

### 4. Test Scripts
- **Location**: `/opt/tower-anime-production/api/test_database_integration.py`
- **Location**: `/opt/tower-anime-production/api/test_api_integration.py`
- **Description**: Validation scripts for database functionality

## Integration Steps

### Step 1: Install Dependencies
Ensure SQLAlchemy is available in the virtual environment:
```bash
cd /opt/tower-anime-production
source venv/bin/activate
pip install sqlalchemy psycopg2-binary
```

### Step 2: Test Database Connection
Run the integration test to verify database connectivity:
```bash
cd /opt/tower-anime-production/api
python3 test_database_integration.py
```

### Step 3: Gradual Migration Strategy

#### Option A: Replace Existing API (Recommended)
1. **Backup current API**: `cp secured_api.py secured_api_backup.py`
2. **Import database components** into existing `secured_api.py`:
   ```python
   from database import get_db, init_database, close_database
   from models import Project, Character, ProductionJob, GeneratedAsset
   ```
3. **Add startup/shutdown events**:
   ```python
   @app.on_event("startup")
   async def startup_event():
       init_database()

   @app.on_event("shutdown")
   async def shutdown_event():
       close_database()
   ```
4. **Replace in-memory `jobs` dict** with database queries

#### Option B: Run Both APIs (Safe Testing)
1. **Keep existing API** on port 8328
2. **Run refactored API** on port 8331 for testing
3. **Gradually migrate endpoints** one by one
4. **Switch nginx routing** when ready

### Step 4: Update Key Endpoints

#### Replace `/api/anime/jobs/{job_id}/progress` endpoint:
```python
@app.get("/api/anime/jobs/{job_id}/progress")
async def get_job_progress(
    job_id: int,
    db: Session = Depends(get_db)
):
    job = db.query(ProductionJob).filter(ProductionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get real-time ComfyUI status if available
    if job.metadata_ and job.metadata_.get("comfyui_id"):
        comfyui_status = await get_comfyui_job_status(job.metadata_["comfyui_id"])
        # Update database with real-time status

    return {
        "job_id": job.id,
        "status": job.status,
        "progress": comfyui_status.get("progress", 0) if comfyui_status else 0,
        "output_path": job.output_path,
        # ... rest of response
    }
```

#### Add project/character CRUD:
```python
@app.get("/api/anime/projects")
async def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    projects = db.query(Project).offset(skip).limit(limit).all()
    return {"projects": [project_to_dict(p) for p in projects]}

@app.post("/api/anime/projects")
async def create_project(
    request: ProjectCreateRequest,
    db: Session = Depends(get_db),
    user_data: dict = Depends(require_auth)
):
    project = Project(name=request.name, description=request.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_to_dict(project)
```

### Step 5: Update Job Creation

When creating jobs in ComfyUI, store them in the database:
```python
# In your generation function
job = ProductionJob(
    project_id=request.get("project_id"),
    character_id=request.get("character_id"),
    job_type="image_generation",
    status="queued",
    prompt=request.prompt,
    metadata_={"comfyui_id": comfyui_prompt_id, "user": user_email}
)
db.add(job)
db.commit()
db.refresh(job)

# Store job ID for tracking
jobs[str(job.id)] = {
    "db_id": job.id,
    "comfyui_id": comfyui_prompt_id,
    # ... other temporary fields
}
```

## Expected Benefits

### 1. Persistent Job Tracking
- Jobs survive API restarts
- Historical job data for analytics
- Proper project/character association

### 2. Improved Performance
- Database queries instead of in-memory dictionaries
- Indexed lookups for fast job status checks
- Connection pooling for concurrent requests

### 3. Better Data Organization
- Structured project management
- Character consistency tracking
- Asset relationship management

### 4. Integration with Existing System
- Works with current ComfyUI setup
- Maintains existing authentication
- Compatible with v2_integration features

## Testing Validation

The database integration has been tested with:
- ✅ Project CRUD operations
- ✅ Character CRUD operations
- ✅ Job creation and status tracking
- ✅ Asset file management
- ✅ Database relationships and joins
- ✅ Connection pooling and error handling

## Migration Timeline

### Week 1: Database Layer
- [ ] Integrate `database.py` and `models.py` into existing API
- [ ] Add startup/shutdown events
- [ ] Test database connectivity in production

### Week 2: Job Tracking Migration
- [ ] Replace in-memory `jobs` dict with database queries
- [ ] Update job creation to use ProductionJob model
- [ ] Migrate existing jobs to database (if needed)

### Week 3: CRUD Endpoints
- [ ] Add project management endpoints
- [ ] Add character management endpoints
- [ ] Update frontend to use new endpoints

### Week 4: Advanced Features
- [ ] Asset tracking and file organization
- [ ] Quality metrics storage
- [ ] Performance optimization and monitoring

## Notes

- All models use `metadata_` instead of `metadata` to avoid SQLAlchemy conflicts
- Database schema matches existing 25 tables in `anime_production` database
- Connection pooling configured for production workload (10 base, 20 overflow)
- Health monitoring includes database status in `/api/anime/health`
- Full backward compatibility with existing ComfyUI integration
- Generated assets table added for better file tracking

## Support

For questions or issues during integration:
1. Check test scripts for examples
2. Review `secured_api_refactored.py` for complete implementation
3. Database health available at `/api/anime/health` endpoint