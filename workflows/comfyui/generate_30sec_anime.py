#!/usr/bin/env python3
"""
30-Second Anime Video Generator using AnimateDiff + RIFE Interpolation
This script automates the generation of 30-second anime videos by:
1. Using AnimateDiff to generate 120 frames (5 seconds at 24fps)
2. Using RIFE VFI to interpolate 6x, creating 720 frames (30 seconds at 24fps)

Author: Claude Code
Date: 2025-10-28
"""

import json
import requests
import time
import sys
import os
import uuid
from typing import Optional, Dict, Any
import argparse

class ComfyUIClient:
    def __init__(self, server_address="127.0.0.1:8188"):
        self.server_address = server_address
        self.client_id = str(uuid.uuid4())

    def queue_prompt(self, prompt: Dict[str, Any], client_id: Optional[str] = None) -> str:
        """Queue a prompt for processing and return the prompt_id"""
        if client_id is None:
            client_id = self.client_id

        p = {"prompt": prompt, "client_id": client_id}
        data = json.dumps(p).encode('utf-8')

        try:
            response = requests.post(f"http://{self.server_address}/prompt", data=data,
                                   headers={'Content-Type': 'application/json'})
            if response.status_code != 200:
                # Print the actual error response for debugging
                try:
                    error_data = response.json()
                    raise Exception(f"Failed to queue prompt (HTTP {response.status_code}): {error_data}")
                except:
                    raise Exception(f"Failed to queue prompt (HTTP {response.status_code}): {response.text}")
            response.raise_for_status()
            return response.json()['prompt_id']
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to queue prompt: {e}")

    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """Download an image from ComfyUI"""
        url = f"http://{self.server_address}/view"
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to download image: {e}")

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """Get the history for a specific prompt_id"""
        try:
            response = requests.get(f"http://{self.server_address}/history/{prompt_id}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get history: {e}")

    def get_queue(self) -> Dict[str, Any]:
        """Get current queue status"""
        try:
            response = requests.get(f"http://{self.server_address}/queue")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get queue: {e}")

def load_workflow(workflow_path: str) -> Dict[str, Any]:
    """Load the workflow JSON file"""
    try:
        with open(workflow_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise Exception(f"Workflow file not found: {workflow_path}")
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in workflow file: {e}")

def update_prompt_in_workflow(workflow: Dict[str, Any], positive_prompt: str, negative_prompt: str = None) -> Dict[str, Any]:
    """Update the text prompts in the workflow"""
    # Update positive prompt (node 1)
    if "1" in workflow and "inputs" in workflow["1"]:
        workflow["1"]["inputs"]["text"] = positive_prompt

    # Update negative prompt (node 2) if provided
    if negative_prompt and "2" in workflow and "inputs" in workflow["2"]:
        workflow["2"]["inputs"]["text"] = negative_prompt

    return workflow

def update_seed_in_workflow(workflow: Dict[str, Any], seed: int) -> Dict[str, Any]:
    """Update the seed in the workflow"""
    # Update seed (node 3 - KSampler)
    if "3" in workflow and "inputs" in workflow["3"]:
        workflow["3"]["inputs"]["seed"] = seed

    return workflow

def wait_for_completion(client: ComfyUIClient, prompt_id: str, check_interval: int = 5) -> bool:
    """Wait for the prompt to complete processing"""
    print(f"Waiting for completion of prompt {prompt_id}...")

    while True:
        try:
            history = client.get_history(prompt_id)
            if prompt_id in history:
                completion_data = history[prompt_id]
                if "outputs" in completion_data:
                    print("✅ Generation completed successfully!")
                    return True
                elif "status" in completion_data and completion_data["status"]["completed"]:
                    print("✅ Generation completed!")
                    return True

            # Check if still in queue
            queue = client.get_queue()
            in_queue = any(item[1]["prompt"][1] == prompt_id for item in queue["queue_running"] + queue["queue_pending"])

            if not in_queue:
                # Not in queue and not in history with outputs - might have failed
                print("❌ Generation may have failed or been interrupted")
                return False

            print(f"⏳ Still processing... (checking again in {check_interval}s)")
            time.sleep(check_interval)

        except Exception as e:
            print(f"Error checking status: {e}")
            time.sleep(check_interval)

def generate_30sec_anime(prompt: str, negative_prompt: str = None, seed: int = None,
                        workflow_path: str = "/mnt/1TB-storage/ComfyUI/anime_30sec_standard.json",
                        server_address: str = "127.0.0.1:8188") -> bool:
    """
    Generate a 30-second anime video with the given prompt

    Args:
        prompt: Positive text prompt for generation
        negative_prompt: Negative text prompt (optional)
        seed: Random seed (optional, will use random if not provided)
        workflow_path: Path to the workflow JSON file
        server_address: ComfyUI server address

    Returns:
        bool: True if generation was successful
    """

    # Initialize client
    client = ComfyUIClient(server_address)

    # Load workflow
    print("📁 Loading workflow...")
    workflow = load_workflow(workflow_path)

    # Update prompts
    print("✏️  Updating prompts...")
    if negative_prompt is None:
        negative_prompt = "worst quality, low quality, blurry, ugly, distorted, static, still image, text, watermark, bad anatomy"

    workflow = update_prompt_in_workflow(workflow, prompt, negative_prompt)

    # Update seed if provided
    if seed is not None:
        print(f"🎲 Setting seed to {seed}")
        workflow = update_seed_in_workflow(workflow, seed)

    # Queue the prompt
    print("🚀 Queueing generation...")
    print(f"📝 Prompt: {prompt}")
    print(f"🚫 Negative: {negative_prompt}")

    try:
        prompt_id = client.queue_prompt(workflow)
        print(f"✅ Queued with ID: {prompt_id}")

        # Wait for completion
        success = wait_for_completion(client, prompt_id)

        if success:
            print("🎉 30-second anime video generation completed!")
            print("📁 Check the ComfyUI output folder for your video:")
            print("   - 5-second AnimateDiff version: animatediff_video_5sec_*.mp4")
            print("   - 30-second RIFE interpolated: anime_30sec_final_*.mp4")
            return True
        else:
            print("❌ Generation failed or was interrupted")
            return False

    except Exception as e:
        print(f"❌ Error during generation: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Generate 30-second anime videos using AnimateDiff + RIFE")
    parser.add_argument("prompt", help="Positive text prompt for generation")
    parser.add_argument("--negative", "-n", help="Negative text prompt",
                       default="worst quality, low quality, blurry, ugly, distorted, static, still image, text, watermark")
    parser.add_argument("--seed", "-s", type=int, help="Random seed for generation")
    parser.add_argument("--workflow", "-w", help="Path to workflow JSON file",
                       default="/mnt/1TB-storage/ComfyUI/anime_30sec_standard.json")
    parser.add_argument("--server", help="ComfyUI server address", default="127.0.0.1:8188")

    args = parser.parse_args()

    print("🎭 30-Second Anime Video Generator")
    print("=" * 50)

    # Check if workflow file exists
    if not os.path.exists(args.workflow):
        print(f"❌ Workflow file not found: {args.workflow}")
        sys.exit(1)

    # Generate the video
    success = generate_30sec_anime(
        prompt=args.prompt,
        negative_prompt=args.negative,
        seed=args.seed,
        workflow_path=args.workflow,
        server_address=args.server
    )

    if success:
        print("\n🎉 SUCCESS: Your 30-second anime video has been generated!")
        sys.exit(0)
    else:
        print("\n❌ FAILED: Video generation was not successful")
        sys.exit(1)

if __name__ == "__main__":
    main()