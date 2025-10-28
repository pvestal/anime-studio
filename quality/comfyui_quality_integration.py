#!/usr/bin/env python3
"""
ComfyUI Quality Integration
Real-time connection between ComfyUI generation and quality assessment system
Automatically processes generated content through quality pipeline
"""

import asyncio
import json
import logging
import websockets
import requests
import aiohttp
import cv2
import numpy as np
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComfyUIQualityIntegration:
    def __init__(self):
        self.comfyui_url = "http://127.0.0.1:8188"
        self.echo_brain_url = "http://127.0.0.1:8309"
        self.websocket_url = "ws://127.0.0.1:8188/ws"

        # Database connection
        self.db_params = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': '***REMOVED***'
        }

        # Quality standards for rejection
        self.quality_thresholds = {
            'min_resolution': (512, 512),
            'min_duration': 1.0,  # seconds
            'max_file_size_mb': 500,
            'min_fps': 15,
            'max_blur_threshold': 0.5,
            'min_contrast': 0.3,
            'min_overall_score': 0.7
        }

        # Active jobs tracking
        self.active_jobs = {}
        self.quality_cache = {}

    async def start_monitoring(self):
        """Start monitoring ComfyUI for completed generations"""
        logger.info("Starting ComfyUI quality integration monitoring...")

        try:
            async with websockets.connect(self.websocket_url) as websocket:
                logger.info("Connected to ComfyUI WebSocket")

                async for message in websocket:
                    try:
                        data = json.loads(message)
                        await self.handle_comfyui_message(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received: {message}")
                    except Exception as e:
                        logger.error(f"Error handling message: {e}")

        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            # Retry connection after delay
            await asyncio.sleep(5)
            await self.start_monitoring()

    async def handle_comfyui_message(self, data: Dict):
        """Process ComfyUI WebSocket messages"""
        if data.get('type') == 'executed':
            node_id = data.get('data', {}).get('node')
            prompt_id = data.get('data', {}).get('prompt_id')

            if node_id and prompt_id:
                # Check if this is a SaveImage node (final output)
                if await self.is_save_image_node(prompt_id, node_id):
                    logger.info(f"Generation completed: {prompt_id}")
                    await self.process_completed_generation(prompt_id, data)

        elif data.get('type') == 'progress':
            # Update job progress
            prompt_id = data.get('data', {}).get('prompt_id')
            progress = data.get('data', {}).get('value', 0)
            if prompt_id:
                await self.update_job_progress(prompt_id, progress)

    async def is_save_image_node(self, prompt_id: str, node_id: str) -> bool:
        """Check if node is a SaveImage node"""
        try:
            # Get prompt details from ComfyUI
            response = await self.get_prompt_details(prompt_id)
            if response and 'prompt' in response:
                prompt_data = response['prompt']
                if node_id in prompt_data and prompt_data[node_id].get('class_type') == 'SaveImage':
                    return True
        except Exception as e:
            logger.error(f"Error checking node type: {e}")
        return False

    async def get_prompt_details(self, prompt_id: str) -> Optional[Dict]:
        """Get prompt details from ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.comfyui_url}/history/{prompt_id}") as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            logger.error(f"Error getting prompt details: {e}")
        return None

    async def process_completed_generation(self, prompt_id: str, data: Dict):
        """Process completed generation through quality pipeline"""
        try:
            # Find generated files
            output_files = await self.find_output_files(prompt_id)

            for file_path in output_files:
                logger.info(f"Processing file: {file_path}")

                # Run quality assessment
                quality_result = await self.assess_video_quality(file_path)

                # Log assessment to database
                await self.log_quality_assessment(prompt_id, file_path, quality_result)

                # Check if quality meets standards
                if quality_result['passes_standards']:
                    logger.info(f"✅ Quality passed: {file_path}")
                    await self.handle_quality_pass(prompt_id, file_path, quality_result)
                else:
                    logger.warning(f"❌ Quality failed: {file_path}")
                    await self.handle_quality_failure(prompt_id, file_path, quality_result)

        except Exception as e:
            logger.error(f"Error processing generation {prompt_id}: {e}")

    async def find_output_files(self, prompt_id: str) -> List[str]:
        """Find output files for a given prompt ID"""
        output_dirs = [
            "/home/patrick/Documents/ComfyUI/output",
            "/opt/ComfyUI/output",
            "/tmp/comfyui_outputs"
        ]

        found_files = []

        for output_dir in output_dirs:
            if os.path.exists(output_dir):
                # Look for files with prompt_id in filename or recent files
                for root, dirs, files in os.walk(output_dir):
                    for file in files:
                        if prompt_id in file or self.is_recent_file(os.path.join(root, file)):
                            file_path = os.path.join(root, file)
                            if self.is_video_or_image(file_path):
                                found_files.append(file_path)

        return found_files

    def is_recent_file(self, file_path: str) -> bool:
        """Check if file was created recently (within last 5 minutes)"""
        try:
            file_time = os.path.getctime(file_path)
            current_time = datetime.now().timestamp()
            return (current_time - file_time) < 300  # 5 minutes
        except:
            return False

    def is_video_or_image(self, file_path: str) -> bool:
        """Check if file is video or image format"""
        extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.gif', '.png', '.jpg', '.jpeg']
        return any(file_path.lower().endswith(ext) for ext in extensions)

    async def assess_video_quality(self, file_path: str) -> Dict:
        """Assess video/image quality using computer vision"""
        try:
            file_hash = hashlib.md5(file_path.encode()).hexdigest()

            # Check cache first
            if file_hash in self.quality_cache:
                return self.quality_cache[file_hash]

            is_video = file_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.gif'))

            if is_video:
                quality_result = await self.assess_video_file(file_path)
            else:
                quality_result = await self.assess_image_file(file_path)

            # Cache result
            self.quality_cache[file_hash] = quality_result

            return quality_result

        except Exception as e:
            logger.error(f"Error assessing quality for {file_path}: {e}")
            return self.create_failed_assessment(file_path, str(e))

    async def assess_video_file(self, file_path: str) -> Dict:
        """Assess video file quality"""
        try:
            cap = cv2.VideoCapture(file_path)

            if not cap.isOpened():
                return self.create_failed_assessment(file_path, "Cannot open video file")

            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0

            # File size
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

            # Analyze frame quality (sample frames)
            quality_scores = []
            frame_sample_count = min(10, frame_count)

            for i in range(frame_sample_count):
                frame_pos = int((i / frame_sample_count) * frame_count)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()

                if ret:
                    score = self.analyze_frame_quality(frame)
                    quality_scores.append(score)

            cap.release()

            # Calculate overall quality
            avg_quality = np.mean(quality_scores) if quality_scores else 0

            # Check against thresholds
            passes_standards = self.check_quality_standards({
                'resolution': (width, height),
                'duration': duration,
                'fps': fps,
                'file_size_mb': file_size_mb,
                'quality_score': avg_quality
            })

            return {
                'file_path': file_path,
                'timestamp': datetime.now(),
                'resolution': (width, height),
                'duration': duration,
                'fps': fps,
                'file_size_mb': file_size_mb,
                'frame_count': frame_count,
                'quality_score': avg_quality,
                'frame_quality_scores': quality_scores,
                'passes_standards': passes_standards,
                'rejection_reasons': self.get_rejection_reasons({
                    'resolution': (width, height),
                    'duration': duration,
                    'fps': fps,
                    'file_size_mb': file_size_mb,
                    'quality_score': avg_quality
                }),
                'is_video': True
            }

        except Exception as e:
            return self.create_failed_assessment(file_path, str(e))

    async def assess_image_file(self, file_path: str) -> Dict:
        """Assess image file quality"""
        try:
            image = cv2.imread(file_path)

            if image is None:
                return self.create_failed_assessment(file_path, "Cannot read image file")

            height, width = image.shape[:2]
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

            # Analyze image quality
            quality_score = self.analyze_frame_quality(image)

            passes_standards = self.check_quality_standards({
                'resolution': (width, height),
                'duration': 0,  # Images have no duration
                'fps': 0,
                'file_size_mb': file_size_mb,
                'quality_score': quality_score
            })

            return {
                'file_path': file_path,
                'timestamp': datetime.now(),
                'resolution': (width, height),
                'duration': 0,
                'fps': 0,
                'file_size_mb': file_size_mb,
                'quality_score': quality_score,
                'passes_standards': passes_standards,
                'rejection_reasons': self.get_rejection_reasons({
                    'resolution': (width, height),
                    'duration': 0,
                    'fps': 0,
                    'file_size_mb': file_size_mb,
                    'quality_score': quality_score
                }),
                'is_video': False
            }

        except Exception as e:
            return self.create_failed_assessment(file_path, str(e))

    def analyze_frame_quality(self, frame: np.ndarray) -> float:
        """Analyze individual frame quality using computer vision"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Blur detection using Laplacian variance
            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
            blur_normalized = min(blur_score / 1000, 1.0)  # Normalize to 0-1

            # Contrast analysis
            contrast = gray.std() / 255.0

            # Brightness analysis
            brightness = gray.mean() / 255.0
            brightness_score = 1.0 - abs(brightness - 0.5) * 2  # Penalize extreme brightness

            # Edge detection for detail analysis
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.count_nonzero(edges) / edges.size

            # Combine metrics (weights can be adjusted)
            quality_score = (
                blur_normalized * 0.3 +
                contrast * 0.3 +
                brightness_score * 0.2 +
                edge_density * 0.2
            )

            return min(quality_score, 1.0)

        except Exception as e:
            logger.error(f"Error analyzing frame quality: {e}")
            return 0.0

    def check_quality_standards(self, metrics: Dict) -> bool:
        """Check if metrics meet quality standards"""
        width, height = metrics['resolution']
        min_width, min_height = self.quality_thresholds['min_resolution']

        if width < min_width or height < min_height:
            return False

        if metrics['duration'] > 0 and metrics['duration'] < self.quality_thresholds['min_duration']:
            return False

        if metrics['file_size_mb'] > self.quality_thresholds['max_file_size_mb']:
            return False

        if metrics['fps'] > 0 and metrics['fps'] < self.quality_thresholds['min_fps']:
            return False

        if metrics['quality_score'] < self.quality_thresholds['min_overall_score']:
            return False

        return True

    def get_rejection_reasons(self, metrics: Dict) -> List[str]:
        """Get list of reasons for quality rejection"""
        reasons = []

        width, height = metrics['resolution']
        min_width, min_height = self.quality_thresholds['min_resolution']

        if width < min_width or height < min_height:
            reasons.append(f"Resolution too low: {width}x{height} < {min_width}x{min_height}")

        if metrics['duration'] > 0 and metrics['duration'] < self.quality_thresholds['min_duration']:
            reasons.append(f"Duration too short: {metrics['duration']}s < {self.quality_thresholds['min_duration']}s")

        if metrics['file_size_mb'] > self.quality_thresholds['max_file_size_mb']:
            reasons.append(f"File too large: {metrics['file_size_mb']}MB > {self.quality_thresholds['max_file_size_mb']}MB")

        if metrics['fps'] > 0 and metrics['fps'] < self.quality_thresholds['min_fps']:
            reasons.append(f"Frame rate too low: {metrics['fps']}fps < {self.quality_thresholds['min_fps']}fps")

        if metrics['quality_score'] < self.quality_thresholds['min_overall_score']:
            reasons.append(f"Overall quality too low: {metrics['quality_score']} < {self.quality_thresholds['min_overall_score']}")

        return reasons

    def create_failed_assessment(self, file_path: str, error: str) -> Dict:
        """Create assessment result for failed analysis"""
        return {
            'file_path': file_path,
            'timestamp': datetime.now(),
            'resolution': (0, 0),
            'duration': 0,
            'fps': 0,
            'file_size_mb': 0,
            'quality_score': 0.0,
            'passes_standards': False,
            'rejection_reasons': [f"Analysis failed: {error}"],
            'error': error
        }

    async def handle_quality_pass(self, prompt_id: str, file_path: str, quality_result: Dict):
        """Handle video that passes quality standards"""
        try:
            # Copy to Jellyfin anime directory
            jellyfin_path = await self.copy_to_jellyfin(file_path, prompt_id)

            # Notify Echo Brain of successful generation
            await self.notify_echo_brain_success(prompt_id, file_path, quality_result)

            # Update database
            await self.update_job_status(prompt_id, "completed", quality_result)

            logger.info(f"✅ Quality passed - File moved to Jellyfin: {jellyfin_path}")

        except Exception as e:
            logger.error(f"Error handling quality pass: {e}")

    async def handle_quality_failure(self, prompt_id: str, file_path: str, quality_result: Dict):
        """Handle video that fails quality standards"""
        try:
            # Generate correction suggestions
            corrections = await self.generate_corrections(quality_result)

            # Notify Echo Brain for prompt improvement
            await self.notify_echo_brain_failure(prompt_id, file_path, quality_result, corrections)

            # Update database with failure reason
            await self.update_job_status(prompt_id, "quality_failed", quality_result)

            # Move failed file to review directory
            await self.move_to_review_directory(file_path, prompt_id)

            logger.warning(f"❌ Quality failed - Corrections suggested: {corrections}")

        except Exception as e:
            logger.error(f"Error handling quality failure: {e}")

    async def generate_corrections(self, quality_result: Dict) -> Dict:
        """Generate correction suggestions based on quality issues"""
        corrections = {}

        for reason in quality_result.get('rejection_reasons', []):
            if 'resolution' in reason.lower():
                corrections['resolution'] = "Increase width and height parameters in ComfyUI workflow"
            elif 'duration' in reason.lower():
                corrections['duration'] = "Increase frame count or adjust animation length"
            elif 'frame rate' in reason.lower():
                corrections['fps'] = "Increase FPS settings in video generation node"
            elif 'quality' in reason.lower():
                corrections['quality'] = "Improve prompt with more detail, adjust CFG scale, increase steps"
            elif 'file size' in reason.lower():
                corrections['compression'] = "Adjust video compression settings"

        return corrections

    async def copy_to_jellyfin(self, file_path: str, prompt_id: str) -> str:
        """Copy successful video to Jellyfin anime directory"""
        jellyfin_dir = Path("/mnt/10TB2/Anime/AI_Generated")
        jellyfin_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        file_ext = Path(file_path).suffix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        jellyfin_filename = f"echo_anime_{timestamp}_{prompt_id[:8]}{file_ext}"
        jellyfin_path = jellyfin_dir / jellyfin_filename

        # Copy file
        import shutil
        shutil.copy2(file_path, jellyfin_path)

        return str(jellyfin_path)

    async def move_to_review_directory(self, file_path: str, prompt_id: str):
        """Move failed video to review directory"""
        review_dir = Path("/opt/tower-anime/review")
        review_dir.mkdir(parents=True, exist_ok=True)

        file_ext = Path(file_path).suffix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        review_filename = f"failed_{timestamp}_{prompt_id[:8]}{file_ext}"
        review_path = review_dir / review_filename

        import shutil
        shutil.move(file_path, review_path)

        logger.info(f"Moved failed file to review: {review_path}")

    async def notify_echo_brain_success(self, prompt_id: str, file_path: str, quality_result: Dict):
        """Notify Echo Brain of successful generation"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "event": "quality_success",
                    "prompt_id": prompt_id,
                    "file_path": file_path,
                    "quality_score": quality_result['quality_score'],
                    "metrics": quality_result
                }

                async with session.post(f"{self.echo_brain_url}/api/quality-feedback", json=data) as response:
                    if response.status == 200:
                        logger.info(f"✅ Echo Brain notified of success: {prompt_id}")
                    else:
                        logger.warning(f"Failed to notify Echo Brain: {response.status}")

        except Exception as e:
            logger.error(f"Error notifying Echo Brain of success: {e}")

    async def notify_echo_brain_failure(self, prompt_id: str, file_path: str, quality_result: Dict, corrections: Dict):
        """Notify Echo Brain of quality failure for learning"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "event": "quality_failure",
                    "prompt_id": prompt_id,
                    "file_path": file_path,
                    "quality_score": quality_result['quality_score'],
                    "rejection_reasons": quality_result.get('rejection_reasons', []),
                    "corrections": corrections,
                    "metrics": quality_result
                }

                async with session.post(f"{self.echo_brain_url}/api/quality-feedback", json=data) as response:
                    if response.status == 200:
                        logger.info(f"🧠 Echo Brain notified of failure for learning: {prompt_id}")
                    else:
                        logger.warning(f"Failed to notify Echo Brain: {response.status}")

        except Exception as e:
            logger.error(f"Error notifying Echo Brain of failure: {e}")

    async def log_quality_assessment(self, prompt_id: str, file_path: str, quality_result: Dict):
        """Log quality assessment to database"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                INSERT INTO quality_assessments
                (prompt_id, file_path, quality_score, passes_standards, rejection_reasons, metrics, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (prompt_id) DO UPDATE SET
                    quality_score = EXCLUDED.quality_score,
                    passes_standards = EXCLUDED.passes_standards,
                    rejection_reasons = EXCLUDED.rejection_reasons,
                    metrics = EXCLUDED.metrics,
                    updated_at = NOW()
            """, (
                prompt_id,
                file_path,
                quality_result.get('quality_score', 0),
                quality_result.get('passes_standards', False),
                json.dumps(quality_result.get('rejection_reasons', [])),
                json.dumps(quality_result),
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error logging quality assessment: {e}")

    async def update_job_status(self, prompt_id: str, status: str, quality_result: Dict):
        """Update job status in database"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()

            cur.execute("""
                UPDATE production_jobs
                SET status = %s, quality_score = %s, updated_at = NOW()
                WHERE parameters::text LIKE %s
            """, (
                status,
                quality_result.get('quality_score', 0),
                f'%{prompt_id}%'
            ))

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating job status: {e}")

    async def update_job_progress(self, prompt_id: str, progress: float):
        """Update job progress"""
        if prompt_id in self.active_jobs:
            self.active_jobs[prompt_id]['progress'] = progress
            logger.debug(f"Job {prompt_id} progress: {progress*100:.1f}%")

# Create database table if it doesn't exist
async def create_quality_table():
    """Create quality assessments table"""
    try:
        conn = psycopg2.connect(
            host='localhost',
            database='tower_consolidated',
            user='patrick',
            password=''
        )
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS quality_assessments (
                id SERIAL PRIMARY KEY,
                prompt_id VARCHAR(255) UNIQUE,
                file_path TEXT,
                quality_score FLOAT,
                passes_standards BOOLEAN,
                rejection_reasons JSONB,
                metrics JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_quality_prompt_id ON quality_assessments(prompt_id);
            CREATE INDEX IF NOT EXISTS idx_quality_passes ON quality_assessments(passes_standards);
            CREATE INDEX IF NOT EXISTS idx_quality_score ON quality_assessments(quality_score);
        """)

        conn.commit()
        cur.close()
        conn.close()
        logger.info("Quality assessments table created/verified")

    except Exception as e:
        logger.error(f"Error creating quality table: {e}")

async def main():
    """Main entry point"""
    # Create database table
    await create_quality_table()

    # Start quality integration
    integration = ComfyUIQualityIntegration()
    await integration.start_monitoring()

if __name__ == "__main__":
    asyncio.run(main())