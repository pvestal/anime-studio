"""Story package router — Characters, Projects, Storylines, World Settings."""

import asyncio, json, logging, re, urllib.request as _ur
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from packages.core.config import BASE_PATH, OLLAMA_URL
from packages.core.db import get_char_project_map, invalidate_char_cache, connect_direct
from packages.core.models import (
    CharacterCreate, ProjectCreate, ProjectUpdate,
    StorylineUpsert, WorldSettingsUpsert, StyleUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()
CHECKPOINTS_DIR = Path("/opt/ComfyUI/models/checkpoints")

_SLUG_SQL = """SELECT c.id, c.name, c.project_id FROM characters c
    WHERE REGEXP_REPLACE(LOWER(REPLACE(c.name,' ','_')),'[^a-z0-9_-]','','g')=$1
      AND c.project_id IS NOT NULL
    ORDER BY LENGTH(COALESCE(c.design_prompt,'')) DESC LIMIT 1"""

_SLUG_ID_SQL = """SELECT id FROM characters
    WHERE REGEXP_REPLACE(LOWER(REPLACE(name,' ','_')),'[^a-z0-9_-]','','g')=$1
      AND project_id IS NOT NULL
    ORDER BY LENGTH(COALESCE(design_prompt,'')) DESC LIMIT 1"""


def _extract_json_from_vision(raw: str) -> dict | None:
    """Extract a JSON object from vision model output."""
    if not raw:
        return None
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None


def _jload(val):
    """Parse a JSON string/None from a DB row."""
    return json.loads(val) if val else None


def _build_world_dict(ws):
    """Build world_settings response dict from a DB row."""
    return {
        "style_preamble": ws["style_preamble"], "art_style": ws["art_style"],
        "aesthetic": ws["aesthetic"], "color_palette": _jload(ws["color_palette"]),
        "cinematography": _jload(ws["cinematography"]),
        "world_location": _jload(ws["world_location"]),
        "time_period": ws["time_period"], "production_notes": ws["production_notes"],
        "known_issues": _jload(ws["known_issues"]),
        "negative_prompt_guidance": ws["negative_prompt_guidance"],
    }


def _dynamic_update(body, fields, params=None, idx=1):
    """Build SET clauses from a pydantic model. Returns (updates, params, next_idx)."""
    updates, params = [], params or []
    for field in fields:
        val = getattr(body, field)
        if val is not None:
            updates.append(f"{field} = ${idx}")
            params.append(val)
            idx += 1
    return updates, params, idx


_NARRATION_PROMPT = (
    "You are a character design expert. Given a character's name, design prompt, "
    "and project context, generate structured appearance data as JSON.\n\n"
    "Character: {character_name}\nDesign prompt: {design_prompt}\n"
    "Project: {project_name}\nProject style: {style_preamble}\n\n"
    "Generate a JSON object with these fields:\n"
    '- "species": what type of creature/being\n'
    '- "body_type": physical build description\n'
    '- "key_colors": object mapping body parts to colors\n'
    '- "key_features": array of 4-6 critical identifying visual features\n'
    '- "reference_character": real-world character reference if applicable\n'
    '- "style": the art style\n'
    '- "common_errors": array of known generation failure modes (optional)\n\n'
    "Return ONLY valid JSON, no explanation."
)

# ── Character endpoints ──────────────────────────────────────────────────

@router.get("/characters")
async def get_characters():
    """Get list of characters with datasets, including project info from DB."""
    char_map = await get_char_project_map()
    characters = []
    for slug, d in sorted(char_map.items(), key=lambda x: x[0]):
        img = BASE_PATH / slug / "images"
        characters.append({
            "name": d["name"], "slug": slug,
            "image_count": len(list(img.glob("*.png"))) if img.exists() else 0,
            "created_at": datetime.fromtimestamp(img.parent.stat().st_ctime).isoformat() if img.exists() else datetime.now().isoformat(),
            "project_name": d.get("project_name", ""), "design_prompt": d.get("design_prompt", ""),
            "default_style": d.get("default_style", ""), "checkpoint_model": d.get("checkpoint_model", ""),
            "cfg_scale": d.get("cfg_scale"), "steps": d.get("steps"), "resolution": d.get("resolution", ""),
        })
    return {"characters": characters}


@router.post("/characters")
async def create_character(character: CharacterCreate):
    """Create a new character: DB record + dataset directory."""
    safe_name = re.sub(r'[^a-z0-9_-]', '', character.name.lower().replace(' ', '_'))
    char_path = BASE_PATH / safe_name

    conn = await connect_direct()
    try:
        project = await conn.fetchrow(
            "SELECT id FROM projects WHERE name=$1", character.project_name)
        if not project:
            raise HTTPException(
                status_code=404, detail=f"Project '{character.project_name}' not found")

        existing = await conn.fetchrow(
            "SELECT id FROM characters WHERE "
            "REGEXP_REPLACE(LOWER(REPLACE(name,' ','_')),'[^a-z0-9_-]','','g')=$1 "
            "AND project_id=$2",
            safe_name, project["id"])
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Character '{character.name}' already exists in this project")

        char_id = await conn.fetchval(
            "INSERT INTO characters (name, project_id, design_prompt) "
            "VALUES($1, $2, $3) RETURNING id",
            character.name, project["id"], character.design_prompt or "")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create character '{character.name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

    (char_path / "images").mkdir(parents=True, exist_ok=True)
    approval_file = char_path / "approval_status.json"
    if not approval_file.exists():
        with open(approval_file, "w") as f:
            json.dump({}, f)

    invalidate_char_cache()
    logger.info(f"Created character '{character.name}' (id={char_id}) in project '{character.project_name}'")
    return {"message": f"Character '{character.name}' created", "slug": safe_name, "id": char_id}


@router.patch("/characters/{character_slug}")
async def update_character(character_slug: str, body: dict):
    """Update a character's design_prompt."""
    design_prompt = body.get("design_prompt")
    if design_prompt is None:
        raise HTTPException(status_code=400, detail="design_prompt is required")
    try:
        conn = await connect_direct()
        row = await conn.fetchrow(_SLUG_SQL, character_slug)
        if not row:
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")
        await conn.execute("UPDATE characters SET design_prompt=$1 WHERE id=$2", design_prompt.strip(), row["id"])
        await conn.close()
        invalidate_char_cache()
        logger.info(f"Updated design_prompt for {row['name']} (id={row['id']})")
        return {"message": f"Updated design_prompt for {row['name']}", "character_id": row["id"],
                "character_name": row["name"], "design_prompt": design_prompt.strip()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update character {character_slug}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/characters/{character_slug}/appearance")
async def get_character_appearance(character_slug: str):
    """Get structured appearance data for a character."""
    char_map = await get_char_project_map()
    if character_slug not in char_map:
        raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")
    info = char_map[character_slug]
    return {"character_name": info["name"], "slug": character_slug,
            "appearance_data": info.get("appearance_data", {}), "design_prompt": info.get("design_prompt", "")}


@router.put("/characters/{character_slug}/appearance")
async def update_character_appearance(character_slug: str, body: dict):
    """Update structured appearance_data for a character."""
    appearance_data = body.get("appearance_data")
    if appearance_data is None:
        raise HTTPException(status_code=400, detail="appearance_data is required")
    try:
        conn = await connect_direct()
        row = await conn.fetchrow(_SLUG_SQL, character_slug)
        if not row:
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")
        await conn.execute("UPDATE characters SET appearance_data=$1::jsonb WHERE id=$2",
                           json.dumps(appearance_data), row["id"])
        await conn.close()
        invalidate_char_cache()
        logger.info(f"Updated appearance_data for {row['name']} (id={row['id']})")
        return {"message": f"Updated appearance_data for {row['name']}", "appearance_data": appearance_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update appearance for {character_slug}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/characters/narrate-appearance")
async def narrate_character_appearance(body: dict):
    """Use LLM to auto-generate appearance_data from design prompts."""
    char_map = await get_char_project_map()
    save = body.get("save", False)
    if body.get("character_slug"):
        slug = body["character_slug"]
        if slug not in char_map:
            raise HTTPException(status_code=404, detail=f"Character '{slug}' not found")
        target_slugs = [slug]
    elif body.get("project_name"):
        target_slugs = [s for s, i in char_map.items() if i.get("project_name") == body["project_name"]]
        if not target_slugs:
            raise HTTPException(status_code=404, detail=f"No characters for project '{body['project_name']}'")
    else:
        raise HTTPException(status_code=400, detail="Provide character_slug or project_name")
    if body.get("missing_only", False):
        target_slugs = [s for s in target_slugs if not char_map[s].get("appearance_data")]
    results, conn = [], (await connect_direct()) if save else None
    for slug in target_slugs:
        info = char_map[slug]
        prompt = _NARRATION_PROMPT.format(
            character_name=info["name"], design_prompt=info.get("design_prompt") or "no design prompt",
            project_name=info.get("project_name", "unknown"),
            style_preamble=info.get("style_preamble") or "standard anime style")
        payload = json.dumps({"model": "gemma3:12b", "prompt": prompt, "stream": False,
                              "options": {"temperature": 0.3, "num_predict": 600}}).encode()
        try:
            req = _ur.Request(f"{OLLAMA_URL}/api/generate", data=payload,
                              headers={"Content-Type": "application/json"})
            raw = json.loads(_ur.urlopen(req, timeout=60).read()).get("response", "").strip()
            appearance = _extract_json_from_vision(raw)
            if appearance is None:
                results.append({"slug": slug, "name": info["name"], "status": "parse_error", "raw": raw[:200]})
                continue
            if save and conn:
                row = await conn.fetchrow(_SLUG_ID_SQL, slug)
                if row:
                    await conn.execute("UPDATE characters SET appearance_data=$1::jsonb WHERE id=$2",
                                       json.dumps(appearance), row["id"])
            results.append({"slug": slug, "name": info["name"], "status": "ok", "appearance_data": appearance})
        except Exception as e:
            logger.warning(f"Narration failed for {slug}: {e}")
            results.append({"slug": slug, "name": info["name"], "status": "error", "error": str(e)})
    if conn:
        await conn.close()
        invalidate_char_cache()
    return {"narrated": sum(1 for r in results if r["status"] == "ok"),
            "errors": sum(1 for r in results if r["status"] != "ok"), "results": results}

# ── Project endpoints ────────────────────────────────────────────────────

@router.get("/projects")
async def get_projects():
    """Get list of projects with their character counts."""
    try:
        conn = await connect_direct()
        rows = await conn.fetch("""SELECT p.id, p.name, p.default_style, COUNT(c.id) as char_count
            FROM projects p LEFT JOIN characters c ON c.project_id=p.id
            GROUP BY p.id, p.name, p.default_style ORDER BY p.name""")
        await conn.close()
        return {"projects": [{"id": r["id"], "name": r["name"], "default_style": r["default_style"],
                              "character_count": r["char_count"]} for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/checkpoints")
async def get_checkpoints():
    """List available checkpoint model files."""
    if not CHECKPOINTS_DIR.exists():
        return {"checkpoints": []}
    return {"checkpoints": [{"filename": f.name, "size_mb": round(f.stat().st_size / 1048576, 1)}
                            for f in sorted(CHECKPOINTS_DIR.iterdir())
                            if f.suffix == ".safetensors" and f.is_file()]}


@router.get("/projects/{project_id}")
async def get_project_detail(project_id: int):
    """Get full project detail including generation style and storyline."""
    try:
        conn = await connect_direct()
        row = await conn.fetchrow("""
            SELECT p.id,p.name,p.description,p.genre,p.status,p.default_style,p.premise,p.content_rating,
                   gs.checkpoint_model,gs.cfg_scale,gs.steps,gs.sampler,gs.scheduler,gs.width,gs.height,
                   gs.positive_prompt_template,gs.negative_prompt_template
            FROM projects p LEFT JOIN generation_styles gs ON gs.style_name=p.default_style
            WHERE p.id=$1""", project_id)
        if not row:
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        sl = await conn.fetchrow("""SELECT title,summary,theme,genre,target_audience,tone,humor_style,themes,story_arcs
            FROM storylines WHERE project_id=$1""", project_id)
        ws = await conn.fetchrow("SELECT * FROM world_settings WHERE project_id=$1", project_id)
        await conn.close()
        style = None
        if row["default_style"]:
            style = {k: (float(row[k]) if k == "cfg_scale" and row[k] else row[k])
                     for k in ("checkpoint_model", "cfg_scale", "steps", "sampler", "scheduler",
                               "width", "height", "positive_prompt_template", "negative_prompt_template")}
        storyline = None
        if sl:
            storyline = {k: sl[k] for k in ("title", "summary", "theme", "genre", "target_audience", "tone", "humor_style")}
            storyline["themes"] = list(sl["themes"]) if sl["themes"] else None
            storyline["story_arcs"] = json.loads(sl["story_arcs"]) if sl["story_arcs"] else None
        return {"project": {
            "id": row["id"], "name": row["name"], "description": row["description"],
            "genre": row["genre"], "status": row["status"], "default_style": row["default_style"],
            "premise": row["premise"], "content_rating": row["content_rating"],
            "style": style, "storyline": storyline,
            "world_settings": _build_world_dict(ws) if ws else None,
        }}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects")
async def create_project(body: ProjectCreate):
    """Create a new project with an auto-generated generation style."""
    style_name = re.sub(r'[^a-z0-9_]', '', body.name.lower().replace(' ', '_')) + "_style"
    try:
        conn = await connect_direct()
        if await conn.fetchval("SELECT style_name FROM generation_styles WHERE style_name=$1", style_name):
            style_name += "_" + str(int(datetime.now().timestamp()) % 10000)
        await conn.execute("""INSERT INTO generation_styles
            (style_name,checkpoint_model,cfg_scale,steps,sampler,width,height,
             positive_prompt_template,negative_prompt_template) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            style_name, body.checkpoint_model, body.cfg_scale, body.steps, body.sampler,
            body.width, body.height, body.positive_prompt_template, body.negative_prompt_template)
        pid = await conn.fetchval("""INSERT INTO projects (name,description,genre,status,default_style)
            VALUES($1,$2,$3,'active',$4) RETURNING id""", body.name, body.description, body.genre, style_name)
        await conn.close()
        logger.info(f"Created project '{body.name}' (id={pid}) with style '{style_name}'")
        return {"project_id": pid, "style_name": style_name, "message": f"Project '{body.name}' created"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}")
async def update_project(project_id: int, body: ProjectUpdate):
    """Update project metadata."""
    try:
        conn = await connect_direct()
        if not await conn.fetchrow("SELECT id FROM projects WHERE id=$1", project_id):
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        updates, params, idx = _dynamic_update(body, ("name", "description", "genre", "premise", "content_rating"))
        if not updates:
            await conn.close()
            return {"message": "No fields to update"}
        params.append(project_id)
        await conn.execute(f"UPDATE projects SET {','.join(updates)} WHERE id=${idx}", *params)
        await conn.close()
        logger.info(f"Updated project {project_id}: {','.join(updates)}")
        return {"message": f"Project {project_id} updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/storyline")
async def upsert_storyline(project_id: int, body: StorylineUpsert):
    """Create or update the storyline for a project."""
    try:
        conn = await connect_direct()
        if not await conn.fetchrow("SELECT id FROM projects WHERE id=$1", project_id):
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        existing = await conn.fetchrow("SELECT id FROM storylines WHERE project_id=$1", project_id)
        if existing:
            updates, params, idx = _dynamic_update(
                body, ("title", "summary", "theme", "genre", "target_audience", "tone", "humor_style"))
            if body.themes is not None:
                updates.append(f"themes=${idx}"); params.append(body.themes); idx += 1
            if body.story_arcs is not None:
                updates.append(f"story_arcs=${idx}::jsonb"); params.append(json.dumps(body.story_arcs)); idx += 1
            if updates:
                params.append(project_id)
                await conn.execute(f"UPDATE storylines SET {','.join(updates)} WHERE project_id=${idx}", *params)
        else:
            await conn.execute("""INSERT INTO storylines
                (project_id,title,summary,theme,genre,target_audience,tone,humor_style,themes,story_arcs)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)""",
                project_id, body.title, body.summary, body.theme, body.genre,
                body.target_audience, body.tone, body.humor_style,
                body.themes, json.dumps(body.story_arcs) if body.story_arcs else None)
        await conn.close()
        logger.info(f"Upserted storyline for project {project_id}")
        return {"message": f"Storyline for project {project_id} saved"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/style")
async def update_style(project_id: int, body: StyleUpdate):
    """Update the generation style for a project. Snapshots current style to style_history before applying changes."""
    try:
        conn = await connect_direct()
        row = await conn.fetchrow(
            "SELECT p.name, p.default_style FROM projects p WHERE p.id=$1", project_id)
        if not row:
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        sn = row["default_style"]
        project_name = row["name"]
        if not sn:
            await conn.close()
            raise HTTPException(status_code=400, detail="Project has no generation style")

        updates, params, idx = _dynamic_update(
            body, ("checkpoint_model", "cfg_scale", "steps", "sampler",
                   "width", "height", "positive_prompt_template", "negative_prompt_template"))
        if not updates:
            await conn.close()
            return {"message": "No fields to update"}

        # Snapshot current style before updating
        current = await conn.fetchrow(
            "SELECT checkpoint_model, cfg_scale, steps, sampler, scheduler, "
            "width, height, positive_prompt_template, negative_prompt_template "
            "FROM generation_styles WHERE style_name=$1", sn)
        if current:
            # Get generation stats for this checkpoint
            stats = await conn.fetchrow("""
                SELECT COUNT(*) as gen_count, AVG(quality_score) as avg_quality
                FROM generation_history
                WHERE project_name=$1 AND checkpoint_model=$2
                  AND quality_score IS NOT NULL
            """, project_name, current["checkpoint_model"])

            await conn.execute("""
                INSERT INTO style_history
                    (project_id, style_name, checkpoint_model, cfg_scale, steps,
                     sampler, scheduler, width, height,
                     positive_prompt_template, negative_prompt_template,
                     reason, generation_count, avg_quality_at_switch)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
                project_id, sn, current["checkpoint_model"],
                float(current["cfg_scale"]) if current["cfg_scale"] else None,
                current["steps"], current["sampler"], current["scheduler"],
                current["width"], current["height"],
                current["positive_prompt_template"], current["negative_prompt_template"],
                body.reason,
                stats["gen_count"] if stats else 0,
                float(stats["avg_quality"]) if stats and stats["avg_quality"] else None,
            )

        # Apply the update (unchanged logic)
        params.append(sn)
        await conn.execute(
            f"UPDATE generation_styles SET {','.join(updates)} WHERE style_name=${idx}", *params)
        await conn.close()
        invalidate_char_cache()

        old_checkpoint = current["checkpoint_model"] if current else None
        new_checkpoint = body.checkpoint_model
        logger.info(f"Updated style '{sn}' for project {project_id}: {','.join(updates)}")

        # Fire-and-forget Echo Brain memory storage
        if new_checkpoint and old_checkpoint and new_checkpoint != old_checkpoint:
            asyncio.create_task(_store_style_switch_memory(
                project_name, old_checkpoint, new_checkpoint, body.reason,
                stats["gen_count"] if stats else 0,
                float(stats["avg_quality"]) if stats and stats["avg_quality"] else None,
            ))

        return {"message": f"Generation style updated for project {project_id}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _store_style_switch_memory(
    project_name: str, old_ckpt: str, new_ckpt: str,
    reason: str | None, gen_count: int, avg_quality: float | None,
):
    """Fire-and-forget: store style switch fact in Echo Brain."""
    try:
        quality_str = f"{avg_quality:.0%}" if avg_quality else "N/A"
        content = (
            f"Project '{project_name}' switched checkpoint from '{old_ckpt}' to '{new_ckpt}' "
            f"on {datetime.now().strftime('%Y-%m-%d')}. "
            f"Stats with old checkpoint: {gen_count} generations, {quality_str} avg quality."
        )
        if reason:
            content += f" Reason: {reason}"
        payload = json.dumps({
            "method": "tools/call",
            "params": {"name": "store_memory", "arguments": {"content": content}},
        }).encode()
        req = _ur.Request(
            "http://localhost:8309/mcp", data=payload,
            headers={"Content-Type": "application/json"})
        _ur.urlopen(req, timeout=5)
        logger.info(f"Stored style switch memory for {project_name}")
    except Exception as e:
        logger.debug(f"Echo Brain memory store failed (non-fatal): {e}")


@router.get("/projects/{project_id}/style-history")
async def get_style_history(project_id: int):
    """Get past style snapshots with live per-checkpoint stats."""
    try:
        conn = await connect_direct()
        if not await conn.fetchrow("SELECT id FROM projects WHERE id=$1", project_id):
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        project_name = await conn.fetchval("SELECT name FROM projects WHERE id=$1", project_id)

        rows = await conn.fetch("""
            SELECT id, style_name, checkpoint_model, cfg_scale, steps, sampler, scheduler,
                   width, height, positive_prompt_template, negative_prompt_template,
                   switched_at, reason, generation_count, avg_quality_at_switch
            FROM style_history
            WHERE project_id=$1
            ORDER BY switched_at DESC
        """, project_id)

        history = []
        for r in rows:
            # Get live stats for this checkpoint from generation_history
            live = await conn.fetchrow("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE status = 'approved') as approved,
                       AVG(quality_score) FILTER (WHERE quality_score IS NOT NULL) as avg_quality
                FROM generation_history
                WHERE project_name=$1 AND checkpoint_model=$2
            """, project_name, r["checkpoint_model"])

            history.append({
                "id": r["id"],
                "checkpoint_model": r["checkpoint_model"],
                "cfg_scale": float(r["cfg_scale"]) if r["cfg_scale"] else None,
                "steps": r["steps"],
                "sampler": r["sampler"],
                "scheduler": r["scheduler"],
                "width": r["width"],
                "height": r["height"],
                "switched_at": r["switched_at"].isoformat() if r["switched_at"] else None,
                "reason": r["reason"],
                "generation_count": r["generation_count"],
                "avg_quality_at_switch": round(float(r["avg_quality_at_switch"]), 3) if r["avg_quality_at_switch"] else None,
                "live_total": live["total"] if live else 0,
                "live_approved": live["approved"] if live else 0,
                "live_avg_quality": round(float(live["avg_quality"]), 3) if live and live["avg_quality"] else None,
            })

        await conn.close()
        return {"history": history}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/style-stats")
async def get_style_stats(project_id: int):
    """Aggregated per-checkpoint quality stats for a project."""
    try:
        conn = await connect_direct()
        project_name = await conn.fetchval("SELECT name FROM projects WHERE id=$1", project_id)
        if not project_name:
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        rows = await conn.fetch("""
            SELECT
                checkpoint_model,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'approved') as approved,
                COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
                AVG(quality_score) FILTER (WHERE quality_score IS NOT NULL) as avg_quality,
                MIN(generated_at) as first_used,
                MAX(generated_at) as last_used
            FROM generation_history
            WHERE project_name = $1
              AND checkpoint_model IS NOT NULL
            GROUP BY checkpoint_model
            ORDER BY avg_quality DESC NULLS LAST
        """, project_name)

        await conn.close()
        return {
            "project_name": project_name,
            "checkpoints": [
                {
                    "checkpoint_model": r["checkpoint_model"],
                    "total": r["total"],
                    "approved": r["approved"],
                    "rejected": r["rejected"],
                    "approval_rate": round(r["approved"] / r["total"], 2) if r["total"] > 0 else 0,
                    "avg_quality": round(float(r["avg_quality"]), 3) if r["avg_quality"] else None,
                    "first_used": r["first_used"].isoformat() if r["first_used"] else None,
                    "last_used": r["last_used"].isoformat() if r["last_used"] else None,
                }
                for r in rows
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/world")
async def get_world_settings(project_id: int):
    """Get world settings for a project."""
    try:
        conn = await connect_direct()
        if not await conn.fetchrow("SELECT id FROM projects WHERE id=$1", project_id):
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        ws = await conn.fetchrow("SELECT * FROM world_settings WHERE project_id=$1", project_id)
        await conn.close()
        return {"world_settings": _build_world_dict(ws) if ws else None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/world")
async def upsert_world_settings(project_id: int, body: WorldSettingsUpsert):
    """Create or update world settings for a project."""
    try:
        conn = await connect_direct()
        if not await conn.fetchrow("SELECT id FROM projects WHERE id=$1", project_id):
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        existing = await conn.fetchrow("SELECT id FROM world_settings WHERE project_id=$1", project_id)
        text_f = ("style_preamble", "art_style", "aesthetic", "time_period", "production_notes", "negative_prompt_guidance")
        json_f = ("color_palette", "cinematography", "world_location", "known_issues")
        if existing:
            updates, params, idx = _dynamic_update(body, text_f)
            for field in json_f:
                val = getattr(body, field)
                if val is not None:
                    updates.append(f"{field}=${idx}::jsonb"); params.append(json.dumps(val)); idx += 1
            if updates:
                updates.append("updated_at=NOW()")
                params.append(project_id)
                await conn.execute(f"UPDATE world_settings SET {','.join(updates)} WHERE project_id=${idx}", *params)
        else:
            await conn.execute("""INSERT INTO world_settings
                (project_id,style_preamble,art_style,aesthetic,color_palette,cinematography,
                 world_location,time_period,production_notes,known_issues,negative_prompt_guidance)
                VALUES($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb,$8,$9,$10::jsonb,$11)""",
                project_id, body.style_preamble, body.art_style, body.aesthetic,
                json.dumps(body.color_palette) if body.color_palette else None,
                json.dumps(body.cinematography) if body.cinematography else None,
                json.dumps(body.world_location) if body.world_location else None,
                body.time_period, body.production_notes,
                json.dumps(body.known_issues) if body.known_issues else None,
                body.negative_prompt_guidance)
        await conn.close()
        invalidate_char_cache()
        logger.info(f"Upserted world_settings for project {project_id}")
        return {"message": f"World settings for project {project_id} saved"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
