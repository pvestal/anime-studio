"""Scene audio functions — download, overlay, mix, dialogue synthesis, auto-generate music."""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from packages.core.config import BASE_PATH

logger = logging.getLogger(__name__)

# ACE-Step music generation server
ACE_STEP_URL = "http://localhost:8440"
MUSIC_CACHE = BASE_PATH / "output" / "music_cache"
MUSIC_CACHE.mkdir(parents=True, exist_ok=True)

# Scene output directory (must match builder.py)
SCENE_OUTPUT_DIR = BASE_PATH.parent / "output" / "scenes"
SCENE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Audio cache directory
AUDIO_CACHE_DIR = SCENE_OUTPUT_DIR / "audio_cache"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def download_preview(url: str, scene_id: str) -> str:
    """Download a 30-sec Apple Music preview to the audio cache. Returns local path."""
    import httpx

    cache_path = AUDIO_CACHE_DIR / f"preview_{scene_id}.m4a"
    if cache_path.exists():
        return str(cache_path)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
        logger.info(f"Downloaded audio preview to {cache_path} ({len(resp.content)} bytes)")
        return str(cache_path)
    except Exception as e:
        logger.error(f"Failed to download audio preview: {e}")
        raise


async def overlay_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    fade_in: float = 1.0,
    fade_out: float = 2.0,
    start_offset: float = 0,
) -> str:
    """Overlay audio onto video using ffmpeg. Copies video stream, encodes audio as AAC.

    - fade_in / fade_out: seconds for audio fade
    - start_offset: skip N seconds into the audio before overlaying
    - Uses -shortest so output matches shorter of video/audio
    """
    # Build afade filter chain
    filters = []
    if start_offset > 0:
        filters.append(f"atrim=start={start_offset}")
        filters.append("asetpts=PTS-STARTPTS")
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in}")
    # We need video duration for fade-out positioning — probe it
    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await probe.communicate()
    video_duration = float(stdout.decode().strip()) if stdout.decode().strip() else 30.0
    if fade_out > 0:
        fade_out_start = max(0, video_duration - fade_out)
        filters.append(f"afade=t=out:st={fade_out_start}:d={fade_out}")

    filter_str = ",".join(filters) if filters else "anull"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", f"[1:a]{filter_str}[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio overlay failed: {stderr.decode()[-300:]}")

    logger.info(f"Audio overlay complete: {output_path}")
    return output_path


async def mix_scene_audio(
    video_path: str,
    output_path: str,
    dialogue_path: str | None = None,
    music_path: str | None = None,
    music_fade_in: float = 1.0,
    music_fade_out: float = 2.0,
    music_start_offset: float = 0,
    music_volume: float = 0.3,
) -> str:
    """Mix dialogue and/or music into a video. Single-pass ffmpeg when both exist."""
    if not dialogue_path and not music_path:
        return video_path

    if dialogue_path and music_path:
        # Both: 3-input ffmpeg with sidechaincompress for audio ducking.
        # Music automatically dips when dialogue is present and returns after.
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", video_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await probe.communicate()
        video_duration = float(stdout.decode().strip()) if stdout.decode().strip() else 30.0

        music_filters = []
        if music_start_offset > 0:
            music_filters.append(f"atrim=start={music_start_offset}")
            music_filters.append("asetpts=PTS-STARTPTS")
        music_filters.append(f"volume={music_volume}")
        if music_fade_in > 0:
            music_filters.append(f"afade=t=in:st=0:d={music_fade_in}")
        if music_fade_out > 0:
            fade_out_start = max(0, video_duration - music_fade_out)
            music_filters.append(f"afade=t=out:st={fade_out_start}:d={music_fade_out}")

        music_chain = ",".join(music_filters)

        # sidechaincompress: dialogue (sidechain input) controls music compression.
        # level_in=1: no input gain on music
        # threshold=0.02: trigger ducking at low dialogue levels (catches quiet speech)
        # ratio=6: compress music 6:1 when dialogue present (strong ducking)
        # attack=200: 200ms ramp-down (smooth entry)
        # release=1000: 1s recovery after dialogue stops
        # makeup=1: no makeup gain after compression
        filter_complex = (
            f"[2:a]{music_chain}[music];"
            f"[music][1:a]sidechaincompress="
            f"level_in=1:threshold=0.02:ratio=6:attack=200:release=1000:makeup=1[ducked];"
            f"[1:a][ducked]amix=inputs=2:duration=shortest:normalize=0[a]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dialogue_path,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_path,
        ]
    elif dialogue_path:
        # Dialogue only
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path, "-i", dialogue_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_path,
        ]
    else:
        # Music only — delegate to existing overlay_audio
        return await overlay_audio(
            video_path=video_path, audio_path=music_path,
            output_path=output_path, fade_in=music_fade_in,
            fade_out=music_fade_out, start_offset=music_start_offset,
        )

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio mix failed: {stderr.decode()[-300:]}")
    logger.info(f"Audio mix complete: {output_path}")
    return output_path


async def build_scene_dialogue(conn, scene_id) -> str | None:
    """Build combined dialogue WAV for a scene from per-shot dialogue fields."""
    shots = await conn.fetch(
        "SELECT dialogue_text, dialogue_character_slug, shot_number "
        "FROM shots WHERE scene_id = $1 AND dialogue_text IS NOT NULL "
        "AND dialogue_text != '' ORDER BY shot_number",
        scene_id,
    )
    if not shots:
        return None

    dialogue_list = [
        {"character_slug": sh["dialogue_character_slug"] or "", "text": sh["dialogue_text"]}
        for sh in shots
    ]

    try:
        from packages.voice_pipeline.synthesis import synthesize_scene_dialogue
        result = await synthesize_scene_dialogue(
            scene_id=str(scene_id),
            dialogue_list=dialogue_list,
            pause_seconds=0.5,
        )
        combined_path = result.get("combined_path")
        if combined_path:
            await conn.execute(
                "UPDATE scenes SET dialogue_audio_path = $2 WHERE id = $1",
                scene_id, combined_path,
            )
        return combined_path
    except Exception as e:
        logger.warning(f"Scene dialogue synthesis failed (non-fatal): {e}")
        return None


async def _auto_generate_scene_music(scene_id: str, mood: str, duration: float = 30.0) -> str | None:
    """Auto-generate music for a scene using ACE-Step. Returns path or None."""
    import urllib.request

    # Mood->caption mapping (matches audio_composition router)
    mood_prompts = {
        "tense": "dark suspenseful orchestral, low strings, building tension, minor key",
        "romantic": "gentle piano melody, soft strings, warm intimate, slow tempo",
        "seductive": "sensual jazz, soft saxophone, intimate atmosphere, slow groove",
        "intimate": "gentle piano melody, soft strings, warm romantic atmosphere, slow tempo",
        "action": "intense percussion, fast electronic, dramatic hits, driving rhythm",
        "melancholy": "slow piano, minor key, ambient pads, emotional strings",
        "comedic": "playful pizzicato, bouncy rhythm, lighthearted woodwinds",
        "threatening": "deep bass drones, dark orchestral, heavy percussion, menacing",
        "powerful": "epic orchestral, brass fanfare, powerful drums, dramatic crescendo",
        "desperate": "dissonant strings, erratic piano, anxious tempo, building dread",
        "vulnerable": "solo piano, fragile melody, sparse arrangement, melancholy",
        "peaceful": "ambient pads, gentle harp, nature sounds, meditative, slow",
        "ambient": "atmospheric pads, gentle textures, ethereal, floating",
    }
    caption = mood_prompts.get(mood, mood_prompts["ambient"])

    payload = json.dumps({
        "prompt": caption,
        "lyrics": "",
        "duration": duration,
        "format": "wav",
        "instrumental": True,
        "infer_steps": 60,
        "guidance_scale": 15.0,
    }).encode()

    req = urllib.request.Request(
        f"{ACE_STEP_URL}/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        task_id = result.get("task_id")
        if not task_id:
            return None
    except Exception:
        return None  # ACE-Step unavailable — non-fatal

    # Poll for completion (music gen takes ~20-70s)
    import time as _time
    start = _time.time()
    while (_time.time() - start) < 120:
        try:
            poll_req = urllib.request.Request(f"{ACE_STEP_URL}/status/{task_id}")
            poll_resp = urllib.request.urlopen(poll_req, timeout=10)
            status = json.loads(poll_resp.read())
            if status.get("status") == "completed" and status.get("output_path"):
                src = Path(status["output_path"])
                if src.exists():
                    dest = MUSIC_CACHE / f"scene_{scene_id}_{src.name}"
                    shutil.copy2(str(src), str(dest))
                    logger.info(f"Auto-generated music for scene {scene_id}: {dest.name}")
                    return str(dest)
            elif status.get("status") == "failed":
                logger.warning(f"ACE-Step generation failed for scene {scene_id}: {status.get('error')}")
                return None
        except Exception:
            pass
        await asyncio.sleep(5)

    logger.warning(f"ACE-Step generation timed out for scene {scene_id}")
    return None


async def apply_scene_audio(conn, scene_id, scene_video_path: str) -> str:
    """Build dialogue + download music + mix all audio into the scene video.

    Non-fatal: logs warnings on failure, never blocks generation.
    Returns the (possibly updated) video path.
    """
    try:
        # Build dialogue audio from shot fields
        dialogue_path = await build_scene_dialogue(conn, scene_id)

        # Get music: prefer ACE-Step generated, then Apple Music preview
        music_path = None
        scene_row = await conn.fetchrow(
            "SELECT audio_preview_url, audio_fade_in, audio_fade_out, "
            "audio_start_offset, generated_music_path "
            "FROM scenes WHERE id = $1", scene_id,
        )
        if scene_row and scene_row.get("generated_music_path"):
            gmp = Path(scene_row["generated_music_path"])
            if gmp.exists():
                music_path = str(gmp)
                logger.info(f"Scene {scene_id}: using ACE-Step generated music: {gmp.name}")
        if not music_path and scene_row and scene_row["audio_preview_url"]:
            try:
                music_path = await download_preview(scene_row["audio_preview_url"], str(scene_id))
            except Exception as dl_err:
                logger.warning(f"Music download failed (non-fatal): {dl_err}")
        if not music_path and scene_row:
            # Auto-generate music from scene mood if ACE-Step is available
            mood = scene_row.get("mood") or scene_row.get("audio_mood") or "ambient"
            try:
                music_path = await _auto_generate_scene_music(scene_id, mood)
            except Exception as gen_err:
                logger.warning(f"Auto music generation failed (non-fatal): {gen_err}")

        if not dialogue_path and not music_path:
            return scene_video_path

        output = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}_audio.mp4")
        await mix_scene_audio(
            video_path=scene_video_path,
            output_path=output,
            dialogue_path=dialogue_path,
            music_path=music_path,
            music_fade_in=scene_row["audio_fade_in"] or 1.0 if scene_row else 1.0,
            music_fade_out=scene_row["audio_fade_out"] or 2.0 if scene_row else 2.0,
            music_start_offset=scene_row["audio_start_offset"] or 0 if scene_row else 0,
        )
        os.replace(output, scene_video_path)

        if music_path:
            await conn.execute(
                "UPDATE scenes SET audio_preview_path = $2 WHERE id = $1",
                scene_id, music_path,
            )
        logger.info(f"Scene {scene_id}: audio applied (dialogue={'yes' if dialogue_path else 'no'}, music={'yes' if music_path else 'no'})")
    except Exception as e:
        logger.warning(f"apply_scene_audio failed (non-fatal): {e}")

    return scene_video_path
