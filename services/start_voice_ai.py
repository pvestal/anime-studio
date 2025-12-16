#!/usr/bin/env python3
"""
Voice AI Service Startup Script
Orchestrates the complete voice AI system for anime production
Handles service initialization, health checks, and error recovery
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import asyncpg
import uvicorn
from voice_api_endpoints import app
from audio_manager import AudioManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/tower-anime-production/logs/voice_ai.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VoiceAIServiceManager:
    """Manages the complete Voice AI service lifecycle"""

    def __init__(self):
        self.services = {}
        self.db_pool: Optional[asyncpg.Pool] = None
        self.audio_manager: Optional[AudioManager] = None
        self.shutdown_event = asyncio.Event()
        self.startup_time = time.time()

        # Configuration
        self.config = {
            "host": "0.0.0.0",
            "port": 8319,
            "log_level": "info",
            "workers": 1,
            "db_host": "192.168.50.135",
            "db_name": "tower_consolidated",
            "db_user": "patrick",
            "db_password": "tower_echo_brain_secret_key_2025"
        }

        # Service health tracking
        self.health_status = {
            "database": False,
            "audio_manager": False,
            "voice_service": False,
            "echo_brain": False,
            "last_health_check": None
        }

    async def initialize_services(self):
        """Initialize all required services"""
        try:
            logger.info("🚀 Initializing Voice AI Service Manager")

            # Initialize database connection
            await self.initialize_database()

            # Initialize audio manager
            await self.initialize_audio_manager()

            # Initialize database schema
            await self.initialize_database_schema()

            # Check external service dependencies
            await self.check_external_services()

            # Set up signal handlers
            self.setup_signal_handlers()

            logger.info("✅ Voice AI Service Manager initialization completed")

        except Exception as e:
            logger.error(f"❌ Service manager initialization failed: {e}")
            raise

    async def initialize_database(self):
        """Initialize database connection pool"""
        try:
            self.db_pool = await asyncpg.create_pool(
                host=self.config["db_host"],
                database=self.config["db_name"],
                user=self.config["db_user"],
                password=self.config["db_password"],
                min_size=5,
                max_size=20,
                command_timeout=30
            )

            # Test connection
            async with self.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

            self.health_status["database"] = True
            logger.info("✅ Database connection pool initialized")

        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            self.health_status["database"] = False
            raise

    async def initialize_audio_manager(self):
        """Initialize audio management system"""
        try:
            self.audio_manager = AudioManager(self.db_pool)
            await self.audio_manager.initialize()

            self.health_status["audio_manager"] = True
            logger.info("✅ Audio manager initialized")

        except Exception as e:
            logger.error(f"❌ Audio manager initialization failed: {e}")
            self.health_status["audio_manager"] = False
            raise

    async def initialize_database_schema(self):
        """Initialize required database tables"""
        try:
            # Voice AI schema
            voice_schema_path = Path(__file__).parent.parent / "database" / "voice_ai_schema.sql"
            if voice_schema_path.exists():
                async with self.db_pool.acquire() as conn:
                    with open(voice_schema_path, 'r') as f:
                        schema_sql = f.read()
                    await conn.execute(schema_sql)

                logger.info("✅ Voice AI database schema initialized")

            # Audio manager schema
            from audio_manager import AUDIO_MANAGER_SCHEMA
            async with self.db_pool.acquire() as conn:
                await conn.execute(AUDIO_MANAGER_SCHEMA)

            logger.info("✅ Audio manager database schema initialized")

        except Exception as e:
            logger.error(f"❌ Database schema initialization failed: {e}")
            # Don't raise here - schema might already exist

    async def check_external_services(self):
        """Check availability of external services"""
        try:
            import httpx

            # Check Echo Brain
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get("http://localhost:8309/api/echo/health")
                    if response.status_code == 200:
                        self.health_status["echo_brain"] = True
                        logger.info("✅ Echo Brain service available")
                    else:
                        self.health_status["echo_brain"] = False
                        logger.warning("⚠️  Echo Brain service not responding")
            except Exception as e:
                self.health_status["echo_brain"] = False
                logger.warning(f"⚠️  Echo Brain service unavailable: {e}")

            # Check anime API
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get("http://localhost:8328/api/anime/health")
                    if response.status_code == 200:
                        logger.info("✅ Anime production service available")
                    else:
                        logger.warning("⚠️  Anime production service not responding")
            except Exception as e:
                logger.warning(f"⚠️  Anime production service unavailable: {e}")

        except Exception as e:
            logger.error(f"❌ External service check failed: {e}")

    def setup_signal_handlers(self):
        """Set up graceful shutdown signal handlers"""
        def signal_handler(signum, frame):
            logger.info(f"📡 Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self.shutdown())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def start_health_monitoring(self):
        """Start background health monitoring"""
        while not self.shutdown_event.is_set():
            try:
                await self.perform_health_check()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"❌ Health monitoring error: {e}")
                await asyncio.sleep(10)

    async def perform_health_check(self):
        """Perform comprehensive health check"""
        try:
            self.health_status["last_health_check"] = datetime.now().isoformat()

            # Check database
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                self.health_status["database"] = True
            except Exception:
                self.health_status["database"] = False

            # Check audio manager
            if self.audio_manager:
                try:
                    cache_size = await self.audio_manager.get_cache_size()
                    self.health_status["audio_manager"] = True
                except Exception:
                    self.health_status["audio_manager"] = False

            # Log health status
            healthy_services = sum(1 for status in self.health_status.values() if status is True)
            total_services = len([k for k, v in self.health_status.items() if isinstance(v, bool)])

            if healthy_services == total_services:
                logger.info(f"💚 All services healthy ({healthy_services}/{total_services})")
            else:
                logger.warning(f"⚠️  Service health: {healthy_services}/{total_services} healthy")
                for service, status in self.health_status.items():
                    if isinstance(status, bool) and not status:
                        logger.warning(f"  ❌ {service}: unhealthy")

        except Exception as e:
            logger.error(f"❌ Health check error: {e}")

    async def get_service_status(self) -> Dict:
        """Get comprehensive service status"""
        uptime = time.time() - self.startup_time

        # Get database statistics
        db_stats = None
        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    voice_jobs = await conn.fetchval(
                        "SELECT COUNT(*) FROM voice_generation_jobs"
                    )
                    characters = await conn.fetchval(
                        "SELECT COUNT(*) FROM voice_profiles"
                    )
                    db_stats = {
                        "voice_jobs": voice_jobs,
                        "character_profiles": characters
                    }
            except Exception as e:
                logger.error(f"Error getting database stats: {e}")

        # Get audio manager statistics
        audio_stats = None
        if self.audio_manager:
            try:
                audio_stats = await self.audio_manager.get_storage_statistics()
            except Exception as e:
                logger.error(f"Error getting audio stats: {e}")

        return {
            "service": "voice-ai-system",
            "status": "operational",
            "uptime_seconds": uptime,
            "startup_time": datetime.fromtimestamp(self.startup_time).isoformat(),
            "health_status": self.health_status,
            "configuration": {
                "host": self.config["host"],
                "port": self.config["port"],
                "workers": self.config["workers"]
            },
            "database_stats": db_stats,
            "audio_stats": audio_stats,
            "timestamp": datetime.now().isoformat()
        }

    async def start_voice_api_server(self):
        """Start the main Voice AI API server"""
        try:
            # Configure the FastAPI app with our services
            app.state.db_pool = self.db_pool
            app.state.audio_manager = self.audio_manager
            app.state.service_manager = self

            # Configure uvicorn
            config = uvicorn.Config(
                app,
                host=self.config["host"],
                port=self.config["port"],
                log_level=self.config["log_level"],
                access_log=True,
                use_colors=True
            )

            server = uvicorn.Server(config)

            self.health_status["voice_service"] = True
            logger.info(f"🌐 Voice AI API server starting on {self.config['host']}:{self.config['port']}")

            # Start server
            await server.serve()

        except Exception as e:
            logger.error(f"❌ Voice API server error: {e}")
            self.health_status["voice_service"] = False
            raise

    async def shutdown(self):
        """Graceful shutdown of all services"""
        try:
            logger.info("🔄 Initiating graceful shutdown...")

            # Set shutdown event
            self.shutdown_event.set()

            # Close audio manager
            if self.audio_manager:
                logger.info("🔄 Shutting down audio manager...")
                # Add any cleanup needed

            # Close database connections
            if self.db_pool:
                logger.info("🔄 Closing database connections...")
                await self.db_pool.close()

            logger.info("✅ Voice AI service shutdown completed")

        except Exception as e:
            logger.error(f"❌ Shutdown error: {e}")

    async def run(self):
        """Main service execution"""
        try:
            await self.initialize_services()

            # Start background tasks
            tasks = [
                asyncio.create_task(self.start_health_monitoring()),
                asyncio.create_task(self.start_voice_api_server())
            ]

            # Wait for shutdown or task completion
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            logger.error(f"❌ Service execution error: {e}")
            raise
        finally:
            await self.shutdown()

# Additional utility functions
def create_service_config() -> Dict:
    """Create service configuration from environment variables"""
    return {
        "host": os.getenv("VOICE_AI_HOST", "0.0.0.0"),
        "port": int(os.getenv("VOICE_AI_PORT", "8319")),
        "log_level": os.getenv("VOICE_AI_LOG_LEVEL", "info"),
        "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY"),
        "db_host": os.getenv("DB_HOST", "192.168.50.135"),
        "db_name": os.getenv("DB_NAME", "tower_consolidated"),
        "db_user": os.getenv("DB_USER", "patrick"),
        "db_password": os.getenv("DB_PASSWORD", "tower_echo_brain_secret_key_2025")
    }

def setup_environment():
    """Set up environment for voice AI service"""
    try:
        # Create required directories
        directories = [
            "/opt/tower-anime-production/logs",
            "/mnt/1TB-storage/ComfyUI/output/voice",
            "/mnt/1TB-storage/ComfyUI/output/voice/cache",
            "/mnt/1TB-storage/ComfyUI/output/voice/temp",
            "/mnt/1TB-storage/ComfyUI/output/voice/optimized",
            "/mnt/1TB-storage/ComfyUI/output/dialogue"
        ]

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

        # Set up logging directory permissions
        os.chmod("/opt/tower-anime-production/logs", 0o755)

        logger.info("✅ Environment setup completed")

    except Exception as e:
        logger.error(f"❌ Environment setup failed: {e}")
        raise

async def main():
    """Main entry point"""
    try:
        # Banner
        print("🎭" + "=" * 58 + "🎭")
        print("🎬  Tower Anime Production - Voice AI Service v1.0.0  🎬")
        print("🎭" + "=" * 58 + "🎭")
        print()

        # Setup environment
        setup_environment()

        # Create and run service manager
        service_manager = VoiceAIServiceManager()
        await service_manager.run()

    except KeyboardInterrupt:
        logger.info("👋 Voice AI service stopped by user")
    except Exception as e:
        logger.error(f"💥 Voice AI service crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Ensure we're in the correct directory
    os.chdir("/opt/tower-anime-production")

    # Run the service
    asyncio.run(main())