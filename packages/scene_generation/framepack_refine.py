"""FramePack vid2vid refinement for Wan T2V output.

Wan T2V 1.3B generates good composition and motion but struggles with fine
detail at 480x720.  This module re-denoises the Wan output through FramePack
(HunyuanVideo) at 544x704, preserving layout while sharpening anatomy/detail.

Pipeline:
  Wan 480x720 mp4 → VHS_LoadVideoPath → resize 544x704 → VAEEncodeTiled → LATENT
  → FramePackSampler(initial_samples=LATENT, denoise_strength=0.4) → decode → mp4

Optional character HunyuanVideo LoRA injected via FramePackLoraSelect node.
"""

import asyncio
import json
import logging
import time
from pathlib import Path

from packages.core.config import COMFYUI_URL, COMFYUI_OUTPUT_DIR

logger = logging.getLogger(__name__)

# Reuse model constants from the I2V module
FRAMEPACK_MODELS = {
    "i2v": "FramePackI2V_HY_fp8_e4m3fn.safetensors",
    "clip_l": "clip_l.safetensors",
    "llava_text": "llava_llama3_fp16.safetensors",
    "clip_vision": "sigclip_vision_patch14_384.safetensors",
    "vae": "hunyuan_video_vae_bf16.safetensors",
}

# Target resolution for FramePack refinement (fits 12GB RTX 3060)
V2V_WIDTH = 544
V2V_HEIGHT = 704


def build_framepack_v2v_workflow(
    video_path: str,
    prompt_text: str,
    negative_text: str = "low quality, blurry, distorted, watermark",
    denoise_strength: float = 0.4,
    total_seconds: float = 3.0,
    steps: int = 25,
    seed: int | None = None,
    guidance_scale: float = 6.0,
    gpu_memory_preservation: float = 6.0,
    lora_name: str | None = None,
    lora_strength: float = 0.8,
    output_prefix: str | None = None,
) -> tuple[dict, str, str]:
    """Build a FramePack vid2vid ComfyUI workflow.

    Takes an existing video (Wan output), encodes it as initial_samples,
    and partially re-denoises through FramePack to refine detail.

    Returns (workflow_dict, sampler_node_id, output_prefix).
    """
    import random as _random

    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    ts = int(time.time())
    prefix = output_prefix or f"fpv2v_{ts}"

    workflow: dict[str, dict] = {}
    nid = 1

    # -- Optional LoRA node (1a) --
    lora_node = None
    if lora_name:
        lora_node = str(nid)
        workflow[lora_node] = {
            "class_type": "FramePackLoraSelect",
            "inputs": {
                "lora": lora_name,
                "strength": lora_strength,
                "fuse_lora": True,
            },
        }
        nid += 1

    # Node 1: LoadFramePackModel
    model_node = str(nid)
    model_inputs: dict = {
        "model": FRAMEPACK_MODELS["i2v"],
        "base_precision": "bf16",
        "quantization": "fp8_e4m3fn",
        "load_device": "offload_device",
        "attention_mode": "sdpa",
    }
    if lora_node:
        model_inputs["lora"] = [lora_node, 0]
    workflow[model_node] = {
        "class_type": "LoadFramePackModel",
        "inputs": model_inputs,
    }
    nid += 1

    # Node 2: DualCLIPLoader
    clip_node = str(nid)
    workflow[clip_node] = {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": FRAMEPACK_MODELS["clip_l"],
            "clip_name2": FRAMEPACK_MODELS["llava_text"],
            "type": "hunyuan_video",
            "device": "default",
        },
    }
    nid += 1

    # Node 3: Positive CLIP encode
    pos_node = str(nid)
    workflow[pos_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node 4: Negative CLIP encode
    neg_node = str(nid)
    workflow[neg_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node 5: VAELoader
    vae_node = str(nid)
    workflow[vae_node] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": FRAMEPACK_MODELS["vae"]},
    }
    nid += 1

    # Node 6: VHS_LoadVideoPath — load Wan output, resize to FramePack resolution
    load_video_node = str(nid)
    workflow[load_video_node] = {
        "class_type": "VHS_LoadVideoPath",
        "inputs": {
            "video": video_path,
            "force_rate": 30,
            "custom_width": V2V_WIDTH,
            "custom_height": V2V_HEIGHT,
            "frame_load_cap": 0,
            "skip_first_frames": 0,
            "select_every_nth": 1,
        },
    }
    nid += 1

    # Node 7: VAEEncodeTiled — encode ALL video frames → initial_samples LATENT
    vae_enc_video_node = str(nid)
    workflow[vae_enc_video_node] = {
        "class_type": "VAEEncodeTiled",
        "inputs": {
            "pixels": [load_video_node, 0],
            "vae": [vae_node, 0],
            "tile_size": 256,
            "overlap": 64,
            "temporal_size": 64,
            "temporal_overlap": 8,
        },
    }
    nid += 1

    # Node 8: ImageFromBatch — extract first frame for start_latent + CLIP vision
    first_frame_node = str(nid)
    workflow[first_frame_node] = {
        "class_type": "ImageFromBatch",
        "inputs": {
            "image": [load_video_node, 0],
            "batch_index": 0,
            "length": 1,
        },
    }
    nid += 1

    # Node 9: VAEEncode — encode first frame → start_latent
    vae_enc_frame_node = str(nid)
    workflow[vae_enc_frame_node] = {
        "class_type": "VAEEncode",
        "inputs": {
            "pixels": [first_frame_node, 0],
            "vae": [vae_node, 0],
        },
    }
    nid += 1

    # Node 10: CLIPVisionLoader
    clip_vis_load_node = str(nid)
    workflow[clip_vis_load_node] = {
        "class_type": "CLIPVisionLoader",
        "inputs": {"clip_name": FRAMEPACK_MODELS["clip_vision"]},
    }
    nid += 1

    # Node 11: CLIPVisionEncode — first frame → image_embeds
    clip_vis_enc_node = str(nid)
    workflow[clip_vis_enc_node] = {
        "class_type": "CLIPVisionEncode",
        "inputs": {
            "clip_vision": [clip_vis_load_node, 0],
            "image": [first_frame_node, 0],
            "crop": "center",
        },
    }
    nid += 1

    # Node 12: FramePackSampler — vid2vid with initial_samples + denoise_strength
    sampler_node = str(nid)
    latent_window_size = 9
    workflow[sampler_node] = {
        "class_type": "FramePackSampler",
        "inputs": {
            "model": [model_node, 0],
            "positive": [pos_node, 0],
            "negative": [neg_node, 0],
            "start_latent": [vae_enc_frame_node, 0],
            "initial_samples": [vae_enc_video_node, 0],
            "image_embeds": [clip_vis_enc_node, 0],
            "denoise_strength": denoise_strength,
            "steps": steps,
            "use_teacache": True,
            "teacache_rel_l1_thresh": 0.15,
            "cfg": 1.0,
            "guidance_scale": guidance_scale,
            "shift": 0.0,
            "seed": seed,
            "latent_window_size": latent_window_size,
            "total_second_length": total_seconds,
            "gpu_memory_preservation": gpu_memory_preservation,
            "sampler": "unipc_bh1",
        },
    }
    nid += 1

    # Node 13: VAEDecodeTiled — decode refined latents
    decode_node = str(nid)
    workflow[decode_node] = {
        "class_type": "VAEDecodeTiled",
        "inputs": {
            "samples": [sampler_node, 0],
            "vae": [vae_node, 0],
            "tile_size": 256,
            "overlap": 64,
            "temporal_size": 64,
            "temporal_overlap": 8,
        },
    }
    nid += 1

    # Node 14: VHS_VideoCombine — output 30fps h264
    output_node = str(nid)
    workflow[output_node] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": [decode_node, 0],
            "frame_rate": 30,
            "loop_count": 0,
            "filename_prefix": prefix,
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True,
        },
    }

    return workflow, sampler_node, prefix


async def refine_wan_video(
    wan_video_path: str,
    prompt_text: str,
    negative_text: str = "low quality, blurry, distorted, watermark",
    denoise_strength: float = 0.4,
    total_seconds: float = 3.0,
    steps: int = 25,
    seed: int | None = None,
    guidance_scale: float = 6.0,
    gpu_memory_preservation: float = 6.0,
    lora_name: str | None = None,
    lora_strength: float = 0.8,
    output_prefix: str | None = None,
) -> str | None:
    """Run FramePack vid2vid refinement on a Wan output video.

    Returns the path to the refined video, or None on failure.
    """
    import urllib.request

    if not Path(wan_video_path).exists():
        logger.warning(f"V2V refine: source video not found: {wan_video_path}")
        return None

    workflow, sampler_node, prefix = build_framepack_v2v_workflow(
        video_path=wan_video_path,
        prompt_text=prompt_text,
        negative_text=negative_text,
        denoise_strength=denoise_strength,
        total_seconds=total_seconds,
        steps=steps,
        seed=seed,
        guidance_scale=guidance_scale,
        gpu_memory_preservation=gpu_memory_preservation,
        lora_name=lora_name,
        lora_strength=lora_strength,
        output_prefix=output_prefix,
    )

    # Submit to ComfyUI
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        prompt_id = result.get("prompt_id", "")
    except Exception as e:
        logger.warning(f"V2V refine: ComfyUI submission failed: {e}")
        return None

    if not prompt_id:
        logger.warning("V2V refine: no prompt_id returned")
        return None

    logger.info(f"V2V refine: submitted prompt_id={prompt_id}, prefix={prefix}")

    # Poll for completion (reuse same logic as builder.poll_comfyui_completion)
    timeout_seconds = 3600  # 60 min — long clips on RTX 3060 can take 40+ min
    start = time.time()
    while (time.time() - start) < timeout_seconds:
        try:
            hist_req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
            hist_resp = urllib.request.urlopen(hist_req, timeout=10)
            history = json.loads(hist_resp.read())
            if prompt_id in history:
                entry = history[prompt_id]
                status_info = entry.get("status", {})
                status_str = status_info.get("status_str", "unknown")
                if status_str == "error":
                    msgs = status_info.get("messages", [])
                    err = ""
                    for msg in msgs:
                        if isinstance(msg, list) and len(msg) >= 2 and "error" in str(msg[0]).lower():
                            err = str(msg[1])[:200]
                    logger.warning(f"V2V refine: ComfyUI error: {err or 'unknown'}")
                    return None
                # Extract output files
                outputs = entry.get("outputs", {})
                videos = []
                for node_output in outputs.values():
                    for key in ("videos", "gifs", "images"):
                        for item in node_output.get(key, []):
                            fn = item.get("filename")
                            if fn:
                                videos.append(fn)
                if videos:
                    refined_path = str(COMFYUI_OUTPUT_DIR / videos[0])
                    logger.info(f"V2V refine: completed → {videos[0]}")
                    return refined_path
                if status_str == "success":
                    # Fallback: scan output dir for prefix match
                    import glob as _glob
                    matches = _glob.glob(str(COMFYUI_OUTPUT_DIR / f"{prefix}*"))
                    mp4s = [f for f in matches if f.endswith((".mp4", ".webm"))]
                    if mp4s:
                        logger.info(f"V2V refine: found via prefix scan → {Path(mp4s[0]).name}")
                        return mp4s[0]
                    logger.warning("V2V refine: completed but no output files found")
                    return None
        except Exception:
            pass
        await asyncio.sleep(5)

    logger.warning(f"V2V refine: timed out after {timeout_seconds}s")
    return None
