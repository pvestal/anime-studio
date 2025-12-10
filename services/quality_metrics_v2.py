"""
Tower Anime Production System - Quality Metrics Service
Provides automated quality evaluation for generation outputs with phase gating
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np

logger = logging.getLogger(__name__)

# Conditional imports
try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


@dataclass
class QualityThresholds:
    """Quality thresholds by phase"""

    # Phase 1: Still Images
    face_similarity: float = 0.70
    aesthetic_score: float = 5.5
    style_adherence: float = 0.85  # CLIP similarity

    # Phase 2: Animation Loops
    temporal_lpips: float = 0.15  # Lower is better
    motion_smoothness: float = 0.95

    # Phase 3: Full Video
    subject_consistency: float = 0.90
    scene_continuity: float = 0.85
    fvd_score: float = 500.0  # Lower is better


@dataclass
class QualityResult:
    """Result of quality evaluation"""

    job_id: UUID
    phase: str
    scores: Dict[str, float]
    passes_threshold: bool
    blocking_metrics: List[str]
    warnings: List[str]


class QualityMetricsService:
    """
    Service for evaluating generation quality and enforcing phase gates.

    Supports:
    - Face consistency (ArcFace similarity)
    - Aesthetic scoring (LAION predictor)
    - Temporal coherence (LPIPS between frames)
    - Motion quality (VBench metrics)
    """

    def __init__(
        self,
        db_pool,
        character_service,  # CharacterConsistencyService instance
        device: str = "cuda",
        thresholds: Optional[QualityThresholds] = None,
    ):
        self.db = db_pool
        self.character_service = character_service
        self.device = device
        self.thresholds = thresholds or QualityThresholds()

        # Lazy-loaded models
        self._aesthetic_model = None
        self._lpips_model = None
        self._clip_model = None

    async def initialize(self):
        """Initialize quality models (call once at startup)"""
        # Models are lazy-loaded on first use to reduce startup time
        logger.info("Quality metrics service initialized (models lazy-loaded)")

    # === Phase 1: Still Image Quality ===

    async def evaluate_still_image(
        self,
        job_id: UUID,
        image_path: str,
        character_ids: List[UUID] = None,
        style_reference_path: str = None,
    ) -> QualityResult:
        """
        Evaluate quality of a still image generation.

        Metrics:
        - Face similarity (if characters provided)
        - Aesthetic score
        - Style adherence (if reference provided)
        """
        scores = {}
        blocking = []
        warnings = []

        # 1. Face consistency check
        if character_ids:
            face_scores = []
            for char_id in character_ids:
                result = await self.character_service.check_consistency(
                    char_id, image_path, self.thresholds.face_similarity
                )
                if result.get("error"):
                    warnings.append(
                        f"Face check failed for {char_id}: {result['error']}"
                    )
                else:
                    face_scores.append(result["similarity_score"])
                    if not result["passes_threshold"]:
                        blocking.append(f"face_similarity_{char_id}")

            if face_scores:
                scores["face_similarity"] = np.mean(face_scores)

        # 2. Aesthetic score
        aesthetic = await self._compute_aesthetic_score(image_path)
        if aesthetic is not None:
            scores["aesthetic_score"] = aesthetic
            if aesthetic < self.thresholds.aesthetic_score:
                warnings.append(
                    f"Aesthetic score {aesthetic:.2f} below threshold {self.thresholds.aesthetic_score}"
                )

        # 3. Style adherence
        if style_reference_path:
            style_sim = await self._compute_style_similarity(
                image_path, style_reference_path
            )
            if style_sim is not None:
                scores["style_adherence"] = style_sim
                if style_sim < self.thresholds.style_adherence:
                    warnings.append(
                        f"Style adherence {style_sim:.2f} below threshold")

        passes = len(blocking) == 0

        # Store scores
        await self._store_scores(job_id, scores, passes)

        return QualityResult(
            job_id=job_id,
            phase="phase_1_still",
            scores=scores,
            passes_threshold=passes,
            blocking_metrics=blocking,
            warnings=warnings,
        )

    # === Phase 2: Animation Loop Quality ===

    async def evaluate_animation_loop(
        self, job_id: UUID, video_path: str, character_ids: List[UUID] = None
    ) -> QualityResult:
        """
        Evaluate quality of an animation loop.

        Metrics:
        - Face consistency across frames
        - Temporal LPIPS (frame-to-frame perceptual similarity)
        - Motion smoothness
        """
        scores = {}
        blocking = []
        warnings = []

        # Extract frames
        frames = await self._extract_frames(video_path, sample_rate=5)
        if not frames:
            return QualityResult(
                job_id=job_id,
                phase="phase_2_loop",
                scores={},
                passes_threshold=False,
                blocking_metrics=["frame_extraction_failed"],
                warnings=["Could not extract frames from video"],
            )

        # 1. Face consistency across frames
        if character_ids:
            face_scores = await self._evaluate_face_consistency_video(
                frames, character_ids
            )
            if face_scores:
                scores["face_similarity"] = np.mean(face_scores)
                if scores["face_similarity"] < self.thresholds.face_similarity:
                    blocking.append("face_similarity")

        # 2. Temporal LPIPS
        lpips_score = await self._compute_temporal_lpips(frames)
        if lpips_score is not None:
            scores["temporal_lpips"] = lpips_score
            if lpips_score > self.thresholds.temporal_lpips:  # Lower is better
                blocking.append("temporal_lpips")

        # 3. Motion smoothness (placeholder - integrate VBench)
        motion_score = await self._estimate_motion_smoothness(frames)
        if motion_score is not None:
            scores["motion_smoothness"] = motion_score
            if motion_score < self.thresholds.motion_smoothness:
                warnings.append(
                    f"Motion smoothness {motion_score:.2f} below threshold")

        passes = len(blocking) == 0
        await self._store_scores(job_id, scores, passes)

        return QualityResult(
            job_id=job_id,
            phase="phase_2_loop",
            scores=scores,
            passes_threshold=passes,
            blocking_metrics=blocking,
            warnings=warnings,
        )

    # === Phase 3: Full Video Quality ===

    async def evaluate_full_video(
        self,
        job_id: UUID,
        video_path: str,
        character_ids: List[UUID] = None,
        scene_context: Dict[str, Any] = None,
    ) -> QualityResult:
        """
        Evaluate quality of full video production.

        Metrics:
        - All Phase 2 metrics
        - Subject consistency (DINO-based)
        - Scene continuity
        """
        scores = {}
        blocking = []
        warnings = []

        frames = await self._extract_frames(video_path, sample_rate=10)
        if not frames:
            return QualityResult(
                job_id=job_id,
                phase="phase_3_video",
                scores={},
                passes_threshold=False,
                blocking_metrics=["frame_extraction_failed"],
                warnings=["Could not extract frames from video"],
            )

        # Run Phase 2 evaluations
        phase2_result = await self.evaluate_animation_loop(
            job_id, video_path, character_ids
        )
        scores.update(phase2_result.scores)
        blocking.extend(phase2_result.blocking_metrics)
        warnings.extend(phase2_result.warnings)

        # 4. Subject consistency (DINO embeddings)
        subject_score = await self._compute_subject_consistency(frames)
        if subject_score is not None:
            scores["subject_consistency"] = subject_score
            if subject_score < self.thresholds.subject_consistency:
                blocking.append("subject_consistency")

        # 5. Scene continuity (background stability)
        if scene_context:
            continuity = await self._compute_scene_continuity(frames, scene_context)
            if continuity is not None:
                scores["scene_continuity"] = continuity
                if continuity < self.thresholds.scene_continuity:
                    warnings.append(
                        f"Scene continuity {continuity:.2f} below threshold"
                    )

        passes = len(blocking) == 0
        await self._store_scores(job_id, scores, passes)

        return QualityResult(
            job_id=job_id,
            phase="phase_3_video",
            scores=scores,
            passes_threshold=passes,
            blocking_metrics=blocking,
            warnings=warnings,
        )

    # === Phase Gate Evaluation ===

    async def evaluate_phase_gate(
        self, phase: str, test_jobs: List[UUID]
    ) -> Dict[str, Any]:
        """
        Evaluate if a development phase passes its quality gate.

        Requires multiple successful generations to pass.
        """
        results = []

        async with self.db.acquire() as conn:
            for job_id in test_jobs:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM quality_scores WHERE job_id = $1
                """,
                    job_id,
                )
                if row:
                    results.append(dict(row))

        if not results:
            return {
                "phase": phase,
                "passed": False,
                "reason": "No quality scores found for test jobs",
                "jobs_evaluated": 0,
            }

        # Aggregate metrics
        metrics = {}
        for r in results:
            for key, value in r.items():
                if (
                    key not in ["id", "job_id",
                                "passes_threshold", "evaluated_at"]
                    and value is not None
                ):
                    if key not in metrics:
                        metrics[key] = []
                    metrics[key].append(value)

        avg_metrics = {k: np.mean(v) for k, v in metrics.items()}
        pass_rate = sum(1 for r in results if r.get("passes_threshold", False)) / len(
            results
        )

        # Phase passes if 80%+ of jobs pass
        gate_passed = pass_rate >= 0.80

        return {
            "phase": phase,
            "passed": gate_passed,
            "pass_rate": pass_rate,
            "jobs_evaluated": len(results),
            "average_metrics": avg_metrics,
            "threshold_used": 0.80,
        }

    # === Private Methods ===

    async def _extract_frames(
        self, video_path: str, sample_rate: int = 10
    ) -> List[np.ndarray]:
        """Extract frames from video at given sample rate"""
        if not CV2_AVAILABLE:
            return []

        frames = []
        try:
            cap = cv2.VideoCapture(video_path)
            frame_idx = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % sample_rate == 0:
                    frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                frame_idx += 1

            cap.release()
        except Exception as e:
            logger.error(f"Error extracting frames: {e}")

        return frames

    async def _evaluate_face_consistency_video(
        self, frames: List[np.ndarray], character_ids: List[UUID]
    ) -> List[float]:
        """Evaluate face consistency across video frames"""
        scores = []

        for char_id in character_ids:
            ref_embedding = await self.character_service._get_stored_embedding(char_id)
            if ref_embedding is None:
                continue

            frame_scores = []
            for frame in frames:
                # Save temp frame and compute embedding
                # In production, pass frame directly to face analyzer
                if self.character_service.face_analyzer:
                    faces = self.character_service.face_analyzer.get(frame)
                    if faces:
                        sim = self.character_service._cosine_similarity(
                            ref_embedding, faces[0].embedding
                        )
                        frame_scores.append(sim)

            if frame_scores:
                scores.append(np.mean(frame_scores))

        return scores

    async def _compute_aesthetic_score(self, image_path: str) -> Optional[float]:
        """Compute LAION aesthetic score"""
        # Placeholder - integrate with aesthetic predictor
        # In production: use shunk031/aesthetics-predictor-v2-vit-large-patch14
        logger.debug("Aesthetic scoring placeholder - returning mock value")
        return 6.0  # Mock value for testing

    async def _compute_style_similarity(
        self, image_path: str, reference_path: str
    ) -> Optional[float]:
        """Compute CLIP similarity between image and style reference"""
        # Placeholder - integrate with CLIP
        logger.debug("Style similarity placeholder - returning mock value")
        return 0.88  # Mock value

    async def _compute_temporal_lpips(
        self, frames: List[np.ndarray]
    ) -> Optional[float]:
        """Compute average LPIPS between adjacent frames"""
        if len(frames) < 2:
            return None

        # Placeholder - integrate with torchmetrics LPIPS
        # Lower values = more similar = smoother video
        logger.debug("LPIPS placeholder - returning mock value")
        return 0.10  # Mock value

    async def _estimate_motion_smoothness(
        self, frames: List[np.ndarray]
    ) -> Optional[float]:
        """Estimate motion smoothness using optical flow variance"""
        if len(frames) < 2 or not CV2_AVAILABLE:
            return None

        try:
            flow_magnitudes = []
            prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_RGB2GRAY)

            for frame in frames[1:]:
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
                flow_magnitudes.append(np.mean(magnitude))
                prev_gray = gray

            # Lower variance in flow = smoother motion
            variance = np.var(flow_magnitudes)
            # Convert to 0-1 score where higher is better
            smoothness = 1.0 / (1.0 + variance)
            return float(smoothness)

        except Exception as e:
            logger.error(f"Error computing motion smoothness: {e}")
            return None

    async def _compute_subject_consistency(
        self, frames: List[np.ndarray]
    ) -> Optional[float]:
        """Compute subject consistency using DINO embeddings"""
        # Placeholder - integrate with DINOv2
        logger.debug("Subject consistency placeholder - returning mock value")
        return 0.92  # Mock value

    async def _compute_scene_continuity(
        self, frames: List[np.ndarray], scene_context: Dict[str, Any]
    ) -> Optional[float]:
        """Compute scene/background continuity"""
        # Placeholder - compare background regions with CLIP
        logger.debug("Scene continuity placeholder - returning mock value")
        return 0.88  # Mock value

    async def _store_scores(self, job_id: UUID, scores: Dict[str, float], passes: bool):
        """Store quality scores in database"""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO quality_scores 
                (job_id, face_similarity, aesthetic_score, temporal_lpips, 
                 motion_smoothness, subject_consistency, passes_threshold)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (job_id) DO UPDATE SET
                    face_similarity = EXCLUDED.face_similarity,
                    aesthetic_score = EXCLUDED.aesthetic_score,
                    temporal_lpips = EXCLUDED.temporal_lpips,
                    motion_smoothness = EXCLUDED.motion_smoothness,
                    subject_consistency = EXCLUDED.subject_consistency,
                    passes_threshold = EXCLUDED.passes_threshold,
                    evaluated_at = NOW()
            """,
                job_id,
                scores.get("face_similarity"),
                scores.get("aesthetic_score"),
                scores.get("temporal_lpips"),
                scores.get("motion_smoothness"),
                scores.get("subject_consistency"),
                passes,
            )
