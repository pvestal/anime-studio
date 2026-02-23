"""Story package router — Projects, Storylines, World Settings.

Character endpoints are in story_characters.py (included as sub-router).
"""

import asyncio, json, logging, re, urllib.request as _ur
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from packages.core.config import BASE_PATH, OLLAMA_URL
from packages.core.db import get_char_project_map, invalidate_char_cache, connect_direct
from packages.core.models import (
    ProjectCreate, ProjectUpdate,
    StorylineUpsert, WorldSettingsUpsert, StyleUpdate,
)

from .story_characters import router as characters_router

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(characters_router)

CHECKPOINTS_DIR = Path("/opt/ComfyUI/models/checkpoints")


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
    """List available checkpoint model files with model profile info."""
    from packages.core.model_profiles import get_model_profile
    if not CHECKPOINTS_DIR.exists():
        return {"checkpoints": []}
    results = []
    for f in sorted(CHECKPOINTS_DIR.iterdir()):
        if f.suffix != ".safetensors" or not f.is_file():
            continue
        profile = get_model_profile(f.name)
        results.append({
            "filename": f.name,
            "size_mb": round(f.stat().st_size / 1048576, 1),
            "style_label": profile.get("style_label", ""),
            "architecture": profile.get("architecture", ""),
            "prompt_format": profile.get("prompt_format", ""),
            "default_cfg": profile.get("default_cfg"),
            "default_steps": profile.get("default_steps"),
            "default_sampler": profile.get("default_sampler", ""),
        })
    return {"checkpoints": results}


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
