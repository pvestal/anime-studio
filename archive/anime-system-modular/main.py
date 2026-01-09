"""
Tower Anime Production System - Main Application
FastAPI service integrating with ComfyUI and Echo Brain
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import anime
from backend.services.character_consistency import CharacterConsistencyService
from backend.services.quality_metrics import QualityMetricsService
from echo_integration.echo_client import EchoBrainClient, EchoWebhookHandlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DATABASE_URL = "postgresql://anime:anime@localhost:5432/anime_production"
COMFYUI_URL = "http://192.168.50.135:8188"
ECHO_BRAIN_URL = "http://192.168.50.135:8309"

# Global service instances
db_pool: asyncpg.Pool = None
character_service: CharacterConsistencyService = None
quality_service: QualityMetricsService = None
echo_client: EchoBrainClient = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager"""
    global db_pool, character_service, quality_service, echo_client
    
    # Startup
    logger.info("Starting Tower Anime Production System...")
    
    # Initialize database pool
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=20
    )
    logger.info("Database pool created")
    
    # Initialize services
    character_service = CharacterConsistencyService(db_pool)
    await character_service.initialize()
    logger.info("Character consistency service initialized")
    
    quality_service = QualityMetricsService(db_pool, character_service)
    await quality_service.initialize()
    logger.info("Quality metrics service initialized")
    
    # Initialize Echo Brain client
    echo_client = EchoBrainClient(
        echo_url=ECHO_BRAIN_URL,
        anime_callback_url="http://192.168.50.135:8328/api/anime/echo"
    )
    try:
        await echo_client.connect()
        logger.info("Connected to Echo Brain")
    except Exception as e:
        logger.warning(f"Could not connect to Echo Brain: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    if echo_client:
        await echo_client.disconnect()
    if db_pool:
        await db_pool.close()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Tower Anime Production System",
    description="GPU-accelerated anime generation with Echo Brain orchestration",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency overrides
async def get_db_pool():
    return db_pool

async def get_character_service():
    return character_service

async def get_quality_service():
    return quality_service

async def get_comfyui_client():
    # Return your existing ComfyUI client
    # This is a placeholder - integrate with your current implementation
    return None

async def get_echo_client():
    return echo_client


# Override router dependencies
app.dependency_overrides[anime.get_db_pool] = get_db_pool
app.dependency_overrides[anime.get_character_service] = get_character_service
app.dependency_overrides[anime.get_quality_service] = get_quality_service
app.dependency_overrides[anime.get_comfyui_client] = get_comfyui_client

# Include routers
app.include_router(anime.router)


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """System health check"""
    db_status = "connected" if db_pool else "disconnected"
    echo_status = "connected" if echo_client and echo_client._registered else "disconnected"
    
    return {
        "status": "healthy",
        "version": "2.0.0",
        "services": {
            "database": db_status,
            "character_consistency": "ready" if character_service else "not initialized",
            "quality_metrics": "ready" if quality_service else "not initialized",
            "echo_brain": echo_status,
            "comfyui": "http://192.168.50.135:8188"
        }
    }


# Echo Brain webhook endpoint
@app.post("/api/anime/echo/webhook")
async def echo_webhook(payload: dict):
    """Handle webhooks from Echo Brain"""
    if not echo_client:
        return {"error": "Echo client not initialized"}
    
    handlers = EchoWebhookHandlers(
        db_pool, character_service, quality_service, None
    )
    
    await echo_client.handle_webhook(
        payload.get("event_type"),
        payload.get("data", {}),
        handlers.get_handlers()
    )
    
    return {"received": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8328,
        reload=True
    )
