#!/usr/bin/env python3
"""
Anime Quality Assessment Agent
Comprehensive video quality analysis and automatic rejection system
Integrates with Tower infrastructure and ComfyUI workflows
"""

import os
import json
import asyncio
import logging
import subprocess
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import websockets
import requests
from fastapi import FastAPI, WebSocket, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import redis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Anime Quality Assessment Agent", version="2.0")

class QualityMetrics(BaseModel):
    motion_smoothness: float  # 1-10 scale
    duration_minutes: float
    resolution: Tuple[int, int]
    frame_rate: float
    file_size_mb: float
    audio_quality: str
    format_compliance: bool
    jellyfin_ready: bool

class QualityAssessmentResult(BaseModel):
    video_path: str
    timestamp: datetime
    metrics: QualityMetrics
    overall_score: float
    passes_standards: bool
    rejection_reasons: List[str]
    comfyui_corrections: Dict[str, Any]

class AnimeQualityAssessment:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': 'admin123'
        }
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        self.comfyui_url = "http://127.0.0.1:8188"
        
        # Quality thresholds from specifications
        self.thresholds = {
            'motion_smoothness_min': 7.0,
            'duration_min_minutes': 10.0,
            'resolution_min': (3840, 2160),  # 4K
            'frame_rate_min': 24.0,
            'frame_rate_max': 60.0
        }
        
        # WebSocket connections for real-time updates
        self.active_connections = set()
        
    async def analyze_video_quality(self, video_path: str) -> QualityAssessmentResult:
        """Comprehensive video quality analysis"""
        logger.info(f"Starting quality analysis for: {video_path}")
        
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail=f"Video not found: {video_path}")
        
        try:
            # Extract video metadata
            metadata = await self._extract_video_metadata(video_path)
            
            # Analyze motion smoothness (key metric)
            motion_score = await self._analyze_motion_smoothness(video_path)
            
            # Check duration
            duration_minutes = metadata['duration'] / 60.0
            
            # Validate resolution
            resolution = (metadata['width'], metadata['height'])
            
            # Check frame rate consistency
            frame_rate = metadata['fps']
            
            # Audio quality check
            audio_quality = await self._analyze_audio_quality(video_path)
            
            # File format compliance
            format_compliance = await self._check_format_compliance(video_path)
            
            # Jellyfin readiness
            jellyfin_ready = await self._check_jellyfin_compatibility(video_path)
            
            # Build metrics
            metrics = QualityMetrics(
                motion_smoothness=motion_score,
                duration_minutes=duration_minutes,
                resolution=resolution,
                frame_rate=frame_rate,
                file_size_mb=os.path.getsize(video_path) / (1024 * 1024),
                audio_quality=audio_quality,
                format_compliance=format_compliance,
                jellyfin_ready=jellyfin_ready
            )
            
            # Calculate overall score and pass/fail status
            result = await self._evaluate_quality_standards(video_path, metrics)
            
            # Save to database
            await self._save_assessment_result(result)
            
            # Broadcast to WebSocket clients
            await self._broadcast_assessment_update(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Quality analysis failed for {video_path}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    async def _extract_video_metadata(self, video_path: str) -> Dict:
        """Extract video metadata using FFprobe"""
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', 
            '-show_format', '-show_streams', video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            metadata = json.loads(result.stdout)
            
            video_stream = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
            
            return {
                'duration': float(metadata['format']['duration']),
                'width': int(video_stream['width']),
                'height': int(video_stream['height']),
                'fps': eval(video_stream['r_frame_rate']),
                'codec': video_stream['codec_name'],
                'bitrate': int(metadata['format'].get('bit_rate', 0))
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"FFprobe failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Metadata extraction failed: {e}")
            raise

    async def _analyze_motion_smoothness(self, video_path: str) -> float:
        """
        Analyze motion smoothness using optical flow
        Returns score 1-10 (10 = perfect smoothness)
        """
        logger.info("Analyzing motion smoothness...")
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception("Could not open video file")
        
        # Parameters for motion analysis
        frame_count = 0
        max_frames = 300  # Sample first 300 frames (~10 seconds at 30fps)
        optical_flow_scores = []
        
        # Read first frame
        ret, prev_frame = cap.read()
        if not ret:
            raise Exception("Could not read first frame")
        
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        
        while frame_count < max_frames:
            ret, curr_frame = cap.read()
            if not ret:
                break
                
            curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
            
            # Calculate optical flow
            flow = cv2.calcOpticalFlowPyrLK(
                prev_gray, curr_gray, 
                np.array([[x, y] for x in range(0, prev_gray.shape[1], 50) 
                         for y in range(0, prev_gray.shape[0], 50)], dtype=np.float32).reshape(-1, 1, 2),
                None
            )[0]
            
            if flow is not None:
                # Calculate motion magnitude
                motion_magnitude = np.mean(np.linalg.norm(flow.reshape(-1, 2), axis=1))
                optical_flow_scores.append(motion_magnitude)
            
            prev_gray = curr_gray
            frame_count += 1
        
        cap.release()
        
        if not optical_flow_scores:
            return 1.0  # Worst score if no motion detected
        
        # Analyze motion consistency (smoothness)
        motion_variance = np.var(optical_flow_scores)
        motion_mean = np.mean(optical_flow_scores)
        
        # Calculate smoothness score (lower variance = smoother)
        # Normalize to 1-10 scale
        smoothness_ratio = motion_mean / (motion_variance + 1e-6)
        score = min(10.0, max(1.0, smoothness_ratio / 10.0 * 10))
        
        logger.info(f"Motion smoothness score: {score:.2f}/10")
        return score

    async def _analyze_audio_quality(self, video_path: str) -> str:
        """Analyze audio quality and return assessment"""
        cmd = [
            'ffprobe', '-v', 'quiet', '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name,sample_rate,channels',
            '-of', 'csv=p=0', video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            audio_info = result.stdout.strip().split(',')
            
            if len(audio_info) >= 3:
                codec, sample_rate, channels = audio_info[:3]
                sample_rate = int(sample_rate)
                channels = int(channels)
                
                if sample_rate >= 48000 and channels >= 2 and codec in ['aac', 'mp3', 'flac']:
                    return "excellent"
                elif sample_rate >= 44100 and channels >= 2:
                    return "good"
                else:
                    return "poor"
            else:
                return "unknown"
                
        except Exception as e:
            logger.warning(f"Audio analysis failed: {e}")
            return "unknown"

    async def _check_format_compliance(self, video_path: str) -> bool:
        """Check if video format is compliant with standards"""
        try:
            # Check file extension
            valid_extensions = ['.mp4', '.mkv', '.avi', '.mov']
            if not any(video_path.lower().endswith(ext) for ext in valid_extensions):
                return False
            
            # Check codec compatibility
            metadata = await self._extract_video_metadata(video_path)
            compatible_codecs = ['h264', 'h265', 'hevc']
            
            return metadata['codec'].lower() in compatible_codecs
        except Exception:
            return False

    async def _check_jellyfin_compatibility(self, video_path: str) -> bool:
        """Check if video is ready for Jellyfin media server"""
        try:
            # Check if it's in proper directory structure
            jellyfin_paths = ['/mnt/', '/media/', '/home/patrick/media/']
            
            # Basic Jellyfin compatibility checks
            metadata = await self._extract_video_metadata(video_path)
            
            # Jellyfin prefers H.264/H.265 with AAC audio
            video_compatible = metadata['codec'].lower() in ['h264', 'h265', 'hevc']
            
            return video_compatible and os.path.exists(video_path)
        except Exception:
            return False

    async def _evaluate_quality_standards(self, video_path: str, metrics: QualityMetrics) -> QualityAssessmentResult:
        """Evaluate against quality standards and generate corrections"""
        rejection_reasons = []
        comfyui_corrections = {}
        
        # Check motion smoothness (CRITICAL)
        if metrics.motion_smoothness < self.thresholds['motion_smoothness_min']:
            rejection_reasons.append(f"Motion smoothness {metrics.motion_smoothness:.1f}/10 below threshold {self.thresholds['motion_smoothness_min']}")
            comfyui_corrections['motion_smoothness'] = {
                'node_type': 'VideoFrameInterpolation',
                'settings': {
                    'interpolation_factor': 2.0,
                    'optical_flow_method': 'RIFE',
                    'motion_blur_reduction': True
                }
            }
        
        # Check duration
        if metrics.duration_minutes < self.thresholds['duration_min_minutes']:
            rejection_reasons.append(f"Duration {metrics.duration_minutes:.1f} minutes below {self.thresholds['duration_min_minutes']} minutes")
            comfyui_corrections['duration'] = {
                'node_type': 'ExtendVideoLength',
                'settings': {
                    'target_duration': self.thresholds['duration_min_minutes'] * 60,
                    'extension_method': 'content_aware_loop'
                }
            }
        
        # Check resolution
        min_width, min_height = self.thresholds['resolution_min']
        if metrics.resolution[0] < min_width or metrics.resolution[1] < min_height:
            rejection_reasons.append(f"Resolution {metrics.resolution} below 4K requirement")
            comfyui_corrections['resolution'] = {
                'node_type': 'VideoUpscaler',
                'settings': {
                    'target_width': min_width,
                    'target_height': min_height,
                    'upscale_method': 'ESRGAN',
                    'enhance_details': True
                }
            }
        
        # Check frame rate
        if not (self.thresholds['frame_rate_min'] <= metrics.frame_rate <= self.thresholds['frame_rate_max']):
            rejection_reasons.append(f"Frame rate {metrics.frame_rate} fps outside acceptable range")
            comfyui_corrections['frame_rate'] = {
                'node_type': 'FrameRateConverter',
                'settings': {
                    'target_fps': 30.0,
                    'conversion_method': 'motion_compensated'
                }
            }
        
        # Audio quality check
        if metrics.audio_quality == 'poor':
            rejection_reasons.append("Poor audio quality detected")
            comfyui_corrections['audio'] = {
                'node_type': 'AudioEnhancer',
                'settings': {
                    'noise_reduction': True,
                    'dynamic_range_compression': True,
                    'target_sample_rate': 48000
                }
            }
        
        # Calculate overall score (weighted)
        weights = {
            'motion_smoothness': 0.4,  # Most important
            'duration': 0.2,
            'resolution': 0.2,
            'frame_rate': 0.1,
            'audio': 0.1
        }
        
        score_components = {
            'motion_smoothness': metrics.motion_smoothness / 10.0,
            'duration': min(1.0, metrics.duration_minutes / self.thresholds['duration_min_minutes']),
            'resolution': min(1.0, (metrics.resolution[0] * metrics.resolution[1]) / (min_width * min_height)),
            'frame_rate': 1.0 if self.thresholds['frame_rate_min'] <= metrics.frame_rate <= self.thresholds['frame_rate_max'] else 0.5,
            'audio': {'excellent': 1.0, 'good': 0.8, 'poor': 0.3, 'unknown': 0.5}[metrics.audio_quality]
        }
        
        overall_score = sum(weights[k] * score_components[k] for k in weights.keys()) * 100
        passes_standards = len(rejection_reasons) == 0
        
        return QualityAssessmentResult(
            video_path=video_path,
            timestamp=datetime.now(),
            metrics=metrics,
            overall_score=overall_score,
            passes_standards=passes_standards,
            rejection_reasons=rejection_reasons,
            comfyui_corrections=comfyui_corrections
        )

    async def _save_assessment_result(self, result: QualityAssessmentResult):
        """Save assessment result to PostgreSQL database"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS anime_quality_assessments (
                    id SERIAL PRIMARY KEY,
                    video_path VARCHAR(500) NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    motion_smoothness FLOAT,
                    duration_minutes FLOAT,
                    resolution_width INT,
                    resolution_height INT,
                    frame_rate FLOAT,
                    file_size_mb FLOAT,
                    audio_quality VARCHAR(50),
                    format_compliance BOOLEAN,
                    jellyfin_ready BOOLEAN,
                    overall_score FLOAT,
                    passes_standards BOOLEAN,
                    rejection_reasons JSONB,
                    comfyui_corrections JSONB
                )
            """)
            
            # Insert assessment result
            cursor.execute("""
                INSERT INTO anime_quality_assessments 
                (video_path, timestamp, motion_smoothness, duration_minutes, 
                 resolution_width, resolution_height, frame_rate, file_size_mb, 
                 audio_quality, format_compliance, jellyfin_ready, overall_score, 
                 passes_standards, rejection_reasons, comfyui_corrections)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                result.video_path, result.timestamp, result.metrics.motion_smoothness,
                result.metrics.duration_minutes, result.metrics.resolution[0], 
                result.metrics.resolution[1], result.metrics.frame_rate,
                result.metrics.file_size_mb, result.metrics.audio_quality,
                result.metrics.format_compliance, result.metrics.jellyfin_ready,
                result.overall_score, result.passes_standards,
                json.dumps(result.rejection_reasons), json.dumps(result.comfyui_corrections)
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Assessment result saved to database for {result.video_path}")
            
        except Exception as e:
            logger.error(f"Failed to save assessment result: {e}")
            raise

    async def _broadcast_assessment_update(self, result: QualityAssessmentResult):
        """Broadcast assessment update to WebSocket clients"""
        if not self.active_connections:
            return
        
        message = {
            'type': 'quality_assessment',
            'data': {
                'video_path': result.video_path,
                'overall_score': result.overall_score,
                'passes_standards': result.passes_standards,
                'rejection_reasons': result.rejection_reasons,
                'timestamp': result.timestamp.isoformat()
            }
        }
        
        # Broadcast to all connected clients
        disconnected = set()
        for websocket in self.active_connections:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception:
                disconnected.add(websocket)
        
        # Remove disconnected clients
        self.active_connections -= disconnected

    async def apply_comfyui_corrections(self, corrections: Dict[str, Any], workflow_id: str) -> Dict:
        """Apply quality corrections to ComfyUI workflow"""
        try:
            # Get current workflow
            response = requests.get(f"{self.comfyui_url}/api/v1/workflows/{workflow_id}")
            if response.status_code != 200:
                raise Exception(f"Failed to get workflow: {response.status_code}")
            
            workflow = response.json()
            
            # Apply corrections to workflow nodes
            for correction_type, correction_data in corrections.items():
                node_type = correction_data['node_type']
                settings = correction_data['settings']
                
                # Find or create node of specified type
                node_id = self._find_or_create_node(workflow, node_type, settings)
                
                logger.info(f"Applied {correction_type} correction with node {node_id}")
            
            # Update workflow
            update_response = requests.put(
                f"{self.comfyui_url}/api/v1/workflows/{workflow_id}",
                json=workflow
            )
            
            if update_response.status_code == 200:
                logger.info(f"ComfyUI workflow {workflow_id} updated with quality corrections")
                return {"status": "success", "workflow_id": workflow_id, "corrections_applied": len(corrections)}
            else:
                raise Exception(f"Failed to update workflow: {update_response.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to apply ComfyUI corrections: {e}")
            return {"status": "error", "message": str(e)}

    def _find_or_create_node(self, workflow: Dict, node_type: str, settings: Dict) -> str:
        """Find existing node or create new one in workflow"""
        # Implementation would depend on ComfyUI workflow structure
        # This is a simplified version
        
        # Check for existing node
        for node_id, node_data in workflow.get('nodes', {}).items():
            if node_data.get('class_type') == node_type:
                # Update existing node settings
                node_data['inputs'].update(settings)
                return node_id
        
        # Create new node
        new_node_id = f"quality_correction_{len(workflow.get('nodes', {}))}"
        workflow.setdefault('nodes', {})[new_node_id] = {
            'class_type': node_type,
            'inputs': settings
        }
        
        return new_node_id

# FastAPI Routes
quality_agent = AnimeQualityAssessment()

@app.post("/assess-quality/")
async def assess_video_quality(video_path: str):
    """Assess video quality and return comprehensive analysis"""
    return await quality_agent.analyze_video_quality(video_path)

@app.post("/apply-corrections/")
async def apply_quality_corrections(workflow_id: str, corrections: Dict[str, Any]):
    """Apply quality corrections to ComfyUI workflow"""
    return await quality_agent.apply_comfyui_corrections(corrections, workflow_id)

@app.get("/assessment-history/")
async def get_assessment_history(limit: int = 50):
    """Get recent quality assessment history"""
    try:
        conn = psycopg2.connect(**quality_agent.db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT * FROM anime_quality_assessments 
            ORDER BY timestamp DESC LIMIT %s
        """, (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        return {"assessments": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time quality updates"""
    await websocket.accept()
    quality_agent.active_connections.add(websocket)
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        quality_agent.active_connections.discard(websocket)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "anime-quality-assessment"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8305)