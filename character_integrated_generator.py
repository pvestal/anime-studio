#!/usr/bin/env python3
"""
Character-Integrated Video Generator
Uses the character system to generate videos with specific project bible characters
"""
import json
import requests
import time
import logging
from datetime import datetime
from character_system import get_character_prompt

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

def create_character_workflow(character_name: str, scene_context: str, duration_seconds: int):
    """Create workflow using character system for proper character integration"""
    frames = duration_seconds * 24

    # Get character-specific prompts
    character_data = get_character_prompt(character_name, scene_context)

    if not character_data['character_found']:
        logger.warning(f"Character '{character_name}' not found, using fallback")
        positive_prompt = f"masterpiece, best quality, anime character {character_name}, {scene_context}"
        negative_prompt = "worst quality, low quality, blurry, ugly, distorted"
    else:
        # Build proper prompt with character data
        positive_prompt = f"masterpiece, best quality, {character_data['prompt']}"
        negative_prompt = f"worst quality, low quality, blurry, ugly, distorted, {character_data['negative_prompt']}"
        logger.info(f"✅ Using project bible character: {character_name}")
        logger.info(f"📝 Character prompt: {positive_prompt[:100]}...")

    # Use the working AnimateDiff-Evolved workflow structure
    workflow = {
        "1": {
            "inputs": {
                "text": positive_prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {
                "title": "CLIP Text Encode (Prompt)"
            }
        },
        "2": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {
                "title": "CLIP Text Encode (Negative)"
            }
        },
        "3": {
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["12", 0],
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler",
            "_meta": {
                "title": "KSampler"
            }
        },
        "4": {
            "inputs": {
                "ckpt_name": "AOM3A1B.safetensors"
            },
            "class_type": "CheckpointLoaderSimple",
            "_meta": {
                "title": "Load Checkpoint"
            }
        },
        "5": {
            "inputs": {
                "width": 1024,
                "height": 1024,
                "batch_size": frames
            },
            "class_type": "EmptyLatentImage",
            "_meta": {
                "title": f"Empty Latent Image ({frames} frames for {duration_seconds} seconds)"
            }
        },
        "6": {
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            },
            "class_type": "VAEDecode",
            "_meta": {
                "title": "VAE Decode"
            }
        },
        "7": {
            "inputs": {
                "images": ["6", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"{character_name.replace(' ', '_')}_{duration_seconds}SEC_",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 18,
                "save_metadata": True,
                "pingpong": False,
                "save_output": True
            },
            "class_type": "VHS_VideoCombine",
            "_meta": {
                "title": f"Video Combine - {duration_seconds} Second Character Video"
            }
        },
        "10": {
            "inputs": {
                "model_name": "mm-Stabilized_high.pth"
            },
            "class_type": "ADE_LoadAnimateDiffModel",
            "_meta": {
                "title": "Load AnimateDiff Model"
            }
        },
        "11": {
            "inputs": {
                "motion_model": ["10", 0],
                "context_options": ["13", 0],
                "start_percent": 0.0,
                "end_percent": 1.0
            },
            "class_type": "ADE_ApplyAnimateDiffModel",
            "_meta": {
                "title": "Apply AnimateDiff Model (WITH Context Options)"
            }
        },
        "12": {
            "inputs": {
                "model": ["4", 0],
                "beta_schedule": "autoselect",
                "m_models": ["11", 0]
            },
            "class_type": "ADE_UseEvolvedSampling",
            "_meta": {
                "title": "Use Evolved Sampling"
            }
        },
        "13": {
            "inputs": {
                "context_length": 24,
                "context_stride": 1,
                "context_overlap": 4,
                "context_schedule": "uniform",
                "closed_loop": True,
                "fuse_method": "pyramid",
                "use_on_equal_length": False,
                "start_percent": 0.0,
                "guarantee_steps": 1
            },
            "class_type": "ADE_LoopedUniformContextOptions",
            "_meta": {
                "title": f"Context Options - 24 frame window for {frames} total frames"
            }
        }
    }
    return workflow

def submit_and_wait(workflow, description, duration):
    """Submit workflow and wait for completion"""
    try:
        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

        logger.info(f"🎬 Generating {description} ({duration}s) - ID: {prompt_id}")

        start_time = time.time()
        timeout = max(duration * 120, 600)  # 2 minutes per second, minimum 10 minutes

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                history = response.json()

                if prompt_id in history:
                    status = history[prompt_id]["status"]
                    if status.get("completed", False):
                        gen_time = time.time() - start_time
                        logger.info(f"✅ {description} completed in {gen_time:.1f}s")

                        # Get output files
                        outputs = history[prompt_id].get("outputs", {})
                        for node_id, output in outputs.items():
                            if "videos" in output:
                                for video in output["videos"]:
                                    logger.info(f"📹 Video saved: {video['filename']}")

                        return True
                    elif "error" in status:
                        logger.error(f"❌ {description} failed: {status['error']}")
                        return False

                elapsed = time.time() - start_time
                logger.info(f"⏳ {description}: {elapsed:.0f}s elapsed")
                time.sleep(10)

            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(10)

        logger.error(f"❌ {description} timeout after {timeout}s")
        return False

    except Exception as e:
        logger.error(f"❌ {description} submit failed: {e}")
        return False

def test_character_generation():
    """Test generation with specific project bible characters"""

    logger.info("="*60)
    logger.info("🎭 TESTING CHARACTER-INTEGRATED VIDEO GENERATION")
    logger.info("Using actual project bible characters")
    logger.info("="*60)

    # Test scenarios with project bible characters (short durations for testing)
    test_scenarios = [
        {
            "character": "Kai Nakamura",
            "scene": "standing confidently in neon-lit cyberpunk alley",
            "duration": 3,
            "description": "Kai Nakamura cyberpunk scene"
        }
    ]

    results = []

    for scenario in test_scenarios:
        logger.info(f"\n🎬 Testing: {scenario['description']}")

        workflow = create_character_workflow(
            scenario['character'],
            scenario['scene'],
            scenario['duration']
        )

        success = submit_and_wait(
            workflow,
            scenario['description'],
            scenario['duration']
        )

        results.append({
            "scenario": scenario['description'],
            "character": scenario['character'],
            "success": success
        })

        if success:
            logger.info(f"✅ SUCCESS: {scenario['description']}")
        else:
            logger.error(f"❌ FAILED: {scenario['description']}")

        # Wait between generations
        time.sleep(5)

    # Summary
    logger.info("\n" + "="*60)
    logger.info("📊 CHARACTER GENERATION TEST RESULTS")
    logger.info("="*60)

    successful = sum(1 for r in results if r['success'])
    total = len(results)

    for result in results:
        status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
        logger.info(f"{status}: {result['scenario']} ({result['character']})")

    logger.info(f"\n🎯 Overall Results: {successful}/{total} successful")

    if successful == total:
        logger.info("🎉 ALL CHARACTER GENERATION TESTS PASSED!")
        logger.info("✅ Character system is properly integrated with video generation")
    else:
        logger.warning("⚠️  Some character generation tests failed")

    return successful == total

if __name__ == "__main__":
    success = test_character_generation()
    exit(0 if success else 1)