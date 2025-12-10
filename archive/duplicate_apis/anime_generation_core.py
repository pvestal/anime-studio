#!/usr/bin/env python3
"""
Unified Anime Generation Core - 93% Consistency System
Shared backend for both CLI and FastAPI interfaces
"""

import requests
import time
import shutil
import json
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Union
import uuid

# Import pose library
from pose_library import pose_library

class AnimeGenerationCore:
    """Core anime generation system with proven 93% consistency"""

    def __init__(self, comfyui_url: str = "http://localhost:8188"):
        self.comfyui_url = comfyui_url
        self.home_dir = Path.home()
        self.characters_dir = self.home_dir / ".anime-characters"
        self.output_dir = self.home_dir / "anime-output"
        self.comfyui_input = Path("/mnt/1TB-storage/ComfyUI/input")
        self.comfyui_output = Path("/mnt/1TB-storage/ComfyUI/output")

        # Default settings - proven values from 93% tests
        self.settings = {
            "checkpoint": "counterfeit_v3.safetensors",
            "ipadapter_weight": 0.9,
            "controlnet_strength": 0.7,
            "steps": 25,
            "cfg": 7.0,
            "width": 512,
            "height": 768
        }

        self._setup_directories()

    def _setup_directories(self):
        """Create necessary directories"""
        self.characters_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)

        # Create today's output folder
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = self.output_dir / today
        today_dir.mkdir(exist_ok=True)

        # Create latest symlink
        latest_dir = self.output_dir / "latest"
        if latest_dir.is_symlink():
            latest_dir.unlink()
        latest_dir.symlink_to(today_dir)

    def get_character_info(self, character_name: str) -> Optional[Dict]:
        """Get character reference and metadata"""
        char_dir = self.characters_dir / character_name
        if not char_dir.exists():
            return None

        # Look for reference image
        for ext in ['png', 'jpg', 'jpeg']:
            ref_file = char_dir / f"reference.{ext}"
            if ref_file.exists():
                metadata_file = char_dir / "metadata.json"
                metadata = {}
                if metadata_file.exists():
                    with open(metadata_file) as f:
                        metadata = json.load(f)

                return {
                    "reference": str(ref_file),
                    "metadata": metadata,
                    "name": character_name
                }
        return None

    def list_characters(self) -> List[str]:
        """List available characters"""
        chars = []
        if not self.characters_dir.exists():
            return chars

        for char_dir in self.characters_dir.iterdir():
            if char_dir.is_dir():
                # Check for reference image
                for ext in ['png', 'jpg', 'jpeg']:
                    if (char_dir / f"reference.{ext}").exists():
                        chars.append(char_dir.name)
                        break
        return sorted(chars)

    def add_character(self, name: str, reference_image: str, description: str = "") -> Dict:
        """Add a new character to the library"""
        char_dir = self.characters_dir / name
        char_dir.mkdir(exist_ok=True)

        # Copy reference image
        ref_source = Path(reference_image)
        if not ref_source.exists():
            raise FileNotFoundError(f"Reference image not found: {reference_image}")

        ref_dest = char_dir / "reference.png"
        shutil.copy(reference_image, ref_dest)

        # Save metadata
        metadata = {
            "name": name,
            "description": description,
            "created": datetime.now().isoformat(),
            "reference_source": str(ref_source)
        }

        with open(char_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        return {
            "name": name,
            "reference_path": str(ref_dest),
            "metadata": metadata
        }

    def get_pose_skeleton(self, pose_description: str = None) -> Optional[str]:
        """Get pose skeleton using the pose library system"""
        if not pose_description:
            pose_description = "standing"

        # Use pose library to get appropriate skeleton
        pose_skeleton = pose_library.get_pose_skeleton(pose_description)

        if pose_skeleton:
            return pose_skeleton

        # Fallback: use default standing pose if library fails
        pose_file = self.comfyui_output / "pose_test_00001_.png"
        if pose_file.exists():
            return str(pose_file)

        # Last fallback: extract pose from any recent image
        recent_images = sorted(self.comfyui_output.glob("*.png"),
                              key=lambda x: x.stat().st_mtime, reverse=True)
        if recent_images:
            return self._extract_openpose(str(recent_images[0]))

        return None

    def _extract_openpose(self, image_path: str) -> Optional[str]:
        """Extract OpenPose from image"""
        img_name = Path(image_path).name
        input_path = self.comfyui_input / img_name
        shutil.copy(image_path, input_path)

        workflow = {
            "1": {
                "inputs": {"image": img_name, "upload": "image"},
                "class_type": "LoadImage"
            },
            "2": {
                "inputs": {"image": ["1", 0]},
                "class_type": "OpenposePreprocessor"
            },
            "3": {
                "inputs": {
                    "filename_prefix": "extracted_pose",
                    "images": ["2", 0]
                },
                "class_type": "SaveImage"
            }
        }

        response = requests.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow})
        if response.status_code == 200:
            time.sleep(8)
            pose_files = list(self.comfyui_output.glob("extracted_pose_*.png"))
            if pose_files:
                return str(sorted(pose_files)[-1])
        return None

    def generate_image(self, character_ref: str, pose_ref: str, prompt: str,
                      seed: Optional[int] = None, job_id: Optional[str] = None) -> Dict:
        """
        Generate image using proven ControlNet + IPAdapter workflow
        Returns: {"success": bool, "output_file": str, "job_id": str, "error": str}
        """
        if seed is None:
            seed = int(time.time()) % 1000000

        if job_id is None:
            job_id = str(uuid.uuid4())

        try:
            # Copy files to ComfyUI input
            char_name = f"char_{seed}.png"
            pose_name = f"pose_{seed}.png"
            shutil.copy(character_ref, self.comfyui_input / char_name)
            shutil.copy(pose_ref, self.comfyui_input / pose_name)

            # Proven 93% consistency workflow from test_actual_fix.py
            workflow = {
                # Base model
                "model": {
                    "inputs": {"ckpt_name": self.settings["checkpoint"]},
                    "class_type": "CheckpointLoaderSimple"
                },

                # IPAdapter for character consistency
                "ipa_loader": {
                    "inputs": {
                        "model": ["model", 0],
                        "preset": "PLUS (high strength)"
                    },
                    "class_type": "IPAdapterUnifiedLoader"
                },
                "char_img": {
                    "inputs": {"image": char_name, "upload": "image"},
                    "class_type": "LoadImage"
                },
                "ipa_apply": {
                    "inputs": {
                        "model": ["ipa_loader", 0],
                        "ipadapter": ["ipa_loader", 1],
                        "image": ["char_img", 0],
                        "weight": self.settings["ipadapter_weight"],
                        "weight_type": "standard",
                        "start_at": 0.0,
                        "end_at": 0.9
                    },
                    "class_type": "IPAdapter"
                },

                # ControlNet for pose control
                "cn_loader": {
                    "inputs": {"control_net_name": "control_v11p_sd15_openpose.pth"},
                    "class_type": "ControlNetLoader"
                },
                "pose_img": {
                    "inputs": {"image": pose_name, "upload": "image"},
                    "class_type": "LoadImage"
                },

                # Text conditioning
                "pos_text": {
                    "inputs": {"text": f"{prompt}, masterpiece, best quality", "clip": ["model", 1]},
                    "class_type": "CLIPTextEncode"
                },
                "neg_text": {
                    "inputs": {"text": "low quality, blurry, different character", "clip": ["model", 1]},
                    "class_type": "CLIPTextEncode"
                },

                # Apply ControlNet to conditioning (CRITICAL FIX)
                "cn_pos": {
                    "inputs": {
                        "conditioning": ["pos_text", 0],
                        "control_net": ["cn_loader", 0],
                        "image": ["pose_img", 0],
                        "strength": self.settings["controlnet_strength"]
                    },
                    "class_type": "ControlNetApply"
                },
                "cn_neg": {
                    "inputs": {
                        "conditioning": ["neg_text", 0],
                        "control_net": ["cn_loader", 0],
                        "image": ["pose_img", 0],
                        "strength": self.settings["controlnet_strength"]
                    },
                    "class_type": "ControlNetApply"
                },

                # Generation
                "latent": {
                    "inputs": {"width": self.settings["width"], "height": self.settings["height"], "batch_size": 1},
                    "class_type": "EmptyLatentImage"
                },
                "sampler": {
                    "inputs": {
                        "seed": seed,
                        "steps": self.settings["steps"],
                        "cfg": self.settings["cfg"],
                        "sampler_name": "dpmpp_2m",
                        "scheduler": "karras",
                        "denoise": 1.0,
                        "model": ["ipa_apply", 0],
                        "positive": ["cn_pos", 0],
                        "negative": ["cn_neg", 0],
                        "latent_image": ["latent", 0]
                    },
                    "class_type": "KSampler"
                },
                "decode": {
                    "inputs": {"samples": ["sampler", 0], "vae": ["model", 2]},
                    "class_type": "VAEDecode"
                },
                "save": {
                    "inputs": {
                        "filename_prefix": f"anime_gen_{seed}",
                        "images": ["decode", 0]
                    },
                    "class_type": "SaveImage"
                }
            }

            response = requests.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow})
            if response.status_code == 200:
                prompt_id = response.json().get('prompt_id')

                # Wait for completion
                time.sleep(12)

                # Find output file
                output_files = list(self.comfyui_output.glob(f"anime_gen_{seed}_*.png"))
                if output_files:
                    output_file = str(sorted(output_files)[-1])
                    return {
                        "success": True,
                        "output_file": output_file,
                        "job_id": job_id,
                        "prompt_id": prompt_id,
                        "seed": seed,
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "output_file": None,
                        "job_id": job_id,
                        "error": "No output file generated"
                    }
            else:
                return {
                    "success": False,
                    "output_file": None,
                    "job_id": job_id,
                    "error": f"ComfyUI error: {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "output_file": None,
                "job_id": job_id,
                "error": str(e)
            }

    def copy_to_output(self, source_file: str, character_name: str, pose_desc: str) -> str:
        """Copy generated file to organized output folder"""
        timestamp = datetime.now().strftime("%H%M%S")
        pose_clean = pose_desc.replace(" ", "_").replace(",", "")[:20]

        today = datetime.now().strftime("%Y-%m-%d")
        output_dir = self.output_dir / today

        filename = f"{character_name}_{pose_clean}_{timestamp}.png"
        dest_file = output_dir / filename

        shutil.copy(source_file, dest_file)
        return str(dest_file)

    def generate_character_variations(self, character_name: str, pose: str,
                                    prompt_extra: str = "", variations: int = 1) -> List[Dict]:
        """Generate multiple variations of a character"""
        results = []

        # Get character info
        char_info = self.get_character_info(character_name)
        if not char_info:
            raise ValueError(f"Character '{character_name}' not found")

        # Get pose skeleton
        pose_ref = self.get_pose_skeleton(pose)
        if not pose_ref:
            raise ValueError("Could not generate pose skeleton")

        # Build full prompt
        char_desc = char_info["metadata"].get("description", f"{character_name}, anime character")
        full_prompt = f"{char_desc}, {pose}"
        if prompt_extra:
            full_prompt += f", {prompt_extra}"

        # Generate variations
        for i in range(variations):
            result = self.generate_image(
                char_info["reference"],
                pose_ref,
                full_prompt,
                seed=None,
                job_id=f"{character_name}_{i}_{int(time.time())}"
            )

            if result["success"]:
                # Copy to organized output
                final_file = self.copy_to_output(result["output_file"], character_name, pose)
                result["organized_output"] = final_file

            results.append(result)

        return results

# Global instance for easy import
anime_core = AnimeGenerationCore()