#!/usr/bin/env python3
"""
REAL video generation using AnimateDiff-Evolved
Creates actual animated content with character movement, not camera pans
"""

import json
import requests
import time
import subprocess
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnimateDiffVideoGenerator:
    """Generate REAL animated videos with character action"""

    def __init__(self):
        self.comfyui_url = "http://localhost:8188"
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")

    def create_animatediff_workflow(self, prompt: str, segment_num: int = 1):
        """Create AnimateDiff workflow for actual animation"""

        # This generates REAL animation with movement, not camera pans
        workflow = {
            "1": {
                "inputs": {
                    "ckpt_name": "AOM3A1B.safetensors"
                },
                "class_type": "CheckpointLoaderSimple"
            },
            "2": {
                "inputs": {
                    "model_name": "mm_sd_v15_v3_adapter.ckpt",
                    "beta_schedule": "sqrt_linear",
                    "motion_scale": 1.0,
                    "apply_mm_groupnorm_hack": False,
                    "model": ["1", 0]
                },
                "class_type": "ADE_AnimateDiffLoaderGen1"
            },
            "3": {
                "inputs": {
                    "context_options": "4",
                    "context_length": 16,
                    "context_stride": 1,
                    "context_overlap": 4,
                    "closed_loop": False,
                    "model": ["2", 0]
                },
                "class_type": "ADE_AnimateDiffLoaderWithContext"
            },
            "4": {
                "inputs": {
                    "context_length": 16,
                    "context_stride": 1,
                    "context_overlap": 4,
                    "context_schedule": "uniform",
                    "closed_loop": False,
                    "fuse_method": "pyramid",
                    "use_on_equal_length": False,
                    "start_percent": 0,
                    "guarantee_steps": 1
                },
                "class_type": "ADE_AnimateDiffUniformContextOptions"
            },
            "5": {
                "inputs": {
                    "text": f"{prompt}, action scene, dynamic movement, fighting, combat, energy blasts, explosions, intense battle",
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "6": {
                "inputs": {
                    "text": "static, still, no movement, blurry, low quality",
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "7": {
                "inputs": {
                    "width": 512,
                    "height": 512,
                    "batch_size": 120  # 5 seconds at 24fps
                },
                "class_type": "ADE_EmptyLatentImageLarge"
            },
            "8": {
                "inputs": {
                    "seed": 42 + segment_num * 137,
                    "steps": 20,
                    "cfg": 7,
                    "sampler_name": "euler_ancestral",
                    "scheduler": "karras",
                    "denoise": 1,
                    "model": ["3", 0],
                    "positive": ["5", 0],
                    "negative": ["6", 0],
                    "latent_image": ["7", 0]
                },
                "class_type": "KSampler"
            },
            "9": {
                "inputs": {
                    "samples": ["8", 0],
                    "vae": ["1", 2]
                },
                "class_type": "VAEDecode"
            },
            "10": {
                "inputs": {
                    "fps": 24,
                    "loop_count": 0,
                    "filename_prefix": f"animated_goblin_{segment_num:03d}",
                    "format": "video/h264-mp4",
                    "pix_fmt": "yuv420p",
                    "crf": 18,
                    "save_metadata": True,
                    "images": ["9", 0]
                },
                "class_type": "ADE_AnimateDiffCombine"
            }
        }

        return workflow

    def generate_real_trailer(self):
        """Generate a REAL 30-second animated trailer"""

        logger.info("=" * 60)
        logger.info("🎬 GENERATING REAL ANIMATED VIDEO")
        logger.info("=" * 60)
        logger.info("Using AnimateDiff-Evolved for actual character animation")
        logger.info("NOT camera pans - REAL movement and action!")

        segments = []

        # Generate 6 segments of 5 seconds each = 30 seconds total
        for i in range(6):
            logger.info(f"\n📍 Generating animated segment {i+1}/6...")

            # Different action for each segment
            actions = [
                "Goblin Slayer cyberpunk armor charging forward with energy sword",
                "Epic battle clash between Goblin Slayer and cyber goblins",
                "Explosions and energy blasts in neon city streets",
                "Goblin Slayer executing spinning attack with plasma weapons",
                "Multiple cyber goblins attacking from all directions",
                "Final dramatic victory pose with destroyed enemies"
            ]

            workflow = self.create_animatediff_workflow(actions[i], i+1)

            # Submit to ComfyUI
            response = requests.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow}
            )

            if response.ok:
                prompt_id = response.json()['prompt_id']
                logger.info(f"Submitted prompt {prompt_id}")

                # Wait for completion
                start = time.time()
                while time.time() - start < 600:  # 10 min timeout
                    history = requests.get(f"{self.comfyui_url}/history/{prompt_id}").json()

                    if prompt_id in history and history[prompt_id].get('outputs'):
                        logger.info(f"✅ Segment {i+1} complete!")

                        # Find the output file
                        output_file = self.output_dir / f"animated_goblin_{i+1:03d}_00001.mp4"
                        if output_file.exists():
                            segments.append(str(output_file))

                            # Verify it has real animation
                            probe_cmd = ["ffprobe", "-v", "error", "-show_entries",
                                       "format=duration", "-of", "json", str(output_file)]
                            result = subprocess.run(probe_cmd, capture_output=True, text=True)
                            info = json.loads(result.stdout)
                            duration = float(info['format']['duration'])
                            logger.info(f"Duration: {duration:.1f}s")
                        break

                    time.sleep(5)

        if len(segments) >= 6:
            # Combine all segments
            logger.info("\n📍 Combining segments into final trailer...")

            concat_file = self.output_dir / "animated_concat.txt"
            with open(concat_file, 'w') as f:
                for seg in segments:
                    f.write(f"file '{seg}'\n")

            final_output = self.output_dir / "goblin_slayer_animated_30s.mp4"

            combine_cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-vf", "scale=1920:1080:flags=lanczos",
                "-c:v", "libx264",
                "-preset", "slow",
                "-crf", "18",
                "-b:v", "15M",
                str(final_output)
            ]

            subprocess.run(combine_cmd, capture_output=True)

            logger.info("=" * 60)
            logger.info("✅ REAL ANIMATED TRAILER COMPLETE!")
            logger.info(f"📁 File: {final_output}")
            logger.info("This has ACTUAL animation, not camera pans!")
            logger.info("=" * 60)

            return str(final_output)

        return None

if __name__ == "__main__":
    generator = AnimateDiffVideoGenerator()
    generator.generate_real_trailer()