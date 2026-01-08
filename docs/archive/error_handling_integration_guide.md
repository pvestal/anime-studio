# Tower Anime Production - Error Handling Integration Guide

## Overview

This guide provides step-by-step instructions for integrating the enhanced error handling, logging, and quality assessment framework into the existing Tower anime production system.

## What We've Built

### 1. Comprehensive Error Handling Framework (`/opt/tower-anime-production/shared/error_handling.py`)

**Key Components:**
- **Structured Exception Hierarchy**: Custom exceptions with categorization and severity levels
- **Metrics Collection System**: Database-backed performance and error tracking
- **Circuit Breaker Pattern**: Prevents cascade failures for external services
- **Quality Assessment Framework**: Automatic validation of generated content
- **Learning System**: Analyzes failures to improve future generations
- **Retry Logic**: Exponential backoff for transient failures

**Example Custom Exceptions:**
```python
# Network errors with context
raise ComfyUIError(
    "Connection timeout",
    status_code=503,
    correlation_id="abc123"
)

# Quality validation errors
raise QualityValidationError(
    "Poor image quality detected",
    validation_type="technical_quality",
    quality_score=0.3
)
```

### 2. Enhanced Real Anime Service (`/opt/tower-anime-production/pipeline/enhanced_real_anime_service.py`)

**Improvements Over Original:**
- **Structured Logging**: JSON-formatted logs with correlation IDs
- **Performance Monitoring**: Tracks generation times, success rates, queue positions
- **Quality Assessment**: Background quality validation with user feedback integration
- **Circuit Breaker Integration**: Automatic failure detection and recovery
- **WebSocket Monitoring**: Real-time generation progress tracking
- **Learning Integration**: Failure pattern analysis and continuous improvement

## Integration Steps

### Step 1: Database Setup

Run the following SQL to create required tables:

```sql
-- Operation metrics table
CREATE TABLE IF NOT EXISTS anime_operation_metrics (
    id SERIAL PRIMARY KEY,
    operation_id VARCHAR(50) UNIQUE NOT NULL,
    operation_type VARCHAR(50) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    duration_seconds FLOAT,
    success BOOLEAN,
    error_details JSONB,
    context JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_operation_type_time ON anime_operation_metrics(operation_type, start_time);
CREATE INDEX idx_success_time ON anime_operation_metrics(success, start_time);

-- Error logs table
CREATE TABLE IF NOT EXISTS anime_error_logs (
    id SERIAL PRIMARY KEY,
    error_id VARCHAR(50) UNIQUE NOT NULL,
    message TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    context JSONB,
    stack_trace TEXT,
    timestamp TIMESTAMP NOT NULL,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_category_timestamp ON anime_error_logs(category, timestamp);
CREATE INDEX idx_severity_resolved ON anime_error_logs(severity, resolved);
```

### Step 2: Update Existing Services

#### Modify Existing `real_anime_service.py`:

```python
# Add imports
from shared.error_handling import (
    ComfyUIError, metrics_collector, comfyui_circuit_breaker,
    OperationMetrics, RetryManager
)

# Replace basic error handling
try:
    response = requests.post(f"{COMFYUI_URL}/prompt", json=payload)
    return response.json()
except Exception as e:
    print(f"Error: {e}")  # OLD
    return None
```

**With structured error handling:**
```python
async def queue_prompt_enhanced(self, workflow, correlation_id):
    metrics = OperationMetrics(
        operation_id=f"queue_{int(time.time())}",
        operation_type="comfyui_queue",
        start_time=datetime.utcnow()
    )

    try:
        async def _queue_request():
            response = requests.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": self.client_id},
                timeout=30
            )
            if response.status_code != 200:
                raise ComfyUIError(
                    f"Queue failed: {response.status_code}",
                    status_code=response.status_code,
                    correlation_id=correlation_id
                )
            return response.json()

        result = await comfyui_circuit_breaker.call(_queue_request)
        metrics.complete(True)
        await metrics_collector.log_operation(metrics)
        return result

    except Exception as e:
        metrics.complete(False, {"error": str(e)})
        await metrics_collector.log_operation(metrics)
        if isinstance(e, ComfyUIError):
            await metrics_collector.log_error(e)
        raise e
```

### Step 3: Environment Configuration

Update your service configuration:

```bash
# Database configuration
export TOWER_DB_HOST="192.168.50.135"
export TOWER_DB_NAME="tower_consolidated"
export TOWER_DB_USER="patrick"
export TOWER_DB_PASSWORD="your_password"

# Service URLs
export COMFYUI_URL="http://127.0.0.1:8188"
export ECHO_BRAIN_URL="http://192.168.50.135:8309"
export TOWER_KB_URL="https://192.168.50.135/kb"
```

### Step 4: Systemd Service Update

Update your systemd service file to use the enhanced version:

```ini
[Unit]
Description=Enhanced Tower Anime Production Service
After=network.target

[Service]
Type=simple
User=patrick
WorkingDirectory=/opt/tower-anime-production
Environment=PATH=/opt/tower-anime-production/venv/bin
ExecStart=/opt/tower-anime-production/venv/bin/python pipeline/enhanced_real_anime_service.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Step 5: Testing Integration

Test the enhanced error handling:

```bash
# Start enhanced service
cd /opt/tower-anime-production
python pipeline/enhanced_real_anime_service.py

# Test health endpoint
curl http://localhost:8352/api/health

# Test enhanced generation
curl -X POST http://localhost:8352/api/generate-enhanced \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "magical battle scene",
    "character": "Sakura",
    "quality_level": "high",
    "user_id": "test_user"
  }'

# Check metrics
curl http://localhost:8352/api/metrics/success-rate

# View failure analysis
curl http://localhost:8352/api/learning/failure-analysis
```

## Key Benefits

### 1. **Observability**
- **Correlation IDs**: Track requests across all services
- **Structured Logs**: JSON format for easy parsing and analysis
- **Performance Metrics**: Real-time success rates and timing data
- **Error Categorization**: Understand failure patterns and trends

### 2. **Reliability**
- **Circuit Breakers**: Prevent cascade failures
- **Retry Logic**: Handle transient network issues
- **Graceful Degradation**: Service remains available during partial failures
- **Health Checks**: Comprehensive dependency validation

### 3. **Quality Assurance**
- **Automatic Assessment**: Quality scoring for all generated content
- **User Feedback Integration**: Learn from user ratings and comments
- **Failure Pattern Analysis**: Identify and fix recurring issues
- **Continuous Improvement**: System learns and improves over time

### 4. **Developer Experience**
- **Rich Error Context**: Detailed error information for debugging
- **Performance Insights**: Identify bottlenecks and optimization opportunities
- **Learning Analytics**: Understand what works and what doesn't
- **Proactive Monitoring**: Catch issues before they impact users

## Monitoring and Alerts

### Database Queries for Monitoring

```sql
-- Success rate over last 24 hours
SELECT
    operation_type,
    COUNT(*) as total_operations,
    COUNT(*) FILTER (WHERE success = true) as successful_operations,
    ROUND(COUNT(*) FILTER (WHERE success = true) * 100.0 / COUNT(*), 2) as success_rate_percent
FROM anime_operation_metrics
WHERE start_time > NOW() - INTERVAL '24 hours'
GROUP BY operation_type;

-- Most common errors
SELECT
    category,
    severity,
    COUNT(*) as frequency
FROM anime_error_logs
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY category, severity
ORDER BY frequency DESC;

-- Average generation times
SELECT
    operation_type,
    AVG(duration_seconds) as avg_duration,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_seconds) as median_duration,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_seconds) as p95_duration
FROM anime_operation_metrics
WHERE success = true
AND start_time > NOW() - INTERVAL '24 hours'
GROUP BY operation_type;
```

### Grafana Dashboard Queries

```sql
-- Success rate over time (for Grafana)
SELECT
    time_bucket('1 hour', start_time) as time,
    operation_type,
    AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) as success_rate
FROM anime_operation_metrics
WHERE start_time > NOW() - INTERVAL '7 days'
GROUP BY time, operation_type
ORDER BY time;
```

## Next Steps

1. **Deploy Enhanced Service**: Replace current anime service with enhanced version
2. **Set Up Monitoring**: Create Grafana dashboards for metrics visualization
3. **Configure Alerts**: Set up alerts for high error rates or performance degradation
4. **Implement Learning**: Use failure analysis to continuously improve prompt generation
5. **User Feedback Loop**: Integrate user ratings into the learning system

## Maintenance

### Regular Tasks
- **Weekly**: Review error patterns and success rates
- **Monthly**: Analyze learning system recommendations
- **Quarterly**: Update circuit breaker thresholds based on performance data

### Database Maintenance
```sql
-- Clean old metrics (keep 30 days)
DELETE FROM anime_operation_metrics
WHERE start_time < NOW() - INTERVAL '30 days';

-- Archive old error logs (keep 90 days)
DELETE FROM anime_error_logs
WHERE timestamp < NOW() - INTERVAL '90 days';
```

This enhanced framework transforms the anime production system from basic error logging to an intelligent, self-improving platform that learns from every operation and continuously optimizes performance and quality.