#!/usr/bin/env python3
"""WebSocket server for real-time anime generation progress updates"""

import asyncio
import websockets
import json
import redis
import logging
from typing import Set, Dict
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProgressServer:
    """WebSocket server that broadcasts job progress updates to connected clients"""

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=1):
        self.redis = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.job_subscriptions: Dict[str, Set[websockets.WebSocketServerProtocol]] = {}

    async def register_client(self, websocket):
        """Register a new WebSocket client"""
        self.clients.add(websocket)
        logger.info(f"Client {websocket.remote_address} connected. Total clients: {len(self.clients)}")

    async def unregister_client(self, websocket):
        """Remove a disconnected client"""
        self.clients.discard(websocket)

        # Remove from job subscriptions
        for job_id, subscribers in list(self.job_subscriptions.items()):
            subscribers.discard(websocket)
            if not subscribers:
                del self.job_subscriptions[job_id]

        logger.info(f"Client {websocket.remote_address} disconnected. Total clients: {len(self.clients)}")

    async def handle_client(self, websocket):
        """Handle WebSocket client connections and messages"""
        await self.register_client(websocket)

        try:
            async for message in websocket:
                data = json.loads(message)

                if data.get('action') == 'subscribe':
                    job_id = data.get('job_id')
                    if job_id:
                        if job_id not in self.job_subscriptions:
                            self.job_subscriptions[job_id] = set()
                        self.job_subscriptions[job_id].add(websocket)

                        # Send current job status
                        job_data = self.redis.hgetall(f'anime:job:{job_id}')
                        if job_data:
                            await websocket.send(json.dumps({
                                'type': 'status',
                                'job_id': job_id,
                                'data': job_data
                            }))

                        logger.info(f"Client subscribed to job {job_id}")

                elif data.get('action') == 'unsubscribe':
                    job_id = data.get('job_id')
                    if job_id and job_id in self.job_subscriptions:
                        self.job_subscriptions[job_id].discard(websocket)
                        logger.info(f"Client unsubscribed from job {job_id}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("Client connection closed")
        except json.JSONDecodeError:
            logger.error("Invalid JSON received from client")
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            await self.unregister_client(websocket)

    async def monitor_redis_updates(self):
        """Monitor Redis for job updates and broadcast to subscribed clients"""
        pubsub = self.redis.pubsub()
        pubsub.subscribe('anime:job:updates')

        while True:
            try:
                # Check for Redis pub/sub messages
                message = pubsub.get_message(timeout=0.1)

                if message and message['type'] == 'message':
                    update_data = json.loads(message['data'])
                    job_id = update_data.get('job_id')

                    if job_id and job_id in self.job_subscriptions:
                        # Get full job data
                        job_data = self.redis.hgetall(f'anime:job:{job_id}')

                        # Prepare progress update message
                        progress_msg = json.dumps({
                            'type': 'progress',
                            'job_id': job_id,
                            'data': {
                                'status': job_data.get('status', 'unknown'),
                                'progress': int(job_data.get('progress', 0)),
                                'updated_at': job_data.get('updated_at', datetime.now().isoformat())
                            }
                        })

                        # Broadcast to all subscribed clients
                        disconnected = set()
                        for client in self.job_subscriptions[job_id]:
                            try:
                                await client.send(progress_msg)
                            except websockets.exceptions.ConnectionClosed:
                                disconnected.add(client)

                        # Clean up disconnected clients
                        for client in disconnected:
                            await self.unregister_client(client)

                # Also poll for job updates directly
                for job_id, subscribers in list(self.job_subscriptions.items()):
                    if subscribers:
                        job_data = self.redis.hgetall(f'anime:job:{job_id}')
                        if job_data:
                            progress_msg = json.dumps({
                                'type': 'progress',
                                'job_id': job_id,
                                'data': {
                                    'status': job_data.get('status', 'unknown'),
                                    'progress': int(job_data.get('progress', 0)),
                                    'updated_at': job_data.get('updated_at')
                                }
                            })

                            disconnected = set()
                            for client in subscribers:
                                try:
                                    await client.send(progress_msg)
                                except websockets.exceptions.ConnectionClosed:
                                    disconnected.add(client)

                            for client in disconnected:
                                await self.unregister_client(client)

                await asyncio.sleep(1)  # Poll interval

            except Exception as e:
                logger.error(f"Error monitoring Redis: {e}")
                await asyncio.sleep(5)

async def main():
    """Run the WebSocket progress server"""
    server = ProgressServer()

    # Start WebSocket server
    ws_server = await websockets.serve(
        server.handle_client,
        'localhost',
        8765,
        ping_interval=20,
        ping_timeout=10
    )

    logger.info("WebSocket progress server started on ws://localhost:8765")

    # Start Redis monitor in background
    monitor_task = asyncio.create_task(server.monitor_redis_updates())

    try:
        await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        logger.info("Shutting down WebSocket server...")
        monitor_task.cancel()
        ws_server.close()
        await ws_server.wait_closed()

if __name__ == '__main__':
    asyncio.run(main())