"""Content reconstruction endpoints — source analysis, context synthesis,
scene timeline, voice map, and text extraction.

These endpoints analyze ingested source material (movies, YouTube downloads)
to extract structured metadata for the Script and Cast tabs.
"""

import asyncio
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.core.config import BASE_PATH, MOVIES_DIR, OLLAMA_URL
from packages.core.db import connect_direct, get_char_project_map

logger = logging.getLogger(__name__)
analysis_router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────


async def _resolve_project(project_name: str) -> dict:
    """Resolve project name → project metadata from DB."""
    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT id, name, genre, premise, default_style FROM projects WHERE name = $1",
            project_name,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        return dict(row)
    finally:
        await conn.close()


async def _get_project_characters(project_name: str) -> list[dict]:
    """Get all characters for a project with their dataset stats."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT c.id, c.name, c.design_prompt, c.role,
                   REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug
            FROM characters c
            JOIN projects p ON c.project_id = p.id
            WHERE p.name = $1 AND (c.archived IS NULL OR c.archived = false)
            ORDER BY c.name
        """, project_name)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def _count_dataset_images(slug: str) -> dict:
    """Count images by status for a character slug."""
    approval_file = BASE_PATH / slug / "approval_status.json"
    if not approval_file.exists():
        return {"total": 0, "approved": 0, "rejected": 0, "pending": 0}
    try:
        statuses = json.loads(approval_file.read_text())
        approved = sum(1 for v in statuses.values() if v == "approved")
        rejected = sum(1 for v in statuses.values() if v == "rejected")
        pending = sum(1 for v in statuses.values() if v == "pending")
        return {"total": len(statuses), "approved": approved, "rejected": rejected, "pending": pending}
    except (json.JSONDecodeError, IOError):
        return {"total": 0, "approved": 0, "rejected": 0, "pending": 0}


def _find_source_videos(project_name: str) -> list[dict]:
    """Find source videos associated with a project in _movies and datasets."""
    videos = []
    # Check _movies directory
    if MOVIES_DIR.exists():
        for f in MOVIES_DIR.iterdir():
            if f.is_file() and f.suffix.lower() in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
                # Match by project name in filename (common pattern)
                if project_name.lower().replace(" ", "_") in f.name.lower().replace(" ", "_"):
                    videos.append({
                        "path": str(f),
                        "filename": f.name,
                        "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                    })
    # Also list all movies if none matched (user can pick)
    if not videos and MOVIES_DIR.exists():
        for f in sorted(MOVIES_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
                videos.append({
                    "path": str(f),
                    "filename": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                })
    return videos


async def _get_video_duration(path: str) -> float | None:
    """Get video duration in seconds via ffprobe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return float(stdout.decode().strip()) if stdout.decode().strip() else None
    except Exception:
        return None


async def _ollama_generate(prompt: str, model: str = "mistral:7b", max_tokens: int = 2000) -> str:
    """Call Ollama generate API and return the response text."""
    import urllib.request
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.3},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=120))
    data = json.loads(resp.read())
    return data.get("response", "")


# ── 1. Source Analysis ───────────────────────────────────────────────────


@analysis_router.get("/ingest/source-analysis/{project_name}")
async def source_analysis(project_name: str):
    """Analyze ingested source material for a project.

    Returns character dataset stats, source video inventory, and
    clip extraction coverage.
    """
    project = await _resolve_project(project_name)
    characters = await _get_project_characters(project_name)

    # Dataset stats per character
    char_stats = []
    for ch in characters:
        slug = ch["slug"]
        counts = _count_dataset_images(slug)
        ref_dir = BASE_PATH / slug / "reference_images"
        ref_count = len(list(ref_dir.glob("*.png"))) + len(list(ref_dir.glob("*.jpg"))) if ref_dir.exists() else 0
        char_stats.append({
            "name": ch["name"],
            "slug": slug,
            "role": ch.get("role"),
            "design_prompt": ch.get("design_prompt", "")[:200],
            "images": counts,
            "reference_images": ref_count,
            "has_dataset": counts["total"] > 0,
        })

    # Source videos
    source_videos = _find_source_videos(project_name)
    for sv in source_videos:
        dur = await _get_video_duration(sv["path"])
        sv["duration_seconds"] = dur

    # Clip extraction stats from DB
    conn = await connect_direct()
    try:
        clip_counts = await conn.fetch("""
            SELECT character_slug, COUNT(*) as clip_count,
                   AVG(similarity) as avg_similarity
            FROM character_clips
            WHERE character_slug = ANY($1::text[])
            GROUP BY character_slug
        """, [ch["slug"] for ch in characters])
        clip_map = {r["character_slug"]: {
            "clip_count": r["clip_count"],
            "avg_similarity": round(float(r["avg_similarity"] or 0), 3),
        } for r in clip_counts}

        # Scene/shot stats
        scene_stats = await conn.fetchrow("""
            SELECT COUNT(DISTINCT s.id) as scene_count,
                   COUNT(sh.id) as shot_count,
                   COUNT(sh.id) FILTER (WHERE sh.status = 'completed') as completed_shots,
                   COUNT(sh.id) FILTER (WHERE sh.output_video_path IS NOT NULL) as shots_with_video
            FROM scenes s
            LEFT JOIN shots sh ON sh.scene_id = s.id
            WHERE s.project_id = $1
        """, project["id"])
    finally:
        await conn.close()

    for cs in char_stats:
        cs["clips"] = clip_map.get(cs["slug"], {"clip_count": 0, "avg_similarity": 0})

    return {
        "source_analysis": {
            "project_name": project_name,
            "project_id": project["id"],
            "genre": project.get("genre"),
            "analyzed_at": datetime.now().isoformat(),
            "characters": char_stats,
            "source_videos": source_videos,
            "scenes": {
                "scene_count": scene_stats["scene_count"] if scene_stats else 0,
                "shot_count": scene_stats["shot_count"] if scene_stats else 0,
                "completed_shots": scene_stats["completed_shots"] if scene_stats else 0,
                "shots_with_video": scene_stats["shots_with_video"] if scene_stats else 0,
            },
            "readiness": {
                "has_characters": len(char_stats) > 0,
                "has_images": any(c["images"]["approved"] > 0 for c in char_stats),
                "has_source_video": len(source_videos) > 0,
                "has_scenes": (scene_stats["scene_count"] if scene_stats else 0) > 0,
                "characters_with_references": sum(1 for c in char_stats if c["reference_images"] > 0),
            },
        }
    }


# ── 2. Synthesize Context ───────────────────────────────────────────────


@analysis_router.post("/ingest/synthesize-context/{project_name}")
async def synthesize_context(project_name: str):
    """Synthesize design prompts and style guidance from ingested source material.

    Uses Ollama to analyze the project's characters, their approved images,
    and source material to generate refined design prompts and style preamble.

    Returns: {project_name, source_analysis, synthesis: {design_prompts, style_preamble, episode_themes, raw_response}}
    """
    # Get source analysis first
    analysis_resp = await source_analysis(project_name)
    sa = analysis_resp["source_analysis"]

    project = await _resolve_project(project_name)
    characters = await _get_project_characters(project_name)

    # Build context for LLM
    char_descriptions = []
    for ch in characters:
        slug = ch["slug"]
        counts = _count_dataset_images(slug)
        char_descriptions.append(
            f"- {ch['name']} (role: {ch.get('role', 'unknown')}, "
            f"{counts['approved']} approved images): "
            f"{ch.get('design_prompt', 'no design prompt')}"
        )

    prompt = f"""You are an anime production assistant analyzing a project for visual consistency.

Project: {project_name}
Genre: {project.get('genre', 'unknown')}
Premise: {project.get('premise', 'not specified')}

Characters:
{chr(10).join(char_descriptions)}

Based on this project's genre and characters, provide:

1. DESIGN_PROMPTS: For each character, write an optimized design prompt that would produce
   consistent, high-quality images. Include visual details like hair color, eye color, clothing,
   body type, and distinctive features. Format as JSON object mapping slug to prompt string.

2. STYLE_PREAMBLE: A single style description that should prefix all generation prompts for
   this project to maintain visual consistency (art style, lighting, color palette, mood).

3. EPISODE_THEMES: A JSON array of 3-5 thematic keywords that capture the project's tone
   (e.g., "dark fantasy", "cyberpunk noir", "action comedy").

Respond in this exact JSON format:
{{
  "design_prompts": {{"character_slug": "detailed design prompt..."}},
  "style_preamble": "art style description...",
  "episode_themes": ["theme1", "theme2", "theme3"]
}}

Return ONLY valid JSON, no markdown fences or explanation."""

    try:
        raw_response = await _ollama_generate(prompt, model="mistral:7b", max_tokens=4000)

        # Parse JSON from response
        synthesis = {"raw_response": raw_response}
        try:
            # Try to extract JSON from the response
            json_start = raw_response.find("{")
            json_end = raw_response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(raw_response[json_start:json_end])
                synthesis["design_prompts"] = parsed.get("design_prompts", {})
                synthesis["style_preamble"] = parsed.get("style_preamble", "")
                synthesis["episode_themes"] = parsed.get("episode_themes", [])
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse synthesis JSON for {project_name}")
            synthesis["design_prompts"] = {}
            synthesis["style_preamble"] = ""
            synthesis["episode_themes"] = []

    except Exception as e:
        logger.error(f"Context synthesis failed for {project_name}: {e}")
        synthesis = {
            "design_prompts": {},
            "style_preamble": "",
            "episode_themes": [],
            "raw_response": f"Synthesis failed: {e}",
        }

    return {
        "project_name": project_name,
        "source_analysis": sa,
        "synthesis": synthesis,
    }


# ── 3. Scene Timeline ───────────────────────────────────────────────────


@analysis_router.get("/ingest/timeline/{project_name}")
async def scene_timeline(project_name: str):
    """Get scene timeline from the scenes/shots tables for a project.

    Returns the structured scene breakdown with character presence,
    duration, and shot counts — matching the SceneTimeline TypeScript interface.
    """
    project = await _resolve_project(project_name)
    source_videos = _find_source_videos(project_name)
    source_url = source_videos[0]["path"] if source_videos else ""

    conn = await connect_direct()
    try:
        scenes = await conn.fetch("""
            SELECT s.id, s.scene_number, s.title, s.description, s.mood,
                   s.setting_description, s.actual_duration_seconds,
                   s.generation_status, s.episode_id,
                   e.episode_number
            FROM scenes s
            LEFT JOIN episodes e ON s.episode_id = e.id
            WHERE s.project_id = $1
            ORDER BY e.episode_number NULLS LAST, s.scene_number
        """, project["id"])

        total_duration = 0.0
        scene_list = []
        for sc in scenes:
            shots = await conn.fetch("""
                SELECT sh.id, sh.shot_number, sh.shot_type, sh.duration_seconds,
                       sh.status, sh.dialogue_character_slug, sh.dialogue_text,
                       sh.video_engine, sh.output_video_path
                FROM shots sh
                WHERE sh.scene_id = $1
                ORDER BY sh.shot_number
            """, sc["id"])

            # Collect unique characters in this scene
            char_slugs = set()
            for sh in shots:
                if sh["dialogue_character_slug"]:
                    char_slugs.add(sh["dialogue_character_slug"])

            duration = float(sc["actual_duration_seconds"] or 0)
            if not duration:
                duration = sum(float(sh["duration_seconds"] or 3.0) for sh in shots)
            total_duration += duration

            scene_list.append({
                "scene_id": sc["scene_number"] or len(scene_list) + 1,
                "start": total_duration - duration,
                "end": total_duration,
                "duration": round(duration, 1),
                "characters": list(char_slugs),
                "environment": sc["setting_description"] or (sc["description"] or "")[:100] or "",
                "mood": sc["mood"] or "",
                "title": sc["title"] or f"Scene {sc['scene_number']}",
                "shot_count": len(shots),
                "status": sc["generation_status"] or "draft",
                "episode_number": sc["episode_number"],
            })
    finally:
        await conn.close()

    return {
        "project_name": project_name,
        "source_url": source_url,
        "analyzed_at": datetime.now().isoformat(),
        "total_duration": round(total_duration, 1),
        "scene_count": len(scene_list),
        "scenes": scene_list,
    }


# ── 4. Voice Map ─────────────────────────────────────────────────────────


@analysis_router.get("/ingest/voice-map/{project_name}")
async def voice_map(project_name: str):
    """Get voice/dialogue segment map for a project.

    Returns dialogue segments from shots linked to characters,
    plus voice sample inventory from the voice_samples table.
    """
    project = await _resolve_project(project_name)
    source_videos = _find_source_videos(project_name)
    source_url = source_videos[0]["path"] if source_videos else ""

    conn = await connect_direct()
    try:
        # Get dialogue segments from shots
        segments_raw = await conn.fetch("""
            SELECT sh.id, sh.shot_number, sh.dialogue_text, sh.dialogue_character_slug,
                   sh.duration_seconds, s.scene_number
            FROM shots sh
            JOIN scenes s ON sh.scene_id = s.id
            WHERE s.project_id = $1
              AND sh.dialogue_text IS NOT NULL
              AND sh.dialogue_text != ''
            ORDER BY s.scene_number, sh.shot_number
        """, project["id"])

        # Get voice samples inventory
        voice_samples = await conn.fetch("""
            SELECT vs.id, vs.character_slug, vs.file_path, vs.duration_seconds,
                   vs.quality_score
            FROM voice_samples vs
            JOIN characters c ON REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = vs.character_slug
            WHERE c.project_id = $1
            ORDER BY vs.character_slug, vs.id
        """, project["id"])

        # Get voice synthesis jobs
        synth_jobs = await conn.fetch("""
            SELECT vsj.id, vsj.character_slug, vsj.status, vsj.engine
            FROM voice_synthesis_jobs vsj
            JOIN characters c ON REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = vsj.character_slug
            WHERE c.project_id = $1
            ORDER BY vsj.id DESC
            LIMIT 50
        """, project["id"])
    finally:
        await conn.close()

    # Build segments matching VoiceSegment interface
    segments = []
    cumulative_time = 0.0
    for seg in segments_raw:
        dur = float(seg["duration_seconds"] or 3.0)
        segments.append({
            "path": "",  # No extracted audio file yet
            "filename": f"scene{seg['scene_number']}_shot{seg['shot_number']}.wav",
            "start": round(cumulative_time, 2),
            "end": round(cumulative_time + dur, 2),
            "duration": round(dur, 2),
            "scene_id": seg["scene_number"],
            "character_slug": seg["dialogue_character_slug"],
            "text": seg["dialogue_text"],
        })
        cumulative_time += dur

    linked = sum(1 for s in segments if s["character_slug"])

    return {
        "project_name": project_name,
        "source_url": source_url,
        "analyzed_at": datetime.now().isoformat(),
        "total_segments": len(segments),
        "linked_segments": linked,
        "segments": segments,
        "voice_inventory": {
            "total_samples": len(voice_samples),
            "by_character": {},
        },
        "synthesis_jobs": [dict(j) for j in synth_jobs] if synth_jobs else [],
    }


# ── 5. Text Extraction ──────────────────────────────────────────────────


@analysis_router.get("/ingest/text/{project_name}")
async def text_extraction(project_name: str):
    """Extract text content from a project — dialogue from shots,
    scene descriptions, and subtitle files if available.

    Returns structured text entries matching the TextExtraction interface.
    """
    project = await _resolve_project(project_name)
    source_videos = _find_source_videos(project_name)
    source_url = source_videos[0]["path"] if source_videos else ""

    entries = []

    conn = await connect_direct()
    try:
        # Scene descriptions
        scenes = await conn.fetch("""
            SELECT scene_number, title, description, mood, setting_description
            FROM scenes WHERE project_id = $1
            ORDER BY scene_number
        """, project["id"])

        for sc in scenes:
            if sc["description"]:
                entries.append({
                    "text": sc["description"],
                    "type": "scene_description",
                    "start_time": None,
                    "end_time": None,
                    "source_frame": None,
                    "scene_number": sc["scene_number"],
                    "title": sc["title"],
                })

        # Shot dialogue
        shots = await conn.fetch("""
            SELECT sh.shot_number, sh.dialogue_text, sh.dialogue_character_slug,
                   sh.duration_seconds, s.scene_number
            FROM shots sh
            JOIN scenes s ON sh.scene_id = s.id
            WHERE s.project_id = $1
              AND sh.dialogue_text IS NOT NULL AND sh.dialogue_text != ''
            ORDER BY s.scene_number, sh.shot_number
        """, project["id"])

        for sh in shots:
            entries.append({
                "text": sh["dialogue_text"],
                "type": "dialogue",
                "start_time": None,
                "end_time": None,
                "source_frame": None,
                "character_slug": sh["dialogue_character_slug"],
                "scene_number": sh["scene_number"],
                "shot_number": sh["shot_number"],
            })

        # Storyline text
        storyline = await conn.fetchrow("""
            SELECT summary FROM storylines WHERE project_id = $1 ORDER BY updated_at DESC LIMIT 1
        """, project["id"])
        if storyline and storyline["summary"]:
            entries.append({
                "text": storyline["summary"],
                "type": "storyline",
                "start_time": None,
                "end_time": None,
                "source_frame": None,
            })
    finally:
        await conn.close()

    # Check for subtitle files alongside source videos
    for sv in source_videos:
        video_path = Path(sv["path"])
        for ext in (".srt", ".vtt", ".ass", ".ssa"):
            sub_path = video_path.with_suffix(ext)
            if sub_path.exists():
                try:
                    sub_text = sub_path.read_text(errors="replace")[:10000]
                    entries.append({
                        "text": sub_text,
                        "type": "subtitle_file",
                        "start_time": None,
                        "end_time": None,
                        "source_frame": sub_path.name,
                    })
                except Exception:
                    pass

    return {
        "project_name": project_name,
        "source_url": source_url,
        "analyzed_at": datetime.now().isoformat(),
        "total_entries": len(entries),
        "entries": entries,
    }
