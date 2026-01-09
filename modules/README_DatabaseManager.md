# Database Manager Module

A clean, modular database manager for the Anime Production System, inspired by Echo Brain's architecture with separation of concerns.

## Features

✅ **Job Tracking**: Complete job lifecycle management
✅ **Connection Pooling**: Efficient PostgreSQL connection management
✅ **Error Handling**: Robust error handling with custom exceptions
✅ **Thread Safety**: Thread-safe connection pooling
✅ **Type Safety**: Full type hints for better IDE support
✅ **Production Ready**: Tested with real database operations

## Core Operations

### Job Management
- `save_job(job_data)` - Create new generation job
- `update_job(job_id, updates)` - Update job status/progress
- `get_job(job_id)` - Retrieve job details
- `list_jobs(status, limit, offset)` - List jobs with filtering
- `get_active_jobs()` - Get pending/processing jobs
- `delete_job(job_id)` - Remove completed jobs

### Database Health
- `get_health_status()` - Connection and performance metrics
- `close()` - Clean connection pool shutdown

## Configuration

```python
class DatabaseConfig:
    host = "192.168.50.135"
    port = 5432
    database = "anime_production"
    user = "patrick"
    password = "tower_echo_brain_secret_key_2025"
    pool_size = 5
```

## Usage Example

```python
from modules.database_manager import DatabaseManager

# Initialize
db = DatabaseManager()
db.initialize()

# Create a generation job
job_data = {
    'prompt': 'Anime character with silver hair in cyberpunk city',
    'character_name': 'Cyber-kun',
    'duration': 4.5,
    'style': 'photorealistic_anime',
    'metadata': {'resolution': '1024x1024', 'fps': 30}
}

job_id = db.save_job(job_data)

# Update during processing
db.update_job(job_id, {
    'status': 'processing',
    'progress': 75,
    'metadata': {'current_frame': 108}
})

# Mark as complete
db.update_job(job_id, {
    'status': 'completed',
    'progress': 100,
    'output_path': '/mnt/1TB-storage/ComfyUI/output/cyber_kun_video.mp4'
})

# Monitor active jobs
active_jobs = db.get_active_jobs()
for job in active_jobs:
    print(f"Job {job['id']}: {job['progress']}% - {job['status']}")

# Clean up
db.close()
```

## Database Schema

The module automatically creates the required `generation_jobs` table:

```sql
CREATE TABLE generation_jobs (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    character_name TEXT,
    duration REAL,
    style TEXT,
    status TEXT DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    output_path TEXT,
    error_message TEXT,
    metadata JSONB
);
```

## Integration Points

### With Job Manager
```python
from modules.database_manager import DatabaseManager
from modules.job_manager import JobManager

db = DatabaseManager()
db.initialize()

job_manager = JobManager(database=db)
```

### With ComfyUI Connector
```python
# Track ComfyUI generation progress
comfyui_job_id = "comfy_123"
db.update_job(comfyui_job_id, {
    'status': 'processing',
    'progress': 45,
    'metadata': {'current_step': 'latent_diffusion'}
})
```

### With Workflow Generator
```python
# Save workflow results
workflow_result = workflow_generator.generate_anime_workflow(prompt)
job_id = db.save_job({
    'prompt': prompt,
    'metadata': {'workflow_id': workflow_result['id']}
})
```

## Error Handling

```python
from modules.database_manager import DatabaseError

try:
    job_id = db.save_job(job_data)
except DatabaseError as e:
    logger.error(f"Database operation failed: {e.message}")
    # Handle gracefully - maybe retry or use fallback
```

## Testing

Run the test suite to verify functionality:

```bash
cd /opt/tower-anime-production
python3 test_database_manager.py
```

Expected output:
```
🧪 Testing Anime Production Database Manager
==================================================
1️⃣ Testing job creation...
   ✅ Created job: test_job_1234567890
...
🎉 All tests passed! Database Manager is ready for production use.
```

## Architecture Benefits

- **Modular Design**: Clean separation from business logic
- **Echo Brain Inspired**: Follows proven patterns from Echo Brain system
- **Production Ready**: Connection pooling and error handling
- **Type Safe**: Full type hints for better development experience
- **Thread Safe**: Can be used in multi-threaded environments
- **Testable**: Comprehensive test suite included

## Dependencies

- `psycopg2-binary` - PostgreSQL adapter
- `typing` - Type hints support

## Performance

- Connection pooling reduces overhead
- Indexed queries for fast lookups
- Batch operations support
- Memory-efficient cursor usage