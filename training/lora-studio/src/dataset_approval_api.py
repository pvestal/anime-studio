#!/usr/bin/env python3
"""
LoRA Studio - Dataset Approval & Training API
Human-in-the-loop quality control for training datasets.

Routes are served under /api/lora/* to match the Vue frontend client.
Database credentials loaded from Vault (secret/anime/database).
"""

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import asyncpg
import asyncio
import os
import subprocess
from pathlib import Path
import json
import shutil
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tower LoRA Studio", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Vault Integration ---

def _load_db_config() -> dict:
    """Load database config from Vault, falling back to env vars."""
    vault_addr = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
    vault_token = os.getenv("VAULT_TOKEN")

    if not vault_token:
        token_file = os.path.expanduser("~/.vault-token")
        if os.path.exists(token_file):
            with open(token_file) as f:
                vault_token = f.read().strip()

    if vault_token:
        try:
            import hvac
            client = hvac.Client(url=vault_addr, token=vault_token)
            if client.is_authenticated():
                response = client.secrets.kv.v2.read_secret_version(
                    path="anime/database", mount_point="secret",
                    raise_on_deleted_version=True,
                )
                data = response["data"]["data"]
                logger.info("Loaded database credentials from Vault: anime/database")
                return {
                    "host": data.get("host", "localhost"),
                    "database": data.get("database", "anime_production"),
                    "user": data.get("user", "patrick"),
                    "password": data["password"],
                }
        except Exception as e:
            logger.warning(f"Vault unavailable ({e}), falling back to env vars")

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "database": os.getenv("DB_NAME", "anime_production"),
        "user": os.getenv("DB_USER", "patrick"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


DB_CONFIG = _load_db_config()

# Resolve paths relative to this file's location
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parent
BASE_PATH = _PROJECT_DIR / "datasets"

# Cache for character→project mapping from DB
_char_project_cache = {}
_cache_time = 0


async def _get_char_project_map() -> dict:
    """Load character→project mapping from DB with generation style info. Cached for 60s."""
    global _char_project_cache, _cache_time
    import time as _time
    if _char_project_cache and (_time.time() - _cache_time) < 60:
        return _char_project_cache

    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG["host"], database=DB_CONFIG["database"],
            user=DB_CONFIG["user"], password=DB_CONFIG["password"],
        )
        rows = await conn.fetch("""
            SELECT c.name,
                   REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug,
                   c.design_prompt, p.name as project_name,
                   p.default_style,
                   gs.checkpoint_model, gs.cfg_scale, gs.steps,
                   gs.width, gs.height, gs.sampler, gs.scheduler
            FROM characters c
            JOIN projects p ON c.project_id = p.id
            LEFT JOIN generation_styles gs ON gs.style_name = p.default_style
        """)
        await conn.close()

        mapping = {}
        for row in rows:
            slug = row["slug"]
            if slug not in mapping or len(row["design_prompt"] or "") > len(mapping[slug].get("design_prompt") or ""):
                mapping[slug] = {
                    "name": row["name"],
                    "slug": slug,
                    "project_name": row["project_name"],
                    "design_prompt": row["design_prompt"],
                    "default_style": row["default_style"],
                    "checkpoint_model": row["checkpoint_model"],
                    "cfg_scale": float(row["cfg_scale"]) if row["cfg_scale"] else None,
                    "steps": row["steps"],
                    "sampler": row["sampler"],
                    "scheduler": row["scheduler"],
                    "width": row["width"],
                    "height": row["height"],
                    "resolution": f"{row['width']}x{row['height']}" if row["width"] else None,
                }
        _char_project_cache = mapping
        _cache_time = _time.time()
    except Exception as e:
        logger.warning(f"Failed to load char→project map: {e}")

    return _char_project_cache

# --- Models ---

class ImageApproval(BaseModel):
    character_name: str
    image_name: str
    approved: bool
    feedback: Optional[str] = None
    edited_prompt: Optional[str] = None

class ApprovalRequest(BaseModel):
    character_name: str
    character_slug: Optional[str] = None
    image_name: str
    approved: bool
    feedback: Optional[str] = None
    edited_prompt: Optional[str] = None

class CharacterCreate(BaseModel):
    name: str
    description: Optional[str] = None
    reference_images: Optional[List[str]] = None

class DatasetImageCreate(BaseModel):
    source_url: Optional[str] = None
    prompt: Optional[str] = None
    tags: Optional[List[str]] = None

class TrainingRequest(BaseModel):
    character_name: str
    epochs: Optional[int] = 20
    learning_rate: Optional[float] = 1e-4
    resolution: Optional[int] = 512

class DatasetStatus(BaseModel):
    character_name: str
    total_images: int
    approved_images: int
    pending_images: int
    rejected_images: int

class GenerateRequest(BaseModel):
    generation_type: str = "image"  # "image" or "video"
    prompt_override: Optional[str] = None
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None

class EchoChatRequest(BaseModel):
    message: str
    character_slug: Optional[str] = None

class EchoEnhanceRequest(BaseModel):
    prompt: str
    character_slug: Optional[str] = None

# --- ComfyUI Generation Pipeline ---

COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_OUTPUT_DIR = Path("/opt/ComfyUI/output")


_SAMPLER_MAP = {
    "DPM++ 2M Karras": ("dpmpp_2m", "karras"),
    "DPM++ 2M SDE Karras": ("dpmpp_2m_sde", "karras"),
    "DPM++ 2S a Karras": ("dpmpp_2s_ancestral", "karras"),
    "DPM++ SDE Karras": ("dpmpp_sde", "karras"),
    "DPM++ 2M": ("dpmpp_2m", "normal"),
    "Euler a": ("euler_ancestral", "normal"),
    "Euler": ("euler", "normal"),
    "DDIM": ("ddim", "ddim_uniform"),
}


def _normalize_sampler(sampler: str | None, scheduler: str | None) -> tuple[str, str]:
    """Convert human-readable sampler names to ComfyUI internal names."""
    if sampler and sampler in _SAMPLER_MAP:
        return _SAMPLER_MAP[sampler]
    return (sampler or "dpmpp_2m", scheduler or "karras")


def _build_comfyui_workflow(
    design_prompt: str,
    checkpoint_model: str,
    cfg_scale: float = 7.0,
    steps: int = 25,
    sampler: str = "dpmpp_2m",
    scheduler: str = "karras",
    width: int = 512,
    height: int = 768,
    negative_prompt: str = "worst quality, low quality, blurry, deformed",
    generation_type: str = "image",
    seed: int | None = None,
    character_slug: str = "output",
) -> dict:
    """Build a ComfyUI workflow dict for image or video generation."""
    import random as _random
    if seed is None:
        seed = _random.randint(1, 2**31)

    batch_size = 1
    if generation_type == "video":
        batch_size = 16
        width = min(width, 512)
        height = min(height, 512)

    workflow = {
        "3": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg_scale,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
        },
        "4": {
            "inputs": {"ckpt_name": checkpoint_model},
            "class_type": "CheckpointLoaderSimple",
        },
        "5": {
            "inputs": {"width": width, "height": height, "batch_size": batch_size},
            "class_type": "EmptyLatentImage",
        },
        "6": {
            "inputs": {"text": design_prompt, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "7": {
            "inputs": {"text": negative_prompt, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "8": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode",
        },
    }

    import time as _time
    ts = int(_time.time())
    prefix = f"lora_{character_slug}_{ts}"

    if generation_type == "video":
        workflow["9"] = {
            "inputs": {
                "frame_rate": 8,
                "loop_count": 0,
                "filename_prefix": prefix,
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "images": ["8", 0],
            },
            "class_type": "VHS_VideoCombine",
        }
    else:
        workflow["9"] = {
            "inputs": {"filename_prefix": prefix, "images": ["8", 0]},
            "class_type": "SaveImage",
        }

    return workflow


def _submit_comfyui_workflow(workflow: dict) -> str:
    """Submit a workflow to ComfyUI and return the prompt_id."""
    import urllib.request
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    return result.get("prompt_id", "")


def _get_comfyui_progress(prompt_id: str) -> dict:
    """Check ComfyUI generation progress for a given prompt_id."""
    import urllib.request
    try:
        req = urllib.request.Request(f"{COMFYUI_URL}/queue")
        resp = urllib.request.urlopen(req, timeout=10)
        queue_data = json.loads(resp.read())

        for job in queue_data.get("queue_running", []):
            if prompt_id in str(job):
                return {"status": "running", "progress": 0.5}

        for job in queue_data.get("queue_pending", []):
            if prompt_id in str(job):
                return {"status": "pending", "progress": 0.1}

        # Check history for completion
        req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
        resp = urllib.request.urlopen(req, timeout=10)
        history = json.loads(resp.read())

        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            images = []
            for node_output in outputs.values():
                images.extend(node_output.get("images", []))
            return {
                "status": "completed",
                "progress": 1.0,
                "images": [img.get("filename") for img in images],
            }

        return {"status": "unknown", "progress": 0.0}
    except Exception as e:
        logger.warning(f"ComfyUI progress check failed: {e}")
        return {"status": "error", "progress": 0.0, "error": str(e)}


# --- Training job storage (file-based until DB wiring is needed) ---

TRAINING_JOBS_FILE = BASE_PATH.parent / "training_jobs.json"

def _load_training_jobs() -> list:
    if TRAINING_JOBS_FILE.exists():
        with open(TRAINING_JOBS_FILE) as f:
            return json.load(f)
    return []

def _save_training_jobs(jobs: list):
    TRAINING_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRAINING_JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)


# ===================================================================
# Routes under /api/lora/* (matching frontend client.ts expectations)
# ===================================================================

@app.get("/api/lora/characters")
async def get_characters():
    """Get list of characters with datasets, including project info from DB.

    Only returns characters that exist in the DB with a project association.
    Dataset directories without a DB match are excluded.
    """
    char_map = await _get_char_project_map()
    characters = []

    for slug, db_info in sorted(char_map.items(), key=lambda x: x[0]):
        # Skip characters without a design_prompt (nothing to generate)
        if not db_info.get("design_prompt"):
            continue

        images_dir = BASE_PATH / slug / "images"
        image_count = len(list(images_dir.glob("*.png"))) if images_dir.exists() else 0

        char = {
            "name": db_info["name"],
            "slug": slug,
            "image_count": image_count,
            "created_at": datetime.fromtimestamp(images_dir.parent.stat().st_ctime).isoformat() if images_dir.exists() else datetime.now().isoformat(),
            "project_name": db_info.get("project_name", ""),
            "design_prompt": db_info.get("design_prompt", ""),
            "default_style": db_info.get("default_style", ""),
            "checkpoint_model": db_info.get("checkpoint_model", ""),
            "cfg_scale": db_info.get("cfg_scale"),
            "steps": db_info.get("steps"),
            "resolution": db_info.get("resolution", ""),
        }
        characters.append(char)
    return {"characters": characters}


@app.post("/api/lora/characters")
async def create_character(character: CharacterCreate):
    """Create a new character dataset directory."""
    safe_name = character.name.lower().replace(" ", "_")
    char_path = BASE_PATH / safe_name
    images_path = char_path / "images"

    if char_path.exists():
        raise HTTPException(status_code=409, detail="Character already exists")

    images_path.mkdir(parents=True, exist_ok=True)

    # Save character metadata
    meta = {
        "name": character.name,
        "description": character.description or "",
        "reference_images": character.reference_images or [],
        "created_at": datetime.now().isoformat(),
    }
    with open(char_path / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)

    return {"message": f"Character '{character.name}' created", "slug": safe_name}


@app.patch("/api/lora/characters/{character_slug}")
async def update_character(character_slug: str, body: dict):
    """Update a character's design_prompt (and optionally other fields)."""
    global _char_project_cache, _cache_time

    design_prompt = body.get("design_prompt")
    if design_prompt is None:
        raise HTTPException(status_code=400, detail="design_prompt is required")

    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG["host"], database=DB_CONFIG["database"],
            user=DB_CONFIG["user"], password=DB_CONFIG["password"],
        )

        # Find the character by slug
        row = await conn.fetchrow("""
            SELECT c.id, c.name, c.project_id
            FROM characters c
            WHERE REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1
              AND c.project_id IS NOT NULL
            ORDER BY LENGTH(COALESCE(c.design_prompt, '')) DESC
            LIMIT 1
        """, character_slug)

        if not row:
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")

        await conn.execute(
            "UPDATE characters SET design_prompt = $1 WHERE id = $2",
            design_prompt.strip(), row["id"],
        )
        await conn.close()

        # Invalidate cache
        _char_project_cache = {}
        _cache_time = 0

        logger.info(f"Updated design_prompt for {row['name']} (id={row['id']})")
        return {
            "message": f"Updated design_prompt for {row['name']}",
            "character_id": row["id"],
            "character_name": row["name"],
            "design_prompt": design_prompt.strip(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update character {character_slug}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/lora/dataset/{character_name}")
async def get_dataset_info(character_name: str):
    """Get dataset images and approval status."""
    safe_name = character_name.lower().replace(" ", "_")
    dataset_path = BASE_PATH / safe_name
    images_path = dataset_path / "images"

    if not images_path.exists():
        raise HTTPException(status_code=404, detail="Dataset not found")

    approval_file = dataset_path / "approval_status.json"
    approval_status = {}
    if approval_file.exists():
        with open(approval_file) as f:
            approval_status = json.load(f)

    images = []
    for img in sorted(images_path.glob("*.png")):
        status = approval_status.get(img.name, "pending")
        # Try to load caption/prompt from .txt sidecar
        caption_file = img.with_suffix(".txt")
        prompt = ""
        if caption_file.exists():
            prompt = caption_file.read_text().strip()
        images.append({
            "id": img.name,
            "name": img.name,
            "status": status,
            "prompt": prompt,
            "created_at": datetime.fromtimestamp(img.stat().st_ctime).isoformat(),
        })

    return {"character": character_name, "images": images}


@app.post("/api/lora/dataset/{character_name}/images")
async def add_dataset_image(character_name: str, image: DatasetImageCreate):
    """Add an image entry to a character's dataset."""
    safe_name = character_name.lower().replace(" ", "_")
    dataset_path = BASE_PATH / safe_name / "images"

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="Character dataset not found")

    image_id = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return {"message": "Image entry created", "image_id": image_id}


@app.get("/api/lora/dataset/{character_name}/image/{image_name}")
async def get_image(character_name: str, image_name: str):
    """Serve an image file."""
    safe_name = character_name.lower().replace(" ", "_")
    image_path = BASE_PATH / safe_name / "images" / image_name

    if not image_path.exists():
        placeholder = _PROJECT_DIR / "static" / "placeholder.png"
        if placeholder.exists():
            return FileResponse(placeholder)
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(image_path)


@app.get("/api/lora/dataset/{character_name}/image/{image_name}/metadata")
async def get_image_metadata(character_name: str, image_name: str):
    """Get generation metadata for a specific image."""
    safe_name = character_name.lower().replace(" ", "_")
    image_path = BASE_PATH / safe_name / "images" / image_name
    meta_path = image_path.with_suffix(".meta.json")

    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    if meta_path.exists():
        with open(meta_path) as f:
            return json.load(f)

    # Fallback: partial metadata from .txt sidecar + project info
    char_map = await _get_char_project_map()
    db_info = char_map.get(safe_name, {})
    caption_file = image_path.with_suffix(".txt")
    return {
        "seed": None,
        "design_prompt": db_info.get("design_prompt", ""),
        "full_prompt": caption_file.read_text().strip() if caption_file.exists() else "",
        "checkpoint_model": db_info.get("checkpoint_model", ""),
        "cfg_scale": db_info.get("cfg_scale"),
        "steps": db_info.get("steps"),
        "source": "backfill_partial",
        "backfilled": True,
    }


@app.get("/api/lora/approval/pending")
async def get_pending_approvals():
    """Get all pending images across all characters, with project info.

    Only returns images from dataset dirs that have a matching DB character.
    """
    pending = []
    if not BASE_PATH.exists():
        return {"pending_images": pending}

    char_map = await _get_char_project_map()

    for char_dir in sorted(BASE_PATH.iterdir()):
        if not char_dir.is_dir():
            continue
        images_path = char_dir / "images"
        if not images_path.exists():
            continue

        db_info = char_map.get(char_dir.name)
        if not db_info:
            # No DB match — skip this directory entirely
            continue

        approval_file = char_dir / "approval_status.json"
        approval_status = {}
        if approval_file.exists():
            with open(approval_file) as f:
                approval_status = json.load(f)

        for img in sorted(images_path.glob("*.png")):
            status = approval_status.get(img.name, "pending")
            if status == "pending":
                # Load caption/prompt from .txt sidecar
                caption_file = img.with_suffix(".txt")
                prompt = ""
                if caption_file.exists():
                    prompt = caption_file.read_text().strip()

                # Load generation metadata from .meta.json sidecar
                meta_path = img.with_suffix(".meta.json")
                metadata = None
                if meta_path.exists():
                    try:
                        with open(meta_path) as f:
                            metadata = json.load(f)
                    except (json.JSONDecodeError, IOError):
                        pass

                entry = {
                    "id": img.name,
                    "character_name": db_info["name"],
                    "character_slug": char_dir.name,
                    "name": img.name,
                    "prompt": prompt,
                    "project_name": db_info.get("project_name", ""),
                    "design_prompt": db_info.get("design_prompt", ""),
                    "checkpoint_model": db_info.get("checkpoint_model", ""),
                    "default_style": db_info.get("default_style", ""),
                    "status": "pending",
                    "created_at": datetime.fromtimestamp(img.stat().st_ctime).isoformat(),
                }
                if metadata:
                    entry["metadata"] = metadata
                pending.append(entry)

    return {"pending_images": pending}


@app.post("/api/lora/approval/approve")
async def approve_image(approval: ApprovalRequest):
    """Approve or reject an image.

    Uses character_slug (preferred) or falls back to character_name for dir lookup.
    If edited_prompt is provided, updates the .txt sidecar for that image.
    """
    # Use slug if provided, otherwise sanitize name
    if approval.character_slug:
        safe_name = approval.character_slug
    else:
        import re
        safe_name = re.sub(r'[^a-z0-9_-]', '', approval.character_name.lower().replace(' ', '_'))

    dataset_path = BASE_PATH / safe_name
    approval_file = dataset_path / "approval_status.json"

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"Character dataset not found: {safe_name}")

    approval_status = {}
    if approval_file.exists():
        with open(approval_file) as f:
            approval_status = json.load(f)

    approval_status[approval.image_name] = "approved" if approval.approved else "rejected"

    with open(approval_file, "w") as f:
        json.dump(approval_status, f, indent=2)

    # If user provided an edited prompt, update BOTH the .txt sidecar AND the DB design_prompt (SSOT)
    prompt_updated = False
    if approval.edited_prompt:
        image_path = dataset_path / "images" / approval.image_name
        caption_path = image_path.with_suffix(".txt")
        caption_path.write_text(approval.edited_prompt)

        # Update the DB design_prompt so future generations use the refined prompt
        try:
            conn = await asyncpg.connect(
                host=DB_CONFIG["host"], database=DB_CONFIG["database"],
                user=DB_CONFIG["user"], password=DB_CONFIG["password"],
            )
            row = await conn.fetchrow("""
                SELECT c.id, c.name, c.design_prompt
                FROM characters c
                WHERE REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1
                  AND c.project_id IS NOT NULL
                ORDER BY LENGTH(COALESCE(c.design_prompt, '')) DESC
                LIMIT 1
            """, safe_name)
            if row:
                old_prompt = row["design_prompt"] or ""
                new_prompt = approval.edited_prompt.strip()
                if new_prompt != old_prompt:
                    await conn.execute(
                        "UPDATE characters SET design_prompt = $1 WHERE id = $2",
                        new_prompt, row["id"],
                    )
                    prompt_updated = True
                    logger.info(f"SSOT updated: {row['name']} design_prompt changed ({len(old_prompt)} → {len(new_prompt)} chars)")
                    # Invalidate the char→project cache so next generation picks up the change
                    global _char_project_cache, _cache_time
                    _char_project_cache = {}
                    _cache_time = 0
            await conn.close()
        except Exception as e:
            logger.warning(f"Failed to update DB design_prompt for {safe_name}: {e}")

    if approval.feedback:
        feedback_file = dataset_path / "feedback.log"
        with open(feedback_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} - {approval.image_name}: {approval.feedback}\n")

    # Store structured rejection data for feedback loop
    if not approval.approved:
        _record_rejection(safe_name, approval.image_name, approval.feedback or "Rejected", approval.edited_prompt)

    # Queue regeneration on both approval and rejection:
    # - Rejection: replacement with feedback-aware negatives
    # - Approval: more of what's working (still need 10 approved total)
    regenerated = False
    try:
        _queue_regeneration(safe_name)
        regenerated = True
    except Exception as e:
        logger.warning(f"Regeneration queue failed for {safe_name}: {e}")

    return {
        "message": f"Image {approval.image_name} {'approved' if approval.approved else 'rejected'}",
        "regeneration_queued": regenerated,
        "design_prompt_updated": prompt_updated,
    }


def _open_gen_log():
    """Open a log file for generation subprocess output."""
    log_dir = BASE_PATH.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "generation.log"
    return open(log_file, "a")


# --- Feedback Loop ---

# Standard rejection reason categories that map to negative prompt terms
REJECTION_NEGATIVE_MAP = {
    "wrong_appearance": "wrong colors, inaccurate character design, wrong outfit",
    "wrong_style": "wrong art style, inconsistent style",
    "bad_quality": "blurry, low quality, artifacts, distorted",
    "not_solo": "multiple characters, crowd, group shot",
    "wrong_pose": "awkward pose, unnatural position",
    "wrong_expression": "wrong facial expression, out of character",
}


def _record_rejection(character_slug: str, image_name: str, feedback: str, edited_prompt: str = None):
    """Record structured rejection data for the feedback loop."""
    dataset_path = BASE_PATH / character_slug
    feedback_json = dataset_path / "feedback.json"

    data = {"rejections": [], "rejection_count": 0, "negative_additions": []}
    if feedback_json.exists():
        try:
            data = json.loads(feedback_json.read_text())
        except (json.JSONDecodeError, IOError):
            pass

    entry = {
        "image": image_name,
        "feedback": feedback,
        "edited_prompt": edited_prompt,
        "timestamp": datetime.now().isoformat(),
    }

    # Parse structured categories from feedback (format: "category:reason" or free text)
    categories = []
    if "|" in feedback:
        # Structured format: "wrong_appearance|bad_quality|Free text note"
        parts = feedback.split("|")
        for part in parts:
            part = part.strip()
            if part in REJECTION_NEGATIVE_MAP:
                categories.append(part)
        entry["categories"] = categories

    data["rejections"].append(entry)
    data["rejection_count"] = len(data["rejections"])

    # Build cumulative negative prompt additions from rejection categories
    neg_terms = set()
    for rej in data["rejections"]:
        for cat in rej.get("categories", []):
            if cat in REJECTION_NEGATIVE_MAP:
                neg_terms.add(REJECTION_NEGATIVE_MAP[cat])
    data["negative_additions"] = list(neg_terms)

    # Keep only last 50 rejections to prevent unbounded growth
    if len(data["rejections"]) > 50:
        data["rejections"] = data["rejections"][-50:]

    feedback_json.write_text(json.dumps(data, indent=2))


def _get_feedback_negatives(character_slug: str) -> str:
    """Read rejection feedback and return additional negative prompt terms."""
    feedback_json = BASE_PATH / character_slug / "feedback.json"
    if not feedback_json.exists():
        return ""
    try:
        data = json.loads(feedback_json.read_text())
        additions = data.get("negative_additions", [])
        return ", ".join(additions) if additions else ""
    except (json.JSONDecodeError, IOError):
        return ""


def _maybe_refine_prompt_via_echo_brain(character_slug: str) -> str | None:
    """After enough rejections, ask Echo Brain to suggest a better design_prompt.

    Returns the suggested prompt if Echo Brain has a recommendation, or None.
    Only triggers after 5+ structured rejections to avoid noise.
    """
    feedback_json = BASE_PATH / character_slug / "feedback.json"
    if not feedback_json.exists():
        return None

    try:
        data = json.loads(feedback_json.read_text())
    except (json.JSONDecodeError, IOError):
        return None

    rejections = data.get("rejections", [])
    structured = [r for r in rejections if r.get("categories")]
    if len(structured) < 3:
        return None  # Not enough structured data to justify a refinement

    # Check if we already suggested recently (within last 10 rejections)
    last_suggestion = data.get("last_echo_brain_suggestion_at_count", 0)
    if data["rejection_count"] - last_suggestion < 5:
        return None

    # Build context for Echo Brain
    categories_count: dict = {}
    free_text_notes = []
    for r in structured[-20:]:  # Last 20 structured rejections
        for cat in r.get("categories", []):
            categories_count[cat] = categories_count.get(cat, 0) + 1
        if r.get("feedback") and "|" in r["feedback"]:
            # Extract free text part (after structured categories)
            parts = r["feedback"].split("|")
            for p in parts:
                if p.strip() and p.strip() not in REJECTION_NEGATIVE_MAP:
                    free_text_notes.append(p.strip())

    top_issues = sorted(categories_count.items(), key=lambda x: -x[1])[:5]
    issue_summary = ", ".join(f"{k} ({v}x)" for k, v in top_issues)

    # Query Echo Brain for character context
    try:
        import urllib.request
        query_payload = json.dumps({
            "method": "tools/call",
            "params": {
                "name": "search_memory",
                "arguments": {
                    "query": f"{character_slug} character design appearance visual description",
                    "limit": 3,
                }
            }
        }).encode()
        req = urllib.request.Request(
            "http://localhost:8309/mcp",
            data=query_payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        echo_result = json.loads(resp.read())
        echo_context = ""
        if "result" in echo_result and "content" in echo_result["result"]:
            for item in echo_result["result"]["content"]:
                if item.get("type") == "text":
                    echo_context += item["text"] + "\n"
    except Exception as e:
        logger.warning(f"Echo Brain query failed for {character_slug}: {e}")
        echo_context = ""

    if echo_context:
        logger.info(f"Echo Brain provided context for {character_slug} prompt refinement ({len(echo_context)} chars)")

    # Record that we attempted a suggestion at this count
    data["last_echo_brain_suggestion_at_count"] = data["rejection_count"]
    data["echo_brain_context"] = echo_context[:500] if echo_context else ""
    data["top_rejection_issues"] = issue_summary
    data["free_text_notes"] = free_text_notes[-10:]
    feedback_json.write_text(json.dumps(data, indent=2))

    return echo_context if echo_context else None


def _queue_regeneration(character_slug: str):
    """Queue a feedback-aware background regeneration for a character."""
    # Check if character already has enough approved images
    dataset_path = BASE_PATH / character_slug
    approval_file = dataset_path / "approval_status.json"
    if approval_file.exists():
        try:
            statuses = json.loads(approval_file.read_text())
            approved_count = sum(1 for v in statuses.values() if v == "approved")
            if approved_count >= 10:
                logger.info(f"Skipping regeneration for {character_slug}: already has {approved_count} approved")
                return
        except (json.JSONDecodeError, IOError):
            pass

    script = _SCRIPT_DIR / "generate_training_images.py"
    if not script.exists():
        logger.warning("Generation script not found")
        return

    cmd = ["python3", str(script), "--count=1", f"--character={character_slug}"]

    # Feedback loop: add rejection-derived negative prompt terms
    feedback_neg = _get_feedback_negatives(character_slug)
    if feedback_neg:
        cmd.append(f"--feedback-negative={feedback_neg}")
        logger.info(f"Feedback loop: adding negatives for {character_slug}: {feedback_neg[:80]}...")

    # Echo Brain analysis (runs periodically, not on every rejection)
    try:
        _maybe_refine_prompt_via_echo_brain(character_slug)
    except Exception as e:
        logger.warning(f"Echo Brain refinement check failed: {e}")

    log_fh = _open_gen_log()
    subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
    logger.info(f"Queued regeneration for {character_slug}")


@app.post("/api/lora/regenerate/{character_slug}")
async def regenerate_character(character_slug: str, count: int = 1,
                               seed: Optional[int] = None,
                               prompt_override: Optional[str] = None):
    """Manually trigger image regeneration for a character.

    count: generate exactly this many images (not a target threshold).
    Optional seed: use this seed (and seed+1, seed+2... for count > 1).
    Optional prompt_override: use this prompt instead of the DB design_prompt.
    """
    dataset_path = BASE_PATH / character_slug
    if not dataset_path.exists():
        # Auto-create dataset dir so generation has somewhere to write
        (dataset_path / "images").mkdir(parents=True, exist_ok=True)

    script = _SCRIPT_DIR / "generate_training_images.py"
    if not script.exists():
        raise HTTPException(status_code=500, detail="Generation script not found")

    cmd = ["python3", str(script), f"--count={count}", f"--character={character_slug}"]
    if seed is not None:
        cmd.append(f"--seed={seed}")
    if prompt_override:
        cmd.append(f"--prompt-override={prompt_override}")

    log_fh = _open_gen_log()
    subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    msg = f"Regeneration started for {character_slug} ({count} images)"
    if seed is not None:
        msg += f" with seed={seed}"
    logger.info(msg)
    return {"message": msg}


@app.get("/api/lora/training/jobs")
async def get_training_jobs():
    """Get all training jobs."""
    jobs = _load_training_jobs()
    return {"training_jobs": jobs}


@app.post("/api/lora/training/start")
async def start_training(training: TrainingRequest):
    """Start a LoRA training job for a character.

    Resolves the checkpoint from the character's project generation_style,
    frees ComfyUI VRAM, and launches train_lora.py as a subprocess.
    """
    import re
    safe_name = re.sub(r'[^a-z0-9_-]', '', training.character_name.lower().replace(' ', '_'))
    dataset_path = BASE_PATH / safe_name
    approval_file = dataset_path / "approval_status.json"

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="Character not found")

    # Count approved images
    approved_count = 0
    if approval_file.exists():
        with open(approval_file) as f:
            statuses = json.load(f)
            approved_count = sum(1 for s in statuses.values() if s == "approved")

    MIN_TRAINING_IMAGES = 10
    if approved_count < MIN_TRAINING_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {MIN_TRAINING_IMAGES} approved images (have {approved_count})"
        )

    # Resolve checkpoint from DB
    char_map = await _get_char_project_map()
    db_info = char_map.get(safe_name, {})
    checkpoint_name = db_info.get("checkpoint_model")
    if not checkpoint_name:
        raise HTTPException(status_code=400, detail="No checkpoint model configured for this character's project")

    checkpoint_path = Path("/opt/ComfyUI/models/checkpoints") / checkpoint_name
    if not checkpoint_path.exists():
        raise HTTPException(status_code=400, detail=f"Checkpoint not found: {checkpoint_name}")

    # Check GPU availability and free ComfyUI VRAM
    from gpu_manager import ensure_gpu_ready
    gpu_ready, gpu_msg = ensure_gpu_ready()
    if not gpu_ready:
        raise HTTPException(status_code=503, detail=f"GPU not available: {gpu_msg}")

    job_id = f"train_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_path = Path("/opt/ComfyUI/models/loras") / f"{safe_name}_lora.safetensors"

    job = {
        "job_id": job_id,
        "character_name": training.character_name,
        "character_slug": safe_name,
        "status": "queued",
        "approved_images": approved_count,
        "epochs": training.epochs,
        "learning_rate": training.learning_rate,
        "resolution": training.resolution,
        "checkpoint": checkpoint_name,
        "output_path": str(output_path),
        "created_at": datetime.now().isoformat(),
    }

    jobs = _load_training_jobs()
    jobs.append(job)
    _save_training_jobs(jobs)

    # Launch training subprocess
    train_script = _SCRIPT_DIR / "train_lora.py"
    log_dir = _PROJECT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{job_id}.log"

    cmd = [
        "/usr/bin/python3", str(train_script),
        f"--job-id={job_id}",
        f"--character-slug={safe_name}",
        f"--checkpoint={checkpoint_path}",
        f"--dataset-dir={dataset_path}",
        f"--output={output_path}",
        f"--epochs={training.epochs}",
        f"--learning-rate={training.learning_rate}",
        f"--resolution={training.resolution}",
    ]

    log_fh = open(log_file, "w")
    subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        cwd=str(_SCRIPT_DIR),
    )

    logger.info(f"Training launched: {job_id} for {training.character_name} ({approved_count} images)")
    return {
        "message": "Training job started",
        "job_id": job_id,
        "approved_images": approved_count,
        "checkpoint": checkpoint_name,
        "output": str(output_path),
        "log_file": str(log_file),
        "gpu": gpu_msg,
    }


@app.get("/api/lora/training/jobs/{job_id}")
async def get_training_job(job_id: str):
    """Get status of a specific training job."""
    jobs = _load_training_jobs()
    for job in jobs:
        if job["job_id"] == job_id:
            return job
    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/lora/training/jobs/{job_id}/log")
async def get_training_log(job_id: str, tail: int = 50):
    """Tail the log file for a training job."""
    log_file = _PROJECT_DIR / "logs" / f"{job_id}.log"
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    lines = log_file.read_text().splitlines()
    return {
        "job_id": job_id,
        "total_lines": len(lines),
        "lines": lines[-tail:],
    }


# ===================================================================
# Ingestion endpoints
# ===================================================================

@app.get("/api/lora/projects")
async def get_projects():
    """Get list of projects with their character counts."""
    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG["host"], database=DB_CONFIG["database"],
            user=DB_CONFIG["user"], password=DB_CONFIG["password"],
        )
        rows = await conn.fetch("""
            SELECT p.id, p.name, p.default_style, COUNT(c.id) as char_count
            FROM projects p
            LEFT JOIN characters c ON c.project_id = p.id
            GROUP BY p.id, p.name, p.default_style
            ORDER BY p.name
        """)
        await conn.close()
        return {
            "projects": [
                {"id": r["id"], "name": r["name"], "default_style": r["default_style"], "character_count": r["char_count"]}
                for r in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _download_and_extract_frames(url: str, max_frames: int, fps: float, tmpdir: str) -> list:
    """Download a video and extract frames to a temp directory. Returns list of frame paths."""
    tmp_video = Path(tmpdir) / "video.mp4"

    # Download with yt-dlp (try with --remote-components for YouTube)
    dl_result = subprocess.run(
        ["yt-dlp", "--js-runtimes", "node", "--remote-components", "ejs:github",
         "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
         "--merge-output-format", "mp4", "-o", str(tmp_video), url],
        capture_output=True, text=True, timeout=300,
    )
    if dl_result.returncode != 0:
        raise HTTPException(status_code=400, detail=f"yt-dlp failed: {dl_result.stderr[:500]}")

    if not tmp_video.exists():
        mp4s = list(Path(tmpdir).glob("*.mp4"))
        if mp4s:
            tmp_video = mp4s[0]
        else:
            raise HTTPException(status_code=500, detail="Video download produced no output")

    # Get video duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(tmp_video)],
        capture_output=True, text=True, timeout=30,
    )
    duration = float(probe.stdout.strip()) if probe.stdout.strip() else 60

    # Extract frames to a subfolder
    frames_dir = Path(tmpdir) / "frames"
    frames_dir.mkdir(exist_ok=True)
    frame_pattern = str(frames_dir / "frame_%04d.png")

    # Use fps parameter for extraction rate, cap at max_frames
    subprocess.run(
        ["ffmpeg", "-i", str(tmp_video), "-vf", f"fps={fps},scale=768:-1",
         "-q:v", "1", "-frames:v", str(max_frames), frame_pattern, "-y"],
        capture_output=True, timeout=300,
    )

    return sorted(frames_dir.glob("frame_*.png"))


@app.post("/api/lora/ingest/youtube")
async def ingest_youtube(body: dict):
    """Extract frames from a YouTube video and add to a character's dataset."""
    url = body.get("url")
    character_slug = body.get("character_slug")
    max_frames = body.get("max_frames", 20)
    fps = body.get("fps", 2)

    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    if not character_slug:
        raise HTTPException(status_code=400, detail="character_slug is required")

    dataset_images = BASE_PATH / character_slug / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)

    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="lora_ingest_")

    try:
        frames = _download_and_extract_frames(url, max_frames, fps, tmpdir)

        char_map = await _get_char_project_map()
        db_info = char_map.get(character_slug, {})

        copied = 0
        for i, frame in enumerate(frames):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_name = f"yt_{character_slug}_{ts}_{i+1:04d}.png"
            dest = dataset_images / dest_name
            shutil.copy2(frame, dest)

            meta = {
                "seed": None,
                "full_prompt": None,
                "design_prompt": db_info.get("design_prompt", ""),
                "checkpoint_model": None,
                "source": "youtube",
                "youtube_url": url,
                "frame_number": i + 1,
                "project_name": db_info.get("project_name", ""),
                "character_name": db_info.get("name", character_slug),
                "generated_at": datetime.now().isoformat(),
            }
            dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
            caption = db_info.get("design_prompt", f"a frame of {character_slug.replace('_', ' ')}")
            dest.with_suffix(".txt").write_text(caption)
            copied += 1

        return {
            "frames_extracted": copied,
            "character": character_slug,
            "status": "pending_approval",
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --- Llava Vision Classification Pipeline ---
# Used by ALL ingestion paths to classify images before assigning to character datasets.

_LLAVA_DESCRIBE_PROMPT = """Describe the characters visible in this animated frame. Focus on:
- What species/type are they (human, dinosaur, turtle, mushroom creature, etc)?
- What color are they?
- What are they wearing (hats, dresses, shells, etc)?
- How many characters are visible?
- Any distinctive features (mustache, crown, fangs, goggles, etc)?
Be specific and concise. Only describe what you actually see."""

# Visual keyword signatures per character. ANY group matching = character detected.
_CHARACTER_SIGNATURES: dict[str, list[list[str]]] = {
    "mario": [["red cap", "mustache"], ["red hat", "overalls"], ["mario"]],
    "luigi": [["green cap"], ["green hat", "overalls"], ["luigi"]],
    "princess_peach": [["pink dress"], ["blonde", "tiara"], ["blonde", "crown"], ["princess"], ["peach"], ["pink gown"]],
    "toad": [["mushroom head"], ["mushroom cap"], ["mushroom creature"], ["toad"], ["blue vest", "small"]],
    "yoshi": [["green dinosaur"], ["yoshi"], ["dinosaur", "saddle"]],
    "rosalina": [["rosalina"], ["blonde", "blue gown"], ["blonde", "star wand"], ["twin tails", "blonde"]],
    "bowser": [["bowser"], ["turtle", "fangs", "large"], ["spiky shell", "dragon"], ["reptilian", "armor", "fangs"], ["scales", "armor", "teeth"], ["dragon turtle"]],
    "bowser_jr": [["bowser jr"], ["small", "bib", "fangs"], ["bandana", "teeth", "small"], ["small koopa", "ponytail"], ["dinosaur", "spikes", "red", "small"], ["small", "spiky", "shell"], ["junior", "turtle"]],
    "kamek": [["kamek"], ["blue robe", "wizard"], ["blue robe", "glasses"], ["magikoopa"]],
    "lakitu": [["lakitu"], ["cloud", "goggles", "turtle"]],
    "luma": [["luma"], ["star creature"], ["star-shaped"]],
    "birdo": [["birdo"], ["pink dinosaur", "bow"], ["pink", "snout", "bow"]],
    "mouser": [["mouser"], ["mouse", "sunglasses"]],
}


def _llava_describe_image(image_path: Path) -> str:
    """Get a visual description of an image using llava:13b."""
    import base64
    import urllib.request as _ur

    img_data = base64.b64encode(image_path.read_bytes()).decode()
    payload = json.dumps({
        "model": "llava:13b",
        "prompt": _LLAVA_DESCRIBE_PROMPT,
        "images": [img_data],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 250},
    }).encode()
    req = _ur.Request("http://localhost:11434/api/generate", data=payload, headers={"Content-Type": "application/json"})
    resp = _ur.urlopen(req, timeout=60)
    return json.loads(resp.read()).get("response", "").strip()


def _match_description_to_characters(description: str, allowed_slugs: list[str] | None = None) -> list[str]:
    """Match a visual description against character keyword signatures."""
    desc_lower = description.lower()
    matched = []
    sigs = _CHARACTER_SIGNATURES if not allowed_slugs else {k: v for k, v in _CHARACTER_SIGNATURES.items() if k in allowed_slugs}
    for slug, sig_groups in sigs.items():
        for keywords in sig_groups:
            if all(kw in desc_lower for kw in keywords):
                matched.append(slug)
                break
    return matched


def _classify_image(image_path: Path, allowed_slugs: list[str] | None = None) -> tuple[list[str], str]:
    """Classify an image: describe with llava, then keyword-match to characters.

    Returns (matched_slugs, description). This is the shared pipeline used by
    all ingestion endpoints (YouTube, upload, video, ComfyUI scan).
    """
    try:
        description = _llava_describe_image(image_path)
        matched = _match_description_to_characters(description, allowed_slugs)
        return matched, description
    except Exception as e:
        logger.warning(f"Llava classification failed for {image_path.name}: {e}")
        return [], ""


@app.post("/api/lora/ingest/youtube-project")
async def ingest_youtube_project(body: dict):
    """Extract frames from a YouTube video, classify with llava, and distribute to matching characters.

    Uses llava vision model to identify which characters appear in each frame,
    then copies each frame ONLY to the datasets of characters that are visible in it.
    """
    url = body.get("url")
    project_name = body.get("project_name")
    max_frames = body.get("max_frames", 60)
    fps = body.get("fps", 4)

    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    if not project_name:
        raise HTTPException(status_code=400, detail="project_name is required")

    # Get all characters in this project
    char_map = await _get_char_project_map()
    project_chars = {slug: info for slug, info in char_map.items() if info.get("project_name") == project_name}

    if not project_chars:
        raise HTTPException(status_code=404, detail=f"No characters found for project '{project_name}'")

    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="lora_project_ingest_")

    try:
        logger.info(f"Project-wide YouTube ingest: {url} → {project_name} ({len(project_chars)} characters)")
        frames = _download_and_extract_frames(url, max_frames, fps, tmpdir)
        logger.info(f"Extracted {len(frames)} frames, classifying with llava...")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        results = {slug: 0 for slug in project_chars}
        skipped = 0
        classifications = {}
        slugs = list(project_chars.keys())

        for i, frame in enumerate(frames):
            frame_num = i + 1
            matched, description = _classify_image(frame, allowed_slugs=slugs)

            if not matched:
                skipped += 1
                logger.info(f"  Frame {frame_num}: no characters (skipped)")
                continue

            classifications[frame.name] = {"characters": matched, "description": description[:200]}
            logger.info(f"  Frame {frame_num}: {', '.join(matched)}")

            for slug in matched:
                db_info = project_chars[slug]
                dataset_images = BASE_PATH / slug / "images"
                dataset_images.mkdir(parents=True, exist_ok=True)

                dest_name = f"yt_ref_{slug}_{ts}_{frame_num:04d}.png"
                dest = dataset_images / dest_name
                shutil.copy2(frame, dest)

                meta = {
                    "seed": None,
                    "full_prompt": None,
                    "design_prompt": db_info.get("design_prompt", ""),
                    "checkpoint_model": None,
                    "source": "youtube_classified",
                    "youtube_url": url,
                    "frame_number": frame_num,
                    "classified_character": slug,
                    "project_name": project_name,
                    "character_name": db_info.get("name", slug),
                    "generated_at": datetime.now().isoformat(),
                }
                dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
                dest.with_suffix(".txt").write_text(
                    f"{db_info.get('name', slug)} from {project_name} reference video, Illumination 3D CGI"
                )
                results[slug] += 1

        # Save classification map
        class_file = BASE_PATH.parent / "frame_classifications.json"
        class_file.write_text(json.dumps(classifications, indent=2))

        # Filter out characters with 0 frames
        results = {k: v for k, v in results.items() if v > 0}

        return {
            "frames_extracted": len(frames),
            "frames_classified": len(classifications),
            "frames_skipped": skipped,
            "project": project_name,
            "characters_seeded": len(results),
            "per_character": results,
            "status": "pending_approval",
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/api/lora/ingest/image")
async def ingest_image(file: UploadFile = File(...), character_slug: str = ""):
    """Upload a single image to a character's dataset. Classifies with llava."""
    if not character_slug:
        raise HTTPException(status_code=400, detail="character_slug is required")

    dataset_images = BASE_PATH / character_slug / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = Path(file.filename).suffix if file.filename else ".png"
    dest_name = f"upload_{character_slug}_{timestamp}{ext}"
    dest = dataset_images / dest_name

    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    # Classify with llava
    matched, description = _classify_image(dest)

    char_map = await _get_char_project_map()
    db_info = char_map.get(character_slug, {})
    meta = {
        "seed": None,
        "full_prompt": None,
        "design_prompt": db_info.get("design_prompt", ""),
        "checkpoint_model": None,
        "source": "upload",
        "original_filename": file.filename,
        "project_name": db_info.get("project_name", ""),
        "character_name": db_info.get("name", character_slug),
        "generated_at": datetime.now().isoformat(),
        "llava_description": description[:300],
        "llava_matched": matched,
    }
    dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    caption = db_info.get("design_prompt", f"a portrait of {character_slug.replace('_', ' ')}")
    dest.with_suffix(".txt").write_text(caption)

    return {
        "image": dest_name,
        "character": character_slug,
        "status": "pending_approval",
        "llava_matched": matched,
        "llava_description": description[:200] if description else None,
    }


@app.post("/api/lora/ingest/video")
async def ingest_video(file: UploadFile = File(...), character_slug: str = "",
                       fps: float = 0.5):
    """Upload a video, extract frames, and add to a character's dataset."""
    if not character_slug:
        raise HTTPException(status_code=400, detail="character_slug is required")

    dataset_images = BASE_PATH / character_slug / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)

    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="lora_video_")
    tmp_video = Path(tmpdir) / (file.filename or "upload.mp4")

    try:
        # Stream file to disk in chunks to avoid memory issues with large videos
        with open(tmp_video, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)

        # Extract frames to temp dir first (for classification before copying)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        frames_staging = Path(tmpdir) / "frames"
        frames_staging.mkdir(exist_ok=True)
        frame_pattern = str(frames_staging / "frame_%04d.png")
        subprocess.run(
            ["ffmpeg", "-i", str(tmp_video), "-vf", f"fps={fps},scale=768:-1",
             "-q:v", "1", frame_pattern, "-y"],
            capture_output=True, timeout=300,
        )

        staged_frames = sorted(frames_staging.glob("frame_*.png"))
        char_map = await _get_char_project_map()
        db_info = char_map.get(character_slug, {})

        copied = 0
        skipped = 0
        for i, frame in enumerate(staged_frames):
            frame_num = i + 1
            # Classify with llava — only copy if target character is detected
            matched, description = _classify_image(frame)
            if character_slug not in matched:
                skipped += 1
                continue

            dest_name = f"vid_{character_slug}_{timestamp}_{frame_num:04d}.png"
            dest = dataset_images / dest_name
            shutil.copy2(frame, dest)

            meta = {
                "seed": None,
                "full_prompt": None,
                "design_prompt": db_info.get("design_prompt", ""),
                "checkpoint_model": None,
                "source": "video_upload",
                "original_filename": file.filename,
                "frame_number": frame_num,
                "project_name": db_info.get("project_name", ""),
                "character_name": db_info.get("name", character_slug),
                "generated_at": datetime.now().isoformat(),
                "llava_description": description[:300],
                "llava_matched": matched,
            }
            dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
            caption = db_info.get("design_prompt", f"a frame of {character_slug.replace('_', ' ')}")
            dest.with_suffix(".txt").write_text(caption)
            copied += 1

        return {
            "frames_extracted": len(staged_frames),
            "frames_matched": copied,
            "frames_skipped": skipped,
            "character": character_slug,
            "status": "pending_approval",
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/api/lora/ingest/scan-comfyui")
async def scan_comfyui():
    """Scan ComfyUI output directory for new untracked images and match to characters."""
    comfyui_output = Path("/opt/ComfyUI/output")
    if not comfyui_output.exists():
        raise HTTPException(status_code=500, detail="ComfyUI output directory not found")

    char_map = await _get_char_project_map()

    # Build set of already-ingested filenames across all datasets
    existing = set()
    if BASE_PATH.exists():
        for char_dir in BASE_PATH.iterdir():
            if char_dir.is_dir():
                images_dir = char_dir / "images"
                if images_dir.exists():
                    existing.update(p.name for p in images_dir.glob("*.png"))

    new_images = 0
    matched_chars = {}
    unmatched = []

    for png in sorted(comfyui_output.glob("*.png")):
        if png.name in existing:
            continue

        # First try filename matching (fast path)
        matched_slug = None
        fn_lower = png.name.lower()
        for slug in char_map:
            if slug in fn_lower or slug.replace("_", "") in fn_lower:
                matched_slug = slug
                break

        # If filename didn't match, use llava vision classification
        llava_matched = []
        llava_description = ""
        if not matched_slug:
            llava_matched, llava_description = _classify_image(png, allowed_slugs=list(char_map.keys()))
            if llava_matched:
                matched_slug = llava_matched[0]  # Primary match for single-character assignment

        if matched_slug:
            db_info = char_map[matched_slug]
            dest_dir = BASE_PATH / matched_slug / "images"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / png.name
            if not dest.exists():
                shutil.copy2(png, dest)
                meta = {
                    "seed": None,
                    "source": "comfyui_scan",
                    "design_prompt": db_info.get("design_prompt") or "",
                    "project_name": db_info.get("project_name") or "",
                    "character_name": db_info.get("name") or matched_slug,
                    "generated_at": datetime.now().isoformat(),
                    "llava_description": llava_description[:300] if llava_description else None,
                    "llava_matched": llava_matched if llava_matched else None,
                }
                dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
                caption = db_info.get("design_prompt") or matched_slug.replace("_", " ")
                dest.with_suffix(".txt").write_text(caption)
                new_images += 1
                matched_chars[matched_slug] = matched_chars.get(matched_slug, 0) + 1

                # If llava found multiple characters, copy to additional datasets
                for extra_slug in llava_matched[1:]:
                    if extra_slug in char_map and extra_slug != matched_slug:
                        extra_info = char_map[extra_slug]
                        extra_dir = BASE_PATH / extra_slug / "images"
                        extra_dir.mkdir(parents=True, exist_ok=True)
                        extra_dest = extra_dir / png.name
                        if not extra_dest.exists():
                            shutil.copy2(png, extra_dest)
                            extra_meta = {
                                "seed": None,
                                "source": "comfyui_scan",
                                "design_prompt": extra_info.get("design_prompt") or "",
                                "project_name": extra_info.get("project_name") or "",
                                "character_name": extra_info.get("name") or extra_slug,
                                "generated_at": datetime.now().isoformat(),
                                "llava_description": llava_description[:300],
                                "llava_matched": llava_matched,
                            }
                            extra_dest.with_suffix(".meta.json").write_text(json.dumps(extra_meta, indent=2))
                            extra_caption = extra_info.get("design_prompt") or extra_slug.replace("_", " ")
                            extra_dest.with_suffix(".txt").write_text(extra_caption)
                            new_images += 1
                            matched_chars[extra_slug] = matched_chars.get(extra_slug, 0) + 1
        else:
            unmatched.append(png.name)

    return {
        "new_images": new_images,
        "matched": matched_chars,
        "unmatched_count": len(unmatched),
        "unmatched_samples": unmatched[:20],
    }


# ===================================================================
# IPAdapter refinement
# ===================================================================

@app.post("/api/lora/refine")
async def refine_image(body: dict):
    """Use an approved image as a style reference via IPAdapter to generate variants."""
    character_slug = body.get("character_slug")
    reference_image = body.get("reference_image")  # filename in the dataset
    prompt_override = body.get("prompt_override")
    count = body.get("count", 3)
    weight = body.get("weight", 0.8)
    denoise = body.get("denoise", 0.65)

    if not character_slug or not reference_image:
        raise HTTPException(status_code=400, detail="character_slug and reference_image are required")

    ref_path = BASE_PATH / character_slug / "images" / reference_image
    if not ref_path.exists():
        raise HTTPException(status_code=404, detail="Reference image not found")

    # Load generation settings from DB
    char_map = await _get_char_project_map()
    db_info = char_map.get(character_slug, {})

    workflow_path = Path("/opt/tower-anime-production/workflows/comfyui/ipadapter_refine.json")
    if not workflow_path.exists():
        raise HTTPException(status_code=500, detail="IPAdapter workflow not found")

    import random
    results = []

    for i in range(count):
        seed = random.randint(1, 2**31)
        workflow = json.loads(workflow_path.read_text())

        # Configure workflow
        prompt_text = prompt_override or db_info.get("design_prompt", "")
        workflow["1"]["inputs"]["text"] = prompt_text
        workflow["3"]["inputs"]["seed"] = seed
        workflow["3"]["inputs"]["denoise"] = denoise
        workflow["4"]["inputs"]["ckpt_name"] = db_info.get("checkpoint_model", "cyberrealistic_v9.safetensors")
        workflow["7"]["inputs"]["filename_prefix"] = f"refine_{character_slug}"
        workflow["9"]["inputs"]["image"] = str(ref_path)
        workflow["10"]["inputs"]["weight"] = weight

        if db_info.get("cfg_scale"):
            workflow["3"]["inputs"]["cfg"] = db_info["cfg_scale"]
        if db_info.get("steps"):
            workflow["3"]["inputs"]["steps"] = db_info["steps"]

        try:
            payload = json.dumps({"prompt": workflow}).encode()
            req = __import__("urllib.request", fromlist=["Request"]).Request(
                "http://127.0.0.1:8188/prompt", data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = __import__("urllib.request", fromlist=["urlopen"]).urlopen(req)
            prompt_id = json.loads(resp.read()).get("prompt_id", "")
            results.append({"prompt_id": prompt_id, "seed": seed})
        except Exception as e:
            results.append({"error": str(e)})

    return {
        "message": f"Queued {count} IPAdapter refinement(s) for {character_slug}",
        "reference_image": reference_image,
        "results": results,
    }


# --- Feedback analysis endpoints ---

@app.get("/api/lora/feedback/{character_slug}")
async def get_feedback(character_slug: str):
    """Get rejection feedback analysis for a character."""
    feedback_json = BASE_PATH / character_slug / "feedback.json"
    if not feedback_json.exists():
        return {"character": character_slug, "rejection_count": 0, "rejections": [], "negative_additions": []}
    try:
        data = json.loads(feedback_json.read_text())
        data["character"] = character_slug
        return data
    except (json.JSONDecodeError, IOError):
        return {"character": character_slug, "rejection_count": 0, "rejections": [], "negative_additions": []}


@app.delete("/api/lora/feedback/{character_slug}")
async def clear_feedback(character_slug: str):
    """Clear rejection feedback for a character (reset the feedback loop)."""
    feedback_json = BASE_PATH / character_slug / "feedback.json"
    if feedback_json.exists():
        feedback_json.unlink()
    return {"message": f"Feedback cleared for {character_slug}"}


# ===================================================================
# ComfyUI Generation endpoints
# ===================================================================

@app.post("/api/lora/generate/clear-stuck")
async def clear_stuck_generations():
    """Clear stuck ComfyUI generation jobs."""
    import urllib.request as _ur
    try:
        req = _ur.Request(f"{COMFYUI_URL}/queue")
        resp = _ur.urlopen(req, timeout=10)
        queue_data = json.loads(resp.read())

        running = queue_data.get("queue_running", [])
        pending = queue_data.get("queue_pending", [])

        cancelled = 0
        for job in pending:
            try:
                cancel_payload = json.dumps({"delete": [job[1]]}).encode()
                cancel_req = _ur.Request(
                    f"{COMFYUI_URL}/queue",
                    data=cancel_payload,
                    headers={"Content-Type": "application/json"},
                )
                _ur.urlopen(cancel_req, timeout=5)
                cancelled += 1
            except Exception:
                pass

        return {
            "message": f"Cleared {cancelled} pending jobs",
            "running": len(running),
            "pending_before": len(pending),
            "cancelled": cancelled,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to communicate with ComfyUI: {e}")


@app.post("/api/lora/generate/{character_slug}")
async def generate_for_character(character_slug: str, body: GenerateRequest):
    """Generate an image or video for a character using SSOT profile."""
    char_map = await _get_char_project_map()
    db_info = char_map.get(character_slug)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")

    checkpoint = db_info.get("checkpoint_model")
    if not checkpoint:
        raise HTTPException(status_code=400, detail="No checkpoint model configured for this character's project")

    prompt = body.prompt_override or db_info.get("design_prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="No design_prompt and no prompt_override provided")

    norm_sampler, norm_scheduler = _normalize_sampler(
        db_info.get("sampler"), db_info.get("scheduler")
    )

    workflow = _build_comfyui_workflow(
        design_prompt=prompt,
        checkpoint_model=checkpoint,
        cfg_scale=db_info.get("cfg_scale") or 7.0,
        steps=db_info.get("steps") or 25,
        sampler=norm_sampler,
        scheduler=norm_scheduler,
        width=db_info.get("width") or 512,
        height=db_info.get("height") or 768,
        negative_prompt=body.negative_prompt or "worst quality, low quality, blurry, deformed",
        generation_type=body.generation_type,
        seed=body.seed,
        character_slug=character_slug,
    )

    try:
        prompt_id = _submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    return {
        "prompt_id": prompt_id,
        "character": character_slug,
        "generation_type": body.generation_type,
        "prompt_used": prompt,
        "checkpoint": checkpoint,
        "seed": workflow["3"]["inputs"]["seed"],
    }


@app.get("/api/lora/generate/{prompt_id}/status")
async def get_generation_status(prompt_id: str):
    """Check ComfyUI generation progress."""
    return _get_comfyui_progress(prompt_id)


# ===================================================================
# Gallery endpoint
# ===================================================================

@app.get("/api/lora/gallery")
async def get_gallery(limit: int = 50):
    """Get recent images from ComfyUI output directory."""
    if not COMFYUI_OUTPUT_DIR.exists():
        return {"images": []}

    image_files = []
    for ext in ("*.png", "*.jpg"):
        image_files.extend(COMFYUI_OUTPUT_DIR.glob(ext))

    image_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return {
        "images": [
            {
                "filename": img.name,
                "created_at": datetime.fromtimestamp(img.stat().st_mtime).isoformat(),
                "size_kb": round(img.stat().st_size / 1024, 1),
            }
            for img in image_files[:limit]
        ]
    }


@app.get("/api/lora/gallery/image/{filename}")
async def get_gallery_image(filename: str):
    """Serve a gallery image from ComfyUI output."""
    image_path = COMFYUI_OUTPUT_DIR / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)


# ===================================================================
# Echo Brain endpoints
# ===================================================================

@app.get("/api/lora/echo/status")
async def echo_status():
    """Check Echo Brain availability."""
    import urllib.request as _ur
    try:
        req = _ur.Request("http://localhost:8309/health")
        resp = _ur.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return {"status": "connected", "echo_brain": data}
    except Exception as e:
        return {"status": "offline", "error": str(e)}


@app.post("/api/lora/echo/chat")
async def echo_chat(body: EchoChatRequest):
    """Send a message to Echo Brain and get a response."""
    import urllib.request as _ur

    context = ""
    if body.character_slug:
        char_map = await _get_char_project_map()
        db_info = char_map.get(body.character_slug, {})
        if db_info:
            context = f"Character: {db_info.get('name', body.character_slug)}, Project: {db_info.get('project_name', '')}, Design: {db_info.get('design_prompt', '')}"

    try:
        search_payload = json.dumps({
            "method": "tools/call",
            "params": {
                "name": "search_memory",
                "arguments": {"query": body.message, "limit": 5},
            }
        }).encode()
        req = _ur.Request(
            "http://localhost:8309/mcp",
            data=search_payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _ur.urlopen(req, timeout=15)
        echo_result = json.loads(resp.read())

        response_text = ""
        if "result" in echo_result and "content" in echo_result["result"]:
            for item in echo_result["result"]["content"]:
                if item.get("type") == "text":
                    response_text += item["text"] + "\n"

        return {
            "response": response_text.strip() or "No relevant memories found.",
            "context_used": bool(context),
            "character_context": context if context else None,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Echo Brain unavailable: {e}")


@app.post("/api/lora/echo/enhance-prompt")
async def echo_enhance_prompt(body: EchoEnhanceRequest):
    """Ask Echo Brain to suggest improvements to a design prompt."""
    import urllib.request as _ur

    char_context = ""
    if body.character_slug:
        char_map = await _get_char_project_map()
        db_info = char_map.get(body.character_slug, {})
        if db_info:
            char_context = f" for {db_info.get('name', body.character_slug)} from {db_info.get('project_name', '')}"

    try:
        query = f"Improve this anime character design prompt{char_context}: {body.prompt}"
        search_payload = json.dumps({
            "method": "tools/call",
            "params": {
                "name": "search_memory",
                "arguments": {"query": query, "limit": 5},
            }
        }).encode()
        req = _ur.Request(
            "http://localhost:8309/mcp",
            data=search_payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _ur.urlopen(req, timeout=15)
        echo_result = json.loads(resp.read())

        memories = []
        if "result" in echo_result and "content" in echo_result["result"]:
            for item in echo_result["result"]["content"]:
                if item.get("type") == "text":
                    memories.append(item["text"])

        return {
            "original_prompt": body.prompt,
            "echo_brain_context": memories,
            "suggestion": f"Based on Echo Brain memories, consider refining: {body.prompt}",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Echo Brain unavailable: {e}")


# Health check
@app.get("/api/lora/health")
async def health():
    return {"status": "healthy", "service": "tower-lora-studio"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8401)
