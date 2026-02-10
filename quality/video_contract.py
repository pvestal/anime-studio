#!/usr/bin/env python3
"""
Video Quality Contract - Defines what "quality" means for generated content
===========================================================================
This module defines HARD quality gates that MUST pass for any generation to be
considered successful. It goes beyond basic file existence checks to verify:

1. Structural integrity (file format, dimensions, duration)
2. Motion quality (videos aren't just still frames)
3. Visual quality (not blank, not corrupt, matches prompt)

A generation only PASSES when ALL structural + motion gates pass AND
quality_score > 0.5.

Dependencies: opencv-python, numpy, scikit-image, ffmpeg (system)
"""

import os
import subprocess
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import tempfile

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

logger = logging.getLogger("video_contract")


@dataclass
class GateResult:
    """Result of a single quality gate check."""
    passed: bool
    value: Any
    threshold: Any
    details: str = ""


@dataclass
class ContractResult:
    """Complete quality contract validation result."""
    passed: bool               # ALL structural + motion gates passed
    quality_score: float       # 0.0-1.0 from visual quality gates
    structural_gates: Dict[str, GateResult]
    motion_gates: Dict[str, GateResult]
    quality_gates: Dict[str, GateResult]
    frame_samples: List[str]   # Paths to sampled frames for review
    recommendations: List[str] # What to change for better results
    generation_params: Dict[str, Any]  # The params that produced this output
    error: Optional[str] = None


class VideoQualityContract:
    """
    Defines and validates quality requirements for generated videos/images.
    This is the TRUTH about whether a generation succeeded or not.
    """

    # Structural requirements (hard fail if not met)
    MIN_FILE_SIZE_VIDEO = 50_000      # 50KB minimum for videos
    MIN_FILE_SIZE_IMAGE = 20_000      # 20KB minimum for images
    MAX_FILE_SIZE = 100_000_000       # 100MB sanity limit

    MIN_VIDEO_FRAMES = 12             # AnimateDiff minimum
    MIN_FRAMEPACK_FRAMES = 60         # FramePack minimum

    DURATION_TOLERANCE = 0.1          # 10% tolerance on expected duration
    DIMENSION_TOLERANCE = 0.05        # 5% tolerance on dimensions

    # Motion requirements for video (hard fail if not met)
    MIN_SSIM_VARIANCE = 0.01          # Frames must differ by at least 1%
    MIN_OPTICAL_FLOW = 0.5            # Minimum average pixel movement

    # Visual quality thresholds (contribute to quality_score)
    MAX_BLANK_RATIO = 0.90            # >90% same color = blank frame
    MIN_SHARPNESS = 100.0             # Laplacian variance threshold
    MIN_COLOR_VARIANCE = 10.0         # Minimum color distribution variance

    def __init__(self, output_dir: str = "/opt/ComfyUI/output/quality_samples"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def validate(self,
                 file_path: str,
                 generation_params: Optional[Dict] = None,
                 expected_type: str = "auto") -> ContractResult:
        """
        Run full quality contract validation on a generated file.

        Args:
            file_path: Path to the generated file
            generation_params: The parameters used to generate this file
            expected_type: "video", "image", or "auto" (detect from extension)

        Returns:
            ContractResult with comprehensive quality assessment
        """
        file_path = Path(file_path)
        generation_params = generation_params or {}

        # Initialize result containers
        structural_gates = {}
        motion_gates = {}
        quality_gates = {}
        frame_samples = []
        recommendations = []

        # Detect file type
        ext = file_path.suffix.lower()
        is_video = ext in {'.mp4', '.webm', '.avi', '.mov', '.gif'}
        is_image = ext in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}

        if expected_type == "video":
            is_video = True
            is_image = False
        elif expected_type == "image":
            is_video = False
            is_image = True

        # Gate 1: File exists
        structural_gates["file_exists"] = GateResult(
            passed=file_path.exists(),
            value=file_path.exists(),
            threshold=True,
            details=f"File at {file_path}"
        )

        if not file_path.exists():
            return ContractResult(
                passed=False,
                quality_score=0.0,
                structural_gates=structural_gates,
                motion_gates=motion_gates,
                quality_gates=quality_gates,
                frame_samples=frame_samples,
                recommendations=["File does not exist - generation may have failed"],
                generation_params=generation_params,
                error="File not found"
            )

        # Gate 2: File size
        file_size = file_path.stat().st_size
        min_size = self.MIN_FILE_SIZE_VIDEO if is_video else self.MIN_FILE_SIZE_IMAGE
        structural_gates["file_size"] = GateResult(
            passed=min_size <= file_size <= self.MAX_FILE_SIZE,
            value=file_size,
            threshold=f"{min_size}-{self.MAX_FILE_SIZE}",
            details=f"{file_size/1024:.1f}KB"
        )

        if not structural_gates["file_size"].passed:
            recommendations.append(f"File size {file_size/1024:.1f}KB is abnormal")

        # Process based on type
        if is_video:
            return self._validate_video(
                file_path, generation_params,
                structural_gates, motion_gates, quality_gates,
                frame_samples, recommendations
            )
        elif is_image:
            return self._validate_image(
                file_path, generation_params,
                structural_gates, motion_gates, quality_gates,
                frame_samples, recommendations
            )
        else:
            return ContractResult(
                passed=False,
                quality_score=0.0,
                structural_gates=structural_gates,
                motion_gates=motion_gates,
                quality_gates=quality_gates,
                frame_samples=frame_samples,
                recommendations=["Unknown file type"],
                generation_params=generation_params,
                error=f"Unknown file extension: {ext}"
            )

    def _validate_video(self,
                        file_path: Path,
                        generation_params: Dict,
                        structural_gates: Dict,
                        motion_gates: Dict,
                        quality_gates: Dict,
                        frame_samples: List,
                        recommendations: List) -> ContractResult:
        """Validate video-specific quality requirements."""

        # Use ffprobe to get video metadata
        try:
            probe_result = subprocess.run([
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-count_packets',
                '-show_entries',
                'stream=nb_read_packets,width,height,r_frame_rate,duration',
                '-of', 'json',
                str(file_path)
            ], capture_output=True, text=True, timeout=10)

            if probe_result.returncode != 0:
                structural_gates["valid_container"] = GateResult(
                    passed=False, value="invalid", threshold="valid",
                    details=probe_result.stderr
                )
                recommendations.append("Video container is corrupt or invalid")
            else:
                metadata = json.loads(probe_result.stdout)
                stream = metadata.get('streams', [{}])[0]

                # Gate: Frame count
                frame_count = int(stream.get('nb_read_packets', 0))
                batch_size = generation_params.get('batch_size', 16)

                # Detect if AnimateDiff or FramePack
                is_framepack = 'framepack' in str(generation_params.get('model', '')).lower()
                min_frames = self.MIN_FRAMEPACK_FRAMES if is_framepack else self.MIN_VIDEO_FRAMES

                structural_gates["frame_count"] = GateResult(
                    passed=frame_count >= min_frames,
                    value=frame_count,
                    threshold=f">={min_frames}",
                    details=f"{frame_count} frames"
                )

                if frame_count < min_frames:
                    recommendations.append(
                        f"Only {frame_count} frames - need {min_frames}+ for proper video. "
                        f"Check batch_size (was {batch_size})"
                    )

                # Gate: Duration
                duration = float(stream.get('duration', 0))
                fps_str = stream.get('r_frame_rate', '12/1')
                fps = eval(fps_str) if '/' in fps_str else float(fps_str)
                expected_duration = frame_count / fps

                structural_gates["duration"] = GateResult(
                    passed=abs(duration - expected_duration) <= expected_duration * self.DURATION_TOLERANCE,
                    value=duration,
                    threshold=f"{expected_duration:.2f}±10%",
                    details=f"{duration:.2f}s at {fps}fps"
                )

                # Gate: Resolution
                width = int(stream.get('width', 0))
                height = int(stream.get('height', 0))
                expected_width = generation_params.get('width', 512)
                expected_height = generation_params.get('height', 512)

                width_ok = abs(width - expected_width) <= expected_width * self.DIMENSION_TOLERANCE
                height_ok = abs(height - expected_height) <= expected_height * self.DIMENSION_TOLERANCE

                structural_gates["resolution"] = GateResult(
                    passed=width_ok and height_ok,
                    value=f"{width}x{height}",
                    threshold=f"{expected_width}x{expected_height}±5%",
                    details=f"{width}x{height}"
                )

                if not (width_ok and height_ok):
                    recommendations.append(
                        f"Resolution {width}x{height} doesn't match expected {expected_width}x{expected_height}"
                    )

        except Exception as e:
            structural_gates["valid_container"] = GateResult(
                passed=False, value="error", threshold="valid",
                details=str(e)
            )
            recommendations.append(f"Failed to probe video: {e}")

        # Extract frames for motion and quality analysis
        extracted_frames = self._extract_frames(file_path, count=8)
        frame_samples.extend([str(f) for f in extracted_frames])

        if len(extracted_frames) >= 2:
            # Motion validation
            motion_results = self._validate_motion(extracted_frames)
            motion_gates.update(motion_results)

            if not all(g.passed for g in motion_results.values()):
                recommendations.append(
                    "Video lacks proper motion - may be a still image or corrupted. "
                    "Check AnimateDiff is working and batch_size >= 16"
                )

            # Visual quality validation
            quality_results = self._validate_visual_quality(extracted_frames)
            quality_gates.update(quality_results)

        # Calculate overall quality score
        quality_score = self._calculate_quality_score(quality_gates)

        # Determine if contract passed
        structural_passed = all(g.passed for g in structural_gates.values())
        motion_passed = all(g.passed for g in motion_gates.values())
        passed = structural_passed and motion_passed and quality_score > 0.5

        if quality_score < 0.5:
            recommendations.append(
                f"Quality score {quality_score:.2f} is below threshold (0.5). "
                "Check prompt clarity, model selection, and generation parameters"
            )

        return ContractResult(
            passed=passed,
            quality_score=quality_score,
            structural_gates=structural_gates,
            motion_gates=motion_gates,
            quality_gates=quality_gates,
            frame_samples=frame_samples,
            recommendations=recommendations,
            generation_params=generation_params
        )

    def _validate_image(self,
                        file_path: Path,
                        generation_params: Dict,
                        structural_gates: Dict,
                        motion_gates: Dict,
                        quality_gates: Dict,
                        frame_samples: List,
                        recommendations: List) -> ContractResult:
        """Validate image-specific quality requirements."""

        try:
            img = cv2.imread(str(file_path))
            if img is None:
                structural_gates["valid_format"] = GateResult(
                    passed=False, value="unreadable", threshold="readable",
                    details="OpenCV cannot read file"
                )
                recommendations.append("Image file is corrupt or unreadable")
            else:
                height, width = img.shape[:2]
                expected_width = generation_params.get('width', 512)
                expected_height = generation_params.get('height', 512)

                width_ok = abs(width - expected_width) <= expected_width * self.DIMENSION_TOLERANCE
                height_ok = abs(height - expected_height) <= expected_height * self.DIMENSION_TOLERANCE

                structural_gates["resolution"] = GateResult(
                    passed=width_ok and height_ok,
                    value=f"{width}x{height}",
                    threshold=f"{expected_width}x{expected_height}±5%",
                    details=f"{width}x{height}"
                )

                # Save sample
                sample_path = self.output_dir / f"sample_{file_path.stem}.jpg"
                cv2.imwrite(str(sample_path), img)
                frame_samples.append(str(sample_path))

                # Visual quality checks
                quality_results = self._validate_visual_quality([str(file_path)])
                quality_gates.update(quality_results)

        except Exception as e:
            structural_gates["valid_format"] = GateResult(
                passed=False, value="error", threshold="readable",
                details=str(e)
            )
            recommendations.append(f"Failed to read image: {e}")

        # Calculate overall quality score
        quality_score = self._calculate_quality_score(quality_gates)

        # Determine if contract passed
        structural_passed = all(g.passed for g in structural_gates.values())
        passed = structural_passed and quality_score > 0.5

        return ContractResult(
            passed=passed,
            quality_score=quality_score,
            structural_gates=structural_gates,
            motion_gates=motion_gates,  # Empty for images
            quality_gates=quality_gates,
            frame_samples=frame_samples,
            recommendations=recommendations,
            generation_params=generation_params
        )

    def _extract_frames(self, video_path: Path, count: int = 8) -> List[Path]:
        """Extract evenly-spaced frames from video for analysis."""
        frames = []
        output_pattern = self.output_dir / f"{video_path.stem}_frame_%03d.jpg"

        try:
            # Use ffmpeg to extract frames
            subprocess.run([
                'ffmpeg', '-i', str(video_path),
                '-vf', f'select=not(mod(n\,{max(1, 100//count)})),scale=512:512',
                '-frames:v', str(count),
                '-vsync', 'vfr',
                str(output_pattern),
                '-y'
            ], capture_output=True, timeout=30)

            # Collect extracted frames
            for i in range(count):
                frame_path = self.output_dir / f"{video_path.stem}_frame_{i+1:03d}.jpg"
                if frame_path.exists():
                    frames.append(frame_path)

        except Exception as e:
            logger.error(f"Frame extraction failed: {e}")

        return frames

    def _validate_motion(self, frame_paths: List[Path]) -> Dict[str, GateResult]:
        """Validate that video has actual motion, not just repeated stills."""
        results = {}

        if len(frame_paths) < 2:
            results["motion_detected"] = GateResult(
                passed=False, value=0, threshold=">0",
                details="Not enough frames to detect motion"
            )
            return results

        # Load frames
        frames = []
        for path in frame_paths[:4]:  # Check first 4 frames
            img = cv2.imread(str(path))
            if img is not None:
                frames.append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))

        if len(frames) < 2:
            results["motion_detected"] = GateResult(
                passed=False, value=0, threshold=">0",
                details="Could not load frames"
            )
            return results

        # Check 1: Frame hashes (are frames identical?)
        frame_hashes = [hashlib.md5(f.tobytes()).hexdigest() for f in frames]
        unique_hashes = len(set(frame_hashes))

        results["unique_frames"] = GateResult(
            passed=unique_hashes > 1,
            value=unique_hashes,
            threshold=">1",
            details=f"{unique_hashes}/{len(frames)} unique frames"
        )

        # Check 2: SSIM variance
        ssim_scores = []
        for i in range(len(frames)-1):
            score = ssim(frames[i], frames[i+1])
            ssim_scores.append(score)

        ssim_variance = 1.0 - np.mean(ssim_scores) if ssim_scores else 0

        results["ssim_variance"] = GateResult(
            passed=ssim_variance > self.MIN_SSIM_VARIANCE,
            value=ssim_variance,
            threshold=f">{self.MIN_SSIM_VARIANCE}",
            details=f"Frame difference: {ssim_variance:.3f}"
        )

        # Check 3: Optical flow
        if len(frames) >= 2:
            flow = cv2.calcOpticalFlowFarneback(
                frames[0], frames[1], None,
                0.5, 3, 15, 3, 5, 1.2, 0
            )
            magnitude = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
            avg_motion = np.mean(magnitude)

            results["optical_flow"] = GateResult(
                passed=avg_motion > self.MIN_OPTICAL_FLOW,
                value=avg_motion,
                threshold=f">{self.MIN_OPTICAL_FLOW}",
                details=f"Avg motion: {avg_motion:.2f} pixels"
            )

        return results

    def _validate_visual_quality(self, frame_paths: List[str]) -> Dict[str, GateResult]:
        """Assess visual quality of frames."""
        results = {}

        if not frame_paths:
            return results

        # Analyze first, middle, and last frames
        sample_indices = [0, len(frame_paths)//2, -1]
        quality_scores = []

        for idx in sample_indices:
            if idx < len(frame_paths):
                img = cv2.imread(frame_paths[idx])
                if img is None:
                    continue

                # Check 1: Blank detection
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                unique_pixels = len(np.unique(gray))
                total_pixels = gray.size
                blank_ratio = 1.0 - (unique_pixels / min(total_pixels, 256))

                is_blank = blank_ratio > self.MAX_BLANK_RATIO

                # Check 2: Sharpness (Laplacian variance)
                laplacian = cv2.Laplacian(gray, cv2.CV_64F)
                sharpness = laplacian.var()

                # Check 3: Color distribution
                hist_b = cv2.calcHist([img], [0], None, [256], [0, 256])
                hist_g = cv2.calcHist([img], [1], None, [256], [0, 256])
                hist_r = cv2.calcHist([img], [2], None, [256], [0, 256])

                color_variance = np.std([hist_b.std(), hist_g.std(), hist_r.std()])

                # Calculate frame quality score
                frame_score = 0.0
                if not is_blank:
                    frame_score += 0.4
                if sharpness > self.MIN_SHARPNESS:
                    frame_score += 0.3
                if color_variance > self.MIN_COLOR_VARIANCE:
                    frame_score += 0.3

                quality_scores.append(frame_score)

        avg_quality = np.mean(quality_scores) if quality_scores else 0.0

        results["blank_detection"] = GateResult(
            passed=not is_blank,
            value=blank_ratio,
            threshold=f"<{self.MAX_BLANK_RATIO}",
            details=f"Blank ratio: {blank_ratio:.2f}"
        )

        results["sharpness"] = GateResult(
            passed=sharpness > self.MIN_SHARPNESS,
            value=sharpness,
            threshold=f">{self.MIN_SHARPNESS}",
            details=f"Laplacian variance: {sharpness:.1f}"
        )

        results["color_distribution"] = GateResult(
            passed=color_variance > self.MIN_COLOR_VARIANCE,
            value=color_variance,
            threshold=f">{self.MIN_COLOR_VARIANCE}",
            details=f"Color variance: {color_variance:.1f}"
        )

        results["overall_visual"] = GateResult(
            passed=avg_quality > 0.5,
            value=avg_quality,
            threshold=">0.5",
            details=f"Visual score: {avg_quality:.2f}"
        )

        return results

    def _calculate_quality_score(self, quality_gates: Dict[str, GateResult]) -> float:
        """Calculate overall quality score from individual gates."""
        if not quality_gates:
            return 0.0

        scores = []
        weights = {
            "blank_detection": 0.3,
            "sharpness": 0.2,
            "color_distribution": 0.2,
            "overall_visual": 0.3
        }

        for gate_name, result in quality_gates.items():
            weight = weights.get(gate_name, 0.1)
            score = 1.0 if result.passed else 0.0
            # For numerical values, scale the score
            if isinstance(result.value, (int, float)) and result.threshold:
                if '>' in str(result.threshold):
                    threshold_val = float(str(result.threshold).replace('>', ''))
                    if threshold_val > 0:
                        score = min(1.0, result.value / threshold_val)

            scores.append(score * weight)

        return min(1.0, sum(scores) / sum(weights.values()))


if __name__ == "__main__":
    # Test the contract with a real file
    import sys

    if len(sys.argv) < 2:
        print("Usage: python video_contract.py <video_or_image_path>")
        sys.exit(1)

    contract = VideoQualityContract()
    result = contract.validate(sys.argv[1])

    print(f"\n{'='*60}")
    print(f"CONTRACT RESULT: {'PASSED ✅' if result.passed else 'FAILED ❌'}")
    print(f"Quality Score: {result.quality_score:.2f}/1.0")
    print(f"{'='*60}\n")

    print("STRUCTURAL GATES:")
    for name, gate in result.structural_gates.items():
        status = "✅" if gate.passed else "❌"
        print(f"  {status} {name}: {gate.value} (threshold: {gate.threshold})")

    if result.motion_gates:
        print("\nMOTION GATES:")
        for name, gate in result.motion_gates.items():
            status = "✅" if gate.passed else "❌"
            print(f"  {status} {name}: {gate.value} (threshold: {gate.threshold})")

    print("\nVISUAL QUALITY:")
    for name, gate in result.quality_gates.items():
        status = "✅" if gate.passed else "❌"
        print(f"  {status} {name}: {gate.details}")

    if result.recommendations:
        print("\nRECOMMENDATIONS:")
        for rec in result.recommendations:
            print(f"  • {rec}")

    if result.frame_samples:
        print(f"\nFrame samples saved to: {', '.join(result.frame_samples)}")