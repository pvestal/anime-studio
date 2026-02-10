# Tower Anime Production Service

Unified anime production system with Echo Brain integration, SSOT content management, and comprehensive testing.

## Status 🟡
- **API Service**: ✅ Running on port 8328 (tower-anime-production.service)
- **Echo Brain Integration**: ✅ MCP API at 8309 functional
- **Quality Contract**: ✅ video_contract.py validates structural, motion, visual gates
- **SSOT Orchestrator**: ✅ ssot_generation_orchestrator.py manages character generation
- **Video Generation**: ⚠️ AnimateDiff requires batch_size≥16 (smoke test issue)
- **Character LoRAs**: ⚠️ Not properly integrated in pipeline
- **Authentication**: ✅ JWT-based with Vault integration

## Current Capabilities

### 🧠 Echo Brain Integration
- **Character Creation**: Detailed anime character generation
- **Story Development**: Multi-scene narrative creation
- **Code Generation**: Python/Pydantic model creation
- **Notifications**: Real-time alert system (149+ endpoints)
- **Agent Development**: Autonomous agent framework

### 📋 SSOT Content Management
- **Content Ratings**: Project rating and classification system
- **Style Templates**: Reusable visual style components
- **Component Library**: Shared asset management

### 🎯 Echo Orchestration Engine
- **Workflow Coordination**: Multi-step process management
- **User Intent Analysis**: Context-aware request handling
- **Learning Adaptation**: Persistent preference memory

## Quick Start

```bash
# Start services
sudo systemctl start tower-anime-production
sudo systemctl start tower-echo-brain

# Frontend development
cd frontend && npm run dev

# API Documentation
open http://localhost:8328/docs
open http://localhost:8309/docs
```

## Testing Status
- ✅ E2E Generation: 100% pass rate (fixed with KSampler seed randomization)
- ✅ Quality Contract: Validates frame count, motion (optical flow), visual quality
- ✅ SSOT Recording: generation_validation + generation_quality_feedback tables
- ⚠️ Video Generation: Works with batch_size≥16, fails with batch_size=1
- ✅ API Service: Swagger docs at http://localhost:8328/docs
- ✅ Workflow Fix: All 12 workflows have SaveImage nodes for output tracking

## Architecture

### `/api/` - REST API Service
- FastAPI-based service following Tower patterns
- Integration with Tower auth, database, and monitoring
- Professional production endpoints + personal creative APIs

### `/pipeline/` - Production Pipeline
- ComfyUI workflow integration
- Video generation and processing
- Quality assessment automation

### `/models/` - AI Model Management
- Model loading and caching
- Style consistency training
- Personal preference learning

### `/quality/` - Quality Assessment
- **video_contract.py**: Validates structural, motion, and visual quality gates
- **echo_brain_reviewer.py**: Learning loop with pattern analysis via Ollama
- **generation_quality_feedback table**: Tracks all quality metrics and learned patterns
- Automated quality scoring with hard pass/fail gates
- Human feedback integration for override scores
- Continuous improvement through Echo Brain analysis

### `/personal/` - Personal Creative Tools
- Personal media analysis
- Creative enlightenment features
- Biometric integration for mood-based generation

## Known Issues & Solutions

### 🔴 Critical: Video Generation Quality
**Problem**: AnimateDiff produces 1-frame "videos" when batch_size < 16
**Root Cause**: Smoke test overrides batch_size=1 for speed, breaking motion generation
**Solution**: Fixed in tower_anime_smoke_test.py - detects AnimateDiff and preserves batch_size≥16

### 🟡 Warning: Character LoRA Integration
**Problem**: Character-specific LoRAs not being loaded in generation pipeline
**Impact**: Generic output instead of character-accurate generation
**Required**: Integration with character_generation_settings and lora_path fields

### 🟢 Fixed: ComfyUI Cache Issue
**Problem**: Identical parameters returned cached empty results
**Solution**: Randomize KSampler seed on every generation

## Integration Points

- **API**: Port 8328 (tower-anime-production.service)
- **Database**: anime_production (PostgreSQL)
- **Auth**: Tower auth service (port 8088)
- **ComfyUI**: Port 8188 integration
- **Echo Brain**: Port 8309 (MCP + API)
- **SSOT Orchestrator**: ssot_generation_orchestrator.py

## Development

```bash
# Start development server
cd services/anime-production
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python api/main.py
```

## Deployment

```bash
# Deploy to production
./deploy-anime-production.sh
sudo systemctl start tower-anime-production
```