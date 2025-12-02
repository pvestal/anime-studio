#!/usr/bin/env python3
"""
WebSocket Integration for Redis Job Queue
Provides real-time progress updates for anime generation jobs
"""

import asyncio
import json
import logging
import websockets
from websockets.server import WebSocketServerProtocol
from typing import Set, Dict, Any
from datetime import datetime
import redis.asyncio as redis
from redis_job_queue import create_job_queue, RedisJobQueue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSocketProgressManager:
    """Manages WebSocket connections for real-time progress updates"""

    def __init__(self):
        self.connections: Set[WebSocketServerProtocol] = set()
        self.job_subscriptions: Dict[str, Set[WebSocketServerProtocol]] = {}
        self.redis_client: redis.Redis = None
        self.job_queue: RedisJobQueue = None
        self.running = False

    async def initialize(self):
        """Initialize Redis connections"""
        self.job_queue = await create_job_queue()

        # Create separate Redis client for pub/sub
        self.redis_client = redis.from_url(
            "redis://localhost:6379/0",
            decode_responses=True
        )

        logger.info("✅ WebSocket Progress Manager initialized")

    async def register_connection(self, websocket: WebSocketServerProtocol):
        """Register new WebSocket connection"""
        self.connections.add(websocket)
        logger.info(f"🔗 WebSocket connected: {websocket.remote_address} (total: {len(self.connections)})")

        # Send initial connection message
        await self.send_to_connection(websocket, {
            "type": "connection_established",
            "message": "Connected to anime production progress updates",
            "timestamp": datetime.utcnow().isoformat()
        })

    async def unregister_connection(self, websocket: WebSocketServerProtocol):
        """Unregister WebSocket connection"""
        self.connections.discard(websocket)

        # Remove from job subscriptions
        for job_id, subscribers in list(self.job_subscriptions.items()):
            subscribers.discard(websocket)
            if not subscribers:
                del self.job_subscriptions[job_id]

        logger.info(f"🔌 WebSocket disconnected: {websocket.remote_address} (total: {len(self.connections)})")

    async def subscribe_to_job(self, websocket: WebSocketServerProtocol, job_id: str):
        """Subscribe WebSocket to specific job updates"""
        if job_id not in self.job_subscriptions:
            self.job_subscriptions[job_id] = set()

        self.job_subscriptions[job_id].add(websocket)

        # Send current job status
        try:
            status = await self.job_queue.get_job_status(job_id)
            if status:
                await self.send_to_connection(websocket, {
                    "type": "job_status",
                    "job_id": job_id,
                    **status
                })
            else:
                await self.send_to_connection(websocket, {
                    "type": "job_not_found",
                    "job_id": job_id,
                    "message": "Job not found"
                })
        except Exception as e:
            logger.error(f"Error sending initial job status: {e}")

        logger.info(f"📡 WebSocket subscribed to job {job_id[:8]}...")

    async def unsubscribe_from_job(self, websocket: WebSocketServerProtocol, job_id: str):
        """Unsubscribe WebSocket from job updates"""
        if job_id in self.job_subscriptions:
            self.job_subscriptions[job_id].discard(websocket)
            if not self.job_subscriptions[job_id]:
                del self.job_subscriptions[job_id]

        logger.info(f"📡 WebSocket unsubscribed from job {job_id[:8]}...")

    async def send_to_connection(self, websocket: WebSocketServerProtocol, message: Dict[str, Any]):
        """Send message to specific WebSocket connection"""
        try:
            await websocket.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            await self.unregister_connection(websocket)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")

    async def broadcast_to_all(self, message: Dict[str, Any]):
        """Broadcast message to all connected WebSockets"""
        if not self.connections:
            return

        disconnected = set()
        for websocket in self.connections.copy():
            try:
                await websocket.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(websocket)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")
                disconnected.add(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.unregister_connection(websocket)

    async def broadcast_to_job_subscribers(self, job_id: str, message: Dict[str, Any]):
        """Broadcast message to subscribers of specific job"""
        if job_id not in self.job_subscriptions:
            return

        message["job_id"] = job_id
        disconnected = set()

        for websocket in self.job_subscriptions[job_id].copy():
            try:
                await websocket.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(websocket)
            except Exception as e:
                logger.error(f"Error sending job update to WebSocket: {e}")
                disconnected.add(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.unregister_connection(websocket)

    async def handle_websocket_message(self, websocket: WebSocketServerProtocol, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            message_type = data.get("type")

            if message_type == "subscribe_job":
                job_id = data.get("job_id")
                if job_id:
                    await self.subscribe_to_job(websocket, job_id)
                else:
                    await self.send_to_connection(websocket, {
                        "type": "error",
                        "message": "job_id required for subscription"
                    })

            elif message_type == "unsubscribe_job":
                job_id = data.get("job_id")
                if job_id:
                    await self.unsubscribe_from_job(websocket, job_id)

            elif message_type == "get_queue_stats":
                stats = await self.job_queue.get_queue_stats()
                await self.send_to_connection(websocket, {
                    "type": "queue_stats",
                    **stats
                })

            elif message_type == "ping":
                await self.send_to_connection(websocket, {
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })

            else:
                await self.send_to_connection(websocket, {
                    "type": "error",
                    "message": f"Unknown message type: {message_type}"
                })

        except json.JSONDecodeError:
            await self.send_to_connection(websocket, {
                "type": "error",
                "message": "Invalid JSON message"
            })
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            await self.send_to_connection(websocket, {
                "type": "error",
                "message": "Internal server error"
            })

    async def start_progress_monitoring(self):
        """Start monitoring job progress and broadcasting updates"""
        logger.info("📊 Starting progress monitoring...")
        self.running = True

        while self.running:
            try:
                # Get all jobs being monitored
                monitored_jobs = set()
                for job_id in self.job_subscriptions.keys():
                    monitored_jobs.add(job_id)

                # Check status of monitored jobs
                for job_id in monitored_jobs:
                    try:
                        status = await self.job_queue.get_job_status(job_id)
                        if status:
                            # Broadcast status update
                            await self.broadcast_to_job_subscribers(job_id, {
                                "type": "progress_update",
                                **status,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                    except Exception as e:
                        logger.error(f"Error checking job {job_id[:8]} status: {e}")

                # Broadcast queue stats periodically
                if len(self.connections) > 0:
                    stats = await self.job_queue.get_queue_stats()
                    await self.broadcast_to_all({
                        "type": "queue_stats_update",
                        **stats,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                # Wait before next check
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error in progress monitoring: {e}")
                await asyncio.sleep(10)

    async def stop_monitoring(self):
        """Stop progress monitoring"""
        self.running = False
        logger.info("🛑 Progress monitoring stopped")

# Global manager instance
progress_manager = WebSocketProgressManager()

async def websocket_handler(websocket: WebSocketServerProtocol, path: str):
    """WebSocket connection handler"""
    await progress_manager.register_connection(websocket)

    try:
        async for message in websocket:
            await progress_manager.handle_websocket_message(websocket, message)
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logger.error(f"WebSocket handler error: {e}")
    finally:
        await progress_manager.unregister_connection(websocket)

async def start_websocket_server(host: str = "localhost", port: int = 8329):
    """Start WebSocket server for progress updates"""
    await progress_manager.initialize()

    # Start progress monitoring in background
    monitoring_task = asyncio.create_task(progress_manager.start_progress_monitoring())

    # Start WebSocket server
    server = await websockets.serve(websocket_handler, host, port)
    logger.info(f"🚀 WebSocket server started on ws://{host}:{port}")

    try:
        await server.wait_closed()
    finally:
        await progress_manager.stop_monitoring()
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass

# FastAPI integration
from fastapi import FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect

async def fastapi_websocket_endpoint(websocket: WebSocket):
    """FastAPI WebSocket endpoint"""
    await websocket.accept()

    # Convert to websockets-style interface
    class FastAPIWebSocketAdapter:
        def __init__(self, ws):
            self.ws = ws
            self.remote_address = (ws.client.host, ws.client.port) if ws.client else ("unknown", 0)

        async def send(self, message):
            await self.ws.send_text(message)

        async def recv(self):
            return await self.ws.receive_text()

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return await self.recv()
            except WebSocketDisconnect:
                raise StopAsyncIteration

    adapter = FastAPIWebSocketAdapter(websocket)
    await progress_manager.register_connection(adapter)

    try:
        while True:
            try:
                message = await websocket.receive_text()
                await progress_manager.handle_websocket_message(adapter, message)
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.error(f"FastAPI WebSocket error: {e}")
    finally:
        await progress_manager.unregister_connection(adapter)

if __name__ == "__main__":
    # Run standalone WebSocket server
    import sys

    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8329

    asyncio.run(start_websocket_server(host, port))