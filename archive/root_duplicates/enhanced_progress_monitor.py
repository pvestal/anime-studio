#!/usr/bin/env python3
"""
Enhanced progress monitor that integrates with WebSocket server.
Extends the existing progress monitoring with real-time WebSocket updates.
"""

import asyncio
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import time
import websockets
import subprocess
import sys
from datetime import datetime
from typing import Dict, Optional, List
import logging
from progress_monitor import ComfyUIProgressMonitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedProgressMonitor(ComfyUIProgressMonitor):
    def __init__(self, websocket_enabled: bool = True, websocket_port: int = 8329):
        super().__init__()
        self.websocket_enabled = websocket_enabled
        self.websocket_port = websocket_port
        self.websocket_server = None
        self.connected_clients = set()
        self.job_history = {}
        self.alert_cooldown = {}  # Prevent spam alerts

    async def send_email_alert(self, subject: str, body: str, to_email: str = "patrick.vestal@gmail.com"):
        """Send email alert using tower-smtp"""
        try:
            result = subprocess.run([
                sys.executable, "/opt/tower-smtp/send_email.py",
                to_email, subject, body
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                logger.info(f"Email alert sent: {subject}")
                return True
            else:
                logger.error(f"Email failed: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.error("Email sending timed out")
            return False
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False

    async def check_alert_conditions(self, job_id: int, progress_data: Dict):
        """Check if email alerts should be sent"""
        status = progress_data.get("status", "unknown")
        progress = progress_data.get("progress", 0)
        elapsed_time = progress_data.get("elapsed_time", 0)

        # Generate alert key for cooldown
        alert_key = f"{job_id}_{status}"
        current_time = time.time()

        # Check cooldown (10 minutes between same alerts)
        if alert_key in self.alert_cooldown:
            if current_time - self.alert_cooldown[alert_key] < 600:
                return

        send_alert = False
        alert_subject = ""
        alert_body = ""

        # Alert for failed jobs
        if status == "failed":
            send_alert = True
            alert_subject = f"🚨 Anime Production Job {job_id} Failed"
            alert_body = f"""Anime Production Alert

JOB FAILED
Job ID: {job_id}
Status: {status}
Progress: {progress}%
Stage: {progress_data.get('current_stage', 'Unknown')}
Elapsed Time: {elapsed_time}s

This job requires manual intervention.

Timestamp: {datetime.now().isoformat()}
Server: Tower (***REMOVED***)

Check the ComfyUI logs for detailed error information."""

        # Alert for extremely long running jobs (>30 minutes)
        elif status == "running" and elapsed_time > 1800:
            send_alert = True
            alert_subject = f"⏰ Anime Production Job {job_id} Running Long"
            alert_body = f"""Anime Production Alert

LONG RUNNING JOB DETECTED
Job ID: {job_id}
Status: {status}
Progress: {progress}%
Stage: {progress_data.get('current_stage', 'Unknown')}
Elapsed Time: {elapsed_time}s ({elapsed_time//60} minutes)
ETA: {progress_data.get('eta_formatted', 'Unknown')}

This job may be stuck or experiencing performance issues.

Timestamp: {datetime.now().isoformat()}
Server: Tower (***REMOVED***)"""

        if send_alert:
            self.alert_cooldown[alert_key] = current_time
            await self.send_email_alert(alert_subject, alert_body)

    async def broadcast_update(self, job_id: int, job_data: dict):
        """Broadcast job update to all connected WebSocket clients"""
        if not self.websocket_enabled or not self.connected_clients:
            return

        message = {
            "type": "progress_update",
            "job_id": job_id,
            "job_data": job_data,
            "timestamp": datetime.now().isoformat()
        }

        # Broadcast to all connected clients
        dead_clients = set()
        for client in self.connected_clients.copy():
            try:
                await client.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                dead_clients.add(client)
            except Exception as e:
                logger.error(f"Error sending to WebSocket client: {e}")
                dead_clients.add(client)

        # Clean up dead connections
        for client in dead_clients:
            self.connected_clients.discard(client)

    async def enhanced_check_progress(self, prompt_id: str, job_id: int) -> Dict:
        """Enhanced progress check with more detailed information and ETA"""
        progress_data = await self.check_comfyui_progress(prompt_id)

        # Add enhanced information
        job_key = f"{job_id}_{prompt_id}"

        # Track job timing for ETA calculation
        if job_key not in self.job_history:
            self.job_history[job_key] = {
                "start_time": time.time(),
                "progress_points": [],
                "stages": []
            }

        job_history = self.job_history[job_key]
        current_time = time.time()
        current_progress = progress_data.get("progress", 0)

        # Record progress point
        job_history["progress_points"].append({
            "time": current_time,
            "progress": current_progress
        })

        # Keep only recent progress points (last 10 minutes)
        cutoff_time = current_time - 600
        job_history["progress_points"] = [
            p for p in job_history["progress_points"]
            if p["time"] > cutoff_time
        ]

        # Calculate ETA based on progress trend
        eta_info = self.calculate_eta(job_history, current_progress)
        progress_data.update(eta_info)

        # Add timing information
        progress_data["elapsed_time"] = int(current_time - job_history["start_time"])
        progress_data["job_id"] = job_id

        # Determine current stage based on status and progress
        stage_info = self.determine_stage(progress_data)
        progress_data.update(stage_info)

        return progress_data

    def calculate_eta(self, job_history: dict, current_progress: int) -> Dict:
        """Calculate ETA based on progress history"""
        if current_progress <= 0 or len(job_history["progress_points"]) < 2:
            return {
                "eta_seconds": None,
                "eta_formatted": "Calculating...",
                "progress_rate": 0
            }

        # Calculate progress rate based on recent points
        recent_points = job_history["progress_points"][-5:]  # Last 5 points
        if len(recent_points) < 2:
            return {
                "eta_seconds": None,
                "eta_formatted": "Calculating...",
                "progress_rate": 0
            }

        # Linear regression for progress rate
        time_diff = recent_points[-1]["time"] - recent_points[0]["time"]
        progress_diff = recent_points[-1]["progress"] - recent_points[0]["progress"]

        if time_diff <= 0 or progress_diff <= 0:
            return {
                "eta_seconds": None,
                "eta_formatted": "Stalled",
                "progress_rate": 0
            }

        progress_rate = progress_diff / time_diff  # percent per second
        remaining_progress = 100 - current_progress
        eta_seconds = remaining_progress / progress_rate if progress_rate > 0 else None

        if eta_seconds is None or eta_seconds < 0:
            eta_formatted = "Unknown"
        elif eta_seconds < 60:
            eta_formatted = f"{int(eta_seconds)}s"
        elif eta_seconds < 3600:
            minutes = int(eta_seconds // 60)
            seconds = int(eta_seconds % 60)
            eta_formatted = f"{minutes}m {seconds}s"
        else:
            hours = int(eta_seconds // 3600)
            minutes = int((eta_seconds % 3600) // 60)
            eta_formatted = f"{hours}h {minutes}m"

        return {
            "eta_seconds": int(eta_seconds) if eta_seconds else None,
            "eta_formatted": eta_formatted,
            "progress_rate": round(progress_rate * 60, 2)  # percent per minute
        }

    def determine_stage(self, progress_data: dict) -> Dict:
        """Determine current processing stage based on progress and status"""
        status = progress_data.get("status", "unknown")
        progress = progress_data.get("progress", 0)

        if status == "queued":
            return {
                "current_stage": "Queued",
                "stage_description": "Waiting in processing queue",
                "frames_complete": 0,
                "estimated_total_frames": 0
            }
        elif status == "running":
            if progress < 10:
                stage = "Initializing"
                description = "Preparing models and inputs"
            elif progress < 30:
                stage = "Processing"
                description = "Generating initial frames"
            elif progress < 70:
                stage = "Rendering"
                description = "Creating video frames"
            elif progress < 90:
                stage = "Post-processing"
                description = "Applying effects and transitions"
            else:
                stage = "Finalizing"
                description = "Encoding final output"

            # Estimate frames based on typical 5-second video
            estimated_frames = 120  # 24fps * 5 seconds
            frames_complete = int((progress / 100) * estimated_frames)

            return {
                "current_stage": stage,
                "stage_description": description,
                "frames_complete": frames_complete,
                "estimated_total_frames": estimated_frames
            }
        elif status == "completed":
            return {
                "current_stage": "Completed",
                "stage_description": "Video generation finished",
                "frames_complete": 120,
                "estimated_total_frames": 120
            }
        elif status == "failed":
            return {
                "current_stage": "Failed",
                "stage_description": "Generation failed - check logs",
                "frames_complete": 0,
                "estimated_total_frames": 0
            }
        else:
            return {
                "current_stage": "Unknown",
                "stage_description": "Status unknown",
                "frames_complete": 0,
                "estimated_total_frames": 0
            }

    async def update_job_status_enhanced(self, job_id: int, comfyui_id: str, progress_data: Dict):
        """Enhanced job status update with WebSocket broadcasting"""
        # Update database with standard method
        update_success = await self.update_job_status(job_id, comfyui_id, progress_data)

        if update_success:
            # Check for alert conditions
            await self.check_alert_conditions(job_id, progress_data)

            # Broadcast the update via WebSocket
            await self.broadcast_update(job_id, progress_data)

            # Log detailed progress
            stage = progress_data.get("current_stage", "Unknown")
            progress = progress_data.get("progress", 0)
            eta = progress_data.get("eta_formatted", "Unknown")

            logger.info(
                f"Job {job_id}: {stage} - {progress}% "
                f"(ETA: {eta}, Rate: {progress_data.get('progress_rate', 0)}%/min)"
            )

        return update_success

    async def handle_websocket_client(self, websocket, path):
        """Handle WebSocket client connections"""
        self.connected_clients.add(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self.connected_clients)}")

        try:
            # Send current active jobs to new client
            jobs = await self.get_active_jobs()
            for job in jobs:
                if job.get("comfyui_job_id"):
                    progress_data = await self.enhanced_check_progress(
                        job["comfyui_job_id"],
                        job["id"]
                    )
                    await websocket.send(json.dumps({
                        "type": "initial_status",
                        "job_id": job["id"],
                        "job_data": progress_data,
                        "timestamp": datetime.now().isoformat()
                    }))

            # Keep connection alive
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("type") == "ping":
                        await websocket.send(json.dumps({
                            "type": "pong",
                            "timestamp": datetime.now().isoformat()
                        }))
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from WebSocket client: {message}")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.connected_clients.discard(websocket)
            logger.info(f"WebSocket client disconnected. Remaining: {len(self.connected_clients)}")

    async def start_websocket_server(self):
        """Start the WebSocket server"""
        if not self.websocket_enabled:
            return None

        logger.info(f"Starting WebSocket server on port {self.websocket_port}...")

        self.websocket_server = await websockets.serve(
            self.handle_websocket_client,
            "127.0.0.1",
            self.websocket_port,
            ping_interval=20,
            ping_timeout=10
        )

        logger.info(f"WebSocket server running on ws://127.0.0.1:{self.websocket_port}")
        return self.websocket_server

    async def enhanced_monitor_loop(self):
        """Enhanced monitoring loop with WebSocket support"""
        logger.info("Starting enhanced ComfyUI progress monitor with WebSocket support...")

        # Start WebSocket server if enabled
        websocket_server = None
        if self.websocket_enabled:
            try:
                websocket_server = await self.start_websocket_server()
            except Exception as e:
                logger.error(f"Failed to start WebSocket server: {e}")
                self.websocket_enabled = False

        try:
            while True:
                try:
                    # Get active jobs
                    jobs = await self.get_active_jobs()

                    if jobs:
                        logger.info(f"Monitoring {len(jobs)} active jobs...")

                        for job in jobs:
                            job_id = job["id"]
                            comfyui_id = job["comfyui_job_id"]

                            # Enhanced progress check
                            progress_data = await self.enhanced_check_progress(comfyui_id, job_id)

                            # Update database and broadcast if status changed
                            if progress_data["status"] != job["status"] or True:  # Always update for progress
                                await self.update_job_status_enhanced(job_id, comfyui_id, progress_data)

                            # Small delay between job checks
                            await asyncio.sleep(0.5)

                    # Wait before next cycle (3 seconds as requested)
                    await asyncio.sleep(3)

                except Exception as e:
                    logger.error(f"Error in enhanced monitor loop: {e}")
                    await asyncio.sleep(10)

        finally:
            # Clean up WebSocket server
            if websocket_server:
                websocket_server.close()
                await websocket_server.wait_closed()
                logger.info("WebSocket server stopped")

    async def test_websocket_integration(self, job_id: int):
        """Test WebSocket integration with a specific job"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, comfyui_job_id, status, prompt
                FROM production_jobs
                WHERE id = %s
            """, (job_id,))

            job = cursor.fetchone()
            cursor.close()
            conn.close()

            if job and job["comfyui_job_id"]:
                logger.info(f"Testing WebSocket integration for job {job_id}")

                # Start minimal WebSocket server for testing
                if not self.websocket_enabled:
                    self.websocket_enabled = True
                    await self.start_websocket_server()

                # Get enhanced progress
                progress_data = await self.enhanced_check_progress(
                    job["comfyui_job_id"],
                    job_id
                )

                print(f"\nEnhanced Progress for Job {job_id}:")
                print(f"  Status: {progress_data.get('status', 'Unknown')}")
                print(f"  Progress: {progress_data.get('progress', 0)}%")
                print(f"  Stage: {progress_data.get('current_stage', 'Unknown')}")
                print(f"  ETA: {progress_data.get('eta_formatted', 'Unknown')}")
                print(f"  Rate: {progress_data.get('progress_rate', 0)} %/min")
                print(f"  Frames: {progress_data.get('frames_complete', 0)}/{progress_data.get('estimated_total_frames', 0)}")
                print(f"  Connected Clients: {len(self.connected_clients)}")

                # Broadcast test update
                await self.broadcast_update(job_id, progress_data)

                return progress_data
            else:
                print(f"Job {job_id} not found or has no ComfyUI ID")
                return None

        except Exception as e:
            logger.error(f"Error testing WebSocket integration: {e}")
            return None

async def main():
    """Main entry point with enhanced functionality"""
    import sys

    # Use enhanced monitor instead of basic one
    monitor = EnhancedProgressMonitor(websocket_enabled=True)

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "test" and len(sys.argv) > 2:
            # Test WebSocket integration with specific job
            job_id = int(sys.argv[2])
            await monitor.test_websocket_integration(job_id)
        elif command == "monitor":
            # Run enhanced monitoring loop
            await monitor.enhanced_monitor_loop()
        elif command.isdigit():
            # Test specific job (backward compatibility)
            job_id = int(command)
            await monitor.test_specific_job(job_id)
        else:
            print("Usage: python enhanced_progress_monitor.py [test <job_id>|monitor|<job_id>]")
    else:
        # Run enhanced monitoring loop
        await monitor.enhanced_monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())