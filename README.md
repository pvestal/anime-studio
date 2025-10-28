# Tower Anime Production Service

Unified anime production system integrating professional workflows with personal creative tools.

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
- Automated quality scoring
- Human feedback integration
- Continuous improvement tracking

### `/personal/` - Personal Creative Tools
- Personal media analysis
- Creative enlightenment features
- Biometric integration for mood-based generation

## Integration Points

- **Port**: 8300 (following Tower service pattern)
- **Database**: tower_consolidated.anime_production schema
- **Auth**: Tower auth service (port 8088)
- **ComfyUI**: Port 8188 integration
- **Echo Brain**: AI assistance integration

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