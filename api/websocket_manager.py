"""
Production-ready WebSocket connection manager for real-time progress updates.
Handles multiple concurrent connections with automatic cleanup and error recovery.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional, Set

import psycopg2
import redis
from fastapi import WebSocket

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Production-ready WebSocket connection manager for anime production progress tracking.

    Features:
    - Multiple concurrent connections per job
    - Automatic cleanup of disconnected clients
    - Broadcast updates to all connected clients for a job
    - Database progress synchronization
    - Error handling and reconnection support
    """


    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        # Dictionary of job_id -> set of WebSocket connections
        self.connections: Dict[str, Set[WebSocket]] = {}
        # Track connection metadata
        self.connection_metadata: Dict[WebSocket, dict] = {}
        # Redis for pub/sub if needed
        self.redis_client = None
        try:
            self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
            self.redis_client.ping()
            logger.info("Redis connection established for WebSocket pub/sub")
        except Exception as e:
            logger.warning(f"Redis not available: {e}. Using direct WebSocket only.")

        # Database connection for progress sync
        self.db_config = {
            "host": "localhost",
            "database": "anime_production",
            "user": "patrick",
            "password": "tower_echo_brain_secret_key_2025",
        }


    async def connect(self, websocket: WebSocket, job_id: str, user_info: Optional[dict] = None):
        """
        Connect a WebSocket client to job progress updates.

        Args:
            websocket: FastAPI WebSocket instance
            job_id: Job ID to track
            user_info: Optional user metadata for connection tracking
        """
        await websocket.accept()

        # Initialize connections set for this job if needed
        if job_id not in self.connections:
            self.connections[job_id] = set()

        # Add connection to job's connection set
        self.connections[job_id].add(websocket)

        # Store connection metadata
        self.connection_metadata[websocket] = {
            "job_id": job_id,
            "user_info": user_info or {},
            "connected_at": datetime.now().isoformat(),
            "last_ping": time.time(),
        }

        logger.info(
            f"WebSocket connected for job {job_id}. Total connections: {len(self.connections[job_id])}"
        )

        # Send initial connection confirmation
        await self.send_to_connection(
            websocket,
            {
                "type": "connection",
                "status": "connected",
                "job_id": job_id,
                "message": "WebSocket connection established",
                "timestamp": datetime.now().isoformat(),
            },
        )


    async def disconnect(self, websocket: WebSocket):
        """
        Disconnect a WebSocket client with proper cleanup.

        Args:
            websocket: WebSocket connection to disconnect
        """
        if websocket in self.connection_metadata:
            metadata = self.connection_metadata[websocket]
            job_id = metadata["job_id"]

            # Remove from connections
            if job_id in self.connections:
                self.connections[job_id].discard(websocket)

                # Clean up empty connection sets
                if not self.connections[job_id]:
                    del self.connections[job_id]

            # Remove metadata
            del self.connection_metadata[websocket]

            logger.info(f"WebSocket disconnected from job {job_id}")


    async def send_to_connection(self, websocket: WebSocket, message: dict):
        """
        Send message to a specific WebSocket connection with error handling.

        Args:
            websocket: Target WebSocket connection
            message: Message dictionary to send
        """
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send message to WebSocket: {e}")
            # Clean up failed connection
            await self.disconnect(websocket)


    async def broadcast_to_job(self, job_id: str, message: dict):
        """
        Broadcast message to all connections for a specific job.

        Args:
            job_id: Job ID to broadcast to
            message: Message dictionary to broadcast
        """
        if job_id not in self.connections:
            logger.debug(f"No WebSocket connections for job {job_id}")
            return

        # Get copy of connections to avoid modification during iteration
        connections = self.connections[job_id].copy()
        disconnected_connections = set()

        for websocket in connections:
            try:
                await websocket.send_text(json.dumps(message))
                # Update last ping time
                if websocket in self.connection_metadata:
                    self.connection_metadata[websocket]["last_ping"] = time.time()
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket in job {job_id}: {e}")
                disconnected_connections.add(websocket)

        # Clean up failed connections
        for websocket in disconnected_connections:
            await self.disconnect(websocket)

        if disconnected_connections:
            logger.info(
                f"Cleaned up {len(disconnected_connections)} disconnected WebSockets for job {job_id}"
            )


    async def send_progress_update(
        self,
        job_id: str,
        progress: int,
        status: str,
        estimated_remaining: int = 0,
        output_path: Optional[str] = None,
        message: str = "",
        error: Optional[str] = None,
    ):
        """
        Send standardized progress update to all job connections.

        Args:
            job_id: Job ID
            progress: Progress percentage (0-100)
            status: Job status (queued, processing, completed, failed)
            estimated_remaining: Estimated seconds remaining
            output_path: Path to generated output (if completed)
            message: Optional status message
            error: Optional error message
        """
        progress_data = {
            "type": "progress",
            "job_id": job_id,
            "status": status,
            "progress": max(0, min(100, progress)),  # Clamp to 0-100
            "estimated_remaining": estimated_remaining,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }

        # Add optional fields if provided
        if output_path:
            progress_data["output_path"] = output_path
        if error:
            progress_data["error"] = error

        # Broadcast to WebSocket clients
        await self.broadcast_to_job(job_id, progress_data)

        # Sync to database
        await self.sync_progress_to_db(
            job_id, progress, status, estimated_remaining, output_path, error
        )

        # Publish to Redis for other services if available
        if self.redis_client:
            try:
                self.redis_client.publish(f"anime_progress:{job_id}", json.dumps(progress_data))
            except Exception as e:
                logger.warning(f"Failed to publish to Redis: {e}")


    async def sync_progress_to_db(
        self,
        job_id: str,
        progress: int,
        status: str,
        estimated_remaining: int,
        output_path: Optional[str],
        error: Optional[str],
    ):
        """
        Synchronize progress to database for persistence.

        Args:
            job_id: Job ID
            progress: Progress percentage
            status: Job status
            estimated_remaining: Estimated seconds remaining
            output_path: Output file path
            error: Error message if any
        """
        try:
            # Convert job_id to int if it's numeric (for database compatibility)
            try:
                job_id_int = int(job_id)
            except ValueError:
                # Skip database sync for non-numeric job IDs
                return

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Update jobs table with current progress
            update_query = """
                UPDATE jobs
                SET status = %s,
                    metadata = metadata || %s,
                    error_message = %s,
                    output_path = COALESCE(%s, output_path),
                    completed_at = CASE WHEN %s = 'completed' THEN NOW() ELSE completed_at END
                WHERE id = %s
            """

            metadata_update = json.dumps(
                {
                    "progress": progress,
                    "estimated_remaining": estimated_remaining,
                    "last_updated": datetime.now().isoformat(),
                }
            )

            cursor.execute(
                update_query, (status, metadata_update, error, output_path, status, job_id_int)
            )

            conn.commit()
            cursor.close()
            conn.close()

            logger.debug(f"Database progress synced for job {job_id}: {progress}% ({status})")

        except Exception as e:
            logger.error(f"Failed to sync progress to database for job {job_id}: {e}")


    async def get_job_connections_count(self, job_id: str) -> int:
        """
        Get number of active connections for a job.

        Args:
            job_id: Job ID

        Returns:
            Number of active connections
        """
        return len(self.connections.get(job_id, set()))


    async def get_all_connections_info(self) -> dict:
        """
        Get information about all active connections.

        Returns:
            Dictionary with connection statistics
        """
        total_connections = sum(len(conns) for conns in self.connections.values())
        jobs_with_connections = len(self.connections)

        # Get connection details
        connection_details = {}
        for job_id, connections in self.connections.items():
            connection_details[job_id] = {"connection_count": len(connections), "connections": []}

            for websocket in connections:
                if websocket in self.connection_metadata:
                    metadata = self.connection_metadata[websocket]
                    connection_details[job_id]["connections"].append(
                        {
                            "connected_at": metadata["connected_at"],
                            "user_info": metadata.get("user_info", {}),
                            "last_ping": metadata.get("last_ping", 0),
                        }
                    )

        return {
            "total_connections": total_connections,
            "jobs_with_connections": jobs_with_connections,
            "connection_details": connection_details,
            "timestamp": datetime.now().isoformat(),
        }


    async def cleanup_stale_connections(self, timeout_seconds: int = 300):
        """
        Clean up connections that haven't been active for timeout_seconds.

        Args:
            timeout_seconds: Connection timeout in seconds
        """
        current_time = time.time()
        stale_connections = []

        for websocket, metadata in self.connection_metadata.items():
            last_ping = metadata.get("last_ping", 0)
            if current_time - last_ping > timeout_seconds:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            logger.info(
                f"Cleaning up stale connection for job {self.connection_metadata[websocket]['job_id']}"
            )
            await self.disconnect(websocket)

        if stale_connections:
            logger.info(f"Cleaned up {len(stale_connections)} stale connections")


    async def ping_all_connections(self):
        """
        Send ping to all connections to check for stale ones.
        """
        ping_message = {"type": "ping", "timestamp": datetime.now().isoformat()}

        for job_id in self.connections.keys():
            await self.broadcast_to_job(job_id, ping_message)


# Global connection manager instance
connection_manager = ConnectionManager()


async def periodic_cleanup():
    """
    Periodic cleanup task for stale connections.
    Run this as a background task.
    """
    while True:
        try:
            await connection_manager.cleanup_stale_connections()
            await asyncio.sleep(60)  # Cleanup every minute
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")
            await asyncio.sleep(60)


async def periodic_ping():
    """
    Periodic ping task to detect stale connections.
    Run this as a background task.
    """
    while True:
        try:
            await connection_manager.ping_all_connections()
            await asyncio.sleep(30)  # Ping every 30 seconds
        except Exception as e:
            logger.error(f"Error in periodic ping: {e}")
            await asyncio.sleep(30)
