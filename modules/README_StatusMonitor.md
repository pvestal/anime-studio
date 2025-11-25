# StatusMonitor Module Documentation

## Overview

The StatusMonitor module provides comprehensive real-time job progress tracking for the anime production system. It addresses the broken job status API by directly interfacing with ComfyUI's `/queue` and `/history` endpoints.

## Key Features

- **Direct ComfyUI Integration**: Bypasses broken job status API by polling ComfyUI directly
- **Real-time WebSocket Updates**: Live progress broadcasting to connected clients
- **Performance Statistics**: Tracks generation times and failure patterns
- **Progress Estimation**: Intelligent completion time estimation based on historical data
- **Robust Error Handling**: Handles timeouts, connection failures, and job crashes
- **Callback System**: Extensible progress notification system

## Core Components

### StatusMonitor Class

Main monitoring class that orchestrates all job tracking functionality.

```python
from modules.status_monitor import StatusMonitor, ProgressUpdate

# Create and start monitor
monitor = StatusMonitor(
    poll_interval=2.0,      # How often to poll ComfyUI (seconds)
    websocket_port=8329     # Port for WebSocket server
)
await monitor.start_monitoring()
```

### ProgressUpdate Data Structure

Standardized progress information:

```python
@dataclass
class ProgressUpdate:
    job_id: int                           # Internal job ID
    comfyui_prompt_id: str               # ComfyUI prompt ID
    status: ProgressStatus               # Current status
    progress_percent: float = 0.0        # 0-100% completion
    current_step: int = 0                # Current processing step
    total_steps: int = 0                 # Total expected steps
    estimated_completion: datetime = None # ETA
    generation_time: float = None        # Actual time taken
    error_message: str = None            # Error details if failed
```

### Progress Status Types

```python
class ProgressStatus(Enum):
    UNKNOWN = "unknown"
    QUEUED = "queued"            # Waiting in ComfyUI queue
    INITIALIZING = "initializing" # Job submitted, not yet in queue
    PROCESSING = "processing"     # Currently generating
    COMPLETING = "completing"     # Final processing
    COMPLETED = "completed"       # Successfully finished
    FAILED = "failed"            # Generation failed
    TIMEOUT = "timeout"          # Job disappeared/timed out
```

## Basic Usage

### 1. Monitor a Job

```python
# Start monitoring a specific job
job_id = 123
comfyui_prompt_id = "prompt_456789"
job_type = "video"  # For statistics tracking

success = monitor.monitor_job(job_id, comfyui_prompt_id, job_type)

# Check progress
progress = await monitor.get_progress(job_id)
print(f"Status: {progress.status.value}")
print(f"Progress: {progress.progress_percent}%")

# Estimate completion
eta = await monitor.estimate_completion(job_id)
print(f"ETA: {eta}")
```

### 2. Progress Callbacks

```python
def my_progress_callback(update: ProgressUpdate):
    """Handle progress updates"""
    print(f"Job {update.job_id}: {update.status.value} - {update.progress_percent}%")

    if update.status == ProgressStatus.COMPLETED:
        print(f"Completed in {update.generation_time}s")
    elif update.status == ProgressStatus.FAILED:
        print(f"Failed: {update.error_message}")

# Add callback
monitor.add_progress_callback(my_progress_callback)
```

### 3. WebSocket Integration

The monitor automatically starts a WebSocket server for real-time updates:

```javascript
// Connect from frontend
const ws = new WebSocket('ws://localhost:8329');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);

    if (data.type === 'progress_update') {
        updateProgressBar(data.data.job_id, data.data.progress_percent);
    }
};

// Request specific job progress
ws.send(JSON.stringify({
    type: 'get_job_progress',
    job_id: 123
}));
```

## Integration with Anime Production API

### API Endpoint Integration

```python
from modules.status_monitor import create_status_monitor
from fastapi import FastAPI, WebSocket

app = FastAPI()

# Global monitor instance
monitor = None

@app.on_event("startup")
async def startup():
    global monitor
    monitor = await create_status_monitor(auto_start=True)

@app.post("/api/anime/generate")
async def generate_video(request: GenerationRequest):
    # Submit to ComfyUI
    async with ComfyUIConnector() as connector:
        prompt_id = await connector.submit_workflow(workflow, client_id)

    if prompt_id:
        # Start monitoring the job
        monitor.monitor_job(job.id, prompt_id, "video")

        return {"job_id": job.id, "status": "submitted", "prompt_id": prompt_id}
    else:
        return {"error": "Failed to submit to ComfyUI"}

@app.get("/api/anime/jobs/{job_id}/progress")
async def get_job_progress(job_id: int):
    progress = await monitor.get_progress(job_id)
    if progress:
        return {
            "job_id": progress.job_id,
            "status": progress.status.value,
            "progress": progress.progress_percent,
            "estimated_completion": progress.estimated_completion,
            "error": progress.error_message
        }
    else:
        return {"error": "Job not found"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Add to monitor's client list or implement custom handling
```

### Database Integration

The monitor can work with the existing database manager:

```python
from modules.database_manager import DatabaseManager

# Initialize with database support
db_manager = DatabaseManager()
monitor = StatusMonitor(database_manager=db_manager)

# Jobs will be automatically updated in database when they complete
```

## Performance Statistics

The monitor collects performance data for optimization:

```python
# Get current statistics
stats = await monitor.get_queue_statistics()

# Example output:
{
    "running_jobs": 1,
    "pending_jobs": 2,
    "monitored_jobs": 3,
    "generation_stats": {
        "completion_times": {
            "video": {
                "count": 50,
                "median": 120.5,
                "mean": 125.3,
                "min": 45.2,
                "max": 450.1
            }
        },
        "average_step_duration": 2.5,
        "failure_patterns": {
            "video:CUDA out of memory": 5,
            "video:Connection timeout": 2
        }
    }
}
```

## Error Handling

The monitor includes robust error handling:

1. **ComfyUI Connection Failures**: Automatic retry with exponential backoff
2. **Job Timeouts**: Configurable timeout detection for stuck jobs
3. **WebSocket Errors**: Graceful client disconnect handling
4. **Database Errors**: Non-blocking database updates

## Configuration Options

```python
monitor = StatusMonitor(
    comfyui_connector=custom_connector,  # Custom ComfyUI connector
    database_manager=db_manager,         # Database integration
    poll_interval=2.0,                   # Polling frequency (seconds)
    websocket_port=8329,                 # WebSocket server port
)
```

## Production Deployment

### 1. Service Integration

Add to your systemd service or Docker configuration:

```python
# In main application
async def main():
    monitor = await create_status_monitor(auto_start=True)

    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        await monitor.stop_monitoring()
```

### 2. Monitoring and Alerting

```python
def failure_alert_callback(update: ProgressUpdate):
    """Send alerts on job failures"""
    if update.status == ProgressStatus.FAILED:
        send_alert(f"Job {update.job_id} failed: {update.error_message}")

monitor.add_progress_callback(failure_alert_callback)
```

### 3. Load Balancing

For multiple ComfyUI instances:

```python
# Create monitors for each instance
monitors = []
for port in [8188, 8189, 8190]:
    connector = ComfyUIConnector(f"http://192.168.50.135:{port}")
    monitor = StatusMonitor(connector, websocket_port=8329 + port - 8188)
    await monitor.start_monitoring()
    monitors.append(monitor)
```

## Troubleshooting

### Common Issues

1. **Jobs showing TIMEOUT status**: Check ComfyUI is responding and not stuck
2. **WebSocket connection failures**: Verify port is not blocked by firewall
3. **No progress updates**: Ensure job was properly submitted to ComfyUI
4. **Memory leaks**: Monitor will automatically cleanup completed jobs

### Debug Mode

```python
import logging
logging.getLogger('modules.status_monitor').setLevel(logging.DEBUG)

# This will show detailed polling and progress information
```

## Testing

Run the included test suite:

```bash
cd /opt/tower-anime-production
python3 test_status_monitor.py
```

This validates all core functionality including ComfyUI connectivity, progress tracking, and WebSocket communication.

## Future Enhancements

Planned improvements:

1. **Node-level Progress**: Detailed progress for each ComfyUI node
2. **GPU Metrics**: VRAM usage and GPU utilization tracking
3. **Batch Job Support**: Multi-job batch progress tracking
4. **Advanced Analytics**: ML-based completion time prediction
5. **Visual Dashboard**: Web-based monitoring interface