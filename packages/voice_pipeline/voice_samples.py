"""Voice Pipeline — sample management sub-router.

Extracted from voice_pipeline/router.py.  Speaker assignment, sample listing,
approval (single + batch), streaming, and per-character stats.
"""

import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH
from packages.core.db import connect_direct
from packages.core.events import event_bus, VOICE_SEGMENT_APPROVED, VOICE_SEGMENT_REJECTED
from packages.core.models import (
    VoiceSpeakerAssignRequest, VoiceSampleApprovalRequest,
    VoiceBatchApprovalRequest,
)
from packages.voice_pipeline.quality import score_voice_sample, compute_snr, compute_duration

logger = logging.getLogger(__name__)
router = APIRouter()

VOICE_BASE = BASE_PATH.parent
VOICE_DATASETS = VOICE_BASE / "voice_datasets"


# =============================================================================
# Speaker Assignment + Sample Management
# =============================================================================

@router.post("/speakers/{speaker_id}/assign")
async def assign_speaker_to_character(speaker_id: int, body: VoiceSpeakerAssignRequest):
    """Assign a speaker cluster to a character."""
    conn = await connect_direct()
    try:
        row = await conn.fetchrow("SELECT * FROM voice_speakers WHERE id = $1", speaker_id)
        if not row:
            raise HTTPException(status_code=404, detail="Speaker not found")

        await conn.execute("""
            UPDATE voice_speakers
            SET assigned_character_id = $1, assigned_character_slug = $2, updated_at = NOW()
            WHERE id = $3
        """, body.character_id, body.character_slug, speaker_id)

        # Move speaker's segments to character's voice_datasets directory
        project_name = row["project_name"]
        safe_project = project_name.lower().replace(" ", "_")[:50]
        voice_dir = VOICE_BASE / "voice" / safe_project

        char_dir = VOICE_DATASETS / body.character_slug / "samples"
        char_dir.mkdir(parents=True, exist_ok=True)

        # Read diarization to find which segments belong to this speaker
        meta_path = voice_dir / "diarization_meta.json"
        copied = 0
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)

            for seg in meta.get("segment_assignments", []):
                if seg.get("speaker") == row["speaker_label"]:
                    src = Path(seg.get("path", ""))
                    if src.exists():
                        dst = char_dir / src.name
                        shutil.copy2(str(src), str(dst))
                        copied += 1

                        # Register in voice_samples
                        snr = compute_snr(str(dst))
                        duration = compute_duration(str(dst))
                        quality = score_voice_sample(
                            str(dst), snr_db=snr, duration_seconds=duration,
                            speaker_confidence=seg.get("speaker_confidence"),
                        )

                        await conn.execute("""
                            INSERT INTO voice_samples
                                (speaker_id, character_slug, project_name, filename, file_path,
                                 duration_seconds, start_time, end_time, snr_db, quality_score,
                                 speaker_confidence, created_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                            ON CONFLICT DO NOTHING
                        """, speaker_id, body.character_slug, project_name,
                            src.name, str(dst), duration, seg.get("start"),
                            seg.get("end"), snr, quality, seg.get("speaker_confidence"))

            # Initialize approval_status.json
            approval_path = VOICE_DATASETS / body.character_slug / "approval_status.json"
            statuses = {}
            if approval_path.exists():
                with open(approval_path) as f:
                    statuses = json.load(f)
            for wav in char_dir.glob("segment_*.wav"):
                if wav.name not in statuses:
                    statuses[wav.name] = "pending"
            with open(approval_path, "w") as f:
                json.dump(statuses, f, indent=2)

        return {
            "speaker_id": speaker_id,
            "character_slug": body.character_slug,
            "segments_copied": copied,
        }
    finally:
        await conn.close()


@router.get("/samples/{character_slug}")
async def list_voice_samples(character_slug: str):
    """List voice samples for a character with quality metrics."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch(
            "SELECT * FROM voice_samples WHERE character_slug = $1 ORDER BY start_time",
            character_slug,
        )

        samples = [dict(r) for r in rows]

        # Fallback: scan filesystem if DB is empty
        if not samples:
            char_dir = VOICE_DATASETS / character_slug / "samples"
            if char_dir.is_dir():
                approval_path = VOICE_DATASETS / character_slug / "approval_status.json"
                statuses = {}
                if approval_path.exists():
                    with open(approval_path) as f:
                        statuses = json.load(f)

                for wav in sorted(char_dir.glob("segment_*.wav")):
                    duration = compute_duration(str(wav))
                    snr = compute_snr(str(wav))
                    samples.append({
                        "filename": wav.name,
                        "file_path": str(wav),
                        "duration_seconds": duration,
                        "snr_db": snr,
                        "quality_score": score_voice_sample(str(wav), snr_db=snr, duration_seconds=duration),
                        "approval_status": statuses.get(wav.name, "pending"),
                    })

        # Compute stats
        approved = sum(1 for s in samples if s.get("approval_status") == "approved")
        total_approved_dur = sum(
            s.get("duration_seconds", 0) or 0
            for s in samples if s.get("approval_status") == "approved"
        )

        return {
            "character_slug": character_slug,
            "samples": samples,
            "total": len(samples),
            "approved": approved,
            "total_approved_duration": round(total_approved_dur, 2),
        }
    finally:
        await conn.close()


@router.get("/samples/{character_slug}/segment/{filename}")
async def stream_voice_sample(character_slug: str, filename: str):
    """Stream a voice sample WAV file."""
    sample_path = VOICE_DATASETS / character_slug / "samples" / filename
    if not sample_path.exists() or not filename.endswith(".wav"):
        raise HTTPException(status_code=404, detail="Sample not found")
    return FileResponse(sample_path, media_type="audio/wav", filename=filename)


@router.post("/samples/approve")
async def approve_voice_sample(body: VoiceSampleApprovalRequest):
    """Approve or reject a single voice sample."""
    char_dir = VOICE_DATASETS / body.character_slug
    sample_path = char_dir / "samples" / body.filename

    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample not found")

    status = "approved" if body.approved else "rejected"

    # Update approval_status.json
    approval_path = char_dir / "approval_status.json"
    statuses = {}
    if approval_path.exists():
        with open(approval_path) as f:
            statuses = json.load(f)
    statuses[body.filename] = status
    with open(approval_path, "w") as f:
        json.dump(statuses, f, indent=2)

    # Update DB
    conn = await connect_direct()
    try:
        await conn.execute("""
            UPDATE voice_samples SET approval_status = $1, reviewed_at = NOW(),
                feedback = $3, rejection_categories = $4
            WHERE character_slug = $2 AND filename = $5
        """, status, body.character_slug, body.feedback,
            body.rejection_categories or [], body.filename)
    finally:
        await conn.close()

    # Write transcript if provided
    if body.transcript:
        txt_path = sample_path.with_suffix(".txt")
        txt_path.write_text(body.transcript)

    event_name = VOICE_SEGMENT_APPROVED if body.approved else VOICE_SEGMENT_REJECTED
    await event_bus.emit(event_name, {
        "character_slug": body.character_slug,
        "filename": body.filename,
        "feedback": body.feedback,
    })

    return {"character_slug": body.character_slug, "filename": body.filename, "status": status}


@router.post("/samples/batch-approve")
async def batch_approve_voice_samples(body: VoiceBatchApprovalRequest):
    """Batch approve or reject multiple voice samples."""
    results = []
    for filename in body.filenames:
        single = VoiceSampleApprovalRequest(
            character_slug=body.character_slug,
            filename=filename,
            approved=body.approved,
            feedback=body.feedback,
        )
        try:
            result = await approve_voice_sample(single)
            results.append(result)
        except HTTPException:
            results.append({"filename": filename, "error": "not found"})

    return {
        "character_slug": body.character_slug,
        "processed": len(results),
        "approved": body.approved,
        "results": results,
    }


@router.get("/samples/{character_slug}/stats")
async def voice_sample_stats(character_slug: str):
    """Get voice sample counts and total approved duration for a character."""
    char_dir = VOICE_DATASETS / character_slug
    approval_path = char_dir / "approval_status.json"

    if not approval_path.exists():
        return {
            "character_slug": character_slug,
            "total": 0, "approved": 0, "rejected": 0, "pending": 0,
            "total_approved_duration": 0,
        }

    with open(approval_path) as f:
        statuses = json.load(f)

    counts = {"approved": 0, "rejected": 0, "pending": 0}
    approved_duration = 0.0
    for fname, status in statuses.items():
        counts[status] = counts.get(status, 0) + 1
        if status == "approved":
            wav_path = char_dir / "samples" / fname
            if wav_path.exists():
                dur = compute_duration(str(wav_path))
                approved_duration += dur or 0

    return {
        "character_slug": character_slug,
        "total": len(statuses),
        **counts,
        "total_approved_duration": round(approved_duration, 2),
    }
