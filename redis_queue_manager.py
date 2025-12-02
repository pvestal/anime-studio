#!/usr/bin/env python3
"""
Redis Queue Manager - Startup and Management Script
Manages Redis job queue workers and WebSocket server
"""

import asyncio
import argparse
import logging
import signal
import sys
import os
from datetime import datetime
from typing import List, Optional
import psutil

from redis_job_queue import RedisJobQueue, create_job_queue
from job_worker import JobWorker
from redis_websocket import start_websocket_server, progress_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RedisQueueManager:
    """Manages the entire Redis queue system"""

    def __init__(self):
        self.workers: List[JobWorker] = []
        self.websocket_server_task: Optional[asyncio.Task] = None
        self.running = False
        self.worker_count = 2  # Default number of workers
        self.websocket_port = 8329

    async def initialize(self):
        """Initialize the queue manager"""
        logger.info("🚀 Initializing Redis Queue Manager...")

        # Test Redis connection
        try:
            queue = await create_job_queue()
            await queue.cleanup_old_jobs(max_age_hours=1)  # Quick cleanup
            logger.info("✅ Redis connection successful")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            return False

        return True

    async def start_workers(self, count: int = None):
        """Start job workers"""
        if count is None:
            count = self.worker_count

        logger.info(f"👷 Starting {count} job workers...")

        for i in range(count):
            worker_id = f"worker-{i+1}"
            worker = JobWorker(worker_id)

            try:
                await worker.initialize()
                self.workers.append(worker)

                # Start worker in background
                asyncio.create_task(worker.start())
                logger.info(f"✅ Worker {worker_id} started")

            except Exception as e:
                logger.error(f"❌ Failed to start worker {worker_id}: {e}")

        logger.info(f"🎯 {len(self.workers)} workers started successfully")

    async def start_websocket_server(self, port: int = None):
        """Start WebSocket server for progress updates"""
        if port is None:
            port = self.websocket_port

        logger.info(f"🔌 Starting WebSocket server on port {port}...")

        try:
            self.websocket_server_task = asyncio.create_task(
                start_websocket_server("0.0.0.0", port)
            )
            logger.info(f"✅ WebSocket server started on port {port}")
        except Exception as e:
            logger.error(f"❌ Failed to start WebSocket server: {e}")

    async def stop_workers(self):
        """Stop all workers gracefully"""
        if not self.workers:
            return

        logger.info("🛑 Stopping workers...")

        # Stop all workers
        stop_tasks = []
        for worker in self.workers:
            stop_tasks.append(asyncio.create_task(worker.stop()))

        # Wait for all workers to stop
        await asyncio.gather(*stop_tasks, return_exceptions=True)

        self.workers.clear()
        logger.info("✅ All workers stopped")

    async def stop_websocket_server(self):
        """Stop WebSocket server"""
        if self.websocket_server_task:
            logger.info("🔌 Stopping WebSocket server...")
            self.websocket_server_task.cancel()
            try:
                await self.websocket_server_task
            except asyncio.CancelledError:
                pass
            self.websocket_server_task = None
            logger.info("✅ WebSocket server stopped")

    async def get_system_status(self) -> dict:
        """Get system status"""
        try:
            queue = await create_job_queue()
            stats = await queue.get_queue_stats()

            # System resources
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                "status": "running" if self.running else "stopped",
                "workers": {
                    "count": len(self.workers),
                    "running": sum(1 for w in self.workers if w.running)
                },
                "websocket_server": {
                    "running": self.websocket_server_task is not None,
                    "port": self.websocket_port,
                    "connections": len(progress_manager.connections) if progress_manager else 0
                },
                "queue_stats": stats,
                "system_resources": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "disk_free_gb": round(disk.free / (1024**3), 2),
                    "disk_percent": round((disk.used / disk.total) * 100, 1)
                },
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def maintenance_loop(self):
        """Perform periodic maintenance tasks"""
        logger.info("🧹 Starting maintenance loop...")

        while self.running:
            try:
                queue = await create_job_queue()

                # Cleanup old jobs (every hour)
                cleaned = await queue.cleanup_old_jobs(max_age_hours=24)
                if cleaned > 0:
                    logger.info(f"🧹 Cleaned {cleaned} old jobs")

                # Handle timeouts
                timeouts = await queue.handle_timeout_jobs()
                if timeouts > 0:
                    logger.warning(f"⏰ Handled {timeouts} timeout jobs")

                # Retry failed jobs (with backoff)
                retried = await queue.retry_failed_jobs()
                if retried > 0:
                    logger.info(f"🔄 Retried {retried} failed jobs")

                # Log system status every 5 minutes
                status = await self.get_system_status()
                logger.info(f"📊 System: {status['workers']['running']}/{status['workers']['count']} workers, "
                           f"{status['queue_stats'].get('total_queued', 0)} queued, "
                           f"{status['system_resources']['cpu_percent']}% CPU")

                # Wait 5 minutes
                await asyncio.sleep(300)

            except Exception as e:
                logger.error(f"❌ Maintenance error: {e}")
                await asyncio.sleep(60)

    async def start(self, worker_count: int = 2, websocket_port: int = 8329):
        """Start the entire Redis queue system"""
        self.worker_count = worker_count
        self.websocket_port = websocket_port
        self.running = True

        logger.info(f"🚀 Starting Redis Queue System...")

        # Initialize
        if not await self.initialize():
            logger.error("❌ Initialization failed")
            return False

        # Start components
        await self.start_workers(worker_count)
        await self.start_websocket_server(websocket_port)

        # Start maintenance loop
        maintenance_task = asyncio.create_task(self.maintenance_loop())

        # Set up signal handlers
        def signal_handler():
            logger.info("📝 Received shutdown signal")
            self.running = False

        if sys.platform != "win32":
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.add_signal_handler(signal.SIGTERM, signal_handler)

        logger.info("✅ Redis Queue System started successfully")
        logger.info(f"📊 Workers: {worker_count}, WebSocket: {websocket_port}")

        # Keep running until shutdown
        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("📝 Received keyboard interrupt")
            self.running = False

        # Shutdown
        logger.info("🛑 Shutting down Redis Queue System...")

        # Cancel maintenance
        maintenance_task.cancel()
        try:
            await maintenance_task
        except asyncio.CancelledError:
            pass

        # Stop components
        await self.stop_workers()
        await self.stop_websocket_server()

        logger.info("✅ Redis Queue System shutdown complete")
        return True

    async def stop(self):
        """Stop the system"""
        self.running = False

def create_systemd_service():
    """Create systemd service file"""
    service_content = """[Unit]
Description=Tower Anime Production Redis Queue Manager
After=network.target redis.service postgresql.service
Requires=redis.service

[Service]
Type=exec
User=patrick
Group=patrick
WorkingDirectory=/opt/tower-anime-production
Environment=PYTHONPATH=/opt/tower-anime-production
ExecStart=/opt/tower-anime-production/venv/bin/python redis_queue_manager.py --daemon --workers 3
ExecStop=/bin/kill -TERM $MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Resource limits
MemoryMax=2G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
"""

    service_file = "/etc/systemd/system/tower-anime-redis-queue.service"

    try:
        with open(service_file, 'w') as f:
            f.write(service_content)

        print(f"✅ Systemd service created: {service_file}")
        print("To enable and start:")
        print("  sudo systemctl daemon-reload")
        print("  sudo systemctl enable tower-anime-redis-queue")
        print("  sudo systemctl start tower-anime-redis-queue")

    except Exception as e:
        print(f"❌ Failed to create systemd service: {e}")

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Redis Queue Manager for Anime Production")

    parser.add_argument("--workers", type=int, default=2,
                       help="Number of worker processes (default: 2)")
    parser.add_argument("--websocket-port", type=int, default=8329,
                       help="WebSocket server port (default: 8329)")
    parser.add_argument("--daemon", action="store_true",
                       help="Run as daemon service")
    parser.add_argument("--status", action="store_true",
                       help="Show system status and exit")
    parser.add_argument("--create-service", action="store_true",
                       help="Create systemd service file and exit")

    args = parser.parse_args()

    if args.create_service:
        create_systemd_service()
        return

    manager = RedisQueueManager()

    if args.status:
        status = await manager.get_system_status()
        print(f"📊 Redis Queue System Status:")
        print(f"  Status: {status['status']}")
        print(f"  Workers: {status['workers']['running']}/{status['workers']['count']}")
        print(f"  WebSocket: {status['websocket_server']['running']} (port {status['websocket_server']['port']})")
        print(f"  Connections: {status['websocket_server']['connections']}")
        print(f"  Queue: {status['queue_stats'].get('total_queued', 0)} jobs")
        print(f"  System: CPU {status['system_resources']['cpu_percent']}%, RAM {status['system_resources']['memory_percent']}%")
        return

    # Start the system
    await manager.start(
        worker_count=args.workers,
        websocket_port=args.websocket_port
    )

if __name__ == "__main__":
    asyncio.run(main())