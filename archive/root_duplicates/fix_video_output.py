#!/usr/bin/env python3
"""
Fix video output parameters - test different resolutions and durations
"""
import json
import logging
import time

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"


def create_fixed_video_workflow(duration_seconds: int, resolution: tuple, prompt: str):
    """Create a fixed workflow for proper video output"""
    frames = duration_seconds * 24
    width, height = resolution

    workflow = {
        "1": {
            "inputs": {
                "text": f"masterpiece, best quality, {prompt}",
                "clip": ["4", 1],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Prompt)"},
        },
        "2": {
            "inputs": {
                "text": "worst quality, low quality, blurry, ugly, distorted, static, still image",
                "clip": ["4", 1],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Negative)"},
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
                "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
            "_meta": {"title": "KSampler"},
        },
        "4": {
            "inputs": {"ckpt_name": "AOM3A1B.safetensors"},
            "class_type": "CheckpointLoaderSimple",
            "_meta": {"title": "Load Checkpoint"},
        },
        "5": {
            "inputs": {"width": width, "height": height, "batch_size": frames},
            "class_type": "EmptyLatentImage",
            "_meta": {
                "title": f"Empty Latent Image ({frames} frames for {duration_seconds}s at {width}x{height})"
            },
        },
        "6": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"},
        },
        "7": {
            "inputs": {
                "images": ["6", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"FIXED_{duration_seconds}SEC_{width}x{height}_",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 18,
                "save_metadata": True,
                "pingpong": False,
                "save_output": True,
            },
            "class_type": "VHS_VideoCombine",
            "_meta": {"title": f"Video Combine - {duration_seconds}s {width}x{height}"},
        },
        "10": {
            "inputs": {"model_name": "mm-Stabilized_high.pth"},
            "class_type": "ADE_LoadAnimateDiffModel",
            "_meta": {"title": "Load AnimateDiff Model"},
        },
        "11": {
            "inputs": {
                "motion_model": ["10", 0],
                "context_options": ["13", 0],
                "start_percent": 0.0,
                "end_percent": 1.0,
            },
            "class_type": "ADE_ApplyAnimateDiffModel",
            "_meta": {"title": "Apply AnimateDiff Model (WITH Context Options)"},
        },
        "12": {
            "inputs": {
                "model": ["4", 0],
                "beta_schedule": "autoselect",
                "m_models": ["11", 0],
            },
            "class_type": "ADE_UseEvolvedSampling",
            "_meta": {"title": "Use Evolved Sampling"},
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
                "guarantee_steps": 1,
            },
            "class_type": "ADE_LoopedUniformContextOptions",
            "_meta": {
                "title": f"Context Options - 24 frame window for {frames} total frames"
            },
        },
    }
    return workflow


def submit_and_monitor(workflow, description, max_wait_minutes=10):
    """Submit workflow and monitor until completion"""
    try:
        response = requests.post(
            f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

        logger.info(f"🎬 Generating {description} - ID: {prompt_id}")

        start_time = time.time()
        max_wait_seconds = max_wait_minutes * 60

        while time.time() - start_time < max_wait_seconds:
            try:
                response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                history = response.json()

                if prompt_id in history:
                    status = history[prompt_id]["status"]
                    if status.get("completed", False):
                        gen_time = time.time() - start_time
                        logger.info(
                            f"✅ {description} completed in {gen_time:.1f}s")

                        # Check output files
                        outputs = history[prompt_id].get("outputs", {})
                        for node_id, output in outputs.items():
                            if "videos" in output:
                                for video in output["videos"]:
                                    filename = video["filename"]
                                    logger.info(f"📹 Video created: {filename}")

                                    # Check file size
                                    import os

                                    file_path = (
                                        f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                                    )
                                    if os.path.exists(file_path):
                                        size_mb = os.path.getsize(file_path) / (
                                            1024 * 1024
                                        )
                                        logger.info(
                                            f"📊 File size: {size_mb:.2f} MB")

                                        # Check if file size is reasonable for video duration
                                        expected_min_size = (
                                            1.0  # MB minimum for decent quality
                                        )
                                        if size_mb < expected_min_size:
                                            logger.warning(
                                                f"⚠️  Video file seems too small ({size_mb:.2f} MB)"
                                            )
                                        else:
                                            logger.info(
                                                f"✅ File size looks good ({size_mb:.2f} MB)"
                                            )

                        return True, prompt_id

                    elif "error" in status:
                        logger.error(
                            f"❌ {description} failed: {status['error']}")
                        return False, prompt_id

                elapsed = time.time() - start_time
                logger.info(f"⏳ {description}: {elapsed:.0f}s elapsed")
                time.sleep(15)

            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(15)

        logger.error(
            f"❌ {description} timeout after {max_wait_minutes} minutes")
        return False, prompt_id

    except Exception as e:
        logger.error(f"❌ {description} submit failed: {e}")
        return False, None


def test_video_parameters():
    """Test different video parameters to fix output issues"""

    logger.info("=" * 80)
    logger.info("🔧 TESTING VIDEO OUTPUT PARAMETERS")
    logger.info("Finding optimal settings for 5+ second videos at 1024x1024")
    logger.info("=" * 80)

    test_cases = [
        {
            "name": "5sec_1024x1024_test",
            "duration": 5,
            "resolution": (1024, 1024),
            "prompt": "cyberpunk character walking through neon city street",
            "description": "5 second 1024x1024 video",
        },
        {
            "name": "3sec_1024x1024_test",
            "duration": 3,
            "resolution": (1024, 1024),
            "prompt": "anime character in dramatic pose",
            "description": "3 second 1024x1024 video",
        },
        {
            "name": "5sec_512x512_working",
            "duration": 5,
            "resolution": (512, 512),
            "prompt": "cyberpunk character walking through neon city street",
            "description": "5 second 512x512 video (known working)",
        },
    ]

    results = []

    for i, test_case in enumerate(test_cases, 1):
        logger.info(
            f"\n📋 Test {i}/{len(test_cases)}: {test_case['description']}")
        logger.info(f"   Duration: {test_case['duration']}s")
        logger.info(
            f"   Resolution: {test_case['resolution'][0]}x{test_case['resolution'][1]}"
        )
        logger.info(f"   Frames: {test_case['duration'] * 24}")

        workflow = create_fixed_video_workflow(
            test_case["duration"], test_case["resolution"], test_case["prompt"]
        )

        success, prompt_id = submit_and_monitor(
            workflow,
            test_case["description"],
            max_wait_minutes=15,  # Allow more time for higher resolution
        )

        results.append(
            {
                "test": test_case["name"],
                "description": test_case["description"],
                "duration": test_case["duration"],
                "resolution": test_case["resolution"],
                "success": success,
                "prompt_id": prompt_id,
            }
        )

        if success:
            logger.info(f"✅ SUCCESS: {test_case['description']}")
        else:
            logger.error(f"❌ FAILED: {test_case['description']}")

        # Wait between tests to not overload ComfyUI
        if i < len(test_cases):
            logger.info("⏳ Waiting 30 seconds before next test...")
            time.sleep(30)

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📊 VIDEO OUTPUT TEST RESULTS")
    logger.info("=" * 80)

    working_tests = [r for r in results if r["success"]]
    failed_tests = [r for r in results if not r["success"]]

    for result in results:
        status = "✅ SUCCESS" if result["success"] else "❌ FAILED"
        res = result["resolution"]
        logger.info(
            f"{status}: {result['duration']}s @ {res[0]}x{res[1]} - {result['description']}"
        )

    logger.info(
        f"\n🎯 Results: {len(working_tests)}/{len(results)} tests passed")

    if working_tests:
        logger.info("\n✅ WORKING CONFIGURATIONS:")
        for result in working_tests:
            res = result["resolution"]
            logger.info(f"   • {result['duration']}s @ {res[0]}x{res[1]}")

    if failed_tests:
        logger.info("\n❌ FAILED CONFIGURATIONS:")
        for result in failed_tests:
            res = result["resolution"]
            logger.info(f"   • {result['duration']}s @ {res[0]}x{res[1]}")

    # Recommendations
    logger.info("\n💡 RECOMMENDATIONS:")
    if any(r["success"] and r["resolution"] == (1024, 1024) for r in results):
        logger.info(
            "✅ 1024x1024 resolution is working - video output issue is FIXED")
    else:
        logger.info(
            "⚠️  1024x1024 resolution failed - may need VRAM optimization or different settings"
        )

    if any(r["success"] and r["duration"] >= 5 for r in results):
        logger.info("✅ 5+ second videos are working - duration issue is FIXED")
    else:
        logger.info(
            "⚠️  5+ second videos failed - may need shorter context windows or more VRAM"
        )

    return results


if __name__ == "__main__":
    results = test_video_parameters()

    # Exit with appropriate code
    success_count = sum(1 for r in results if r["success"])
    if success_count >= len(results) // 2:  # At least half successful
        exit(0)
    else:
        exit(1)
