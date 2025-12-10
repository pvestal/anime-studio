#!/usr/bin/env python3
"""
User Experience Enhancement Module for Tower Anime Production
Provides real-time preview streaming, contextual progress, and smart error recovery
"""

import asyncio
import base64
import io
import json
import logging
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)

class GenerationPhase(Enum):
    """Phases of generation with user-friendly descriptions"""
    INITIALIZING = ("Preparing workspace", 0, 5)
    LOADING_MODELS = ("Loading AI models", 5, 15)
    PROCESSING_PROMPT = ("Understanding your request", 15, 25)
    GENERATING_LATENTS = ("Creating initial composition", 25, 50)
    REFINING_DETAILS = ("Refining character details", 50, 70)
    APPLYING_STYLE = ("Applying artistic style", 70, 85)
    FINALIZING = ("Finalizing high-quality output", 85, 95)
    SAVING = ("Saving your creation", 95, 100)
    COMPLETE = ("Generation complete!", 100, 100)

    def __init__(self, message: str, start_percent: int, end_percent: int):
        self.message = message
        self.start_percent = start_percent
        self.end_percent = end_percent

@dataclass
class ProgressUpdate:
    """Rich progress update with contextual information"""
    job_id: str
    phase: GenerationPhase
    current_step: int
    total_steps: int
    message: str
    percentage: float
    preview_image: Optional[str] = None  # Base64 encoded preview
    estimated_time_remaining: Optional[float] = None
    metadata: Dict[str, Any] = None

    def to_websocket_message(self) -> str:
        """Convert to WebSocket message format"""
        data = {
            "type": "progress",
            "job_id": self.job_id,
            "phase": self.phase.name,
            "phase_message": self.phase.message,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "message": self.message,
            "percentage": self.percentage,
            "preview_image": self.preview_image,
            "estimated_time_remaining": self.estimated_time_remaining,
            "metadata": self.metadata or {}
        }
        return json.dumps(data)

class PreviewGenerator:
    """Generates real-time preview images during generation"""

    def __init__(self, comfyui_output_dir: str = "/mnt/1TB-storage/ComfyUI/output/"):
        self.output_dir = Path(comfyui_output_dir)
        self.preview_cache = {}

    async def generate_preview_from_latents(
        self,
        latents_path: Optional[str] = None,
        target_size: tuple = (256, 256)
    ) -> Optional[str]:
        """Generate a preview image from latents or intermediate output"""
        try:
            if latents_path and Path(latents_path).exists():
                # Load and process the intermediate image
                img = Image.open(latents_path)

                # Resize for preview
                img.thumbnail(target_size, Image.Resampling.LANCZOS)

                # Convert to base64
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=60)
                img_str = base64.b64encode(buffer.getvalue()).decode()

                return f"data:image/jpeg;base64,{img_str}"
        except Exception as e:
            logger.error(f"Failed to generate preview: {e}")
            return None

    async def create_progress_visualization(
        self,
        percentage: float,
        phase: GenerationPhase,
        size: tuple = (256, 64)
    ) -> str:
        """Create a visual progress bar as an image"""
        try:
            # Create progress bar image
            img = Image.new('RGB', size, color='#1a1a1a')
            pixels = img.load()

            # Draw progress bar
            progress_width = int(size[0] * (percentage / 100))
            for x in range(progress_width):
                for y in range(10, 30):
                    # Gradient effect
                    intensity = 255 - int((y - 10) * 3)
                    pixels[x, y] = (0, intensity, 128)

            # Add text overlay (would need PIL.ImageDraw for text)

            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=80)
            img_str = base64.b64encode(buffer.getvalue()).decode()

            return f"data:image/jpeg;base64,{img_str}"
        except Exception as e:
            logger.error(f"Failed to create progress visualization: {e}")
            return ""

class ContextualProgressTracker:
    """Tracks generation progress with contextual messages"""

    def __init__(self, preview_generator: PreviewGenerator):
        self.preview_generator = preview_generator
        self.job_progress = {}
        self.start_times = {}

    def start_job(self, job_id: str, total_steps: int = 20):
        """Initialize tracking for a new job"""
        self.job_progress[job_id] = {
            "current_step": 0,
            "total_steps": total_steps,
            "phase": GenerationPhase.INITIALIZING,
            "start_time": time.time(),
            "phase_times": {}
        }
        self.start_times[job_id] = time.time()

    def update_phase(self, job_id: str, phase: GenerationPhase):
        """Update the current phase of generation"""
        if job_id in self.job_progress:
            old_phase = self.job_progress[job_id].get("phase")
            if old_phase:
                # Track time spent in each phase
                phase_key = old_phase.name
                if phase_key not in self.job_progress[job_id]["phase_times"]:
                    self.job_progress[job_id]["phase_times"][phase_key] = 0
                self.job_progress[job_id]["phase_times"][phase_key] += \
                    time.time() - self.job_progress[job_id].get("phase_start", time.time())

            self.job_progress[job_id]["phase"] = phase
            self.job_progress[job_id]["phase_start"] = time.time()

    def estimate_time_remaining(self, job_id: str) -> Optional[float]:
        """Estimate remaining time based on progress"""
        if job_id not in self.job_progress:
            return None

        progress = self.job_progress[job_id]
        elapsed = time.time() - self.start_times[job_id]
        current_step = progress["current_step"]
        total_steps = progress["total_steps"]

        if current_step == 0:
            return None

        avg_time_per_step = elapsed / current_step
        remaining_steps = total_steps - current_step

        return avg_time_per_step * remaining_steps

    async def create_progress_update(
        self,
        job_id: str,
        current_step: int,
        custom_message: Optional[str] = None,
        preview_path: Optional[str] = None
    ) -> ProgressUpdate:
        """Create a rich progress update with all context"""
        if job_id not in self.job_progress:
            self.start_job(job_id)

        progress = self.job_progress[job_id]
        progress["current_step"] = current_step

        # Determine phase based on step
        percentage = (current_step / progress["total_steps"]) * 100
        phase = self._determine_phase(percentage)

        # Generate preview if available
        preview_image = None
        if preview_path:
            preview_image = await self.preview_generator.generate_preview_from_latents(preview_path)
        elif percentage > 25:  # Generate progress visualization after 25%
            preview_image = await self.preview_generator.create_progress_visualization(
                percentage, phase
            )

        # Create contextual message
        if custom_message:
            message = custom_message
        else:
            message = self._generate_contextual_message(phase, percentage)

        # Estimate time remaining
        time_remaining = self.estimate_time_remaining(job_id)

        return ProgressUpdate(
            job_id=job_id,
            phase=phase,
            current_step=current_step,
            total_steps=progress["total_steps"],
            message=message,
            percentage=percentage,
            preview_image=preview_image,
            estimated_time_remaining=time_remaining,
            metadata={
                "elapsed_time": time.time() - self.start_times[job_id],
                "phase_times": progress.get("phase_times", {})
            }
        )

    def _determine_phase(self, percentage: float) -> GenerationPhase:
        """Determine the current phase based on percentage"""
        # Special case for exactly 100%
        if percentage >= 100:
            return GenerationPhase.COMPLETE

        for phase in GenerationPhase:
            if phase.start_percent <= percentage < phase.end_percent:
                return phase
        return GenerationPhase.COMPLETE

    def _generate_contextual_message(self, phase: GenerationPhase, percentage: float) -> str:
        """Generate a contextual message based on phase and progress"""
        messages = {
            GenerationPhase.INITIALIZING: [
                "Setting up your creative workspace...",
                "Preparing generation environment..."
            ],
            GenerationPhase.LOADING_MODELS: [
                "Loading artistic AI models...",
                "Preparing character generation models..."
            ],
            GenerationPhase.PROCESSING_PROMPT: [
                "Analyzing your creative vision...",
                "Understanding character requirements..."
            ],
            GenerationPhase.GENERATING_LATENTS: [
                "Composing initial character structure...",
                "Building foundational elements..."
            ],
            GenerationPhase.REFINING_DETAILS: [
                "Adding facial features and expressions...",
                "Refining character proportions...",
                "Enhancing clothing and accessories..."
            ],
            GenerationPhase.APPLYING_STYLE: [
                "Applying anime art style...",
                "Adding artistic finishing touches...",
                "Enhancing colors and shading..."
            ],
            GenerationPhase.FINALIZING: [
                "Producing high-quality output...",
                "Applying final quality enhancements..."
            ],
            GenerationPhase.SAVING: [
                "Saving your masterpiece...",
                "Organizing generated assets..."
            ],
            GenerationPhase.COMPLETE: [
                "Your character is ready!",
                "Generation successful!"
            ]
        }

        phase_messages = messages.get(phase, ["Processing..."])
        # Select message based on progress within phase
        index = min(int(percentage / 10) % len(phase_messages), len(phase_messages) - 1)
        return phase_messages[index]

class SmartErrorRecovery:
    """Intelligent error recovery with user-friendly suggestions"""

    def __init__(self):
        self.error_patterns = {
            "out of memory": self._handle_memory_error,
            "cuda out of memory": self._handle_memory_error,
            "model not found": self._handle_model_error,
            "invalid prompt": self._handle_prompt_error,
            "timeout": self._handle_timeout_error,
            "connection refused": self._handle_connection_error
        }

        self.recovery_strategies = {
            "memory": ["reduce_resolution", "decrease_batch_size", "use_draft_mode"],
            "model": ["download_model", "use_alternative_model", "wait_and_retry"],
            "prompt": ["sanitize_prompt", "provide_examples", "use_defaults"],
            "timeout": ["increase_timeout", "use_faster_mode", "retry_later"],
            "connection": ["restart_service", "check_network", "use_fallback"]
        }

    async def handle_error(
        self,
        error: Exception,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle errors intelligently with recovery suggestions"""
        error_str = str(error).lower()

        # Find matching error pattern
        for pattern, handler in self.error_patterns.items():
            if pattern in error_str:
                return await handler(error, context)

        # Default error handling
        return await self._handle_generic_error(error, context)

    async def _handle_memory_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle out of memory errors"""
        current_resolution = context.get("width", 1024), context.get("height", 1024)

        suggestions = []
        auto_fix_params = {}

        # Suggest resolution reduction
        if current_resolution[0] > 512 or current_resolution[1] > 512:
            new_res = (min(512, current_resolution[0]), min(512, current_resolution[1]))
            suggestions.append(f"Reduce resolution to {new_res[0]}x{new_res[1]}")
            auto_fix_params["width"] = new_res[0]
            auto_fix_params["height"] = new_res[1]

        # Suggest draft mode
        if context.get("quality_mode") != "draft":
            suggestions.append("Switch to draft mode for faster generation")
            auto_fix_params["quality_mode"] = "draft"

        # Suggest batch size reduction
        if context.get("batch_size", 1) > 1:
            suggestions.append("Reduce batch size to 1")
            auto_fix_params["batch_size"] = 1

        return {
            "error_type": "memory",
            "user_message": "Not enough GPU memory for this request",
            "suggestions": suggestions,
            "auto_fix_available": bool(auto_fix_params),
            "auto_fix_params": auto_fix_params,
            "retry_with_fix": True
        }

    async def _handle_model_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle model not found errors"""
        model_name = context.get("model", "unknown")

        return {
            "error_type": "model",
            "user_message": f"The requested model '{model_name}' is not available",
            "suggestions": [
                "Use the default model instead",
                "Wait for model to download",
                "Choose a different art style"
            ],
            "auto_fix_available": True,
            "auto_fix_params": {"model": "default"},
            "retry_with_fix": True
        }

    async def _handle_prompt_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle invalid prompt errors"""
        return {
            "error_type": "prompt",
            "user_message": "Your prompt contains invalid or problematic content",
            "suggestions": [
                "Remove special characters from prompt",
                "Shorten prompt to under 200 characters",
                "Use simpler descriptions"
            ],
            "auto_fix_available": True,
            "auto_fix_params": {"sanitize_prompt": True},
            "retry_with_fix": True
        }

    async def _handle_timeout_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle timeout errors"""
        return {
            "error_type": "timeout",
            "user_message": "Generation is taking longer than expected",
            "suggestions": [
                "Try draft mode for faster results",
                "Reduce image complexity",
                "Check if other jobs are running"
            ],
            "auto_fix_available": True,
            "auto_fix_params": {"quality_mode": "draft", "timeout": 300},
            "retry_with_fix": True
        }

    async def _handle_connection_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle connection errors"""
        return {
            "error_type": "connection",
            "user_message": "Cannot connect to generation service",
            "suggestions": [
                "Check if ComfyUI is running",
                "Restart the generation service",
                "Try again in a few moments"
            ],
            "auto_fix_available": False,
            "auto_fix_params": {},
            "retry_with_fix": False
        }

    async def _handle_generic_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle generic errors"""
        return {
            "error_type": "unknown",
            "user_message": "An unexpected error occurred",
            "suggestions": [
                "Try again with default settings",
                "Check the system status",
                "Contact support if problem persists"
            ],
            "auto_fix_available": False,
            "auto_fix_params": {},
            "retry_with_fix": False
        }

    async def attempt_auto_recovery(
        self,
        error_response: Dict[str, Any],
        original_request: Dict[str, Any],
        retry_function: Callable
    ) -> Optional[Any]:
        """Attempt automatic recovery with suggested fixes"""
        if not error_response.get("auto_fix_available"):
            return None

        if not error_response.get("retry_with_fix"):
            return None

        # Apply auto-fix parameters
        fixed_request = {**original_request, **error_response["auto_fix_params"]}

        logger.info(f"Attempting auto-recovery with fixes: {error_response['auto_fix_params']}")

        try:
            # Retry with fixed parameters
            result = await retry_function(fixed_request)
            return result
        except Exception as e:
            logger.error(f"Auto-recovery failed: {e}")
            return None

class UXEnhancementManager:
    """Main manager for all UX enhancements"""

    def __init__(self):
        self.preview_generator = PreviewGenerator()
        self.progress_tracker = ContextualProgressTracker(self.preview_generator)
        self.error_recovery = SmartErrorRecovery()
        self.websocket_connections = {}  # job_id -> websocket connection

    async def track_generation(
        self,
        job_id: str,
        websocket_send: Optional[Callable] = None,
        total_steps: int = 20
    ):
        """Track generation progress with rich updates"""
        self.progress_tracker.start_job(job_id, total_steps)

        if websocket_send:
            self.websocket_connections[job_id] = websocket_send

        # Send initial update
        await self._send_progress_update(job_id, 0)

    async def update_progress(
        self,
        job_id: str,
        current_step: int,
        preview_path: Optional[str] = None,
        custom_message: Optional[str] = None
    ):
        """Send a progress update with preview"""
        update = await self.progress_tracker.create_progress_update(
            job_id, current_step, custom_message, preview_path
        )

        # Send via WebSocket if connected
        if job_id in self.websocket_connections:
            await self.websocket_connections[job_id](update.to_websocket_message())

        return update

    async def handle_generation_error(
        self,
        job_id: str,
        error: Exception,
        context: Dict[str, Any],
        retry_function: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Handle generation errors with smart recovery"""
        error_response = await self.error_recovery.handle_error(error, context)

        # Send error update via WebSocket
        if job_id in self.websocket_connections:
            error_message = json.dumps({
                "type": "error",
                "job_id": job_id,
                **error_response
            })
            await self.websocket_connections[job_id](error_message)

        # Attempt auto-recovery if available
        if retry_function and error_response.get("auto_fix_available"):
            recovery_result = await self.error_recovery.attempt_auto_recovery(
                error_response, context, retry_function
            )

            if recovery_result:
                # Send recovery success update
                if job_id in self.websocket_connections:
                    success_message = json.dumps({
                        "type": "recovery_success",
                        "job_id": job_id,
                        "message": "Successfully recovered with automatic fixes",
                        "applied_fixes": error_response["auto_fix_params"]
                    })
                    await self.websocket_connections[job_id](success_message)

                return recovery_result

        return error_response

    async def _send_progress_update(self, job_id: str, step: int):
        """Internal method to send progress updates"""
        await self.update_progress(job_id, step)

    def cleanup_job(self, job_id: str):
        """Clean up resources for a completed job"""
        if job_id in self.websocket_connections:
            del self.websocket_connections[job_id]

        if job_id in self.progress_tracker.job_progress:
            del self.progress_tracker.job_progress[job_id]

        if job_id in self.progress_tracker.start_times:
            del self.progress_tracker.start_times[job_id]

# Export the main manager
ux_manager = UXEnhancementManager()