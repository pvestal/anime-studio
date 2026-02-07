"""
Scene Orchestrator
Coordinates all generation agents to produce complete scene outputs.
"""

import json
import logging
import time
from typing import Optional, List, Dict
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor

import sys
sys.path.insert(0, '/opt/tower-anime-production')

from services.story_engine.story_manager import StoryManager
from services.story_engine.change_propagation import ChangePropagator
from services.story_engine.agents.writing_agent import WritingAgent
from services.story_engine.agents.visual_agent import VisualAgent
from services.story_engine.agents.audio_agent import AudioAgent, generate_scene_audio_sync
from services.story_engine.agents.compositor import Compositor

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "RP78eIrW7cI2jYvL5akt1yurE",
}


class SceneOrchestrator:
    """
    Coordinates the full scene generation pipeline.

    Workflow:
    1. WritingAgent generates dialogue and narration
    2. Store dialogue in DB
    3. VisualAgent generates keyframes/video
    4. AudioAgent generates TTS and music
    5. Compositor assembles final output
    6. Update scene status throughout

    Supports partial regeneration based on scopes:
    - writing: Just dialogue/narration
    - visual: Just images/video
    - audio: Just TTS/music
    - composition: Just final assembly
    - all: Complete regeneration
    """

    def __init__(self):
        self.story_manager = StoryManager()
        self.propagator = ChangePropagator()
        self.writing_agent = WritingAgent()
        self.visual_agent = VisualAgent()
        self.audio_agent = AudioAgent()
        self.compositor = Compositor()

    def generate_scene(self, scene_id: str, scopes: Optional[List[str]] = None) -> dict:
        """
        Generate or regenerate a scene.

        Args:
            scene_id: UUID string of the scene
            scopes: List of generation scopes to run. None = all.
                   Options: ['writing', 'visual', 'audio', 'composition']

        Returns:
            {
                "scene_id": str,
                "outputs": {
                    "dialogue": dict,      # From WritingAgent
                    "visuals": dict,       # From VisualAgent
                    "audio": dict,         # From AudioAgent
                    "final_video": dict    # From Compositor
                },
                "timings": dict,           # Time taken for each step
                "status": str,             # final status
                "errors": list             # Any errors encountered
            }
        """
        if scopes is None:
            scopes = ['writing', 'visual', 'audio', 'composition']

        result = {
            "scene_id": scene_id,
            "outputs": {},
            "timings": {},
            "status": "started",
            "errors": []
        }

        # Update scene status
        self._update_scene_status(scene_id, "generating")

        try:
            # 1. Writing Generation
            if 'writing' in scopes:
                start = time.time()
                try:
                    logger.info(f"Generating script for scene {scene_id}")
                    dialogue_output = self.writing_agent.generate_scene_script(scene_id)
                    result["outputs"]["dialogue"] = dialogue_output

                    # Store dialogue in DB
                    if dialogue_output.get("dialogue"):
                        self._store_dialogue(scene_id, dialogue_output)

                    result["timings"]["writing"] = time.time() - start
                except Exception as e:
                    logger.error(f"Writing generation failed: {e}")
                    result["errors"].append(f"Writing: {str(e)}")
                    dialogue_output = None
            else:
                # Load existing dialogue for other agents
                dialogue_output = self._load_dialogue(scene_id)

            # 2. Visual Generation
            if 'visual' in scopes:
                start = time.time()
                try:
                    logger.info(f"Generating visuals for scene {scene_id}")
                    visual_output = self.visual_agent.generate_scene_visuals(scene_id)
                    result["outputs"]["visuals"] = visual_output
                    result["timings"]["visual"] = time.time() - start
                except Exception as e:
                    logger.error(f"Visual generation failed: {e}")
                    result["errors"].append(f"Visual: {str(e)}")
                    visual_output = None
            else:
                visual_output = self._load_visual_assets(scene_id)

            # 3. Audio Generation
            if 'audio' in scopes and dialogue_output:
                start = time.time()
                try:
                    logger.info(f"Generating audio for scene {scene_id}")
                    dialogue_data = dialogue_output.get("dialogue", [])
                    audio_output = generate_scene_audio_sync(scene_id, dialogue_data)
                    result["outputs"]["audio"] = audio_output
                    result["timings"]["audio"] = time.time() - start
                except Exception as e:
                    logger.error(f"Audio generation failed: {e}")
                    result["errors"].append(f"Audio: {str(e)}")
                    audio_output = None
            else:
                audio_output = self._load_audio_assets(scene_id)

            # 4. Final Composition
            if 'composition' in scopes:
                start = time.time()
                try:
                    logger.info(f"Composing final video for scene {scene_id}")

                    # Gather assets
                    visual_assets = []
                    if visual_output and visual_output.get("assets"):
                        visual_assets = visual_output["assets"]

                    audio_path = None
                    if audio_output and audio_output.get("audio_path"):
                        audio_path = audio_output["audio_path"]

                    dialogue_data = []
                    if dialogue_output and dialogue_output.get("dialogue"):
                        dialogue_data = dialogue_output["dialogue"]

                    # Compose
                    final_output = self.compositor.compose_scene(
                        scene_id,
                        visual_assets,
                        audio_path,
                        dialogue_data
                    )
                    result["outputs"]["final_video"] = final_output
                    result["timings"]["composition"] = time.time() - start

                    # Store final asset path in DB
                    if final_output.get("video_path"):
                        self._store_final_asset(scene_id, final_output["video_path"])

                except Exception as e:
                    logger.error(f"Composition failed: {e}")
                    result["errors"].append(f"Composition: {str(e)}")

            # Update final status
            if result["errors"]:
                result["status"] = "partial"
                self._update_scene_status(scene_id, "partial")
            else:
                result["status"] = "complete"
                self._update_scene_status(scene_id, "complete")

        except Exception as e:
            logger.error(f"Scene generation failed: {e}")
            result["status"] = "failed"
            result["errors"].append(str(e))
            self._update_scene_status(scene_id, "failed")

        return result

    def generate_episode(self, episode_id: str) -> dict:
        """Generate all scenes in an episode."""
        results = {
            "episode_id": episode_id,
            "scenes": [],
            "total_time": 0,
            "success_count": 0,
            "failure_count": 0
        }

        start_time = time.time()

        # Get all scenes for episode
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, scene_number
                    FROM scenes
                    WHERE episode_id = %s::uuid
                    ORDER BY scene_number
                """, (episode_id,))
                scenes = cur.fetchall()

        # Generate each scene
        for scene in scenes:
            scene_id = str(scene["id"])
            logger.info(f"Generating episode {episode_id} scene {scene['scene_number']}")

            scene_result = self.generate_scene(scene_id)
            results["scenes"].append(scene_result)

            if scene_result["status"] == "complete":
                results["success_count"] += 1
            else:
                results["failure_count"] += 1

        # Optionally compose full episode video
        if results["success_count"] > 0:
            scene_videos = []
            for idx, scene_result in enumerate(results["scenes"]):
                if scene_result.get("outputs", {}).get("final_video", {}).get("video_path"):
                    scene_videos.append({
                        "scene_id": scene_result["scene_id"],
                        "video_path": scene_result["outputs"]["final_video"]["video_path"],
                        "order": idx
                    })

            if scene_videos:
                episode_output = self.compositor.compose_episode(episode_id, scene_videos)
                results["episode_video"] = episode_output

        results["total_time"] = time.time() - start_time
        return results

    def process_queue(self, limit: int = 10) -> List[dict]:
        """
        Process pending items from the generation queue.

        First processes any pending changes, then works through queued generation jobs.
        """
        results = []

        # First, process any pending change propagations
        self.propagator.process_pending_changes()

        # Now process generation queue
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get queued jobs with row locking
                cur.execute("""
                    SELECT * FROM scene_generation_queue
                    WHERE status = 'queued'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                """, (limit,))
                jobs = cur.fetchall()

                for job in jobs:
                    job = dict(job)
                    scene_id = str(job["scene_id"])
                    scope = job.get("generation_scope", "all")

                    # Mark as processing
                    cur.execute("""
                        UPDATE scene_generation_queue
                        SET status = 'processing', started_at = NOW()
                        WHERE id = %s
                    """, (job["id"],))
                    conn.commit()

                    # Generate scene with specified scope
                    scopes = ['writing', 'visual', 'audio', 'composition'] if scope == "all" else [scope]

                    try:
                        result = self.generate_scene(scene_id, scopes)
                        results.append(result)

                        # Mark job complete
                        cur.execute("""
                            UPDATE scene_generation_queue
                            SET status = 'complete', completed_at = NOW()
                            WHERE id = %s
                        """, (job["id"],))
                    except Exception as e:
                        logger.error(f"Queue processing failed for job {job['id']}: {e}")
                        # Mark job failed
                        cur.execute("""
                            UPDATE scene_generation_queue
                            SET status = 'failed', error = %s, completed_at = NOW()
                            WHERE id = %s
                        """, (str(e), job["id"]))
                        results.append({
                            "scene_id": scene_id,
                            "status": "failed",
                            "error": str(e)
                        })

                    conn.commit()

        return results

    def _update_scene_status(self, scene_id: str, status: str) -> None:
        """Update scene generation status in DB."""
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE scenes
                    SET generation_status = %s, updated_at = NOW()
                    WHERE id = %s::uuid
                """, (status, scene_id))
                conn.commit()

    def _store_dialogue(self, scene_id: str, dialogue_output: dict) -> None:
        """Store generated dialogue in the scenes table."""
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE scenes
                    SET dialogue = %s, updated_at = NOW()
                    WHERE id = %s::uuid
                """, (json.dumps(dialogue_output["dialogue"]), scene_id))
                conn.commit()

    def _load_dialogue(self, scene_id: str) -> Optional[dict]:
        """Load existing dialogue from DB."""
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT dialogue FROM scenes WHERE id = %s::uuid
                """, (scene_id,))
                result = cur.fetchone()
                if result and result["dialogue"]:
                    return {"dialogue": result["dialogue"]}
        return None

    def _store_final_asset(self, scene_id: str, video_path: str) -> None:
        """Store final video asset path in scene_assets table."""
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO scene_assets (scene_id, asset_type, file_path, generation_params)
                    VALUES (%s::uuid, 'final_video', %s, %s)
                    ON CONFLICT (scene_id, asset_type) DO UPDATE
                    SET file_path = EXCLUDED.file_path, created_at = NOW()
                """, (scene_id, video_path, json.dumps({"generated_by": "orchestrator"})))
                conn.commit()

    def _load_visual_assets(self, scene_id: str) -> Optional[dict]:
        """Load existing visual assets from DB."""
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT file_path, generation_params
                    FROM scene_assets
                    WHERE scene_id = %s::uuid AND asset_type IN ('image', 'video')
                    ORDER BY created_at
                """, (scene_id,))
                results = cur.fetchall()
                if results:
                    return {"assets": [r["file_path"] for r in results]}
        return None

    def _load_audio_assets(self, scene_id: str) -> Optional[dict]:
        """Load existing audio assets from DB."""
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT file_path, generation_params
                    FROM scene_assets
                    WHERE scene_id = %s::uuid AND asset_type = 'audio'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (scene_id,))
                result = cur.fetchone()
                if result:
                    return {"audio_path": result["file_path"]}
        return None