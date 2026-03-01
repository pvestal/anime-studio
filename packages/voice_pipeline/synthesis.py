"""Voice synthesis — multi-engine speech generation with scene integration.

Resolution order for voice engine:
1. RVC v2 model (highest quality, if trained)
2. GPT-SoVITS model (fast prototyping, if trained)
3. XTTS v2 voice clone (zero-shot from reference sample)
4. edge-tts with character's preset voice
5. edge-tts default voice
"""

import asyncio
import json
import logging
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from packages.core.config import BASE_PATH, OLLAMA_URL
from packages.core.db import connect_direct

logger = logging.getLogger(__name__)

VOICE_DATASETS = BASE_PATH.parent / "voice_datasets"
SOVITS_DIR = Path("/opt/GPT-SoVITS")
RVC_DIR = Path("/opt/rvc-v2")

# Default edge-tts voice when character has no preset
DEFAULT_EDGE_VOICE = "en-US-GuyNeural"

# Diverse voice pools for auto-assignment when characters lack voice_preset
EDGE_TTS_VOICE_POOL = {
    "male": [
        "en-US-GuyNeural",
        "en-US-ChristopherNeural",
        "en-US-EricNeural",
        "en-US-RogerNeural",
        "en-GB-RyanNeural",
        "en-AU-WilliamNeural",
    ],
    "female": [
        "en-US-JennyNeural",
        "en-US-AriaNeural",
        "en-US-MichelleNeural",
        "en-US-SaraNeural",
        "en-GB-SoniaNeural",
        "en-AU-NatashaNeural",
    ],
    "neutral": [
        "en-US-GuyNeural",
        "en-US-JennyNeural",
        "en-US-AriaNeural",
        "en-US-ChristopherNeural",
        "en-US-EricNeural",
        "en-US-MichelleNeural",
    ],
}

_FEMALE_KEYWORDS = {"female", "woman", "girl", "she", "her", "lady", "queen", "princess", "mother", "wife", "goddess", "maiden"}
_MALE_KEYWORDS = {"male", "man", "boy", "he", "him", "guy", "king", "prince", "father", "husband", "god", "lord"}


async def _get_voice_profile(character_slug: str) -> dict:
    """Load voice_profile JSONB from characters table."""
    conn = await connect_direct()
    try:
        raw = await conn.fetchval(
            "SELECT voice_profile FROM characters WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1 AND project_id IS NOT NULL",
            character_slug,
        )
        if raw:
            return json.loads(raw) if isinstance(raw, str) else raw
        return {}
    finally:
        await conn.close()


def _infer_gender(design_prompt: str) -> str:
    """Infer gender from design_prompt keywords. Returns 'male', 'female', or 'neutral'."""
    if not design_prompt:
        return "neutral"
    words = set(design_prompt.lower().split())
    female_hits = len(words & _FEMALE_KEYWORDS)
    male_hits = len(words & _MALE_KEYWORDS)
    if female_hits > male_hits:
        return "female"
    elif male_hits > female_hits:
        return "male"
    return "neutral"


async def _auto_assign_edge_voice(character_slug: str) -> str:
    """Pick a deterministic, diverse edge-tts voice for a character and persist it.

    Uses hash(slug) to pick from the appropriate gender pool so the same
    character always gets the same voice across runs.
    """
    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT voice_profile, design_prompt FROM characters "
            "WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1 "
            "AND project_id IS NOT NULL",
            character_slug,
        )
        if not row:
            return DEFAULT_EDGE_VOICE

        profile = json.loads(row["voice_profile"]) if row["voice_profile"] and isinstance(row["voice_profile"], str) else (row["voice_profile"] or {})

        # If already assigned, return it
        if profile.get("voice_preset"):
            return profile["voice_preset"]

        gender = _infer_gender(row["design_prompt"] or "")
        pool = EDGE_TTS_VOICE_POOL[gender]
        voice = pool[hash(character_slug) % len(pool)]

        # Persist to DB so it's stable
        profile["voice_preset"] = voice
        profile["voice_auto_assigned"] = True
        await conn.execute(
            "UPDATE characters SET voice_profile = $2::jsonb "
            "WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1 "
            "AND project_id IS NOT NULL",
            character_slug, json.dumps(profile),
        )
        logger.info(f"Auto-assigned edge-tts voice '{voice}' ({gender}) to {character_slug}")
        return voice
    finally:
        await conn.close()


async def _resolve_character_slug(slug: str) -> str:
    """Resolve a short slug (e.g. 'mei') to the full slug (e.g. 'mei_kobayashi').

    Shots may store abbreviated slugs. This checks voice_datasets directories
    and the characters table to find the full slug.
    """
    # If voice_datasets dir exists with this exact slug, use it
    if (VOICE_DATASETS / slug / "samples").is_dir():
        return slug

    # Check if any voice_datasets dir starts with this slug
    for d in VOICE_DATASETS.iterdir():
        if d.is_dir() and d.name.startswith(slug + "_"):
            return d.name

    # Fallback: query DB for a character whose computed slug starts with this
    conn = await connect_direct()
    try:
        full_slug = await conn.fetchval(
            """SELECT REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g')
               FROM characters
               WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') LIKE $1 || '%'
               AND project_id IS NOT NULL
               LIMIT 1""",
            slug,
        )
        return full_slug or slug
    finally:
        await conn.close()


async def synthesize_dialogue(
    character_slug: str,
    text: str,
    engine: str | None = None,
    output_dir: Path | None = None,
) -> dict:
    """Generate speech from text using the best available voice for a character.

    Args:
        character_slug: Character identifier
        text: Text to speak
        engine: Force specific engine ('rvc', 'sovits', 'edge-tts'), or None for auto
        output_dir: Where to save output WAV, defaults to voice_datasets/{slug}/synthesis/

    Returns:
        dict with output_path, engine_used, duration_seconds
    """
    # Resolve short slugs (e.g. "mei" → "mei_kobayashi")
    character_slug = await _resolve_character_slug(character_slug)
    profile = await _get_voice_profile(character_slug)
    if output_dir is None:
        output_dir = VOICE_DATASETS / character_slug / "synthesis"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"synth_{uuid.uuid4().hex[:8]}.wav"

    # Determine engine to use
    if engine is None:
        # Respect explicit tts_model preference in voice_profile (e.g. "edge-tts")
        preferred = profile.get("tts_model")
        if preferred:
            engine = preferred
        elif profile.get("rvc_model_path") and Path(profile["rvc_model_path"]).exists():
            engine = "rvc"
        elif profile.get("sovits_model_path") and Path(profile["sovits_model_path"]).exists():
            engine = "sovits"
        elif _has_xtts_samples(character_slug):
            engine = "xtts"
        else:
            engine = "edge-tts"

    # Auto-assign a diverse voice if falling back to edge-tts with no preset
    if engine == "edge-tts" and not profile.get("voice_preset"):
        voice = await _auto_assign_edge_voice(character_slug)
        profile["voice_preset"] = voice

    success = False
    if engine == "rvc":
        success = await _synthesize_rvc(profile, text, output_path)
    elif engine == "sovits":
        success = await _synthesize_sovits(profile, text, output_path)
    elif engine == "xtts":
        success = await _synthesize_xtts(character_slug, text, output_path)
    elif engine == "edge-tts":
        success = await _synthesize_edge_tts(profile, text, output_path)

    if not success and engine != "edge-tts":
        # Fallback to edge-tts
        engine = "edge-tts"
        success = await _synthesize_edge_tts(profile, text, output_path)

    if not success:
        return {"error": "All synthesis engines failed"}

    # Get output duration
    duration = 0.0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(result.stdout.strip()) if result.stdout.strip() else 0
    except Exception:
        pass

    return {
        "output_path": str(output_path),
        "engine_used": engine,
        "duration_seconds": round(duration, 2),
        "character_slug": character_slug,
        "text": text,
    }


async def _synthesize_rvc(profile: dict, text: str, output_path: Path) -> bool:
    """Synthesize via RVC v2: edge-tts → source audio → RVC conversion."""
    rvc_model = profile.get("rvc_model_path")
    if not rvc_model or not Path(rvc_model).exists():
        return False

    # Step 1: Generate source audio with edge-tts
    source_path = output_path.with_suffix(".source.wav")
    edge_voice = profile.get("voice_preset", DEFAULT_EDGE_VOICE)

    try:
        proc = await asyncio.create_subprocess_exec(
            "edge-tts", "--voice", edge_voice, "--text", text,
            "--write-media", str(source_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)
    except Exception as e:
        logger.warning(f"edge-tts source generation failed: {e}")
        return False

    if not source_path.exists():
        return False

    # Step 2: Run RVC voice conversion
    try:
        cmd = [
            str(RVC_DIR / "venv" / "bin" / "python"),
            str(RVC_DIR / "tools" / "infer_cli.py"),
            "--model_path", rvc_model,
            "--input_path", str(source_path),
            "--output_path", str(output_path),
            "--f0method", "rmvpe",
            "--index_rate", "0.75",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=str(RVC_DIR),
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "0"},
        )

        source_path.unlink(missing_ok=True)

        if result.returncode == 0 and output_path.exists():
            return True
        logger.warning(f"RVC inference failed: {result.stderr[:500]}")
        return False

    except Exception as e:
        logger.warning(f"RVC synthesis failed: {e}")
        source_path.unlink(missing_ok=True)
        return False


async def _synthesize_sovits(profile: dict, text: str, output_path: Path) -> bool:
    """Synthesize via GPT-SoVITS using reference audio."""
    sovits_model = profile.get("sovits_model_path")
    ref_audio = profile.get("ref_audio")

    if not sovits_model or not Path(sovits_model).exists():
        return False
    if not ref_audio or not Path(ref_audio).exists():
        return False

    try:
        cmd = [
            str(SOVITS_DIR / "venv" / "bin" / "python"),
            str(SOVITS_DIR / "GPT_SoVITS" / "inference_cli.py"),
            "--model_path", sovits_model,
            "--ref_audio", ref_audio,
            "--text", text,
            "--output_path", str(output_path),
            "--language", "en",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=str(SOVITS_DIR),
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "0"},
        )

        if result.returncode == 0 and output_path.exists():
            return True
        logger.warning(f"SoVITS inference failed: {result.stderr[:500]}")
        return False

    except Exception as e:
        logger.warning(f"SoVITS synthesis failed: {e}")
        return False


def _has_xtts_samples(character_slug: str) -> bool:
    """Check if character has approved voice samples for XTTS cloning."""
    samples_dir = VOICE_DATASETS / character_slug / "samples"
    if not samples_dir.is_dir():
        return False
    wavs = list(samples_dir.glob("*.wav"))
    return len(wavs) >= 1


def _pick_xtts_reference(character_slug: str) -> Path | None:
    """Pick the best reference sample for XTTS (prefer 3-10s clips)."""
    samples_dir = VOICE_DATASETS / character_slug / "samples"
    if not samples_dir.is_dir():
        return None
    wavs = sorted(samples_dir.glob("*.wav"))
    if not wavs:
        return None
    # Prefer a mid-length sample (3-10s) — just pick the first one that exists
    # since they were already curated via diarization + approval
    return wavs[0]


async def _synthesize_xtts(character_slug: str, text: str, output_path: Path) -> bool:
    """Synthesize via XTTS v2 zero-shot voice cloning using python3.11."""
    ref_wav = _pick_xtts_reference(character_slug)
    if not ref_wav:
        logger.warning(f"No XTTS reference sample for {character_slug}")
        return False

    # XTTS v2 is installed on system python3.11, not the venv python3.12
    # We call it via subprocess with a small inline script
    script = f"""
import sys, os
os.environ.setdefault("MECAB_RCFILE", "/usr/local/etc/mecabrc")
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=True)
tts.tts_to_file(
    text={text!r},
    speaker_wav={str(ref_wav)!r},
    language="ja",
    file_path={str(output_path)!r},
)
"""

    try:
        proc = await asyncio.create_subprocess_exec(
            "python3.11", "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "MECAB_RCFILE": "/usr/local/etc/mecabrc"},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode == 0 and output_path.exists():
            logger.info(f"XTTS synthesis OK for {character_slug}: {output_path.name}")
            return True
        logger.warning(f"XTTS synthesis failed (rc={proc.returncode}): {stderr.decode()[:500]}")
        return False

    except asyncio.TimeoutError:
        logger.warning(f"XTTS synthesis timed out for {character_slug}")
        return False
    except Exception as e:
        logger.warning(f"XTTS synthesis error: {e}")
        return False


async def _synthesize_edge_tts(profile: dict, text: str, output_path: Path) -> bool:
    """Synthesize using edge-tts with character's preset voice or default."""
    voice = profile.get("voice_preset", DEFAULT_EDGE_VOICE)

    try:
        proc = await asyncio.create_subprocess_exec(
            "edge-tts", "--voice", voice, "--text", text,
            "--write-media", str(output_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)
        return output_path.exists()
    except Exception as e:
        logger.warning(f"edge-tts failed: {e}")
        return False


async def synthesize_scene_dialogue(
    scene_id: str,
    dialogue_list: list[dict],
    pause_seconds: float = 0.5,
) -> dict:
    """Synthesize all dialogue lines for a scene and concatenate with pauses.

    dialogue_list: [{"character_slug": "mario", "text": "It's-a me!"}, ...]
    """
    output_dir = VOICE_DATASETS / "_scenes" / scene_id
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    wav_files = []

    for i, line in enumerate(dialogue_list):
        slug = line.get("character_slug", "")
        text = line.get("text", "")
        if not text:
            continue

        result = await synthesize_dialogue(
            character_slug=slug,
            text=text,
            engine=line.get("engine"),
            output_dir=output_dir,
        )
        results.append(result)

        if "output_path" in result:
            wav_files.append(result["output_path"])

    if not wav_files:
        return {"error": "No dialogue synthesized successfully"}

    # Create silence pad
    silence_path = output_dir / "silence.wav"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i",
         f"anullsrc=r=22050:cl=mono:d={pause_seconds}",
         "-acodec", "pcm_s16le", str(silence_path), "-y"],
        capture_output=True, timeout=10,
    )

    # Build concat list interleaving dialogue with pauses
    concat_list = output_dir / "dialogue_concat.txt"
    with open(concat_list, "w") as f:
        for i, wav in enumerate(wav_files):
            f.write(f"file '{wav}'\n")
            if i < len(wav_files) - 1 and silence_path.exists():
                f.write(f"file '{silence_path}'\n")

    # Concatenate
    combined_path = output_dir / "scene_dialogue.wav"
    subprocess.run(
        ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-acodec", "pcm_s16le", str(combined_path), "-y"],
        capture_output=True, timeout=60,
    )

    silence_path.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)

    # Get total duration
    duration = 0.0
    if combined_path.exists():
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(combined_path)],
                capture_output=True, text=True, timeout=10,
            )
            duration = float(result.stdout.strip()) if result.stdout.strip() else 0
        except Exception:
            pass

    # Record in DB
    conn = await connect_direct()
    try:
        for r in results:
            if "output_path" in r:
                job_id = f"synth_{uuid.uuid4().hex[:8]}"
                await conn.execute("""
                    INSERT INTO voice_synthesis_jobs
                        (job_id, scene_id, character_slug, engine, text,
                         output_path, duration_seconds, status, created_at, completed_at)
                    VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, 'completed', NOW(), NOW())
                """, job_id, scene_id, r.get("character_slug", ""),
                    r.get("engine_used", ""), r.get("text", ""),
                    r.get("output_path", ""), r.get("duration_seconds", 0))
    finally:
        await conn.close()

    return {
        "scene_id": scene_id,
        "dialogue_count": len(results),
        "combined_path": str(combined_path) if combined_path.exists() else None,
        "total_duration_seconds": round(duration, 2),
        "lines": results,
    }


async def generate_dialogue_from_story(
    scene_id: str,
    description: str,
    characters: list[str],
) -> list[dict]:
    """Use LLM (gemma3 via Ollama) to write dialogue for a scene.

    Returns list of {"character_slug": str, "text": str} ready for synthesis.
    """
    import httpx

    char_list = ", ".join(characters)
    prompt = f"""Write short dialogue for an anime scene.

Scene description: {description}
Characters present: {char_list}

Write 3-6 lines of dialogue. Output ONLY a JSON array where each element has "character" (name) and "text" (spoken line).
Example: [{{"character": "Mario", "text": "Let's-a go!"}}]

Keep lines short (1-2 sentences). Match character personalities. No narration."""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json={
                "model": "gemma3:12b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7},
            })
            resp.raise_for_status()
            text = resp.json().get("response", "")

        # Parse JSON from response (may be wrapped in markdown code block)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        dialogue = json.loads(text)
        if not isinstance(dialogue, list):
            return []

        # Convert character names to slugs
        import re
        results = []
        for line in dialogue:
            name = line.get("character", "")
            slug = re.sub(r'[^a-z0-9_-]', '', name.lower().replace(' ', '_'))
            results.append({
                "character_slug": slug,
                "character_name": name,
                "text": line.get("text", ""),
            })
        return results

    except Exception as e:
        logger.error(f"Dialogue generation failed: {e}")
        return []


async def get_voice_models(character_slug: str) -> dict:
    """Get available voice models/options for a character."""
    profile = await _get_voice_profile(character_slug)

    models = {
        "character_slug": character_slug,
        "available_engines": [],
        "preferred_engine": None,
        "voice_preset": profile.get("voice_preset"),
    }

    if profile.get("rvc_model_path") and Path(profile["rvc_model_path"]).exists():
        models["available_engines"].append({
            "engine": "rvc",
            "model_path": profile["rvc_model_path"],
            "quality": "production",
        })
        models["preferred_engine"] = "rvc"

    if profile.get("sovits_model_path") and Path(profile["sovits_model_path"]).exists():
        models["available_engines"].append({
            "engine": "sovits",
            "model_path": profile["sovits_model_path"],
            "quality": "prototype",
        })
        if not models["preferred_engine"]:
            models["preferred_engine"] = "sovits"

    if _has_xtts_samples(character_slug):
        ref = _pick_xtts_reference(character_slug)
        samples_dir = VOICE_DATASETS / character_slug / "samples"
        models["available_engines"].append({
            "engine": "xtts",
            "reference_sample": str(ref) if ref else None,
            "total_samples": len(list(samples_dir.glob("*.wav"))),
            "quality": "clone",
        })
        if not models["preferred_engine"]:
            models["preferred_engine"] = "xtts"

    # edge-tts always available
    models["available_engines"].append({
        "engine": "edge-tts",
        "voice": profile.get("voice_preset", DEFAULT_EDGE_VOICE),
        "quality": "fallback",
    })
    if not models["preferred_engine"]:
        models["preferred_engine"] = "edge-tts"

    return models


async def synthesize_episode_dialogue(episode_id: str) -> dict:
    """Synthesize dialogue for all scenes in an episode that lack dialogue audio.

    Queries scenes via episode_scenes join, ordered by position. For each scene
    missing a dialogue_audio_path (or whose file no longer exists), calls
    build_scene_dialogue from the scene_audio module.

    Returns summary with per-scene results.
    """
    from packages.scene_generation.scene_audio import build_scene_dialogue

    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT es.scene_id, es.position, s.dialogue_audio_path, s.title
            FROM episode_scenes es
            JOIN scenes s ON es.scene_id = s.id
            WHERE es.episode_id = $1::uuid
            ORDER BY es.position
        """, episode_id)

        if not rows:
            return {"error": "No scenes found for episode", "episode_id": episode_id}

        scenes_processed = 0
        scenes_skipped = 0
        scenes_failed = 0
        results = []

        for row in rows:
            scene_id = row["scene_id"]
            existing = row["dialogue_audio_path"]

            # Skip if audio file already exists on disk
            if existing and Path(existing).exists():
                scenes_skipped += 1
                results.append({
                    "scene_id": str(scene_id),
                    "position": row["position"],
                    "title": row["title"],
                    "status": "skipped",
                    "reason": "dialogue_audio_path exists",
                })
                continue

            try:
                dialogue_path = await build_scene_dialogue(conn, scene_id)
                if dialogue_path:
                    scenes_processed += 1
                    results.append({
                        "scene_id": str(scene_id),
                        "position": row["position"],
                        "title": row["title"],
                        "status": "synthesized",
                        "dialogue_audio_path": dialogue_path,
                    })
                else:
                    scenes_skipped += 1
                    results.append({
                        "scene_id": str(scene_id),
                        "position": row["position"],
                        "title": row["title"],
                        "status": "skipped",
                        "reason": "no dialogue in shots",
                    })
            except Exception as e:
                scenes_failed += 1
                results.append({
                    "scene_id": str(scene_id),
                    "position": row["position"],
                    "title": row["title"],
                    "status": "failed",
                    "error": str(e),
                })
                logger.warning(f"Dialogue synthesis failed for scene {scene_id}: {e}")

        return {
            "episode_id": episode_id,
            "scenes_processed": scenes_processed,
            "scenes_skipped": scenes_skipped,
            "scenes_failed": scenes_failed,
            "total_scenes": len(rows),
            "results": results,
        }
    finally:
        await conn.close()
