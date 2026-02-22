"""Feedback loop helpers — rejection tracking, negative prompt derivation, Echo Brain refinement.

Also includes training job file helpers and image status registration utilities.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from packages.core.config import BASE_PATH

logger = logging.getLogger(__name__)

# --- Training job storage (file-based until DB wiring is needed) ---

TRAINING_JOBS_FILE = BASE_PATH.parent / "training_jobs.json"


def load_training_jobs() -> list:
    if TRAINING_JOBS_FILE.exists():
        with open(TRAINING_JOBS_FILE) as f:
            return json.load(f)
    return []


def save_training_jobs(jobs: list):
    TRAINING_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRAINING_JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)


def reconcile_training_jobs() -> int:
    """Detect and fix stale training jobs (running/queued but process is dead)."""
    jobs = load_training_jobs()
    reconciled = 0
    for job in jobs:
        if job.get("status") not in ("running", "queued"):
            continue
        pid = job.get("pid")
        alive = False
        if pid:
            try:
                os.kill(pid, 0)
                alive = True
            except (OSError, ProcessLookupError):
                pass
        if not alive:
            job["status"] = "failed"
            job["error"] = "Process died without updating status (detected at startup)"
            job["failed_at"] = datetime.now().isoformat()
            reconciled += 1
            logger.warning(f"Reconciled stale job {job['job_id']} (pid={pid})")
    if reconciled:
        save_training_jobs(jobs)
        logger.info(f"Reconciled {reconciled} stale training job(s)")
    return reconciled


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


def record_rejection(character_slug: str, image_name: str, feedback: str, edited_prompt: str = None):
    """Record structured rejection data for the feedback loop."""
    dataset_path = BASE_PATH / character_slug
    feedback_json = dataset_path / "feedback.json"

    data = {"rejections": [], "rejection_count": 0, "negative_additions": [], "categories": []}
    if feedback_json.exists():
        try:
            loaded = json.loads(feedback_json.read_text())
            if isinstance(loaded, dict):
                data.update(loaded)
        except (json.JSONDecodeError, IOError):
            pass
    # Ensure required keys exist (bulk reject may have written partial structure)
    if not isinstance(data.get("rejections"), list):
        data["rejections"] = []
    if not isinstance(data.get("negative_additions"), list):
        data["negative_additions"] = []
    if not isinstance(data.get("categories"), list):
        data["categories"] = []

    entry = {
        "image": image_name,
        "feedback": feedback,
        "edited_prompt": edited_prompt,
        "timestamp": datetime.now().isoformat(),
    }

    # Parse structured categories from feedback
    # Formats: "wrong_appearance|bad_quality|Free text", "wrong_appearance", or plain text
    categories = []
    parts = feedback.split("|") if "|" in feedback else [feedback.strip()]
    for part in parts:
        part = part.strip()
        if part in REJECTION_NEGATIVE_MAP:
            categories.append(part)
    # Default to wrong_appearance if no structured category was found
    if not categories and feedback.lower() in ("rejected", "batch rejected", ""):
        categories.append("wrong_appearance")
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


def get_feedback_negatives(character_slug: str) -> str:
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


def maybe_refine_prompt_via_echo_brain(character_slug: str) -> str | None:
    """After enough rejections, ask Echo Brain to suggest a better design_prompt.

    Returns the suggested prompt if Echo Brain has a recommendation, or None.
    Only triggers after 5+ structured rejections to avoid noise.
    """
    import urllib.request

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


def open_gen_log():
    """Open a log file for generation subprocess output."""
    log_dir = BASE_PATH.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "generation.log"
    return open(log_file, "a")


def queue_regeneration(character_slug: str):
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

    # Echo Brain analysis (runs periodically, not on every rejection)
    try:
        maybe_refine_prompt_via_echo_brain(character_slug)
    except Exception as e:
        logger.warning(f"Echo Brain refinement check failed: {e}")

    # Launch generate_batch as background asyncio task
    # (feedback negatives are included automatically by generate_batch)
    from packages.core.generation import generate_batch
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(generate_batch(character_slug=character_slug, count=1))
        logger.info(f"Queued regeneration for {character_slug}")
    except RuntimeError:
        logger.warning(f"No running event loop for queue_regeneration of {character_slug}")


# --- Image status registration helpers ---

def register_pending_image(character_slug: str, image_name: str):
    """Register a single image as pending in approval_status.json (thread-safe enough for single writer)."""
    register_image_status(character_slug, image_name, "pending")


def register_image_status(character_slug: str, image_name: str, status: str):
    """Register a single image with given status in approval_status.json."""
    approval_file = BASE_PATH / character_slug / "approval_status.json"
    approval_status = {}
    if approval_file.exists():
        try:
            approval_status = json.loads(approval_file.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    approval_status[image_name] = status
    approval_file.write_text(json.dumps(approval_status, indent=2))
