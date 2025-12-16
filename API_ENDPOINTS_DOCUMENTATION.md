# 🎭 Anime Production API Documentation

**Base URL**: `http://localhost:8328`
**API Version**: 3.0.0-bulletproof
**Authentication**: Optional for most endpoints

---

## 📊 **WORKING PUBLIC ENDPOINTS**

### ✅ **System Status**
```bash
GET /api/anime/health
```
**Response**: System health, GPU status, job counts, features
```json
{
  "status": "healthy",
  "service": "secured-anime-production",
  "version": "3.0.0-bulletproof",
  "components": {
    "comfyui": {"status": "healthy", "queue_running": 0},
    "gpu": {"available": true, "active_generation": false},
    "jobs": {"active_count": 0, "total_tracked": 0}
  },
  "bulletproof_features": [
    "Real-time job status tracking",
    "WebSocket progress updates",
    "Structured file organization",
    "GPU resource management",
    "Character consistency checking",
    "Error handling and recovery",
    "Performance optimization (15 steps)"
  ]
}
```

### ✅ **View Jobs**
```bash
GET /api/anime/jobs
```
**Response**: List all generation jobs (anonymous) or user jobs (authenticated)
```json
{
  "jobs": [],
  "count": 0,
  "user": "anonymous"
}
```

### ✅ **Gallery**
```bash
GET /api/anime/gallery
```
**Response**: Public gallery content
```json
{
  "message": "Public gallery",
  "gallery": "Limited gallery content"
}
```

### ✅ **Production Phases**
```bash
GET /api/anime/phases
```
**Response**: 3-phase production workflow
```json
{
  "phases": [
    {
      "id": 1,
      "name": "CHARACTER_SHEET",
      "description": "Static character reference",
      "engine": "IPAdapter",
      "output": "8-pose sheet"
    },
    {
      "id": 2,
      "name": "ANIMATION_LOOP",
      "description": "Short loops",
      "engine": "AnimateDiff",
      "output": "2-second loops"
    },
    {
      "id": 3,
      "name": "FULL_VIDEO",
      "description": "Complete videos",
      "engine": "SVD",
      "output": "5-second videos"
    }
  ],
  "workflow": "Phase 1 to Phase 2 to Phase 3",
  "quality_gates": "80% quality required per phase"
}
```

---

## 🚧 **ENDPOINTS UNDER REPAIR**

### ⚠️ **Generate Anime** (Public but has errors)
```bash
POST /api/anime/generate
Content-Type: application/json

{
  "prompt": "anime girl with blue hair",
  "width": 512,
  "height": 512,
  "steps": 10
}
```
**Status**: Returns `Internal Server Error` - needs ComfyUI connection fix

### ⚠️ **Job Status**
```bash
GET /api/anime/generation/{job_id}/status
```
**Status**: Available but no jobs to track yet

---

## 🔗 **WEBSOCKET ENDPOINTS**

### **Real-time Progress**
```javascript
ws://localhost:8328/ws/job/{job_id}
```
**Purpose**: Live generation progress updates
**Features**: Progress percentage, ETA, stage info

---

## 🔒 **ADMIN ENDPOINTS** (Auth Required)

### **Admin Statistics**
```bash
GET /api/anime/admin/stats
Authorization: Bearer <token>
```
**Purpose**: System analytics and performance metrics

### **Orchestration**
```bash
POST /api/anime/orchestrate
Authorization: Bearer <token>
```
**Purpose**: Complex multi-step generation workflows

---

## 🎯 **SYSTEM FEATURES**

**✅ Working Components**:
- Health monitoring and system status
- Job tracking and queue management
- Gallery and phase workflow display
- WebSocket real-time updates
- Public access (no auth required for core features)

**🔧 Needs Connection Fixes**:
- ComfyUI integration for actual generation
- File output management
- Error handling in generation pipeline

**🚀 Advanced Features**:
- Character consistency via IP-Adapter
- 3-phase production workflow (Character → Loop → Video)
- GPU resource optimization
- Performance monitoring (15-step optimization)

---

## 📋 **QUICK TEST COMMANDS**

```bash
# Test system health
curl http://localhost:8328/api/anime/health

# View production phases
curl http://localhost:8328/api/anime/phases

# Check jobs queue
curl http://localhost:8328/api/anime/jobs

# View gallery
curl http://localhost:8328/api/anime/gallery

# Test generation (currently errors)
curl -X POST http://localhost:8328/api/anime/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"anime girl","width":512,"height":512,"steps":10}'
```

---

**Status**: ✅ Core API infrastructure working
**Next**: Fix ComfyUI connection for actual generation
**Updated**: 2025-12-15