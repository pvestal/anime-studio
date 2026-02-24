"""Story package — Character CRUD sub-router.

Extracted from story/router.py.  Character listing, creation, update,
appearance data, and LLM-driven narration endpoints.
"""

import json, logging, re, urllib.request as _ur
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.core.config import BASE_PATH, OLLAMA_URL
from packages.core.db import get_char_project_map, invalidate_char_cache, connect_direct
from packages.core.models import CharacterCreate

logger = logging.getLogger(__name__)
router = APIRouter()

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

    # Fetch per-character generation history checkpoints
    gen_checkpoints: dict[str, list[dict]] = {}
    try:
        conn = await connect_direct()
        gen_rows = await conn.fetch("""
            SELECT character_slug, checkpoint_model, COUNT(*) as count
            FROM generation_history
            WHERE checkpoint_model IS NOT NULL AND checkpoint_model != ''
            GROUP BY character_slug, checkpoint_model
            ORDER BY character_slug, count DESC
        """)
        await conn.close()
        for row in gen_rows:
            slug = row["character_slug"]
            if slug not in gen_checkpoints:
                gen_checkpoints[slug] = []
            gen_checkpoints[slug].append({
                "checkpoint": row["checkpoint_model"],
                "count": row["count"],
            })
    except Exception as e:
        logger.warning(f"Failed to fetch generation checkpoints: {e}")

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
            "generation_checkpoints": gen_checkpoints.get(slug, []),
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


@router.get("/characters/{character_slug}/detail")
async def get_character_detail(character_slug: str):
    """Get full character profile with all columns."""
    try:
        conn = await connect_direct()
        row = await conn.fetchrow("""
            SELECT c.id, c.name, c.description, c.design_prompt, c.traits, c.age,
                   c.appearance_data, c.personality, c.background, c.role,
                   c.character_role, c.personality_tags, c.relationships,
                   c.voice_profile, c.lora_trigger, c.lora_path,
                   c.created_at, c.updated_at, c.project_id,
                   p.name AS project_name
            FROM characters c
            LEFT JOIN projects p ON p.id = c.project_id
            WHERE REGEXP_REPLACE(LOWER(REPLACE(c.name,' ','_')),'[^a-z0-9_-]','','g')=$1
              AND c.project_id IS NOT NULL
            ORDER BY LENGTH(COALESCE(c.design_prompt,'')) DESC LIMIT 1
        """, character_slug)
        await conn.close()
        if not row:
            raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")

        def _parse_jsonb(val):
            if val is None:
                return None
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    return val
            return val

        return {
            "id": row["id"],
            "name": row["name"],
            "slug": character_slug,
            "project_id": row["project_id"],
            "project_name": row["project_name"],
            "description": row["description"],
            "design_prompt": row["design_prompt"],
            "age": row["age"],
            "role": row["role"],
            "character_role": row["character_role"],
            "personality": row["personality"],
            "background": row["background"],
            "personality_tags": row["personality_tags"],
            "traits": _parse_jsonb(row["traits"]),
            "appearance_data": _parse_jsonb(row["appearance_data"]),
            "relationships": _parse_jsonb(row["relationships"]),
            "voice_profile": _parse_jsonb(row["voice_profile"]),
            "lora_trigger": row["lora_trigger"],
            "lora_path": row["lora_path"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get character detail {character_slug}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_PATCH_ALLOWED = {
    "design_prompt": "text",
    "description": "text",
    "personality": "text",
    "background": "text",
    "role": "text",
    "character_role": "text",
    "age": "int",
    "personality_tags": "text[]",
    "traits": "jsonb",
    "appearance_data": "jsonb",
    "relationships": "jsonb",
    "voice_profile": "jsonb",
    "archived": "bool",
}


@router.patch("/characters/{character_slug}")
async def update_character(character_slug: str, body: dict):
    """Update character fields. Accepts any combination of allowed fields."""
    updates = {k: v for k, v in body.items() if k in _PATCH_ALLOWED}
    if not updates:
        raise HTTPException(status_code=400, detail=f"No valid fields provided. Allowed: {list(_PATCH_ALLOWED.keys())}")

    try:
        conn = await connect_direct()
        row = await conn.fetchrow(_SLUG_SQL, character_slug)
        if not row:
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")

        set_parts = []
        params = []
        idx = 1
        for field, value in updates.items():
            ftype = _PATCH_ALLOWED[field]
            if ftype == "text":
                set_parts.append(f"{field}=${idx}")
                params.append(value.strip() if isinstance(value, str) else value)
            elif ftype == "int":
                set_parts.append(f"{field}=${idx}")
                params.append(int(value) if value is not None else None)
            elif ftype == "bool":
                set_parts.append(f"{field}=${idx}")
                params.append(bool(value))
            elif ftype == "jsonb":
                set_parts.append(f"{field}=${idx}::jsonb")
                params.append(json.dumps(value) if value is not None else None)
            elif ftype == "text[]":
                set_parts.append(f"{field}=${idx}::text[]")
                params.append(value)
            idx += 1

        set_parts.append(f"updated_at=NOW()")
        sql = f"UPDATE characters SET {', '.join(set_parts)} WHERE id=${idx}"
        params.append(row["id"])

        await conn.execute(sql, *params)
        await conn.close()
        invalidate_char_cache()
        logger.info(f"Updated {list(updates.keys())} for {row['name']} (id={row['id']})")
        return {
            "message": f"Updated {list(updates.keys())} for {row['name']}",
            "character_id": row["id"],
            "character_name": row["name"],
            "updated_fields": list(updates.keys()),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update character {character_slug}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/characters/{character_slug}/archive")
async def archive_character(character_slug: str, body: dict = {}):
    """Archive or unarchive a character. Body: {"archived": true/false}"""
    archived = body.get("archived", True)
    try:
        conn = await connect_direct()
        row = await conn.fetchrow(_SLUG_SQL, character_slug)
        if not row:
            await conn.close()
            raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")
        await conn.execute("UPDATE characters SET archived=$1, updated_at=NOW() WHERE id=$2",
                           bool(archived), row["id"])
        await conn.close()
        invalidate_char_cache()
        action = "archived" if archived else "unarchived"
        logger.info(f"{action} character {row['name']} (id={row['id']})")
        return {"message": f"Character '{row['name']}' {action}", "archived": bool(archived)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to archive character {character_slug}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/characters/archived")
async def get_archived_characters():
    """List archived characters."""
    try:
        conn = await connect_direct()
        rows = await conn.fetch("""
            SELECT c.name,
                   REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug,
                   p.name as project_name, c.id
            FROM characters c
            JOIN projects p ON c.project_id = p.id
            WHERE c.archived = true
            ORDER BY p.name, c.name
        """)
        await conn.close()
        return {"characters": [{"id": r["id"], "name": r["name"], "slug": r["slug"],
                                "project_name": r["project_name"]} for r in rows]}
    except Exception as e:
        logger.error(f"Failed to list archived characters: {e}")
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
