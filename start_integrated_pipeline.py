#!/usr/bin/env python3
"""
Startup script for the Integrated Anime Pipeline
Replaces the conflicting services with a unified, working system
"""

import asyncio
import logging
import sys
import os
import signal
from pathlib import Path

# Add paths
sys.path.append('/opt/tower-anime-production/pipeline')
sys.path.append('/opt/tower-anime-production/quality')

from integrated_anime_pipeline import IntegratedAnimePipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/tower-anime-production/pipeline.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class PipelineService:
    def __init__(self):
        self.pipeline = None
        self.running = False

    async def start(self):
        """Start the integrated pipeline service"""
        try:
            logger.info("🚀 Starting Integrated Anime Pipeline Service...")

            # Initialize pipeline
            self.pipeline = IntegratedAnimePipeline()
            await self.pipeline.initialize_pipeline()

            # Test the pipeline
            logger.info("🧪 Running initial pipeline test...")
            test_result = await self.pipeline.test_pipeline_integration()

            if test_result.get('test_completed', False):
                logger.info("✅ Pipeline test successful - Service ready for production")
            else:
                logger.warning(f"⚠️ Pipeline test had issues: {test_result.get('error', 'Unknown')}")

            # Mark as running
            self.running = True

            # Service loop
            logger.info("🎬 Integrated Anime Pipeline Service is now running...")
            logger.info("📊 Pipeline Statistics:")

            stats = await self.pipeline.get_pipeline_statistics()
            for component, status in stats.get('components', {}).items():
                logger.info(f"  - {component}: {status}")

            # Keep service alive
            while self.running:
                await asyncio.sleep(30)

                # Periodic status check
                if hasattr(self.pipeline, 'metrics_tracker'):
                    queue_status = await self.pipeline.metrics_tracker.get_generation_queue_status()
                    if queue_status.get('active_generations', 0) > 0:
                        logger.info(f"🎬 Active generations: {queue_status['active_generations']}")

        except Exception as e:
            logger.error(f"❌ Pipeline service error: {e}")
            raise

    async def stop(self):
        """Stop the pipeline service"""
        logger.info("🛑 Stopping Integrated Anime Pipeline Service...")
        self.running = False

        if self.pipeline:
            # End any active creative sessions
            if hasattr(self.pipeline.creative_director, 'creative_sessions'):
                for session_id in list(self.pipeline.creative_director.creative_sessions.keys()):
                    await self.pipeline.creative_director.end_creative_session(session_id)

        logger.info("✅ Pipeline service stopped gracefully")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    asyncio.create_task(service.stop())

async def main():
    """Main entry point"""
    global service
    service = PipelineService()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("🛑 Service interrupted by user")
    except Exception as e:
        logger.error(f"❌ Service failed: {e}")
        sys.exit(1)
    finally:
        await service.stop()

if __name__ == "__main__":
    asyncio.run(main())