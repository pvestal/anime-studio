#!/usr/bin/env python3
"""
Gate 3: Temporal Consistency & Motion Smoothness Testing
Tests frame sequence quality, temporal consistency, and motion flow
"""

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import httpx
import numpy as np
from pydantic import BaseModel
from skimage.metrics import structural_similarity as ssim

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TemporalQualityResult(BaseModel):
    """Temporal quality assessment result"""
    sequence_id: str
    frame_count: int
    flicker_score: float
    motion_smoothness_score: float
    temporal_consistency_score: float
    overall_score: float
    passed: bool
    issues: List[str] = []

class Gate3TemporalChecker:
    """Temporal consistency and motion smoothness quality gate checker"""

    def __init__(self, project_root: Path, echo_brain_url: str = "http://localhost:8309"):
        self.project_root = Path(project_root)
        self.echo_brain_url = echo_brain_url

        # Quality thresholds
        self.FLICKER_THRESHOLD = 0.85  # SSIM threshold for consecutive frames
        self.MOTION_SMOOTHNESS_THRESHOLD = 0.8
        self.TEMPORAL_CONSISTENCY_THRESHOLD = 0.25
        self.OVERALL_THRESHOLD = 0.3

        # Create directories
        (self.project_root / "quality" / "temporal_analysis").mkdir(parents=True, exist_ok=True)

    async def check_temporal_consistency(self, frame_sequence: List[str]) -> Dict[str, float]:
        """
        Gate 3.1: Temporal Consistency Check
        Analyzes character appearance and lighting consistency between frames
        """
        logger.info("⏱️ Gate 3.1: Checking temporal consistency...")

        if len(frame_sequence) < 2:
            logger.warning("❌ Need at least 2 frames for temporal consistency check")
            return {"temporal_consistency": 0.0}

        consistency_scores = []

        for i in range(len(frame_sequence) - 1):
            frame1_path = frame_sequence[i]
            frame2_path = frame_sequence[i + 1]

            try:
                # Load consecutive frames
                img1 = cv2.imread(frame1_path)
                img2 = cv2.imread(frame2_path)

                if img1 is None or img2 is None:
                    logger.warning(f"❌ Could not load frames {i} or {i+1}")
                    continue

                # Calculate temporal consistency metrics
                consistency_score = await self._calculate_temporal_consistency(img1, img2)
                consistency_scores.append(consistency_score)

                if consistency_score >= self.FLICKER_THRESHOLD:
                    logger.debug(f"✅ Frames {i}-{i+1}: Good consistency ({consistency_score:.3f})")
                else:
                    logger.warning(f"⚠️ Frames {i}-{i+1}: Potential flicker ({consistency_score:.3f})")

            except Exception as e:
                logger.error(f"❌ Error analyzing frames {i}-{i+1}: {e}")
                consistency_scores.append(0.0)

        # Calculate overall temporal consistency
        if consistency_scores:
            avg_consistency = sum(consistency_scores) / len(consistency_scores)
            min_consistency = min(consistency_scores)
            logger.info(f"📊 Temporal consistency: avg={avg_consistency:.3f}, min={min_consistency:.3f}")
        else:
            avg_consistency = 0.0
            logger.error("❌ No valid consistency scores calculated")

        return {
            "temporal_consistency": avg_consistency,
            "consistency_scores": consistency_scores,
            "frame_pairs_analyzed": len(consistency_scores)
        }

    async def check_motion_smoothness(self, frame_sequence: List[str]) -> Dict[str, float]:
        """
        Gate 3.2: Motion Smoothness Check
        Analyzes optical flow and motion vectors for smooth movement
        """
        logger.info("🌊 Gate 3.2: Checking motion smoothness...")

        if len(frame_sequence) < 3:
            logger.warning("❌ Need at least 3 frames for motion analysis")
            return {"motion_smoothness": 0.0}

        motion_scores = []
        flow_magnitudes = []

        for i in range(len(frame_sequence) - 2):
            try:
                # Load three consecutive frames for motion analysis
                img1 = cv2.imread(frame_sequence[i], cv2.IMREAD_GRAYSCALE)
                img2 = cv2.imread(frame_sequence[i + 1], cv2.IMREAD_GRAYSCALE)
                img3 = cv2.imread(frame_sequence[i + 2], cv2.IMREAD_GRAYSCALE)

                if img1 is None or img2 is None or img3 is None:
                    continue

                # Calculate optical flow between consecutive frames
                flow_12 = cv2.calcOpticalFlowPyrLK(
                    img1, img2,
                    cv2.goodFeaturesToTrack(img1, maxCorners=100, qualityLevel=0.3, minDistance=7),
                    None
                )[0]

                flow_23 = cv2.calcOpticalFlowPyrLK(
                    img2, img3,
                    cv2.goodFeaturesToTrack(img2, maxCorners=100, qualityLevel=0.3, minDistance=7),
                    None
                )[0]

                # Analyze motion smoothness
                smoothness_score = await self._analyze_motion_smoothness(flow_12, flow_23)
                motion_scores.append(smoothness_score)

                # Calculate flow magnitude for motion intensity analysis
                if flow_12 is not None and len(flow_12) > 0:
                    flow_magnitude = np.mean(np.linalg.norm(flow_12.reshape(-1, 2), axis=1))
                    flow_magnitudes.append(flow_magnitude)

            except Exception as e:
                logger.error(f"❌ Error analyzing motion for frames {i}-{i+2}: {e}")
                motion_scores.append(0.0)

        # Calculate overall motion smoothness
        if motion_scores:
            avg_smoothness = sum(motion_scores) / len(motion_scores)
            motion_variance = float(np.var(flow_magnitudes)) if flow_magnitudes else 0.0
            logger.info(f"📊 Motion smoothness: avg={avg_smoothness:.3f}, variance={motion_variance:.3f}")
        else:
            avg_smoothness = 0.0
            motion_variance = 0.0
            logger.error("❌ No valid motion scores calculated")

        return {
            "motion_smoothness": avg_smoothness,
            "motion_scores": motion_scores,
            "motion_variance": motion_variance,
            "flow_magnitudes": [float(x) for x in flow_magnitudes]
        }

    async def run_gate_3_tests(self, frame_sequence: List[str], sequence_name: str = "unnamed") -> Dict:
        """
        Run complete Gate 3 testing suite
        Returns: Combined temporal quality results with pass/fail status
        """
        logger.info("🚪 Starting Gate 3: Temporal Consistency & Motion Smoothness Tests")

        start_time = datetime.now()

        # Validate input
        if len(frame_sequence) < 2:
            logger.error("❌ Need at least 2 frames for temporal analysis")
            return {
                "gate": "Gate 3: Temporal Consistency & Motion Smoothness",
                "pass": False,
                "error": "Insufficient frames for analysis"
            }

        # Run both checks in parallel
        consistency_task = self.check_temporal_consistency(frame_sequence)
        smoothness_task = self.check_motion_smoothness(frame_sequence)

        consistency_results, smoothness_results = await asyncio.gather(
            consistency_task, smoothness_task
        )

        # Extract key metrics
        temporal_consistency = consistency_results.get("temporal_consistency", 0.0)
        motion_smoothness = smoothness_results.get("motion_smoothness", 0.0)

        # Calculate flicker score (based on minimum SSIM between consecutive frames)
        consistency_scores = consistency_results.get("consistency_scores", [])
        flicker_score = min(consistency_scores) if consistency_scores else 0.0

        # Calculate overall quality score
        overall_score = (temporal_consistency + motion_smoothness + flicker_score) / 3.0

        # Determine pass/fail status
        issues = []

        temporal_pass = temporal_consistency >= self.TEMPORAL_CONSISTENCY_THRESHOLD
        if not temporal_pass:
            issues.append(f"Temporal consistency low ({temporal_consistency:.3f})")

        motion_pass = motion_smoothness >= self.MOTION_SMOOTHNESS_THRESHOLD
        if not motion_pass:
            issues.append(f"Motion not smooth ({motion_smoothness:.3f})")

        flicker_pass = flicker_score >= self.FLICKER_THRESHOLD
        if not flicker_pass:
            issues.append(f"Flicker detected ({flicker_score:.3f})")

        overall_pass = (
            temporal_pass and
            motion_pass and
            flicker_pass and
            overall_score >= self.OVERALL_THRESHOLD
        )

        # Create result object
        result = TemporalQualityResult(
            sequence_id=sequence_name,
            frame_count=len(frame_sequence),
            flicker_score=flicker_score,
            motion_smoothness_score=motion_smoothness,
            temporal_consistency_score=temporal_consistency,
            overall_score=overall_score,
            passed=overall_pass,
            issues=issues
        )

        # Generate video analysis if frames are sequential
        video_analysis = await self._create_video_analysis(frame_sequence, sequence_name)

        # Log to Echo Brain for learning
        await self._log_to_echo_brain({
            "gate": "gate_3_temporal_consistency",
            "sequence_name": sequence_name,
            "frame_count": len(frame_sequence),
            "temporal_consistency": temporal_consistency,
            "motion_smoothness": motion_smoothness,
            "flicker_score": flicker_score,
            "overall_score": overall_score,
            "gate_pass": overall_pass,
            "issues": issues,
            "timestamp": start_time.isoformat()
        })

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        results = {
            "gate": "Gate 3: Temporal Consistency & Motion Smoothness",
            "pass": overall_pass,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "sequence": {
                "name": sequence_name,
                "frame_count": len(frame_sequence),
                "frames": [os.path.basename(f) for f in frame_sequence]
            },
            "quality_metrics": result.dict(),
            "detailed_analysis": {
                "temporal_consistency": consistency_results,
                "motion_smoothness": smoothness_results
            },
            "video_analysis": video_analysis
        }

        # Save results
        await self._save_gate_results("gate_3", results)

        if overall_pass:
            logger.info(f"🎉 Gate 3 PASSED - {len(frame_sequence)} frames analyzed in {duration:.2f}s")
            logger.info(f"   ✅ Temporal consistency: {temporal_consistency:.3f}")
            logger.info(f"   ✅ Motion smoothness: {motion_smoothness:.3f}")
            logger.info(f"   ✅ Flicker score: {flicker_score:.3f}")
        else:
            logger.error(f"💥 Gate 3 FAILED - Issues found in {duration:.2f}s")
            for issue in issues:
                logger.error(f"   ❌ {issue}")

        return results

    async def _calculate_temporal_consistency(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Calculate temporal consistency between two consecutive frames"""
        try:
            # Convert to grayscale for SSIM calculation
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY) if len(img1.shape) == 3 else img1
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY) if len(img2.shape) == 3 else img2

            # Ensure images are same size
            if gray1.shape != gray2.shape:
                h, w = min(gray1.shape[0], gray2.shape[0]), min(gray1.shape[1], gray2.shape[1])
                gray1 = cv2.resize(gray1, (w, h))
                gray2 = cv2.resize(gray2, (w, h))

            # Calculate SSIM (Structural Similarity Index)
            ssim_score = ssim(gray1, gray2, data_range=gray1.max() - gray1.min())

            return float(ssim_score)

        except Exception as e:
            logger.error(f"Error calculating temporal consistency: {e}")
            return 0.0

    async def _analyze_motion_smoothness(self, flow_12: Optional[np.ndarray],
                                       flow_23: Optional[np.ndarray]) -> float:
        """Analyze motion smoothness based on optical flow consistency"""
        try:
            if flow_12 is None or flow_23 is None or len(flow_12) == 0 or len(flow_23) == 0:
                return 0.0

            # Calculate motion vectors
            vectors_12 = flow_12.reshape(-1, 2)
            vectors_23 = flow_23.reshape(-1, 2)

            # Calculate motion consistency (similarity of motion directions)
            if len(vectors_12) > 0 and len(vectors_23) > 0:
                # Use minimum length for comparison
                min_len = min(len(vectors_12), len(vectors_23))
                v12 = vectors_12[:min_len]
                v23 = vectors_23[:min_len]

                # Calculate directional consistency
                magnitudes_12 = np.linalg.norm(v12, axis=1)
                magnitudes_23 = np.linalg.norm(v23, axis=1)

                # Avoid division by zero
                valid_idx = (magnitudes_12 > 0) & (magnitudes_23 > 0)
                if np.sum(valid_idx) == 0:
                    return 0.5  # Neutral score for no motion

                # Calculate directional similarity
                directions_12 = v12[valid_idx] / magnitudes_12[valid_idx].reshape(-1, 1)
                directions_23 = v23[valid_idx] / magnitudes_23[valid_idx].reshape(-1, 1)

                # Dot product for directional similarity
                dot_products = np.sum(directions_12 * directions_23, axis=1)
                avg_directional_similarity = np.mean(np.abs(dot_products))

                # Calculate magnitude consistency
                magnitude_ratio = np.minimum(magnitudes_12[valid_idx], magnitudes_23[valid_idx]) / \
                                np.maximum(magnitudes_12[valid_idx], magnitudes_23[valid_idx])
                avg_magnitude_consistency = np.mean(magnitude_ratio)

                # Combine directional and magnitude consistency
                smoothness_score = (avg_directional_similarity + avg_magnitude_consistency) / 2.0

                return float(smoothness_score)

            return 0.5  # Neutral score

        except Exception as e:
            logger.error(f"Error analyzing motion smoothness: {e}")
            return 0.0

    async def _create_video_analysis(self, frame_sequence: List[str], sequence_name: str) -> Dict:
        """Create a temporary video for visual analysis"""
        try:
            temp_dir = self.project_root / "quality" / "temporal_analysis"
            temp_video = temp_dir / f"{sequence_name}_analysis.mp4"

            # Create video from frame sequence using ffmpeg
            frame_pattern = os.path.dirname(frame_sequence[0]) + "/frame_%03d.png"

            cmd = [
                "ffmpeg", "-y", "-framerate", "24",
                "-i", frame_pattern,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(temp_video)
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    file_size = os.path.getsize(temp_video) if temp_video.exists() else 0
                    return {
                        "video_created": True,
                        "video_path": str(temp_video),
                        "file_size_bytes": file_size,
                        "frame_count": len(frame_sequence)
                    }
                else:
                    logger.warning(f"ffmpeg failed: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning("Video creation timed out")

        except Exception as e:
            logger.warning(f"Could not create analysis video: {e}")

        return {
            "video_created": False,
            "reason": "Video creation failed"
        }

    async def _log_to_echo_brain(self, data: Dict):
        """Log results to Echo Brain for learning"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.echo_brain_url}/api/echo/query",
                    json={
                        "query": f"Gate 3 temporal analysis results: {json.dumps(data)}",
                        "conversation_id": "anime_quality_gates",
                        "context": "temporal_consistency_assessment"
                    },
                    timeout=5.0
                )
                if response.status_code == 200:
                    logger.info("📊 Temporal analysis results logged to Echo Brain")
        except Exception as e:
            logger.warning(f"Could not log to Echo Brain: {e}")

    async def _save_gate_results(self, gate_name: str, results: Dict):
        """Save gate results to file"""
        results_dir = self.project_root / "quality" / "results"
        results_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = results_dir / f"{gate_name}_{timestamp}.json"

        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"💾 Temporal analysis results saved to {results_file}")

# Example usage
if __name__ == "__main__":
    async def main():
        checker = Gate3TemporalChecker("/opt/tower-anime-production")

        # Example test data - frame sequence
        frame_sequence = [
            "/opt/tower-anime-production/generated/frames/frame_001.png",
            "/opt/tower-anime-production/generated/frames/frame_002.png",
            "/opt/tower-anime-production/generated/frames/frame_003.png",
            "/opt/tower-anime-production/generated/frames/frame_004.png",
            "/opt/tower-anime-production/generated/frames/frame_005.png"
        ]

        results = await checker.run_gate_3_tests(frame_sequence, "yuki_turn_sequence")
        print(f"Gate 3 Results: {'PASS' if results['pass'] else 'FAIL'}")
        print(f"Overall score: {results['quality_metrics']['overall_score']:.3f}")

    asyncio.run(main())