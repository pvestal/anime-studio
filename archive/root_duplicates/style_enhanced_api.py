#!/usr/bin/env python3
"""
Style-Enhanced Anime API
Based on minimal_working_api.py with Patrick's learned style preferences
Integrates Echo Brain's creative guidance while keeping proven ComfyUI integration
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from enum import Enum
import requests
import json
import time
import uuid
import glob
import os
from typing import Optional, Dict, List

app = FastAPI(title="Style-Enhanced Anime API", version="1.0.0")

class StylePreset(str, Enum):
    """Patrick's learned style preferences"""
    DEFAULT = "default"
    PHOTOREALISTIC = "photorealistic"
    CARTOON = "cartoon"
    SOFT_LIGHTING = "soft_lighting"
    HIGH_CONTRAST = "high_contrast"
    ETHEREAL = "ethereal"
    DRAMATIC = "dramatic"

class Character(str, Enum):
    """Known characters Patrick works with"""
    KAI_NAKAMURA = "kai_nakamura"
    LIGHT_YAGAMI = "light_yagami"
    LELOUCH = "lelouch"
    EDWARD_ELRIC = "edward_elric"
    CUSTOM = "custom"

class GenerateRequest(BaseModel):
    prompt: str
    character: Optional[Character] = None
    style_preset: Optional[StylePreset] = StylePreset.DEFAULT
    negative_prompt: Optional[str] = None
    width: int = 768
    height: int = 768
    steps: int = 15

class GenerateResponse(BaseModel):
    success: bool
    job_id: str
    status: str
    enhanced_prompt: Optional[str] = None
    image_path: Optional[str] = None
    generation_time: Optional[float] = None
    style_applied: Optional[str] = None
    error: Optional[str] = None

# Patrick's learned style preferences
STYLE_PREFERENCES = {
    StylePreset.DEFAULT: {
        "prompt_suffix": ", anime, high quality, detailed, vibrant colors",
        "negative_additions": "blurry, low quality, multiple body parts, distorted, unrealistic proportions"
    },
    StylePreset.PHOTOREALISTIC: {
        "prompt_suffix": ", anime, photorealistic style, detailed shading, realistic proportions, professional lighting",
        "negative_additions": "cartoon, chibi, simplified, blurry, low quality, distorted"
    },
    StylePreset.CARTOON: {
        "prompt_suffix": ", anime, cartoon style, super-deformed, chibi, energetic lines, traditional anime",
        "negative_additions": "photorealistic, realistic, blurry, low quality, distorted"
    },
    StylePreset.SOFT_LIGHTING: {
        "prompt_suffix": ", anime, soft lighting, warm glow, gentle shadows, ambient occlusion, ethereal atmosphere",
        "negative_additions": "harsh lighting, high contrast, dark shadows, blurry, low quality"
    },
    StylePreset.HIGH_CONTRAST: {
        "prompt_suffix": ", anime, high contrast lighting, deep shadows, bright highlights, dramatic lighting, cinematic",
        "negative_additions": "flat lighting, soft shadows, blurry, low quality, washed out"
    },
    StylePreset.ETHEREAL: {
        "prompt_suffix": ", anime, ethereal lighting, misty atmosphere, soft golden light, dreamlike, magical glow",
        "negative_additions": "harsh, dark, realistic, blurry, low quality, mundane"
    },
    StylePreset.DRAMATIC: {
        "prompt_suffix": ", anime, dramatic composition, dynamic pose, cinematic angle, visual flow, balanced composition",
        "negative_additions": "static, boring composition, cluttered, blurry, low quality, unbalanced"
    }
}

# Character-specific prompts based on Patrick's preferences
CHARACTER_TEMPLATES = {
    Character.KAI_NAKAMURA: {
        "base_description": "Kai Nakamura, young anime male character",
        "visual_traits": "spiky dark hair, determined expression, athletic build",
        "personality_hints": "confident pose, slight smirk, intense gaze"
    },
    Character.LIGHT_YAGAMI: {
        "base_description": "Light Yagami from Death Note",
        "visual_traits": "tall, slender, black hair, brown eyes, intelligent appearance",
        "personality_hints": "calculating expression, school uniform or formal attire"
    },
    Character.LELOUCH: {
        "base_description": "Lelouch vi Britannia from Code Geass",
        "visual_traits": "tall, dark hair, blue eyes, aristocratic appearance",
        "personality_hints": "commanding presence, dramatic pose, royal attire"
    },
    Character.EDWARD_ELRIC: {
        "base_description": "Edward Elric from Fullmetal Alchemist",
        "visual_traits": "short blonde hair, brown eyes, automail arm",
        "personality_hints": "determined expression, alchemy pose, red coat"
    }
}

# Available models (REAL ones, verified working)
AVAILABLE_MODELS = [
    "Counterfeit-V2.5.safetensors",
    "counterfeit_v3.safetensors",
    "juggernautXL_v9.safetensors"
]

def enhance_prompt_with_style(base_prompt: str, character: Optional[Character], style_preset: StylePreset) -> tuple[str, str]:
    """
    Enhance prompt with Patrick's learned preferences
    Returns: (enhanced_prompt, style_description)
    """
    enhanced_prompt = base_prompt
    style_applied = []

    # Add character-specific details if specified
    if character and character != Character.CUSTOM:
        char_info = CHARACTER_TEMPLATES.get(character, {})
        if char_info:
            enhanced_prompt = f"{char_info['base_description']}, {char_info['visual_traits']}, {char_info['personality_hints']}, {enhanced_prompt}"
            style_applied.append(f"Character: {character.value}")

    # Apply style preferences
    style_config = STYLE_PREFERENCES.get(style_preset, STYLE_PREFERENCES[StylePreset.DEFAULT])
    enhanced_prompt += style_config["prompt_suffix"]
    style_applied.append(f"Style: {style_preset.value}")

    return enhanced_prompt, " | ".join(style_applied)

def create_enhanced_negative_prompt(base_negative: Optional[str], style_preset: StylePreset) -> str:
    """Create comprehensive negative prompt based on Patrick's preferences"""
    style_config = STYLE_PREFERENCES.get(style_preset, STYLE_PREFERENCES[StylePreset.DEFAULT])

    negative_parts = []
    if base_negative:
        negative_parts.append(base_negative)

    negative_parts.append(style_config["negative_additions"])

    return ", ".join(negative_parts)

def create_comfyui_workflow(prompt: str, negative_prompt: str, width: int, height: int, steps: int) -> dict:
    """Create ComfyUI workflow with REAL available models"""
    return {
        "1": {
            "inputs": {"ckpt_name": AVAILABLE_MODELS[0]},  # Use verified model
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {
                "text": prompt,
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "5": {
            "inputs": {
                "seed": int(time.time()),
                "steps": steps,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0]
            },
            "class_type": "KSampler"
        },
        "6": {
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            "class_type": "VAEDecode"
        },
        "7": {
            "inputs": {
                "images": ["6", 0],
                "filename_prefix": f"style_enhanced_{int(time.time())}"
            },
            "class_type": "SaveImage"
        }
    }

@app.post("/generate", response_model=GenerateResponse)
async def generate_image(request: GenerateRequest):
    """Generate anime image with Patrick's learned style preferences"""

    client_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        # Enhance prompt with Patrick's preferences
        enhanced_prompt, style_applied = enhance_prompt_with_style(
            request.prompt,
            request.character,
            request.style_preset
        )

        # Create comprehensive negative prompt
        enhanced_negative = create_enhanced_negative_prompt(
            request.negative_prompt,
            request.style_preset
        )

        # Create workflow with enhanced prompts
        workflow = create_comfyui_workflow(
            enhanced_prompt,
            enhanced_negative,
            request.width,
            request.height,
            request.steps
        )

        # Submit to ComfyUI (proven working approach)
        response = requests.post(
            "http://localhost:8188/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=10
        )

        if response.status_code != 200:
            return GenerateResponse(
                success=False,
                job_id=client_id,
                status="failed",
                enhanced_prompt=enhanced_prompt,
                style_applied=style_applied,
                error=f"ComfyUI submission failed: {response.text}"
            )

        result = response.json()
        prompt_id = result.get("prompt_id")

        # Wait for completion with realistic timeout
        timeout = 60  # 1 minute max
        check_interval = 2

        for attempt in range(timeout // check_interval):
            time.sleep(check_interval)

            # Check ComfyUI history
            history_response = requests.get(f"http://localhost:8188/history/{prompt_id}")

            if history_response.status_code == 200:
                history = history_response.json()

                if prompt_id in history:
                    job_info = history[prompt_id]
                    status = job_info.get("status", {})

                    if status.get("status_str") == "success":
                        generation_time = time.time() - start_time

                        # Find output file
                        output_files = glob.glob(f"/mnt/1TB-storage/ComfyUI/output/style_enhanced_{int(start_time)}_*.png")

                        if output_files:
                            image_path = max(output_files, key=os.path.getctime)

                            return GenerateResponse(
                                success=True,
                                job_id=client_id,
                                status="completed",
                                enhanced_prompt=enhanced_prompt,
                                image_path=image_path,
                                generation_time=generation_time,
                                style_applied=style_applied
                            )
                        else:
                            return GenerateResponse(
                                success=False,
                                job_id=client_id,
                                status="failed",
                                enhanced_prompt=enhanced_prompt,
                                style_applied=style_applied,
                                error="Generation completed but no output file found"
                            )

                    elif "error" in status:
                        return GenerateResponse(
                            success=False,
                            job_id=client_id,
                            status="failed",
                            enhanced_prompt=enhanced_prompt,
                            style_applied=style_applied,
                            error=str(status.get("error"))
                        )

        # Timeout
        return GenerateResponse(
            success=False,
            job_id=client_id,
            status="timeout",
            enhanced_prompt=enhanced_prompt,
            style_applied=style_applied,
            error="Generation timed out after 60 seconds"
        )

    except Exception as e:
        return GenerateResponse(
            success=False,
            job_id=client_id,
            status="error",
            enhanced_prompt=enhanced_prompt if 'enhanced_prompt' in locals() else request.prompt,
            style_applied=style_applied if 'style_applied' in locals() else "None",
            error=str(e)
        )

@app.get("/styles")
async def list_styles():
    """List available style presets"""
    return {
        "styles": [style.value for style in StylePreset],
        "style_descriptions": {
            StylePreset.DEFAULT.value: "Patrick's general anime preferences",
            StylePreset.PHOTOREALISTIC.value: "Detailed, realistic anime style",
            StylePreset.CARTOON.value: "Traditional cartoon anime style",
            StylePreset.SOFT_LIGHTING.value: "Gentle, warm lighting",
            StylePreset.HIGH_CONTRAST.value: "Dramatic lighting with deep shadows",
            StylePreset.ETHEREAL.value: "Misty, magical atmosphere",
            StylePreset.DRAMATIC.value: "Dynamic composition and poses"
        }
    }

@app.get("/characters")
async def list_characters():
    """List available character presets"""
    return {
        "characters": [char.value for char in Character],
        "character_descriptions": {char.value: info["base_description"] for char, info in CHARACTER_TEMPLATES.items()}
    }

@app.post("/preview-prompt")
async def preview_enhanced_prompt(request: GenerateRequest):
    """Preview how prompt will be enhanced without generating"""
    enhanced_prompt, style_applied = enhance_prompt_with_style(
        request.prompt,
        request.character,
        request.style_preset
    )

    enhanced_negative = create_enhanced_negative_prompt(
        request.negative_prompt,
        request.style_preset
    )

    return {
        "original_prompt": request.prompt,
        "enhanced_prompt": enhanced_prompt,
        "original_negative": request.negative_prompt or "None",
        "enhanced_negative": enhanced_negative,
        "style_applied": style_applied,
        "character": request.character.value if request.character else "None"
    }

@app.get("/health")
async def health_check():
    """Health check with ComfyUI verification and style system status"""
    try:
        response = requests.get("http://localhost:8188/system_stats", timeout=5)
        comfyui_working = response.status_code == 200

        return {
            "status": "healthy" if comfyui_working else "degraded",
            "comfyui_connected": comfyui_working,
            "available_models": AVAILABLE_MODELS,
            "style_system": "loaded",
            "available_styles": len(STYLE_PREFERENCES),
            "available_characters": len(CHARACTER_TEMPLATES)
        }
    except:
        return {
            "status": "unhealthy",
            "comfyui_connected": False,
            "style_system": "loaded",
            "error": "Cannot connect to ComfyUI"
        }

@app.get("/models")
async def list_models():
    """List REAL available models"""
    return {"models": AVAILABLE_MODELS}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Style-Enhanced Anime API")
    print("✅ Patrick's learned preferences integrated")
    print("✅ Based on proven ComfyUI integration")
    print("✅ Characters: Kai Nakamura, Light Yagami, Lelouch, Edward Elric")
    print("✅ Styles: Photorealistic, Cartoon, Soft Lighting, High Contrast, Ethereal, Dramatic")
    uvicorn.run(app, host="0.0.0.0", port=8332)