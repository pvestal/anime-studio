#!/usr/bin/env python3
"""
Phase 3: Full Video Production with SVD
Stable Video Diffusion for full video sequences from character sheets
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import cv2
import httpx
import logging

logger = logging.getLogger(__name__)

@dataclass
class VideoConfig:
    """Configuration for video generation"""
    duration: int = 5  # seconds
    fps: int = 24
    width: int = 1024
    height: int = 576
    motion_bucket_id: int = 127  # SVD motion strength
    augmentation_level: float = 0.0
    decode_chunk_size: int = 8
    seed: int = -1

@dataclass
class VideoQualityMetrics:
    """Quality metrics for full video"""
    temporal_coherence: float  # Target: >0.85
    motion_quality: float       # Target: >0.80
    character_consistency: float  # Target: >0.90
    scene_stability: float      # Target: >0.85
    overall_quality: float      # Weighted average

class VideoProductionEngine:
    """Phase 3 video production using SVD and AnimateDiff"""

    def __init__(self, comfyui_host: str = "localhost", comfyui_port: int = 8188):
        self.comfyui_url = f"http://{comfyui_host}:{comfyui_port}"
        self.client_id = str(uuid.uuid4())

    async def generate_video_from_character_sheet(
        self,
        character_sheet_path: str,
        prompt: str,
        motion_prompt: str,
        config: VideoConfig = None
    ) -> Dict[str, any]:
        """Generate full video from character sheet using SVD"""

        if config is None:
            config = VideoConfig()

        workflow = self._create_svd_workflow(
            character_sheet_path,
            prompt,
            motion_prompt,
            config
        )

        try:
            # Submit workflow to ComfyUI
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": workflow, "client_id": self.client_id}
                )

                if response.status_code != 200:
                    raise Exception(f"ComfyUI error: {response.text}")

                prompt_id = response.json()["prompt_id"]

                # Monitor generation
                output_path = await self._monitor_generation(prompt_id)

                # Evaluate quality
                metrics = await self._evaluate_video_quality(output_path)

                return {
                    "success": True,
                    "prompt_id": prompt_id,
                    "output_path": output_path,
                    "config": config.__dict__,
                    "metrics": metrics.__dict__,
                    "phase": 3,
                    "type": "full_video"
                }

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "phase": 3
            }

    def _create_svd_workflow(
        self,
        character_sheet: str,
        prompt: str,
        motion_prompt: str,
        config: VideoConfig
    ) -> Dict:
        """Create SVD workflow for video generation"""

        total_frames = config.fps * config.duration

        workflow = {
            "1": {
                "class_type": "LoadImage",
                "inputs": {
                    "image": character_sheet,
                    "upload": "image"
                }
            },
            "2": {
                "class_type": "StableVideoDiffusionModel",
                "inputs": {
                    "model": "svd_xt",  # Extended temporal model
                    "motion_bucket_id": config.motion_bucket_id,
                    "augmentation_level": config.augmentation_level,
                    "fps": config.fps,
                    "num_frames": min(total_frames, 120),  # SVD limit
                    "decode_chunk_size": config.decode_chunk_size,
                    "seed": config.seed if config.seed > 0 else np.random.randint(0, 2**32),
                    "image": ["1", 0]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": f"{prompt}, {motion_prompt}",
                    "clip": ["4", 0]
                }
            },
            "4": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "clip_l.safetensors"
                }
            },
            "5": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "frame_rate": config.fps,
                    "format": "video/h264-mp4",
                    "images": ["2", 0]
                }
            },
            "6": {
                "class_type": "SaveVideo",
                "inputs": {
                    "filename_prefix": f"phase3_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "images": ["5", 0]
                }
            }
        }

        # Add frame interpolation for smoother motion
        if total_frames > 120:
            workflow["7"] = {
                "class_type": "RIFE_FrameInterpolation",
                "inputs": {
                    "frames": ["2", 0],
                    "multiplier": 2,  # Double frames
                    "model": "rife4.6"
                }
            }
            workflow["6"]["inputs"]["images"] = ["7", 0]

        return workflow

    async def _monitor_generation(self, prompt_id: str) -> str:
        """Monitor video generation progress"""

        async with httpx.AsyncClient() as client:
            while True:
                try:
                    # Check history
                    history = await client.get(f"{self.comfyui_url}/history/{prompt_id}")
                    if history.status_code == 200:
                        data = history.json()
                        if prompt_id in data and data[prompt_id].get("outputs"):
                            # Find video output
                            for output in data[prompt_id]["outputs"].values():
                                if "videos" in output:
                                    return output["videos"][0]["filename"]

                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                    await asyncio.sleep(2)

    async def _evaluate_video_quality(self, video_path: str) -> VideoQualityMetrics:
        """Evaluate video quality metrics"""

        try:
            cap = cv2.VideoCapture(video_path)
            frames = []

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                frames.append(frame)

            cap.release()

            # Calculate metrics
            temporal_coherence = self._calc_temporal_coherence(frames)
            motion_quality = self._calc_motion_quality(frames)
            character_consistency = self._calc_character_consistency(frames)
            scene_stability = self._calc_scene_stability(frames)

            overall = (
                temporal_coherence * 0.3 +
                motion_quality * 0.2 +
                character_consistency * 0.3 +
                scene_stability * 0.2
            )

            return VideoQualityMetrics(
                temporal_coherence=temporal_coherence,
                motion_quality=motion_quality,
                character_consistency=character_consistency,
                scene_stability=scene_stability,
                overall_quality=overall
            )

        except Exception as e:
            logger.error(f"Quality evaluation failed: {e}")
            return VideoQualityMetrics(0, 0, 0, 0, 0)

    def _calc_temporal_coherence(self, frames: List[np.ndarray]) -> float:
        """Calculate temporal coherence between frames"""
        if len(frames) < 2:
            return 0.0

        coherences = []
        for i in range(1, len(frames)):
            # Simple frame difference
            diff = cv2.absdiff(frames[i-1], frames[i])
            coherence = 1.0 - (np.mean(diff) / 255.0)
            coherences.append(coherence)

        return np.mean(coherences)

    def _calc_motion_quality(self, frames: List[np.ndarray]) -> float:
        """Calculate motion quality using optical flow"""
        if len(frames) < 2:
            return 0.0

        flows = []
        for i in range(1, len(frames)):
            gray1 = cv2.cvtColor(frames[i-1], cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)

            flow = cv2.calcOpticalFlowFarneback(
                gray1, gray2, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )

            # Check flow smoothness
            flow_mag = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
            flows.append(np.mean(flow_mag))

        # Consistent motion is good
        flow_std = np.std(flows)
        quality = 1.0 / (1.0 + flow_std)  # Lower variance = better

        return min(quality, 1.0)

    def _calc_character_consistency(self, frames: List[np.ndarray]) -> float:
        """Calculate character appearance consistency"""
        # Simplified - compare histograms
        if len(frames) < 2:
            return 0.0

        ref_hist = cv2.calcHist([frames[0]], [0,1,2], None, [8,8,8], [0,256,0,256,0,256])
        ref_hist = cv2.normalize(ref_hist, ref_hist).flatten()

        similarities = []
        for frame in frames[1:]:
            hist = cv2.calcHist([frame], [0,1,2], None, [8,8,8], [0,256,0,256,0,256])
            hist = cv2.normalize(hist, hist).flatten()

            similarity = cv2.compareHist(ref_hist, hist, cv2.HISTCMP_CORREL)
            similarities.append(similarity)

        return np.mean(similarities)

    def _calc_scene_stability(self, frames: List[np.ndarray]) -> float:
        """Calculate scene/background stability"""
        if len(frames) < 2:
            return 0.0

        # Use SSIM for structural stability
        stabilities = []
        for i in range(1, len(frames)):
            gray1 = cv2.cvtColor(frames[i-1], cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)

            # Simple SSIM approximation
            mse = np.mean((gray1.astype(float) - gray2.astype(float)) ** 2)
            if mse == 0:
                stabilities.append(1.0)
            else:
                stability = 1.0 / (1.0 + mse / 1000.0)
                stabilities.append(stability)

        return np.mean(stabilities)


# Integration with v2.0 tracking
async def generate_phase3_video(
    character_sheet: str,
    prompt: str,
    motion_prompt: str,
    project_id: int,
    v2_job_id: int = None
) -> Dict:
    """Generate Phase 3 video with v2.0 tracking"""

    from v2_integration import v2_integration, complete_job_with_quality

    engine = VideoProductionEngine()
    config = VideoConfig()

    # Generate video
    result = await engine.generate_video_from_character_sheet(
        character_sheet,
        prompt,
        motion_prompt,
        config
    )

    # Update v2.0 tracking if job exists
    if v2_job_id and result["success"]:
        metrics = result["metrics"]

        # Calculate quality scores for v2 system
        face_similarity = metrics["character_consistency"]
        aesthetic_score = metrics["overall_quality"] * 10  # Scale to 0-10

        gate_status = await complete_job_with_quality(
            job_id=v2_job_id,
            output_path=result["output_path"],
            face_similarity=face_similarity,
            aesthetic_score=aesthetic_score
        )

        result["v2_gate_status"] = gate_status
        result["v2_job_id"] = v2_job_id

    return result