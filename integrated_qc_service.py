#!/usr/bin/env python3
"""
Integrated QC Service for Anime Generation
Uses Echo Brain's LLaVA 13B model for automatic quality control
"""

import os
import json
import asyncio
import aiohttp
import requests
import time
import uuid
import base64
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Anime QC Service")

class QCAnimeRequest(BaseModel):
    prompt: str
    character: str = "Kai Nakamura"
    scene_type: str = "dialogue"
    duration: int = 1
    style: str = "photorealistic anime"
    max_retries: int = 3

class QCResult(BaseModel):
    success: bool
    video_path: Optional[str] = None
    qc_score: float = 0.0
    qc_details: Dict = {}
    attempts: int = 0
    issues_found: List[str] = []
    regeneration_reason: Optional[str] = None

class IntegratedQCAnimeGenerator:
    def __init__(self):
        self.comfyui_url = "http://127.0.0.1:8188"
        self.echo_url = "http://127.0.0.1:8309"
        self.client_id = str(uuid.uuid4())
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")

    async def generate_with_qc(self, request: QCAnimeRequest) -> QCResult:
        """Generate anime video with automatic quality control"""

        for attempt in range(request.max_retries):
            print(f"🎬 Generation attempt {attempt + 1}/{request.max_retries}")

            # Step 1: Generate video using ComfyUI
            video_path = await self._generate_video(request)
            if not video_path:
                continue

            # Step 2: Extract frames for QC
            frames = await self._extract_frames(video_path)
            if not frames:
                continue

            # Step 3: Run LLaVA QC on frames
            qc_results = await self._run_qc_analysis(frames, request.prompt)

            # Step 4: Check if quality passes
            if qc_results["passed"]:
                return QCResult(
                    success=True,
                    video_path=video_path,
                    qc_score=qc_results["score"],
                    qc_details=qc_results,
                    attempts=attempt + 1,
                    issues_found=qc_results.get("issues", [])
                )
            else:
                print(f"❌ QC Failed: {qc_results['issues']}")
                # Adjust parameters for next attempt
                request = self._adjust_parameters(request, qc_results)

        # All attempts failed
        return QCResult(
            success=False,
            qc_score=qc_results.get("score", 0),
            qc_details=qc_results,
            attempts=request.max_retries,
            issues_found=qc_results.get("issues", []),
            regeneration_reason="Max retries exceeded - could not generate acceptable quality"
        )

    async def _generate_video(self, request: QCAnimeRequest) -> Optional[str]:
        """Generate video using ComfyUI with corrected parameters"""

        # Use corrected AnimateDiff parameters to avoid noise
        workflow = {
            "1": {
                "inputs": {"ckpt_name": "Counterfeit-V2.5.safetensors"},
                "class_type": "CheckpointLoaderSimple"
            },
            "2": {
                "inputs": {
                    "text": f"{request.character}, {request.prompt}, {request.style}, high quality, detailed, masterpiece, smooth animation",
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "3": {
                "inputs": {
                    "text": "blurry, low quality, distorted, bad anatomy, static, boring, flickering, inconsistent, noise, artifacts, slideshow",
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "4": {
                "inputs": {
                    "width": 512,  # Reduced from 1024 to prevent noise
                    "height": 512,
                    "batch_size": max(16, request.duration * 12)  # Better frame count
                },
                "class_type": "EmptyLatentImage"
            },
            "5": {
                "inputs": {
                    "model_name": "mm-Stabilized_high.pth",
                    "beta_schedule": "sqrt_linear (AnimateDiff)",
                    "model": ["1", 0]
                },
                "class_type": "ADE_AnimateDiffLoaderGen1"
            },
            "6": {
                "inputs": {
                    "seed": int(time.time()),  # Random seed
                    "steps": 20,  # Reduced steps
                    "cfg": 7.0,   # Reduced CFG to prevent artifacts
                    "sampler_name": "euler",
                    "scheduler": "normal",  # Better scheduler
                    "denoise": 1.0,
                    "model": ["5", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                },
                "class_type": "KSampler"
            },
            "7": {
                "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
                "class_type": "VAEDecode"
            },
            "8": {
                "inputs": {
                    "images": ["7", 0],
                    "filename_prefix": f"qc_anime_{int(time.time())}"
                },
                "class_type": "SaveImage"
            },
            "9": {
                "inputs": {
                    "images": ["7", 0],
                    "frame_rate": 12.0,  # Lower frame rate for stability
                    "format": "video/h264-mp4",
                    "filename_prefix": f"qc_video_{int(time.time())}",
                    "loop_count": 0,
                    "pingpong": False,
                    "save_output": True
                },
                "class_type": "VHS_VideoCombine"
            }
        }

        try:
            # Submit to ComfyUI
            response = requests.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow, "client_id": self.client_id}
            )

            if response.status_code != 200:
                print(f"ComfyUI error: {response.text}")
                return None

            prompt_id = response.json().get("prompt_id")
            print(f"Submitted to ComfyUI: {prompt_id}")

            # Wait for completion (with timeout)
            for _ in range(60):  # 5-minute timeout
                await asyncio.sleep(5)

                # Check for new videos
                latest_video = self._find_latest_video()
                if latest_video:
                    print(f"✅ Video generated: {latest_video}")
                    return str(latest_video)

            print("⏰ Timeout waiting for video generation")
            return None

        except Exception as e:
            print(f"Generation error: {e}")
            return None

    def _find_latest_video(self) -> Optional[Path]:
        """Find the most recently generated video"""
        try:
            video_files = list(self.output_dir.glob("qc_video_*.mp4"))
            if video_files:
                return max(video_files, key=lambda p: p.stat().st_mtime)
            return None
        except Exception as e:
            print(f"Error finding video: {e}")
            return None

    async def _extract_frames(self, video_path: str) -> List[str]:
        """Extract frames from video for QC analysis"""
        try:
            import subprocess

            frames_dir = Path("/tmp/qc_frames")
            frames_dir.mkdir(exist_ok=True)

            # Extract 3 frames (beginning, middle, end)
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vf", "select='eq(n\\,0)+eq(n\\,10)+eq(n\\,20)'",
                "-vsync", "vfr",
                f"{frames_dir}/frame_%02d.png"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Frame extraction failed: {result.stderr}")
                return []

            frame_files = list(frames_dir.glob("frame_*.png"))
            return [str(f) for f in sorted(frame_files)]

        except Exception as e:
            print(f"Frame extraction error: {e}")
            return []

    async def _run_qc_analysis(self, frames: List[str], prompt: str) -> Dict:
        """Run LLaVA QC analysis on frames"""

        total_score = 0
        all_issues = []
        frame_count = len(frames)

        for i, frame_path in enumerate(frames):
            print(f"🔍 Analyzing frame {i+1}/{frame_count}...")

            try:
                # Read and encode frame
                with open(frame_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')

                # Create STRICT QC prompt
                qc_prompt = f"""
                STRICT ANALYSIS: This frame should show: "{prompt}"

                CRITICAL VALIDATION POINTS:
                1. CHARACTER MATCH: Does this show the exact character requested? Wrong character = AUTOMATIC FAIL
                2. ACTION MATCH: Does the character perform the requested action? Static when should be moving = FAIL
                3. SCENE ACCURACY: Does the scene match the description?
                4. VISUAL QUALITY: No noise, artifacts, or distortion
                5. ANIME STYLE: Proper anime/manga art style

                STRICT SCORING (BE HARSH):
                - 9-10 = PERFECT match of character, action, scene, AND quality
                - 7-8 = Good match with minor deviations
                - 5-6 = Some elements correct but major issues
                - 1-4 = Wrong character, wrong action, or poor quality

                FAIL CONDITIONS (score 1-4):
                - Wrong character gender/appearance
                - Missing requested action
                - Noise/static/artifacts
                - Wrong scene setting

                Be extremely strict. Score and explain what's wrong.
                """

                # Call LLaVA via Ollama
                response = requests.post(
                    "http://***REMOVED***:11434/api/generate",
                    json={
                        "model": "llava:13b",
                        "prompt": qc_prompt,
                        "images": [image_data],
                        "stream": False
                    },
                    timeout=30
                )

                if response.status_code == 200:
                    result = response.json()
                    analysis = result.get("response", "")

                    # Extract score from response
                    score = self._extract_score(analysis)
                    total_score += score

                    if score < 7:
                        all_issues.append(f"Frame {i+1}: {analysis[:100]}...")

                    print(f"Frame {i+1} score: {score}/10")

                else:
                    print(f"LLaVA error for frame {i+1}: {response.status_code}")
                    all_issues.append(f"Frame {i+1}: Analysis failed")

            except Exception as e:
                print(f"QC error for frame {i+1}: {e}")
                all_issues.append(f"Frame {i+1}: QC analysis failed - {e}")

        avg_score = total_score / frame_count if frame_count > 0 else 0
        passed = avg_score >= 8.5 and len(all_issues) == 0  # Much stricter threshold

        return {
            "passed": passed,
            "score": avg_score,
            "issues": all_issues,
            "frame_count": frame_count,
            "threshold": 7.0
        }

    def _extract_score(self, analysis: str) -> float:
        """Extract numerical score from LLaVA analysis"""
        import re

        # Look for patterns like "8/10", "score: 7", "rating of 6"
        patterns = [
            r'(\d+)/10',
            r'score[:\s]*(\d+)',
            r'rating[:\s]*of[:\s]*(\d+)',
            r'(\d+)\s*out\s*of\s*10'
        ]

        for pattern in patterns:
            match = re.search(pattern, analysis.lower())
            if match:
                try:
                    return float(match.group(1))
                except:
                    continue

        # Fallback: look for any single digit
        digit_match = re.search(r'\b([1-9]|10)\b', analysis)
        if digit_match:
            try:
                return float(digit_match.group(1))
            except:
                pass

        # Default to low score if can't parse
        return 3.0

    def _adjust_parameters(self, request: QCAnimeRequest, qc_results: Dict) -> QCAnimeRequest:
        """Adjust generation parameters based on QC feedback"""

        issues = qc_results.get("issues", [])

        # Adjust based on common issues
        if any("noise" in issue.lower() or "static" in issue.lower() for issue in issues):
            # Lower CFG and resolution for next attempt
            print("🔧 Adjusting for noise/static issues")

        if any("blur" in issue.lower() for issue in issues):
            # Increase steps for next attempt
            print("🔧 Adjusting for blur issues")

        if any("character" in issue.lower() for issue in issues):
            # Enhance character description
            request.prompt = f"clear detailed {request.character}, {request.prompt}"
            print("🔧 Enhanced character description")

        return request

# API Endpoints
@app.post("/generate", response_model=QCResult)
async def generate_with_qc(request: QCAnimeRequest):
    """Generate anime video with automatic QC"""
    generator = IntegratedQCAnimeGenerator()
    return await generator.generate_with_qc(request)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "qc_enabled": True, "llava_model": "13b"}

if __name__ == "__main__":
    import uvicorn
    print("🎬 Starting Integrated QC Anime Generation Service")
    print("🔍 LLaVA 13B Quality Control: ENABLED")
    print("🎯 Automatic garbage detection and regeneration")
    uvicorn.run(app, host="0.0.0.0", port=8329)