"""
Tower Anime Production System - Echo Brain Integration
Client for communicating with Echo Brain orchestrator (port 8309)
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from uuid import UUID, uuid4
from enum import Enum
import json

import aiohttp

logger = logging.getLogger(__name__)


class EchoAgentType(str, Enum):
    """Specialized agents within Echo Brain"""
    STORY_BIBLE = "story_bible_agent"
    CHARACTER_DESIGNER = "character_designer_agent"
    SCENE_COMPOSER = "scene_composer_agent"
    QUALITY_REVIEWER = "quality_reviewer_agent"
    RENDER_DISPATCHER = "render_dispatcher_agent"


class EchoTaskPriority(int, Enum):
    """Task priority levels"""
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


class EchoBrainClient:
    """
    Client for interacting with Echo Brain orchestrator.
    
    Echo Brain handles:
    - Story bible management and narrative consistency
    - Character design sessions with user collaboration
    - Scene composition and staging
    - Quality gate enforcement
    - Multi-agent coordination for complex tasks
    
    The anime system registers as a render worker that Echo Brain
    dispatches tasks to.
    """
    
    def __init__(
        self,
        echo_url: str = "http://***REMOVED***:8309",
        anime_callback_url: str = "http://***REMOVED***:8328/api/anime/echo",
        worker_id: str = None
    ):
        self.echo_url = echo_url.rstrip('/')
        self.callback_url = anime_callback_url
        self.worker_id = worker_id or f"anime-worker-{uuid4().hex[:8]}"
        self._session: Optional[aiohttp.ClientSession] = None
        self._registered = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        
    async def connect(self):
        """Initialize connection to Echo Brain"""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        await self._register_worker()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
    async def disconnect(self):
        """Clean disconnect from Echo Brain"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        await self._unregister_worker()
        if self._session:
            await self._session.close()
    
    # === Worker Registration ===
    
    async def _register_worker(self):
        """Register anime system as render worker with Echo Brain"""
        try:
            payload = {
                "worker_id": self.worker_id,
                "worker_type": "anime_renderer",
                "capabilities": [
                    "still_image",
                    "animation_loop",
                    "full_video",
                    "character_sheet",
                    "consistency_check"
                ],
                "callback_url": self.callback_url,
                "gpu_info": {
                    "model": "RTX 3060",
                    "vram_gb": 12,
                    "driver": "550.x"
                },
                "max_concurrent_jobs": 1,  # GPU blocks during generation
                "status": "ready"
            }
            
            async with self._session.post(
                f"{self.echo_url}/api/workers/register",
                json=payload
            ) as resp:
                if resp.status == 200:
                    self._registered = True
                    logger.info(f"Registered with Echo Brain as {self.worker_id}")
                else:
                    logger.error(f"Failed to register: {await resp.text()}")
                    
        except aiohttp.ClientError as e:
            logger.warning(f"Could not connect to Echo Brain: {e}")
    
    async def _unregister_worker(self):
        """Unregister worker on shutdown"""
        if not self._registered:
            return
            
        try:
            async with self._session.post(
                f"{self.echo_url}/api/workers/{self.worker_id}/unregister"
            ) as resp:
                if resp.status == 200:
                    logger.info("Unregistered from Echo Brain")
        except Exception as e:
            logger.warning(f"Error unregistering: {e}")
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to Echo Brain"""
        while True:
            try:
                await asyncio.sleep(30)  # Every 30 seconds
                await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")
    
    async def _send_heartbeat(self):
        """Send heartbeat with current status"""
        payload = {
            "worker_id": self.worker_id,
            "status": "ready",  # or "busy" during generation
            "timestamp": datetime.utcnow().isoformat()
        }
        
        async with self._session.post(
            f"{self.echo_url}/api/workers/{self.worker_id}/heartbeat",
            json=payload
        ) as resp:
            if resp.status != 200:
                logger.warning(f"Heartbeat failed: {resp.status}")
    
    # === Task Submission ===
    
    async def submit_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
        project_id: UUID = None,
        priority: EchoTaskPriority = EchoTaskPriority.NORMAL,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Submit a task to Echo Brain for orchestration.
        
        Echo Brain will process the task through its agent pipeline
        and dispatch render jobs back to this anime system.
        """
        task_id = uuid4()
        
        request = {
            "task_id": str(task_id),
            "task_type": task_type,
            "project_id": str(project_id) if project_id else None,
            "priority": priority.value,
            "payload": payload,
            "context": context or {},
            "submitted_by": self.worker_id,
            "submitted_at": datetime.utcnow().isoformat()
        }
        
        try:
            async with self._session.post(
                f"{self.echo_url}/api/tasks",
                json=request
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(f"Submitted task {task_id} to Echo Brain")
                    return result
                else:
                    error = await resp.text()
                    logger.error(f"Task submission failed: {error}")
                    return {"error": error}
                    
        except aiohttp.ClientError as e:
            logger.error(f"Failed to submit task: {e}")
            return {"error": str(e)}
    
    # === Character Design Session ===
    
    async def start_character_session(
        self,
        project_id: UUID,
        character_name: str,
        initial_description: str,
        style_reference: str = None
    ) -> Dict[str, Any]:
        """
        Start an interactive character design session with Echo Brain.
        
        Echo Brain's character designer agent will collaborate with
        the user to iteratively refine the character design.
        """
        return await self.submit_task(
            task_type="character_design_session",
            payload={
                "character_name": character_name,
                "initial_description": initial_description,
                "style_reference": style_reference,
                "mode": "interactive"
            },
            project_id=project_id,
            priority=EchoTaskPriority.NORMAL
        )
    
    async def send_character_feedback(
        self,
        session_id: UUID,
        feedback: str,
        selected_variant: int = None
    ) -> Dict[str, Any]:
        """Send user feedback during character design session"""
        return await self.submit_task(
            task_type="character_feedback",
            payload={
                "session_id": str(session_id),
                "feedback": feedback,
                "selected_variant": selected_variant
            },
            priority=EchoTaskPriority.HIGH
        )
    
    # === Scene Composition ===
    
    async def compose_scene(
        self,
        project_id: UUID,
        scene_description: str,
        character_ids: List[UUID],
        location: str = None,
        mood: str = None,
        camera_angle: str = None
    ) -> Dict[str, Any]:
        """
        Request scene composition from Echo Brain.
        
        The scene composer agent will determine character positioning,
        lighting, and camera setup based on the story context.
        """
        return await self.submit_task(
            task_type="compose_scene",
            payload={
                "scene_description": scene_description,
                "character_ids": [str(c) for c in character_ids],
                "location": location,
                "mood": mood,
                "camera_angle": camera_angle
            },
            project_id=project_id,
            priority=EchoTaskPriority.NORMAL
        )
    
    # === Story Bible Operations ===
    
    async def update_story_context(
        self,
        project_id: UUID,
        update_type: str,
        content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update story bible through Echo Brain.
        
        Echo Brain validates updates against narrative consistency
        and propagates changes to affected scenes/characters.
        """
        return await self.submit_task(
            task_type="story_bible_update",
            payload={
                "update_type": update_type,  # "add_event", "modify_character", etc.
                "content": content
            },
            project_id=project_id,
            priority=EchoTaskPriority.NORMAL
        )
    
    async def get_story_context(
        self,
        project_id: UUID,
        context_type: str = "full",
        character_ids: List[UUID] = None
    ) -> Dict[str, Any]:
        """
        Get story context from Echo Brain for generation.
        
        Returns relevant narrative context, character states,
        and consistency constraints.
        """
        try:
            params = {"context_type": context_type}
            if character_ids:
                params["character_ids"] = ",".join(str(c) for c in character_ids)
            
            async with self._session.get(
                f"{self.echo_url}/api/projects/{project_id}/context",
                params=params
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {"error": await resp.text()}
                    
        except aiohttp.ClientError as e:
            return {"error": str(e)}
    
    # === Quality Review ===
    
    async def request_quality_review(
        self,
        job_id: UUID,
        output_path: str,
        quality_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Request Echo Brain quality review for a generation.
        
        The quality reviewer agent assesses both technical metrics
        and narrative/style consistency.
        """
        return await self.submit_task(
            task_type="quality_review",
            payload={
                "job_id": str(job_id),
                "output_path": output_path,
                "technical_scores": quality_scores
            },
            priority=EchoTaskPriority.HIGH
        )
    
    # === Batch Operations ===
    
    async def queue_batch(
        self,
        project_id: UUID,
        tasks: List[Dict[str, Any]],
        sequence_mode: str = "parallel"
    ) -> Dict[str, Any]:
        """
        Queue a batch of related tasks for efficient processing.
        
        sequence_mode:
        - "parallel": Execute all tasks concurrently
        - "sequential": Execute in order, passing results forward
        - "conditional": Execute based on previous results
        """
        return await self.submit_task(
            task_type="batch_dispatch",
            payload={
                "tasks": tasks,
                "sequence_mode": sequence_mode
            },
            project_id=project_id,
            priority=EchoTaskPriority.NORMAL
        )
    
    # === Webhook Handler ===
    
    async def handle_webhook(
        self,
        event_type: str,
        data: Dict[str, Any],
        handlers: Dict[str, Callable]
    ):
        """
        Handle incoming webhook from Echo Brain.
        
        Called by the anime API when Echo Brain sends callbacks.
        Routes to appropriate handler based on event type.
        """
        handler = handlers.get(event_type)
        if handler:
            await handler(data)
        else:
            logger.warning(f"No handler for Echo event: {event_type}")


# === Webhook Event Handlers ===

class EchoWebhookHandlers:
    """Default handlers for Echo Brain webhook events"""
    
    def __init__(self, db_pool, char_service, quality_service, comfyui_client):
        self.db = db_pool
        self.char_service = char_service
        self.quality_service = quality_service
        self.comfyui = comfyui_client
    
    async def on_render_requested(self, data: Dict[str, Any]):
        """Handle render job dispatch from Echo Brain"""
        logger.info(f"Echo requested render: {data.get('task_id')}")
        # Create job and queue for processing
        
    async def on_character_approved(self, data: Dict[str, Any]):
        """Handle character design approval"""
        character_id = UUID(data.get('character_id'))
        reference_image = data.get('approved_reference')
        
        # Store approved reference and compute embedding
        await self.char_service.store_character_embedding(
            character_id, reference_image
        )
        
    async def on_quality_decision(self, data: Dict[str, Any]):
        """Handle quality gate decision from Echo Brain"""
        job_id = UUID(data.get('job_id'))
        decision = data.get('decision')  # "approved", "regenerate", "reject"
        
        if decision == "regenerate":
            # Trigger regeneration with Echo's suggestions
            suggestions = data.get('suggestions', {})
            logger.info(f"Echo requested regeneration for {job_id}: {suggestions}")
    
    async def on_story_updated(self, data: Dict[str, Any]):
        """Handle story bible update notification"""
        project_id = UUID(data.get('project_id'))
        affected_characters = data.get('affected_characters', [])
        
        logger.info(f"Story updated for project {project_id}")
        # Could trigger consistency re-checks for affected content
    
    def get_handlers(self) -> Dict[str, Callable]:
        """Return mapping of event types to handlers"""
        return {
            "render.requested": self.on_render_requested,
            "character.approved": self.on_character_approved,
            "quality.decision": self.on_quality_decision,
            "story.updated": self.on_story_updated,
        }
