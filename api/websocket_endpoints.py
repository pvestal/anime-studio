"""
WebSocket endpoint implementations for real-time progress tracking.
Designed to be imported into secured_api.py for production use.
"""

import asyncio
import logging
import time
from typing import Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from websocket_manager import connection_manager

logger = logging.getLogger(__name__)


def add_websocket_endpoints(
    app: FastAPI, jobs: Dict[str, dict], get_comfyui_job_status_func
):
    """
    Add WebSocket endpoints to the FastAPI app.

    Args:
        app: FastAPI application instance
        jobs: Jobs dictionary from secured_api.py
        get_comfyui_job_status_func: Function to get ComfyUI status
    """

    @app.websocket("/ws/{job_id}")
    async def websocket_progress_endpoint(websocket: WebSocket, job_id: str):
        """
        WebSocket endpoint for real-time progress updates.

        This endpoint provides:
        - Real-time progress updates from ComfyUI
        - Database synchronization
        - Automatic cleanup of disconnected clients
        - Error handling and reconnection support
        """
        try:
            # Connect to WebSocket manager
            await connection_manager.connect(websocket, job_id)
            logger.info(f"WebSocket connected for job {job_id}")

            # Check if job exists
            if job_id not in jobs:
                await connection_manager.send_to_connection(
                    websocket,
                    {
                        "type": "error",
                        "job_id": job_id,
                        "error": "Job not found",
                        "timestamp": time.time(),
                    },
                )
                return

            # Main progress monitoring loop
            while True:
                try:
                    job = jobs[job_id]

                    # Get real-time status from ComfyUI
                    comfyui_id = job.get("comfyui_id", job_id)
                    real_status = await get_comfyui_job_status_func(comfyui_id)

                    if real_status:
                        # Update job with real ComfyUI status
                        job.update(real_status)

                        # Send progress update via WebSocket manager
                        await connection_manager.send_progress_update(
                            job_id=job_id,
                            progress=real_status.get("progress", 0),
                            status=real_status.get("status", "unknown"),
                            estimated_remaining=real_status.get(
                                "estimated_remaining", 0
                            ),
                            output_path=real_status.get("output_path"),
                            message=f"Generation in progress - {real_status.get('status', 'processing')}",
                        )

                        # Check if job is completed or failed
                        if real_status.get("status") in ["completed", "failed"]:
                            logger.info(
                                f"WebSocket job {job_id} finished with status: {real_status.get('status')}"
                            )

                            # Send final status
                            final_message = (
                                "Generation completed successfully!"
                                if real_status.get("status") == "completed"
                                else "Generation failed"
                            )
                            await connection_manager.send_progress_update(
                                job_id=job_id,
                                progress=(
                                    100
                                    if real_status.get("status") == "completed"
                                    else 0
                                ),
                                status=real_status.get("status"),
                                estimated_remaining=0,
                                output_path=real_status.get("output_path"),
                                message=final_message,
                                error=real_status.get("error"),
                            )
                            break
                    else:
                        # No status from ComfyUI - job might be lost
                        await connection_manager.send_progress_update(
                            job_id=job_id,
                            progress=0,
                            status="unknown",
                            estimated_remaining=0,
                            message="Unable to get status from ComfyUI",
                            error="ComfyUI status unavailable",
                        )

                    # Wait before next update (configurable interval)
                    await asyncio.sleep(2)

                except asyncio.CancelledError:
                    # Connection was cancelled
                    break
                except Exception as e:
                    logger.error(f"Error in WebSocket loop for job {job_id}: {e}")
                    await connection_manager.send_to_connection(
                        websocket,
                        {
                            "type": "error",
                            "job_id": job_id,
                            "error": str(e),
                            "timestamp": time.time(),
                        },
                    )
                    await asyncio.sleep(5)  # Wait before retry

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for job {job_id}")
        except Exception as e:
            logger.error(f"WebSocket error for job {job_id}: {e}")
        finally:
            # Always cleanup connection
            await connection_manager.disconnect(websocket)

    @app.websocket("/ws/monitor")
    async def websocket_system_monitor(websocket: WebSocket):
        """
        WebSocket endpoint for system-wide monitoring.
        Provides real-time updates on all jobs and system status.
        """
        try:
            await websocket.accept()
            logger.info("System monitor WebSocket connected")

            while True:
                try:
                    # Get system-wide status
                    connection_info = (
                        await connection_manager.get_all_connections_info()
                    )

                    # Get job statistics
                    active_jobs = len(
                        [j for j in jobs.values() if j.get("status") == "processing"]
                    )
                    total_jobs = len(jobs)

                    # Prepare system status message
                    system_status = {
                        "type": "system_status",
                        "timestamp": time.time(),
                        "jobs": {
                            "total": total_jobs,
                            "active": active_jobs,
                            "completed": len(
                                [
                                    j
                                    for j in jobs.values()
                                    if j.get("status") == "completed"
                                ]
                            ),
                            "failed": len(
                                [
                                    j
                                    for j in jobs.values()
                                    if j.get("status") == "failed"
                                ]
                            ),
                        },
                        "websockets": {
                            "total_connections": connection_info["total_connections"],
                            "jobs_with_connections": connection_info[
                                "jobs_with_connections"
                            ],
                        },
                        "recent_jobs": [
                            {
                                "id": job_id,
                                "status": job["status"],
                                "created_at": job.get("created_at", 0),
                                "progress": job.get("progress", 0),
                            }
                            for job_id, job in sorted(
                                jobs.items(),
                                key=lambda x: x[1].get("created_at", 0),
                                reverse=True,
                            )[:10]
                        ],
                    }

                    await websocket.send_json(system_status)
                    await asyncio.sleep(10)  # Update every 10 seconds

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in system monitor WebSocket: {e}")
                    await asyncio.sleep(10)

        except WebSocketDisconnect:
            logger.info("System monitor WebSocket disconnected")
        except Exception as e:
            logger.error(f"System monitor WebSocket error: {e}")

    @app.get("/api/anime/websocket/status")
    async def websocket_status():
        """
        Get WebSocket connection status and statistics.
        """
        try:
            connection_info = await connection_manager.get_all_connections_info()
            return {
                "status": "healthy",
                "websocket_manager": "active",
                "connections": connection_info,
                "endpoints": [
                    {"path": "/ws/{job_id}", "description": "Real-time job progress"},
                    {"path": "/ws/monitor", "description": "System monitoring"},
                ],
            }
        except Exception as e:
            logger.error(f"Error getting WebSocket status: {e}")
            raise HTTPException(
                status_code=500, detail=f"WebSocket status error: {str(e)}"
            )


def start_background_tasks():
    """
    Start background tasks for WebSocket maintenance.
    Call this when starting the FastAPI app.
    """
    # Import here to avoid circular imports
    from websocket_manager import periodic_cleanup, periodic_ping

    # Start background tasks
    asyncio.create_task(periodic_cleanup())
    asyncio.create_task(periodic_ping())

    logger.info("WebSocket background tasks started")
