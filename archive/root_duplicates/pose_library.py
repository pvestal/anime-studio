#!/usr/bin/env python3
"""
Pose Library System
Manages pose extraction, storage, and retrieval for anime generation
Based on verified test results
"""

import json
import time
import shutil
import requests
from pathlib import Path
from typing import Dict, Optional, List
import hashlib

class PoseLibrary:
    """Manage pose skeletons for consistent character generation"""

    def __init__(self):
        self.pose_dir = Path.home() / ".anime-poses"
        self.pose_dir.mkdir(exist_ok=True)
        self.comfyui_url = "http://localhost:8188"
        self.comfyui_input = Path("/mnt/1TB-storage/ComfyUI/input")
        self.comfyui_output = Path("/mnt/1TB-storage/ComfyUI/output")

        # Text-to-pose mappings (verified in tests)
        self.pose_mappings = {
            "standing": ["standing", "stand", "upright", "neutral", "idle"],
            "sitting": ["sitting", "sit", "seated", "chair", "bench"],
            "running": ["running", "run", "jogging", "sprint", "dash"],
            "jumping": ["jumping", "jump", "leap", "hop", "airborne"],
            "fighting": ["fighting", "combat", "battle", "action", "martial"],
            "walking": ["walking", "walk", "stroll", "stride"],
            "crouching": ["crouching", "crouch", "squat", "kneel"],
            "lying": ["lying", "lay", "recline", "prone", "supine"],
            "dancing": ["dancing", "dance", "twirl", "spin"],
            "waving": ["waving", "wave", "greeting", "hello", "bye"]
        }

        # Initialize with default poses from existing files
        self._initialize_defaults()

    def _initialize_defaults(self):
        """Initialize library with any existing pose files"""
        # Check for existing extracted poses
        existing_poses = {
            "standing": self.comfyui_output / "pose_test_00001_.png",
            "sitting": self.comfyui_output / "extracted_pose_test_sitting_00001_.png",
            "running": self.comfyui_output / "extracted_pose_test_running,_00001_.png",
            "jumping": self.comfyui_output / "extracted_pose_test_jumping_00001_.png"
        }

        for pose_name, pose_path in existing_poses.items():
            if pose_path.exists() and not (self.pose_dir / pose_name).exists():
                self.add_pose(pose_name, str(pose_path), f"Default {pose_name} pose")
                print(f"  Initialized: {pose_name} pose")

    def find_pose_type(self, description: str) -> str:
        """Map text description to pose type"""
        description_lower = description.lower()

        for pose_type, keywords in self.pose_mappings.items():
            for keyword in keywords:
                if keyword in description_lower:
                    return pose_type

        return "standing"  # Default pose

    def get_pose_skeleton(self, pose_description: str) -> Optional[str]:
        """Get pose skeleton file for given description"""
        pose_type = self.find_pose_type(pose_description)
        pose_path = self.pose_dir / pose_type / "skeleton.png"

        if pose_path.exists():
            return str(pose_path)

        # Try to extract from any similar existing image
        return self._extract_pose_from_description(pose_description)

    def add_pose(self, name: str, skeleton_path: str, description: str = ""):
        """Add a pose to the library"""
        if not Path(skeleton_path).exists():
            raise FileNotFoundError(f"Skeleton file not found: {skeleton_path}")

        pose_subdir = self.pose_dir / name
        pose_subdir.mkdir(exist_ok=True)

        # Copy skeleton
        dest_path = pose_subdir / "skeleton.png"
        shutil.copy(skeleton_path, dest_path)

        # Save metadata
        metadata = {
            "name": name,
            "description": description,
            "source": str(skeleton_path),
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "hash": self._calculate_hash(dest_path)
        }

        with open(pose_subdir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        return dest_path

    def extract_pose(self, image_path: str, save_name: Optional[str] = None) -> Optional[str]:
        """Extract OpenPose skeleton from an image"""
        if not Path(image_path).exists():
            return None

        # Copy to ComfyUI input
        img_name = Path(image_path).name
        input_path = self.comfyui_input / img_name
        shutil.copy(image_path, input_path)

        # Create workflow for pose extraction
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
                    "filename_prefix": f"extracted_pose_{int(time.time())}",
                    "images": ["2", 0]
                },
                "class_type": "SaveImage"
            }
        }

        try:
            response = requests.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow})
            if response.status_code != 200:
                return None

            # Wait for extraction
            time.sleep(8)

            # Find output file
            prefix = workflow["3"]["inputs"]["filename_prefix"]
            output_files = list(self.comfyui_output.glob(f"{prefix}_*.png"))

            if output_files:
                extracted_path = str(output_files[-1])

                # Save to library if name provided
                if save_name:
                    self.add_pose(save_name, extracted_path, f"Extracted from {img_name}")

                return extracted_path

        except Exception as e:
            print(f"Pose extraction error: {e}")

        return None

    def _extract_pose_from_description(self, description: str) -> Optional[str]:
        """Generate an image with the description and extract its pose"""
        # Generate a simple image with the pose
        workflow = {
            "4": {
                "inputs": {"ckpt_name": "counterfeit_v3.safetensors"},
                "class_type": "CheckpointLoaderSimple"
            },
            "6": {
                "inputs": {
                    "text": f"anime character {description}, full body, simple background",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "7": {
                "inputs": {"text": "bad quality, cropped, partial", "clip": ["4", 1]},
                "class_type": "CLIPTextEncode"
            },
            "5": {
                "inputs": {"width": 512, "height": 768, "batch_size": 1},
                "class_type": "EmptyLatentImage"
            },
            "3": {
                "inputs": {
                    "seed": int(time.time() * 1000) % 2147483647,
                    "steps": 10,  # Quick generation
                    "cfg": 7,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "8": {
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
                "class_type": "VAEDecode"
            },
            "9": {
                "inputs": {
                    "filename_prefix": f"pose_gen_{int(time.time())}",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage"
            }
        }

        try:
            response = requests.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow})
            if response.status_code == 200:
                time.sleep(10)

                # Find generated image
                prefix = workflow["9"]["inputs"]["filename_prefix"]
                images = list(self.comfyui_output.glob(f"{prefix}_*.png"))

                if images:
                    # Extract pose from generated image
                    pose_type = self.find_pose_type(description)
                    return self.extract_pose(str(images[-1]), pose_type)

        except Exception as e:
            print(f"Pose generation error: {e}")

        return None

    def list_poses(self) -> List[Dict]:
        """List all available poses in the library"""
        poses = []

        for pose_subdir in self.pose_dir.iterdir():
            if pose_subdir.is_dir() and (pose_subdir / "skeleton.png").exists():
                metadata_path = pose_subdir / "metadata.json"
                metadata = {"name": pose_subdir.name, "description": ""}

                if metadata_path.exists():
                    with open(metadata_path) as f:
                        metadata = json.load(f)

                poses.append(metadata)

        return poses

    def get_random_pose(self) -> Optional[str]:
        """Get a random pose from the library"""
        poses = self.list_poses()
        if poses:
            import random
            pose = random.choice(poses)
            return str(self.pose_dir / pose["name"] / "skeleton.png")
        return None

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate hash of a file for duplicate detection"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def remove_duplicates(self):
        """Remove duplicate poses based on file hash"""
        hashes = {}
        duplicates = []

        for pose in self.list_poses():
            pose_path = self.pose_dir / pose["name"] / "skeleton.png"
            if pose_path.exists():
                file_hash = self._calculate_hash(pose_path)

                if file_hash in hashes:
                    duplicates.append(pose["name"])
                else:
                    hashes[file_hash] = pose["name"]

        for dup in duplicates:
            shutil.rmtree(self.pose_dir / dup)
            print(f"  Removed duplicate: {dup}")

        return len(duplicates)

# Global instance for easy import
pose_library = PoseLibrary()