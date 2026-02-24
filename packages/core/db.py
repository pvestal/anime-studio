"""Database — connection pool, migrations, and cached queries.

Migrations have been split into db_migrations.py for modularity.
This module re-exports run_migrations for backward compatibility.
"""

import json
import logging
import time as _time

import asyncpg

from .config import DB_CONFIG

logger = logging.getLogger(__name__)

# Module-level pool reference
_pool: asyncpg.Pool | None = None

# Cache for character→project mapping from DB
_char_project_cache: dict = {}
_cache_time: float = 0


async def init_pool():
    """Create the asyncpg connection pool. Call once at startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        min_size=2,
        max_size=10,
    )
    logger.info(f"DB pool created: {DB_CONFIG['database']}@{DB_CONFIG['host']}")


async def get_pool() -> asyncpg.Pool:
    """Return the connection pool, initializing if needed."""
    global _pool
    if _pool is None:
        await init_pool()
    return _pool


async def get_connection():
    """Acquire a connection from the pool. Use as: async with get_connection() as conn:"""
    pool = await get_pool()
    return pool.acquire()


async def connect_direct() -> asyncpg.Connection:
    """Open a direct (non-pooled) connection. Caller must close it."""
    return await asyncpg.connect(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )


async def run_migrations():
    """Run schema migrations at startup. Delegates to db_migrations module."""
    from .db_migrations import run_migrations as _run_migrations_impl
    return await _run_migrations_impl()


async def log_model_change(
    action: str,
    checkpoint_model: str,
    previous_model: str | None = None,
    project_name: str | None = None,
    style_name: str | None = None,
    reason: str | None = None,
    changed_by: str = "system",
    metadata: dict | None = None,
) -> int | None:
    """Log a model change to the audit table. Fire-and-forget safe.

    Actions: 'switch', 'download', 'remove', 'config_update', 'profile_add'
    """
    try:
        conn = await connect_direct()
        await conn.execute("SET search_path TO public")
        row = await conn.fetchrow(
            """INSERT INTO model_audit_log
               (action, checkpoint_model, previous_model, project_name,
                style_name, reason, changed_by, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
               RETURNING id""",
            action, checkpoint_model, previous_model, project_name,
            style_name, reason, changed_by,
            json.dumps(metadata or {}),
        )
        await conn.close()
        logger.info(f"Model audit: {action} {checkpoint_model} (project={project_name})")
        return row["id"] if row else None
    except Exception as e:
        logger.warning(f"Model audit log failed (non-fatal): {e}")
        return None


async def get_char_project_map() -> dict:
    """Load character→project mapping from DB with generation style info. Cached for 60s."""
    global _char_project_cache, _cache_time
    if _char_project_cache and (_time.time() - _cache_time) < 60:
        return _char_project_cache

    try:
        conn = await connect_direct()
        rows = await conn.fetch("""
            SELECT c.name,
                   REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug,
                   c.design_prompt, c.appearance_data, p.name as project_name,
                   p.default_style,
                   gs.checkpoint_model, gs.cfg_scale, gs.steps,
                   gs.width, gs.height, gs.sampler, gs.scheduler,
                   gs.positive_prompt_template, gs.negative_prompt_template,
                   gs.model_architecture, gs.prompt_format,
                   ws.style_preamble
            FROM characters c
            JOIN projects p ON c.project_id = p.id
            LEFT JOIN generation_styles gs ON gs.style_name = p.default_style
            LEFT JOIN world_settings ws ON ws.project_id = p.id
            WHERE COALESCE(c.archived, false) = false
        """)
        await conn.close()

        mapping = {}
        for row in rows:
            slug = row["slug"]
            if slug not in mapping or len(row["design_prompt"] or "") > len(mapping[slug].get("design_prompt") or ""):
                appearance_raw = row["appearance_data"]
                appearance = json.loads(appearance_raw) if isinstance(appearance_raw, str) else (appearance_raw or {})
                mapping[slug] = {
                    "name": row["name"],
                    "slug": slug,
                    "project_name": row["project_name"],
                    "design_prompt": row["design_prompt"],
                    "appearance_data": appearance,
                    "default_style": row["default_style"],
                    "checkpoint_model": row["checkpoint_model"],
                    "cfg_scale": float(row["cfg_scale"]) if row["cfg_scale"] else None,
                    "steps": row["steps"],
                    "sampler": row["sampler"],
                    "scheduler": row["scheduler"],
                    "width": row["width"],
                    "height": row["height"],
                    "resolution": f"{row['width']}x{row['height']}" if row["width"] else None,
                    "positive_prompt_template": row["positive_prompt_template"],
                    "negative_prompt_template": row["negative_prompt_template"],
                    "style_preamble": row["style_preamble"],
                    "model_architecture": row["model_architecture"],
                    "prompt_format": row["prompt_format"],
                }
        _char_project_cache = mapping
        _cache_time = _time.time()
    except Exception as e:
        logger.warning(f"Failed to load char→project map: {e}")

    return _char_project_cache


async def get_approved_images_for_project(project_id: int) -> dict[str, list[str]]:
    """Get approved image names grouped by character slug, verified on disk.

    Queries the approvals table joined to characters (via slug derivation)
    to filter by project_id. Verifies each image file exists on disk.

    Returns:
        {slug: [image_name, ...]} sorted by quality descending within each slug.
        This is the exact format recommend_for_scene() expects.
    """
    from .config import BASE_PATH

    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT a.character_slug, a.image_name, COALESCE(a.quality_score, 0.5) as quality_score
            FROM approvals a
            JOIN characters c
              ON a.character_slug = REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g')
            WHERE c.project_id = $1
              AND a.image_name IS NOT NULL
            ORDER BY a.character_slug, a.quality_score DESC
        """, project_id)
    finally:
        await conn.close()

    result: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()

    for row in rows:
        slug = row["character_slug"]
        image_name = row["image_name"]

        # Deduplicate
        key = (slug, image_name)
        if key in seen:
            continue
        seen.add(key)

        # Verify file exists on disk
        img_path = BASE_PATH / slug / "images" / image_name
        if not img_path.exists():
            continue

        result.setdefault(slug, []).append(image_name)

    return result


def invalidate_char_cache():
    """Invalidate the character→project cache so it reloads on next access."""
    global _char_project_cache, _cache_time
    _char_project_cache = {}
    _cache_time = 0
