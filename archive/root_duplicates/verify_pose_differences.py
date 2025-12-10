#!/usr/bin/env python3
"""
PROPER pose verification test
Generate FULL BODY images with different poses to verify they actually work
"""

import requests
import time
import shutil
from pathlib import Path

def generate_full_body_with_pose(character_id: str, pose_desc: str, test_name: str):
    """Generate FULL BODY image with specific pose"""

    payload = {
        "prompt": f"anime girl, pink hair, green eyes, FULL BODY, standing, wide shot, full figure visible, head to toe",
        "negative_prompt": "cropped, close-up, portrait, face only, half body, cut off",
        "width": 512,
        "height": 768,
        "character_id": character_id,
        "pose_description": pose_desc,
        "project_id": "test_poses"
    }

    print(f"\nGenerating {test_name} with pose: {pose_desc}")
    print(f"  Prompt includes: FULL BODY, wide shot, head to toe")

    response = requests.post("http://localhost:8328/generate", json=payload)
    if response.status_code != 200:
        print(f"  ❌ Failed to start generation: {response.status_code}")
        return None

    job_data = response.json()
    job_id = job_data["job_id"]
    print(f"  Job ID: {job_id}")

    # Wait for completion
    max_wait = 30
    while max_wait > 0:
        time.sleep(2)
        status_response = requests.get(f"http://localhost:8328/jobs/{job_id}")

        if status_response.status_code == 200:
            job_status = status_response.json()

            if job_status["status"] == "completed":
                output_path = job_status.get("output_path")
                if output_path:
                    # Copy to test directory with descriptive name
                    test_dir = Path("/tmp/pose_verification")
                    test_dir.mkdir(exist_ok=True)

                    dest_path = test_dir / f"{test_name}_{pose_desc.replace(' ', '_')}.png"
                    shutil.copy(output_path, dest_path)

                    print(f"  ✅ Generated: {dest_path.name}")
                    return str(dest_path)
                else:
                    print(f"  ❌ No output path in completed job")
                    return None

            elif job_status["status"] == "failed":
                print(f"  ❌ Generation failed: {job_status.get('error')}")
                return None

        max_wait -= 1

    print(f"  ❌ Timeout waiting for generation")
    return None

def extract_better_poses():
    """Extract poses from actual full-body images"""
    print("\n=== Extracting Better Pose Skeletons ===")

    # Generate full-body reference images first
    test_poses = [
        ("anime girl sitting on chair, full body, side view", "sitting"),
        ("anime girl standing upright, full body, front view", "standing"),
        ("anime girl running, full body, side view", "running"),
        ("anime girl jumping in air, full body", "jumping")
    ]

    for prompt, pose_name in test_poses:
        print(f"\nGenerating full-body image for {pose_name} pose...")

        # Generate a full-body image
        workflow = {
            "4": {
                "inputs": {"ckpt_name": "counterfeit_v3.safetensors"},
                "class_type": "CheckpointLoaderSimple"
            },
            "6": {
                "inputs": {"text": prompt, "clip": ["4", 1]},
                "class_type": "CLIPTextEncode"
            },
            "7": {
                "inputs": {"text": "cropped, close-up, portrait", "clip": ["4", 1]},
                "class_type": "CLIPTextEncode"
            },
            "5": {
                "inputs": {"width": 512, "height": 768, "batch_size": 1},
                "class_type": "EmptyLatentImage"
            },
            "3": {
                "inputs": {
                    "seed": int(time.time() * 1000) % 2147483647,
                    "steps": 20,
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
                    "filename_prefix": f"fullbody_{pose_name}",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage"
            }
        }

        response = requests.post("http://localhost:8188/prompt", json={"prompt": workflow})
        if response.status_code == 200:
            time.sleep(12)

            # Find generated image
            output_files = list(Path("/mnt/1TB-storage/ComfyUI/output").glob(f"fullbody_{pose_name}_*.png"))
            if output_files:
                source_img = str(output_files[-1])
                print(f"  Generated: {Path(source_img).name}")

                # Now extract pose from this full-body image
                img_name = Path(source_img).name
                shutil.copy(source_img, f"/mnt/1TB-storage/ComfyUI/input/{img_name}")

                extract_workflow = {
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
                            "filename_prefix": f"better_pose_{pose_name}",
                            "images": ["2", 0]
                        },
                        "class_type": "SaveImage"
                    }
                }

                response = requests.post("http://localhost:8188/prompt", json={"prompt": extract_workflow})
                if response.status_code == 200:
                    time.sleep(8)

                    pose_files = list(Path("/mnt/1TB-storage/ComfyUI/output").glob(f"better_pose_{pose_name}_*.png"))
                    if pose_files:
                        # Update the pose library with better skeleton
                        pose_lib_dir = Path.home() / f".anime-poses/{pose_name}"
                        pose_lib_dir.mkdir(parents=True, exist_ok=True)

                        dest = pose_lib_dir / "skeleton.png"
                        shutil.copy(str(pose_files[-1]), dest)
                        print(f"  ✅ Updated {pose_name} pose skeleton")

def main():
    print("="*60)
    print("PROPER POSE VERIFICATION TEST")
    print("="*60)

    # First, extract better pose skeletons from full-body images
    extract_better_poses()

    # Test poses
    test_cases = [
        ("standing", "Test_1_Standing"),
        ("sitting on chair", "Test_2_Sitting"),
        ("running", "Test_3_Running"),
        ("jumping", "Test_4_Jumping")
    ]

    print("\n" + "="*60)
    print("GENERATING FULL BODY IMAGES WITH DIFFERENT POSES")
    print("="*60)

    results = []
    for pose_desc, test_name in test_cases:
        result = generate_full_body_with_pose("sakura", pose_desc, test_name)
        results.append((test_name, pose_desc, result))

    # Summary
    print("\n" + "="*60)
    print("VERIFICATION RESULTS")
    print("="*60)

    print("\nGenerated Images (check these for DIFFERENT body positions):")
    for test_name, pose_desc, result in results:
        if result:
            print(f"  ✅ {test_name}: {result}")
        else:
            print(f"  ❌ {test_name}: Failed")

    print("\nTo verify poses are different:")
    print("1. Check that all images show FULL BODY (not just face)")
    print("2. Compare body positions between images")
    print("3. Standing should be upright")
    print("4. Sitting should show bent legs/seated position")
    print("5. Running should show dynamic leg position")
    print("6. Jumping should show airborne position")

    print("\nImages saved to: /tmp/pose_verification/")

if __name__ == "__main__":
    main()