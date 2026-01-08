"""Quality Analyzer for FramePack video generation.

Measures frame consistency (SSIM) and motion smoothness (optical flow)
to provide quality scores for generated segments.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Quality metrics for a video segment."""

    frame_consistency_score: float  # SSIM-based, 0-1
    motion_smoothness_score: float  # Optical flow variance, 0-1
    overall_score: float  # Combined weighted score
    frame_count: int
    analysis_details: Dict


class QualityAnalyzer:
    """Analyzes video quality for FramePack generations.

    Metrics:
    - Frame Consistency: Uses SSIM between consecutive frames
    - Motion Smoothness: Uses optical flow magnitude variance
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        """Initialize quality analyzer.

        Args:
            ffmpeg_path: Path to ffmpeg binary
            ffprobe_path: Path to ffprobe binary
        """
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def analyze_video(self, video_path: str) -> QualityMetrics:
        """Analyze video quality and return metrics.

        Args:
            video_path: Path to video file

        Returns:
            QualityMetrics with scores from 0-1
        """
        path = Path(video_path)
        if not path.exists():
            logger.error(f"Video not found: {video_path}")
            return QualityMetrics(
                frame_consistency_score=0.0,
                motion_smoothness_score=0.0,
                overall_score=0.0,
                frame_count=0,
                analysis_details={"error": "Video file not found"},
            )

        try:
            # Extract frames for analysis
            frames = self._extract_frames(video_path)
            if len(frames) < 2:
                logger.warning(f"Not enough frames to analyze: {len(frames)}")
                return QualityMetrics(
                    frame_consistency_score=0.5,
                    motion_smoothness_score=0.5,
                    overall_score=0.5,
                    frame_count=len(frames),
                    analysis_details={"warning": "Not enough frames for full analysis"},
                )

            # Calculate metrics
            frame_consistency = self._calculate_frame_consistency(frames)
            motion_smoothness = self._calculate_motion_smoothness(frames)

            # Combined score (weighted average)
            overall_score = (frame_consistency * 0.6) + (motion_smoothness * 0.4)

            metrics = QualityMetrics(
                frame_consistency_score=frame_consistency,
                motion_smoothness_score=motion_smoothness,
                overall_score=overall_score,
                frame_count=len(frames),
                analysis_details={
                    "frame_count": len(frames),
                    "consistency_method": "ssim",
                    "smoothness_method": "optical_flow_variance",
                },
            )

            logger.info(
                f"Quality analysis for {video_path}: "
                f"consistency={frame_consistency:.3f}, "
                f"smoothness={motion_smoothness:.3f}, "
                f"overall={overall_score:.3f}"
            )

            return metrics

        except Exception as e:
            logger.error(f"Error analyzing video {video_path}: {e}")
            return QualityMetrics(
                frame_consistency_score=0.0,
                motion_smoothness_score=0.0,
                overall_score=0.0,
                frame_count=0,
                analysis_details={"error": str(e)},
            )

    def _extract_frames(
        self, video_path: str, max_frames: int = 30, sample_rate: int = 5
    ) -> List[np.ndarray]:
        """Extract frames from video for analysis.

        Args:
            video_path: Path to video
            max_frames: Maximum frames to extract
            sample_rate: Extract every Nth frame

        Returns:
            List of frame arrays (RGB)
        """
        try:
            # Use OpenCV if available, otherwise fall back to ffmpeg + numpy
            try:
                import cv2

                return self._extract_frames_cv2(video_path, max_frames, sample_rate)
            except ImportError:
                return self._extract_frames_ffmpeg(video_path, max_frames, sample_rate)
        except Exception as e:
            logger.error(f"Frame extraction failed: {e}")
            return []

    def _extract_frames_cv2(
        self, video_path: str, max_frames: int, sample_rate: int
    ) -> List[np.ndarray]:
        """Extract frames using OpenCV."""
        import cv2

        frames = []
        cap = cv2.VideoCapture(video_path)

        frame_idx = 0
        while cap.isOpened() and len(frames) < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_rate == 0:
                # Convert BGR to RGB and resize for faster processing
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_resized = cv2.resize(frame_rgb, (320, 240))
                frames.append(frame_resized)

            frame_idx += 1

        cap.release()
        return frames

    def _extract_frames_ffmpeg(
        self, video_path: str, max_frames: int, sample_rate: int
    ) -> List[np.ndarray]:
        """Extract frames using ffmpeg (fallback)."""
        import tempfile

        frames = []

        with tempfile.TemporaryDirectory() as tmpdir:
            # Extract frames at 1fps sample rate
            output_pattern = f"{tmpdir}/frame_%04d.png"
            cmd = [
                self.ffmpeg_path,
                "-i",
                video_path,
                "-vf",
                f"select=not(mod(n\\,{sample_rate})),scale=320:240",
                "-vsync",
                "vfr",
                "-frames:v",
                str(max_frames),
                output_pattern,
                "-y",
                "-loglevel",
                "error",
            ]

            subprocess.run(cmd, check=True, capture_output=True)

            # Load extracted frames
            from PIL import Image

            for i in range(1, max_frames + 1):
                frame_path = Path(tmpdir) / f"frame_{i:04d}.png"
                if frame_path.exists():
                    img = Image.open(frame_path)
                    frames.append(np.array(img))

        return frames

    def _calculate_frame_consistency(self, frames: List[np.ndarray]) -> float:
        """Calculate frame consistency using SSIM between consecutive frames.

        High consistency = smooth, coherent video
        Low consistency = flickering, artifacts

        Returns:
            Score from 0-1
        """
        if len(frames) < 2:
            return 0.5

        try:
            from skimage.metrics import structural_similarity as ssim

            ssim_scores = []
            for i in range(len(frames) - 1):
                # Calculate SSIM between consecutive frames
                score = ssim(frames[i], frames[i + 1], channel_axis=2, data_range=255)
                ssim_scores.append(score)

            # Average SSIM, but penalize high variance (flickering)
            mean_ssim = np.mean(ssim_scores)
            ssim_std = np.std(ssim_scores)

            # Penalize inconsistency (high std = bad)
            consistency_score = mean_ssim * (1 - min(ssim_std, 0.5))

            return float(np.clip(consistency_score, 0, 1))

        except ImportError:
            # Fallback: simple pixel difference
            logger.warning("skimage not available, using simple pixel difference")
            return self._simple_consistency(frames)

    def _simple_consistency(self, frames: List[np.ndarray]) -> float:
        """Simple consistency check using pixel differences."""
        if len(frames) < 2:
            return 0.5

        diffs = []
        for i in range(len(frames) - 1):
            diff = np.mean(np.abs(frames[i].astype(float) - frames[i + 1].astype(float)))
            diffs.append(diff)

        # Normalize: lower diff = higher consistency
        mean_diff = np.mean(diffs)
        # Typical good diff is < 20, bad is > 50
        score = 1.0 - min(mean_diff / 50.0, 1.0)

        return float(np.clip(score, 0, 1))

    def _calculate_motion_smoothness(self, frames: List[np.ndarray]) -> float:
        """Calculate motion smoothness using optical flow.

        Smooth motion = low variance in flow magnitudes
        Jerky motion = high variance in flow magnitudes

        Returns:
            Score from 0-1
        """
        if len(frames) < 2:
            return 0.5

        try:
            import cv2

            flow_magnitudes = []
            prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_RGB2GRAY)

            for i in range(1, len(frames)):
                curr_gray = cv2.cvtColor(frames[i], cv2.COLOR_RGB2GRAY)

                # Calculate optical flow
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray,
                    curr_gray,
                    None,
                    pyr_scale=0.5,
                    levels=3,
                    winsize=15,
                    iterations=3,
                    poly_n=5,
                    poly_sigma=1.2,
                    flags=0,
                )

                # Calculate flow magnitude
                magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
                flow_magnitudes.append(np.mean(magnitude))

                prev_gray = curr_gray

            if not flow_magnitudes:
                return 0.5

            # Calculate smoothness from flow variance
            flow_array = np.array(flow_magnitudes)
            flow_std = np.std(flow_array)
            flow_mean = np.mean(flow_array)

            # Coefficient of variation (lower = smoother)
            if flow_mean > 0:
                cv = flow_std / flow_mean
            else:
                cv = 0

            # Convert to score: low cv = high smoothness
            # Typical good cv < 0.3, bad cv > 1.0
            smoothness_score = 1.0 - min(cv / 1.0, 1.0)

            return float(np.clip(smoothness_score, 0, 1))

        except ImportError:
            logger.warning("OpenCV not available for optical flow, using fallback")
            return self._simple_smoothness(frames)

    def _simple_smoothness(self, frames: List[np.ndarray]) -> float:
        """Simple smoothness check using frame-to-frame pixel differences."""
        if len(frames) < 3:
            return 0.5

        # Calculate second derivative of frame differences
        diffs = []
        for i in range(len(frames) - 1):
            diff = np.mean(np.abs(frames[i].astype(float) - frames[i + 1].astype(float)))
            diffs.append(diff)

        # Smoothness = low variance in differences
        diff_std = np.std(diffs)
        # Typical good std < 5, bad std > 20
        score = 1.0 - min(diff_std / 20.0, 1.0)

        return float(np.clip(score, 0, 1))

    def get_video_info(self, video_path: str) -> Optional[Dict]:
        """Get video metadata using ffprobe.

        Returns:
            Dict with duration, fps, resolution, codec info
        """
        try:
            cmd = [
                self.ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                video_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            import json

            data = json.loads(result.stdout)

            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                return None

            # Parse frame rate
            fps_str = video_stream.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = map(int, fps_str.split("/"))
                fps = num / den if den else 30
            else:
                fps = float(fps_str)

            return {
                "duration": float(data.get("format", {}).get("duration", 0)),
                "fps": fps,
                "width": video_stream.get("width"),
                "height": video_stream.get("height"),
                "codec": video_stream.get("codec_name"),
                "frame_count": int(video_stream.get("nb_frames", 0)),
            }

        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None
