#!/usr/bin/env python3
"""
WebSocket-based real-time progress system for anime production.
Broadcasts job progress updates to connected clients.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, List
import websockets
import psycopg2
from psycopg2.extras import RealDictCursor
import aiohttp
from threading import Thread
import weakref

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSocketProgressServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8329):
        self.host = host
        self.port = port
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.db_config = {
            "host": "localhost",
            "database": "anime_production",
            "user": "patrick",
            "password": "tower_echo_brain_secret_key_2025",
            "port": 5432,
            "options": "-c search_path=anime_api,public"
        }
        self.comfyui_url = "http://localhost:8188"
        self.job_start_times: Dict[str, float] = {}
        self.job_progress_history: Dict[str, List[Dict]] = {}
        self.running = False

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)

    async def register_client(self, websocket):
        """Register a new WebSocket client"""
        self.connected_clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.connected_clients)}")

        # Send current active jobs on connect
        try:
            active_jobs = await self.get_active_jobs_with_progress()
            if active_jobs:
                await self.send_to_client(websocket, {
                    "type": "initial_jobs",
                    "jobs": active_jobs,
                    "timestamp": datetime.now().isoformat()
                })
        except Exception as e:
            logger.error(f"Error sending initial jobs to client: {e}")

    async def unregister_client(self, websocket):
        """Unregister a WebSocket client"""
        self.connected_clients.discard(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.connected_clients)}")

    async def send_to_client(self, websocket, message: dict):
        """Send message to a specific client"""
        try:
            await websocket.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            await self.unregister_client(websocket)
        except Exception as e:
            logger.error(f"Error sending to client: {e}")

    async def broadcast_progress_update(self, job_data: dict):
        """Broadcast progress update to all connected clients"""
        message = {
            "type": "progress_update",
            "job": job_data,
            "timestamp": datetime.now().isoformat()
        }

        # Remove closed connections
        dead_clients = set()
        for client in self.connected_clients.copy():
            try:
                await self.send_to_client(client, message)
            except websockets.exceptions.ConnectionClosed:
                dead_clients.add(client)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                dead_clients.add(client)

        # Clean up dead connections
        for client in dead_clients:
            self.connected_clients.discard(client)

    async def get_active_jobs_with_progress(self) -> List[Dict]:
        """Get all active jobs with current progress information"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, comfyui_job_id, status, prompt, created_at, updated_at,
                       output_path, project_id, job_type, generation_type
                FROM production_jobs
                WHERE status IN ('processing', 'queued', 'pending')
                AND comfyui_job_id IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 20
            """)

            jobs = cursor.fetchall()
            cursor.close()
            conn.close()

            jobs_with_progress = []
            for job in jobs:
                job_dict = dict(job)

                # Get ComfyUI progress if available
                if job['comfyui_job_id']:
                    progress_info = await self.check_comfyui_progress(job['comfyui_job_id'])
                    job_dict.update(progress_info)

                    # Calculate ETA
                    eta_info = self.calculate_eta(job['comfyui_job_id'], progress_info.get('progress', 0))
                    job_dict.update(eta_info)

                jobs_with_progress.append(job_dict)

            return jobs_with_progress

        except Exception as e:
            logger.error(f"Error getting active jobs: {e}")
            return []

    async def check_comfyui_progress(self, prompt_id: str) -> Dict:
        """Enhanced progress check with more detailed information"""
        async with aiohttp.ClientSession() as session:
            try:
                # Check queue status
                async with session.get(f"{self.comfyui_url}/queue") as response:
                    if response.status == 200:
                        queue = await response.json()

                        # Check if running
                        for job in queue.get("queue_running", []):
                            if len(job) > 1 and job[1] == prompt_id:
                                # Record start time if not already recorded
                                if prompt_id not in self.job_start_times:
                                    self.job_start_times[prompt_id] = time.time()

                                # Try to get more detailed progress from execution info
                                progress = await self.get_execution_progress(session, prompt_id)

                                return {
                                    "progress": progress.get("progress", 50),
                                    "status": "running",
                                    "current_stage": progress.get("current_stage", "Generating frames"),
                                    "frames_complete": progress.get("frames_complete", 0),
                                    "total_frames": progress.get("total_frames", 0),
                                    "message": progress.get("message", "Processing...")
                                }

                        # Check if pending
                        for idx, job in enumerate(queue.get("queue_pending", [])):
                            if len(job) > 1 and job[1] == prompt_id:
                                return {
                                    "progress": 0,
                                    "status": "queued",
                                    "current_stage": "Waiting in queue",
                                    "queue_position": idx + 1,
                                    "message": f"Position {idx + 1} in queue"
                                }

                # Check history for completed jobs
                async with session.get(f"{self.comfyui_url}/history/{prompt_id}") as response:
                    if response.status == 200:
                        history = await response.json()
                        if prompt_id in history:
                            job_data = history[prompt_id]

                            if "outputs" in job_data:
                                outputs = self.parse_outputs(job_data["outputs"])
                                return {
                                    "progress": 100,
                                    "status": "completed",
                                    "current_stage": "Completed",
                                    "outputs": outputs,
                                    "message": f"Completed with {len(outputs)} outputs"
                                }
                            else:
                                return {
                                    "progress": 0,
                                    "status": "failed",
                                    "current_stage": "Failed",
                                    "message": "Completed without outputs"
                                }

                return {
                    "progress": 0,
                    "status": "unknown",
                    "current_stage": "Unknown",
                    "message": "Job not found in queue or history"
                }

            except Exception as e:
                logger.error(f"Error checking ComfyUI progress: {e}")
                return {
                    "progress": 0,
                    "status": "error",
                    "current_stage": "Error",
                    "message": str(e)
                }

    async def get_execution_progress(self, session, prompt_id: str) -> Dict:
        """Get detailed execution progress if available"""
        try:
            # Try to get execution info (may not be available in all ComfyUI versions)
            async with session.get(f"{self.comfyui_url}/object_info") as response:
                if response.status == 200:
                    # This is a fallback - actual progress tracking would need
                    # ComfyUI to expose more detailed progress information
                    return {
                        "progress": 50,
                        "current_stage": "Processing nodes",
                        "message": "Generating content..."
                    }
        except:
            pass

        return {
            "progress": 50,
            "current_stage": "Processing",
            "message": "Generating..."
        }

    def parse_outputs(self, outputs_data: dict) -> List[Dict]:
        """Parse ComfyUI outputs into structured format"""
        outputs = []
        for node_id, node_output in outputs_data.items():
            if "videos" in node_output:
                for video in node_output["videos"]:
                    outputs.append({
                        "type": "video",
                        "filename": video.get("filename"),
                        "subfolder": video.get("subfolder", ""),
                        "format": video.get("format", "mp4"),
                        "node_id": node_id
                    })
            if "images" in node_output:
                for image in node_output["images"]:
                    outputs.append({
                        "type": "image",
                        "filename": image.get("filename"),
                        "subfolder": image.get("subfolder", ""),
                        "node_id": node_id
                    })
        return outputs

    def calculate_eta(self, prompt_id: str, current_progress: int) -> Dict:
        """Calculate estimated time of arrival for job completion"""
        if prompt_id not in self.job_start_times:
            return {"eta_seconds": None, "eta_formatted": "Calculating..."}

        start_time = self.job_start_times[prompt_id]
        elapsed_time = time.time() - start_time

        if current_progress <= 0:
            return {"eta_seconds": None, "eta_formatted": "Calculating..."}

        # Estimate total time based on current progress
        estimated_total_time = (elapsed_time / current_progress) * 100
        remaining_time = estimated_total_time - elapsed_time

        if remaining_time < 0:
            remaining_time = 0

        # Format ETA
        if remaining_time < 60:
            eta_formatted = f"{int(remaining_time)}s"
        elif remaining_time < 3600:
            minutes = int(remaining_time // 60)
            seconds = int(remaining_time % 60)
            eta_formatted = f"{minutes}m {seconds}s"
        else:
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)
            eta_formatted = f"{hours}h {minutes}m"

        return {
            "eta_seconds": int(remaining_time),
            "eta_formatted": eta_formatted,
            "elapsed_time": int(elapsed_time)
        }

    async def handle_client_connection(self, websocket, path):
        """Handle individual client WebSocket connections"""
        await self.register_client(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.handle_client_message(websocket, data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from client: {message}")
                except Exception as e:
                    logger.error(f"Error handling client message: {e}")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)

    async def handle_client_message(self, websocket, data: dict):
        """Handle messages from clients"""
        message_type = data.get("type")

        if message_type == "subscribe_job":
            job_id = data.get("job_id")
            if job_id:
                # Send current status of specific job
                job_status = await self.get_job_status(job_id)
                if job_status:
                    await self.send_to_client(websocket, {
                        "type": "job_status",
                        "job": job_status,
                        "timestamp": datetime.now().isoformat()
                    })

        elif message_type == "ping":
            await self.send_to_client(websocket, {
                "type": "pong",
                "timestamp": datetime.now().isoformat()
            })

    async def get_job_status(self, job_id: int) -> Optional[Dict]:
        """Get status of a specific job"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, comfyui_job_id, status, prompt, created_at, updated_at,
                       output_path, project_id, job_type, generation_type
                FROM production_jobs
                WHERE id = %s
            """, (job_id,))

            job = cursor.fetchone()
            cursor.close()
            conn.close()

            if job:
                job_dict = dict(job)
                if job['comfyui_job_id']:
                    progress_info = await self.check_comfyui_progress(job['comfyui_job_id'])
                    job_dict.update(progress_info)

                    eta_info = self.calculate_eta(job['comfyui_job_id'], progress_info.get('progress', 0))
                    job_dict.update(eta_info)

                return job_dict

            return None

        except Exception as e:
            logger.error(f"Error getting job status: {e}")
            return None

    async def progress_monitoring_loop(self):
        """Main progress monitoring loop that broadcasts updates"""
        logger.info("Starting progress monitoring loop...")

        while self.running:
            try:
                if self.connected_clients:
                    jobs = await self.get_active_jobs_with_progress()

                    for job in jobs:
                        # Broadcast each job's progress
                        await self.broadcast_progress_update(job)

                        # Small delay between job broadcasts
                        await asyncio.sleep(0.1)

                # Wait before next monitoring cycle
                await asyncio.sleep(3)  # 3-second intervals as requested

            except Exception as e:
                logger.error(f"Error in progress monitoring loop: {e}")
                await asyncio.sleep(5)

    async def start_server(self):
        """Start the WebSocket server and monitoring loop"""
        self.running = True

        # Start the WebSocket server
        server = await websockets.serve(
            self.handle_client_connection,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10
        )

        logger.info(f"WebSocket progress server started on ws://{self.host}:{self.port}")

        # Start the monitoring loop
        monitoring_task = asyncio.create_task(self.progress_monitoring_loop())

        # Keep server running
        try:
            await server.wait_closed()
        finally:
            self.running = False
            monitoring_task.cancel()
            try:
                await monitoring_task
            except asyncio.CancelledError:
                pass

    def stop_server(self):
        """Stop the server"""
        self.running = False

# CLI interface for testing
async def main():
    import sys

    server = WebSocketProgressServer()

    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            # Test specific functionality
            jobs = await server.get_active_jobs_with_progress()
            print(f"Found {len(jobs)} active jobs:")
            for job in jobs:
                print(f"  Job {job['id']}: {job.get('status', 'unknown')} - {job.get('progress', 0)}%")
        else:
            print("Usage: python websocket_progress_server.py [test]")
    else:
        # Start server
        try:
            await server.start_server()
        except KeyboardInterrupt:
            logger.info("Server stopped by user")

if __name__ == "__main__":
    asyncio.run(main())