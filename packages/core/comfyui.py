"""Shared ComfyUI workflow builders — IP-Adapter, txt2img, etc."""


def build_txt2img_workflow(
    prompt_text: str,
    negative_text: str,
    checkpoint: str,
    seed: int,
    steps: int,
    cfg: float,
    width: int,
    height: int,
    filename_prefix: str,
    sampler_name: str = "euler_ancestral",
    scheduler: str = "normal",
) -> dict:
    """Build pure txt2img workflow — no IP-Adapter, no reference image.

    Best for multi-character explicit scenes where IP-Adapter would
    anchor to a single character and kill the second person.
    """
    return {
        "1": {
            "inputs": {"text": prompt_text, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "2": {
            "inputs": {"text": negative_text, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "3": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
        },
        "4": {
            "inputs": {"ckpt_name": checkpoint},
            "class_type": "CheckpointLoaderSimple",
        },
        "5": {
            "inputs": {"width": width, "height": height, "batch_size": 1},
            "class_type": "EmptyLatentImage",
        },
        "6": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode",
        },
        "7": {
            "inputs": {"filename_prefix": filename_prefix, "images": ["6", 0]},
            "class_type": "SaveImage",
        },
    }


def build_ipadapter_workflow(
    prompt_text: str,
    negative_text: str,
    checkpoint: str,
    ref_image_name: str,
    seed: int,
    steps: int,
    cfg: float,
    denoise: float,
    weight: float,
    width: int,
    height: int,
    filename_prefix: str,
    sampler_name: str = "dpmpp_2m",
    scheduler: str = "karras",
    use_img2img: bool = True,
) -> dict:
    """Build IPAdapter workflow using ComfyUI-IPAdapter-Plus nodes.

    Used by both /refine (ingest_router) and /variant (training_router).

    Args:
        use_img2img: If True, uses VAEEncode of ref image as latent (img2img).
                     If False, uses EmptyLatentImage (txt2img) with IPA for
                     identity guidance only. False is better for multi-char.
    """
    workflow = {
        "1": {
            "inputs": {"text": prompt_text, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "2": {
            "inputs": {"text": negative_text, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "4": {
            "inputs": {"ckpt_name": checkpoint},
            "class_type": "CheckpointLoaderSimple",
        },
        "6": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode",
        },
        "7": {
            "inputs": {"filename_prefix": filename_prefix, "images": ["6", 0]},
            "class_type": "SaveImage",
        },
        # Load reference image for IP-Adapter
        "9": {
            "inputs": {"image": ref_image_name},
            "class_type": "LoadImage",
        },
        # IP-Adapter: identity guidance from reference
        "10": {
            "inputs": {
                "weight": weight,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0.0,
                "end_at": 0.85,
                "embeds_scaling": "K+V",
                "unfold_batch": False,
                "model": ["11", 0],
                "ipadapter": ["11", 1],
                "image": ["9", 0],
            },
            "class_type": "IPAdapterAdvanced",
        },
        "11": {
            "inputs": {
                "model": ["4", 0],
                "preset": "PLUS (high strength)",
            },
            "class_type": "IPAdapterUnifiedLoader",
        },
    }

    if use_img2img:
        # img2img: encode reference as latent starting point
        workflow["8"] = {
            "inputs": {"pixels": ["9", 0], "vae": ["4", 2]},
            "class_type": "VAEEncode",
        }
        latent_source = ["8", 0]
    else:
        # txt2img: empty latent, IPA for identity only
        workflow["8"] = {
            "inputs": {"width": width, "height": height, "batch_size": 1},
            "class_type": "EmptyLatentImage",
        }
        latent_source = ["8", 0]

    workflow["3"] = {
        "inputs": {
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler_name,
            "scheduler": scheduler,
            "denoise": denoise,
            "model": ["10", 0],
            "positive": ["1", 0],
            "negative": ["2", 0],
            "latent_image": latent_source,
        },
        "class_type": "KSampler",
    }

    return workflow
