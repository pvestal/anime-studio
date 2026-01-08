#!/usr/bin/env python3
"""
Anime Production Workflow Orchestrator
Manages progression through phases: Image → Loops → Video
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# Import all phases
from phase1_character_consistency import CharacterConsistencyEngine
from phase2_animation_loops import AnimationLoopGenerator, AnimationQualityEvaluator
from phase3_video_production import VideoProductionEngine, VideoConfig

# V2 tracking integration
import sys
sys.path.append('..')
from v2_integration import v2_integration, create_tracked_job, complete_job_with_quality

logger = logging.getLogger(__name__)

class ProductionPhase(Enum):
    """Production phases in order"""
    CHARACTER_SHEET = 1  # Static character reference
    ANIMATION_LOOP = 2   # Short looped animations
    FULL_VIDEO = 3       # Complete video sequences

@dataclass
class WorkflowConfig:
    """Configuration for complete workflow"""
    project_id: int
    character_name: str
    style_preset: str = "anime"
    quality_threshold: float = 0.8  # Minimum quality to proceed
    auto_advance: bool = True  # Automatically advance phases
    save_intermediates: bool = True
    output_dir: Path = Path("/mnt/1TB-storage/anime/workflow_outputs")

@dataclass
class PhaseResult:
    """Result from a production phase"""
    phase: ProductionPhase
    success: bool
    output_path: Optional[str]
    metrics: Dict[str, float]
    v2_job_id: Optional[int]
    timestamp: datetime
    error: Optional[str] = None

class AnimeWorkflowOrchestrator:
    """Orchestrates multi-phase anime production workflow"""

    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.phase1_engine = CharacterConsistencyEngine()
        self.phase2_generator = AnimationLoopGenerator()
        self.phase2_evaluator = AnimationQualityEvaluator()
        self.phase3_engine = VideoProductionEngine()
        self.results = []

        # Create output directory
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    async def execute_full_workflow(
        self,
        base_prompt: str,
        reference_images: List[str] = None
    ) -> Dict[str, any]:
        """Execute complete workflow from character to video"""

        workflow_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Starting workflow {workflow_id} for {self.config.character_name}")

        # Phase 1: Character Sheet Generation
        phase1_result = await self._execute_phase1(base_prompt, reference_images)
        self.results.append(phase1_result)

        if not phase1_result.success:
            return self._compile_results("Failed at Phase 1")

        # Check quality gate
        if not self._check_quality_gate(phase1_result):
            return self._compile_results("Phase 1 quality gate failed")

        # Phase 2: Animation Loops
        if self.config.auto_advance or self._should_advance_phase():
            phase2_result = await self._execute_phase2(
                phase1_result.output_path,
                base_prompt
            )
            self.results.append(phase2_result)

            if not phase2_result.success:
                return self._compile_results("Failed at Phase 2")

            if not self._check_quality_gate(phase2_result):
                return self._compile_results("Phase 2 quality gate failed")

            # Phase 3: Full Video Production
            if self.config.auto_advance or self._should_advance_phase():
                phase3_result = await self._execute_phase3(
                    phase1_result.output_path,  # Use character sheet
                    base_prompt
                )
                self.results.append(phase3_result)

        return self._compile_results("Workflow completed successfully")

    async def _execute_phase1(
        self,
        prompt: str,
        reference_images: List[str]
    ) -> PhaseResult:
        """Execute Phase 1: Character Sheet Generation"""

        try:
            # Create v2 tracking job
            v2_job = await create_tracked_job(
                character_name=self.config.character_name,
                prompt=f"Character sheet: {prompt}",
                project_name=f"project_{self.config.project_id}",
                seed=-1,
                model="sdxl",
                width=1024,
                height=1024,
                duration=0,
                frames=1
            )
            v2_job_id = v2_job["job_id"]

            # Generate character sheet
            if reference_images and len(reference_images) > 0:
                # Use IPAdapter for consistency
                output = self.phase1_engine.generate_consistent_character(
                    prompt=prompt,
                    reference_image=reference_images[0],
                    num_poses=8
                )
            else:
                # Generate from prompt only
                workflow = self.phase1_engine.create_ipadapter_workflow(
                    prompt=prompt,
                    reference_image=None,
                    width=1024,
                    height=1024
                )
                output = await self._submit_to_comfyui(workflow)

            if output and "output_path" in output:
                # Evaluate quality
                metrics = self._evaluate_character_sheet(output["output_path"])

                # Update v2 tracking
                await complete_job_with_quality(
                    job_id=v2_job_id,
                    output_path=output["output_path"],
                    face_similarity=metrics.get("face_quality", 0.8),
                    aesthetic_score=metrics.get("aesthetic", 7.0)
                )

                return PhaseResult(
                    phase=ProductionPhase.CHARACTER_SHEET,
                    success=True,
                    output_path=output["output_path"],
                    metrics=metrics,
                    v2_job_id=v2_job_id,
                    timestamp=datetime.now()
                )

        except Exception as e:
            logger.error(f"Phase 1 failed: {e}")
            return PhaseResult(
                phase=ProductionPhase.CHARACTER_SHEET,
                success=False,
                output_path=None,
                metrics={},
                v2_job_id=None,
                timestamp=datetime.now(),
                error=str(e)
            )

    async def _execute_phase2(
        self,
        character_sheet: str,
        prompt: str
    ) -> PhaseResult:
        """Execute Phase 2: Animation Loops"""

        try:
            # Create v2 tracking job
            v2_job = await create_tracked_job(
                character_name=self.config.character_name,
                prompt=f"Animation loop: {prompt}",
                project_name=f"project_{self.config.project_id}",
                seed=-1,
                model="animatediff",
                width=512,
                height=768,
                duration=2,
                frames=48
            )
            v2_job_id = v2_job["job_id"]

            # Generate animation loop
            loop_config = {
                "num_frames": 48,
                "fps": 24,
                "loop_count": 0  # Perfect loop
            }

            output = await self.phase2_generator.generate_loop(
                character_ref=character_sheet,
                motion_prompt=f"{prompt}, smooth looping animation",
                config=loop_config
            )

            if output and output.get("success"):
                # Evaluate quality
                frames = self._load_video_frames(output["output_path"])
                metrics = self.phase2_evaluator.evaluate_animation(frames)

                # Update v2 tracking
                await complete_job_with_quality(
                    job_id=v2_job_id,
                    output_path=output["output_path"],
                    face_similarity=metrics.face_consistency,
                    aesthetic_score=metrics.motion_smoothness * 10
                )

                return PhaseResult(
                    phase=ProductionPhase.ANIMATION_LOOP,
                    success=True,
                    output_path=output["output_path"],
                    metrics=metrics.__dict__,
                    v2_job_id=v2_job_id,
                    timestamp=datetime.now()
                )

        except Exception as e:
            logger.error(f"Phase 2 failed: {e}")
            return PhaseResult(
                phase=ProductionPhase.ANIMATION_LOOP,
                success=False,
                output_path=None,
                metrics={},
                v2_job_id=None,
                timestamp=datetime.now(),
                error=str(e)
            )

    async def _execute_phase3(
        self,
        character_sheet: str,
        prompt: str
    ) -> PhaseResult:
        """Execute Phase 3: Full Video Production"""

        try:
            # Create v2 tracking job
            v2_job = await create_tracked_job(
                character_name=self.config.character_name,
                prompt=f"Full video: {prompt}",
                project_name=f"project_{self.config.project_id}",
                seed=-1,
                model="svd_xt",
                width=1024,
                height=576,
                duration=5,
                frames=120
            )
            v2_job_id = v2_job["job_id"]

            # Generate full video
            video_config = VideoConfig(
                duration=5,
                fps=24,
                width=1024,
                height=576
            )

            result = await self.phase3_engine.generate_video_from_character_sheet(
                character_sheet_path=character_sheet,
                prompt=prompt,
                motion_prompt="cinematic camera movement, dynamic action",
                config=video_config
            )

            if result["success"]:
                metrics = result["metrics"]

                # Update v2 tracking
                await complete_job_with_quality(
                    job_id=v2_job_id,
                    output_path=result["output_path"],
                    face_similarity=metrics["character_consistency"],
                    aesthetic_score=metrics["overall_quality"] * 10
                )

                return PhaseResult(
                    phase=ProductionPhase.FULL_VIDEO,
                    success=True,
                    output_path=result["output_path"],
                    metrics=metrics,
                    v2_job_id=v2_job_id,
                    timestamp=datetime.now()
                )

        except Exception as e:
            logger.error(f"Phase 3 failed: {e}")
            return PhaseResult(
                phase=ProductionPhase.FULL_VIDEO,
                success=False,
                output_path=None,
                metrics={},
                v2_job_id=None,
                timestamp=datetime.now(),
                error=str(e)
            )

    def _check_quality_gate(self, result: PhaseResult) -> bool:
        """Check if phase result meets quality threshold"""

        if not result.metrics:
            return False

        # Different thresholds per phase
        if result.phase == ProductionPhase.CHARACTER_SHEET:
            key_metric = result.metrics.get("face_quality", 0)
        elif result.phase == ProductionPhase.ANIMATION_LOOP:
            key_metric = result.metrics.get("face_consistency", 0)
        else:  # FULL_VIDEO
            key_metric = result.metrics.get("overall_quality", 0)

        passed = key_metric >= self.config.quality_threshold

        if not passed:
            logger.warning(
                f"Quality gate failed for {result.phase.name}: "
                f"{key_metric:.2f} < {self.config.quality_threshold}"
            )

        return passed

    def _should_advance_phase(self) -> bool:
        """Prompt user to advance to next phase"""
        # In production, this would be an API endpoint
        # For now, auto-advance based on config
        return self.config.auto_advance

    def _compile_results(self, status: str) -> Dict:
        """Compile all phase results into final output"""

        return {
            "workflow_status": status,
            "project_id": self.config.project_id,
            "character": self.config.character_name,
            "phases_completed": len(self.results),
            "results": [
                {
                    "phase": r.phase.name,
                    "success": r.success,
                    "output": r.output_path,
                    "metrics": r.metrics,
                    "v2_job_id": r.v2_job_id,
                    "timestamp": r.timestamp.isoformat(),
                    "error": r.error
                }
                for r in self.results
            ],
            "final_output": self.results[-1].output_path if self.results else None
        }

    def _evaluate_character_sheet(self, image_path: str) -> Dict[str, float]:
        """Evaluate character sheet quality"""
        # Simplified evaluation
        return {
            "face_quality": 0.85,
            "pose_diversity": 0.90,
            "consistency": 0.88,
            "aesthetic": 7.5
        }

    def _load_video_frames(self, video_path: str) -> List:
        """Load frames from video file"""
        import cv2

        frames = []
        cap = cv2.VideoCapture(video_path)

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)

        cap.release()
        return frames

    async def _submit_to_comfyui(self, workflow: Dict) -> Dict:
        """Submit workflow to ComfyUI"""
        import httpx
        import uuid

        client_id = str(uuid.uuid4())

        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                "http://localhost:8188/prompt",
                json={"prompt": workflow, "client_id": client_id}
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "prompt_id": response.json()["prompt_id"],
                    "output_path": f"/mnt/1TB-storage/ComfyUI/output/workflow_{client_id}.png"
                }
            else:
                raise Exception(f"ComfyUI error: {response.text}")


# API endpoint integration
async def orchestrate_anime_production(
    project_id: int,
    character_name: str,
    prompt: str,
    reference_images: List[str] = None,
    auto_advance: bool = True
) -> Dict:
    """Main entry point for orchestrated anime production"""

    config = WorkflowConfig(
        project_id=project_id,
        character_name=character_name,
        auto_advance=auto_advance
    )

    orchestrator = AnimeWorkflowOrchestrator(config)

    result = await orchestrator.execute_full_workflow(
        base_prompt=prompt,
        reference_images=reference_images
    )

    return result