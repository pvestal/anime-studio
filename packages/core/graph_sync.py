"""Graph Sync — sync relational anime_production data into Apache AGE graph.

Uses MERGE for idempotent upserts. All functions are safe to call repeatedly.

The graph lives in anime_production DB as 'anime_graph' with AGE extension.
AGE Cypher is invoked via SQL: SELECT * FROM cypher('anime_graph', $$ ... $$) AS (r agtype);

asyncpg requires SET search_path per connection to include ag_catalog.
"""

import json
import logging
from pathlib import Path

import asyncpg

from .config import DB_CONFIG, BASE_PATH

logger = logging.getLogger(__name__)

GRAPH_NAME = "anime_graph"


async def _get_conn() -> asyncpg.Connection:
    """Get a direct connection with AGE search_path configured.

    statement_cache_size=0 is required because AGE uses custom types (agtype)
    that asyncpg's prepared statement cache can't handle.
    """
    conn = await asyncpg.connect(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        statement_cache_size=0,
    )
    await conn.execute('SET search_path = ag_catalog, "$user", public')
    return conn


async def _cypher(conn: asyncpg.Connection, query: str) -> list:
    """Execute a Cypher query and return results as list of agtype strings."""
    # Count RETURN columns to build the AS clause
    # AGE requires: SELECT * FROM cypher(...) AS (col1 agtype, col2 agtype, ...)
    sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $cypher${query}$cypher$) AS (result agtype)"
    try:
        rows = await conn.fetch(sql)
        return [row["result"] for row in rows]
    except Exception as e:
        logger.error(f"Cypher query failed: {e}\nQuery: {query[:200]}")
        raise


async def _cypher_multi(conn: asyncpg.Connection, query: str, columns: list[str]) -> list[dict]:
    """Execute a Cypher query with multiple RETURN columns."""
    col_def = ", ".join(f"{c} agtype" for c in columns)
    sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $cypher${query}$cypher$) AS ({col_def})"
    try:
        rows = await conn.fetch(sql)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Cypher multi-column query failed: {e}\nQuery: {query[:200]}")
        raise


async def _cypher_void(conn: asyncpg.Connection, query: str):
    """Execute a Cypher query that returns nothing (CREATE/MERGE without RETURN)."""
    sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $cypher${query}$cypher$) AS (result agtype)"
    try:
        await conn.fetch(sql)
    except Exception as e:
        logger.error(f"Cypher void query failed: {e}\nQuery: {query[:200]}")
        raise


def _esc(value) -> str:
    """Escape a value for embedding in Cypher string literals."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # String: escape single quotes and backslashes
    s = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


# ── Sync Functions ──────────────────────────────────────────────────────


async def sync_projects(conn: asyncpg.Connection | None = None) -> int:
    """Upsert Project vertices from projects table."""
    close_conn = conn is None
    if conn is None:
        conn = await _get_conn()

    try:
        rows = await conn.fetch("""
            SELECT p.id, p.name, p.default_style, p.content_rating, p.premise
            FROM projects p
        """)

        count = 0
        for row in rows:
            props = {
                "db_id": row["id"],
                "name": row["name"],
                "default_style": row["default_style"],
                "content_rating": row["content_rating"],
                "premise": row["premise"],
            }
            prop_sets = ", ".join(
                f"p.{k} = {_esc(v)}" for k, v in props.items() if k != "name" and v is not None
            )
            query = f"""
                MERGE (p:Project {{name: {_esc(row['name'])}}})
                SET {prop_sets}
                RETURN p
            """
            await _cypher(conn, query)
            count += 1

        logger.info(f"graph_sync: synced {count} projects")
        return count
    finally:
        if close_conn:
            await conn.close()


async def sync_characters(conn: asyncpg.Connection | None = None) -> int:
    """Upsert Character vertices + BELONGS_TO edges to their Projects."""
    close_conn = conn is None
    if conn is None:
        conn = await _get_conn()

    try:
        rows = await conn.fetch("""
            SELECT c.id, c.name, c.project_id, c.role, c.design_prompt, c.appearance_data,
                   REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug,
                   p.name as project_name
            FROM characters c
            JOIN projects p ON c.project_id = p.id
        """)

        count = 0
        for row in rows:
            appearance = row["appearance_data"]
            if isinstance(appearance, str):
                try:
                    appearance = json.loads(appearance)
                except (json.JSONDecodeError, TypeError):
                    appearance = {}
            appearance = appearance or {}

            species = appearance.get("species", "")
            body_type = appearance.get("body_type", "")
            key_colors = appearance.get("key_colors", "")
            key_features = appearance.get("key_features", "")

            # Merge Character vertex
            query = f"""
                MERGE (c:Character {{slug: {_esc(row['slug'])}}})
                SET c.name = {_esc(row['name'])},
                    c.db_id = {_esc(row['id'])},
                    c.species = {_esc(species)},
                    c.body_type = {_esc(body_type)},
                    c.key_colors = {_esc(key_colors)},
                    c.key_features = {_esc(key_features)},
                    c.role = {_esc(row['role'])}
                RETURN c
            """
            await _cypher(conn, query)

            # Merge BELONGS_TO edge
            query = f"""
                MATCH (c:Character {{slug: {_esc(row['slug'])}}}),
                      (p:Project {{name: {_esc(row['project_name'])}}})
                MERGE (c)-[r:BELONGS_TO]->(p)
                SET r.role = {_esc(row['role'])}
                RETURN r
            """
            await _cypher(conn, query)
            count += 1

        logger.info(f"graph_sync: synced {count} characters")
        return count
    finally:
        if close_conn:
            await conn.close()


async def sync_checkpoints(conn: asyncpg.Connection | None = None) -> int:
    """Upsert Checkpoint vertices from generation_styles + USES_CHECKPOINT edges to Projects."""
    close_conn = conn is None
    if conn is None:
        conn = await _get_conn()

    try:
        rows = await conn.fetch("""
            SELECT gs.style_name, gs.checkpoint_model, gs.model_architecture, gs.prompt_format,
                   gs.cfg_scale, gs.steps, gs.sampler, gs.width, gs.height,
                   p.name as project_name
            FROM generation_styles gs
            LEFT JOIN projects p ON p.default_style = gs.style_name
        """)

        count = 0
        for row in rows:
            # Merge Checkpoint vertex (keyed on checkpoint_model)
            query = f"""
                MERGE (ck:Checkpoint {{checkpoint_model: {_esc(row['checkpoint_model'])}}})
                SET ck.style_name = {_esc(row['style_name'])},
                    ck.architecture = {_esc(row['model_architecture'])},
                    ck.prompt_format = {_esc(row['prompt_format'])},
                    ck.cfg = {_esc(row['cfg_scale'] or 7)},
                    ck.steps = {_esc(row['steps'] or 25)},
                    ck.sampler = {_esc(row['sampler'])},
                    ck.width = {_esc(row['width'] or 768)},
                    ck.height = {_esc(row['height'] or 768)}
                RETURN ck
            """
            await _cypher(conn, query)

            # Link to project if exists
            if row["project_name"]:
                query = f"""
                    MATCH (ck:Checkpoint {{checkpoint_model: {_esc(row['checkpoint_model'])}}}),
                          (p:Project {{name: {_esc(row['project_name'])}}})
                    MERGE (p)-[r:USES_CHECKPOINT]->(ck)
                    RETURN r
                """
                await _cypher(conn, query)

            count += 1

        logger.info(f"graph_sync: synced {count} checkpoints")
        return count
    finally:
        if close_conn:
            await conn.close()


async def sync_generation_history(conn: asyncpg.Connection | None = None) -> int:
    """Sync generation_history → Image vertices + DEPICTS/GENERATED_WITH/REVIEWED_AS edges."""
    close_conn = conn is None
    if conn is None:
        conn = await _get_conn()

    try:
        rows = await conn.fetch("""
            SELECT gh.id, gh.character_slug, gh.project_name, gh.checkpoint_model,
                   gh.quality_score, gh.status, gh.artifact_path, gh.cfg_scale,
                   gh.steps, gh.sampler, gh.solo, gh.generated_at,
                   gh.correction_of
            FROM generation_history gh
            WHERE gh.character_slug IS NOT NULL
        """)

        count = 0
        for row in rows:
            img_id = f"gh_{row['id']}"
            filename = Path(row["artifact_path"]).name if row["artifact_path"] else img_id

            # Merge Image vertex
            query = f"""
                MERGE (i:Image {{img_id: {_esc(img_id)}}})
                SET i.filename = {_esc(filename)},
                    i.status = {_esc(row['status'])},
                    i.quality_score = {_esc(row['quality_score'])},
                    i.checkpoint_model = {_esc(row['checkpoint_model'])},
                    i.character_slug = {_esc(row['character_slug'])},
                    i.solo = {_esc(row['solo'])},
                    i.generated_at = {_esc(str(row['generated_at']) if row['generated_at'] else None)}
                RETURN i
            """
            await _cypher(conn, query)

            # DEPICTS edge → Character
            if row["character_slug"]:
                query = f"""
                    MATCH (i:Image {{img_id: {_esc(img_id)}}}),
                          (c:Character {{slug: {_esc(row['character_slug'])}}})
                    MERGE (i)-[r:DEPICTS]->(c)
                    RETURN r
                """
                try:
                    await _cypher(conn, query)
                except Exception:
                    pass  # character may not exist in graph yet

            # GENERATED_WITH edge → Checkpoint
            if row["checkpoint_model"]:
                query = f"""
                    MATCH (i:Image {{img_id: {_esc(img_id)}}}),
                          (ck:Checkpoint {{checkpoint_model: {_esc(row['checkpoint_model'])}}})
                    MERGE (i)-[r:GENERATED_WITH]->(ck)
                    SET r.cfg = {_esc(row['cfg_scale'])},
                        r.steps = {_esc(row['steps'])},
                        r.sampler = {_esc(row['sampler'])}
                    RETURN r
                """
                try:
                    await _cypher(conn, query)
                except Exception:
                    pass  # checkpoint may not exist in graph yet

            # REGENERATED_FROM edge (correction chain)
            if row["correction_of"]:
                parent_id = f"gh_{row['correction_of']}"
                query = f"""
                    MATCH (child:Image {{img_id: {_esc(img_id)}}}),
                          (parent:Image {{img_id: {_esc(parent_id)}}})
                    MERGE (child)-[r:REGENERATED_FROM]->(parent)
                    RETURN r
                """
                try:
                    await _cypher(conn, query)
                except Exception:
                    pass  # parent may not exist

            count += 1

        logger.info(f"graph_sync: synced {count} generation history images")
        return count
    finally:
        if close_conn:
            await conn.close()


async def sync_scenes(conn: asyncpg.Connection | None = None) -> int:
    """Sync scenes + shots → Scene/Shot vertices + edges."""
    close_conn = conn is None
    if conn is None:
        conn = await _get_conn()

    try:
        # Scenes
        scene_rows = await conn.fetch("""
            SELECT s.id::text as scene_id, s.title, s.mood, s.location, s.scene_number,
                   p.name as project_name
            FROM scenes s
            JOIN projects p ON s.project_id = p.id
        """)

        scene_count = 0
        for row in scene_rows:
            query = f"""
                MERGE (s:Scene {{scene_id: {_esc(row['scene_id'])}}})
                SET s.title = {_esc(row['title'])},
                    s.mood = {_esc(row['mood'])},
                    s.location = {_esc(row['location'])},
                    s.scene_number = {_esc(row['scene_number'])}
                RETURN s
            """
            await _cypher(conn, query)
            scene_count += 1

        # Shots
        shot_rows = await conn.fetch("""
            SELECT sh.id::text as shot_id, sh.scene_id::text as scene_id,
                   sh.shot_number, sh.shot_type, sh.duration_seconds,
                   sh.generation_prompt, sh.quality_score, sh.status,
                   sh.dialogue_character_slug
            FROM shots sh
        """)

        shot_count = 0
        for row in shot_rows:
            query = f"""
                MERGE (sh:Shot {{shot_id: {_esc(row['shot_id'])}}})
                SET sh.shot_number = {_esc(row['shot_number'])},
                    sh.shot_type = {_esc(row['shot_type'])},
                    sh.duration = {_esc(row['duration_seconds'])},
                    sh.prompt = {_esc(row['generation_prompt'])},
                    sh.quality_score = {_esc(row['quality_score'])},
                    sh.status = {_esc(row['status'])}
                RETURN sh
            """
            await _cypher(conn, query)

            # PART_OF edge → Scene
            if row["scene_id"]:
                query = f"""
                    MATCH (sh:Shot {{shot_id: {_esc(row['shot_id'])}}}),
                          (s:Scene {{scene_id: {_esc(row['scene_id'])}}})
                    MERGE (sh)-[r:PART_OF]->(s)
                    SET r.shot_order = {_esc(row['shot_number'])}
                    RETURN r
                """
                await _cypher(conn, query)

            # APPEARS_IN edge for dialogue character
            if row["dialogue_character_slug"]:
                query = f"""
                    MATCH (c:Character {{slug: {_esc(row['dialogue_character_slug'])}}}),
                          (sh:Shot {{shot_id: {_esc(row['shot_id'])}}})
                    MERGE (c)-[r:APPEARS_IN]->(sh)
                    RETURN r
                """
                try:
                    await _cypher(conn, query)
                except Exception:
                    pass

            shot_count += 1

        # SCENE_IN edges for episodes
        ep_scene_rows = await conn.fetch("""
            SELECT es.scene_id::text as scene_id, e.id::text as episode_id, es.position
            FROM episode_scenes es
            JOIN episodes e ON es.episode_id = e.id
        """)
        for row in ep_scene_rows:
            query = f"""
                MATCH (s:Scene {{scene_id: {_esc(row['scene_id'])}}}),
                      (ep:Episode {{episode_id: {_esc(row['episode_id'])}}})
                MERGE (s)-[r:SCENE_IN]->(ep)
                SET r.position = {_esc(row['position'])}
                RETURN r
            """
            try:
                await _cypher(conn, query)
            except Exception:
                pass  # episode vertex may not exist yet

        logger.info(f"graph_sync: synced {scene_count} scenes, {shot_count} shots")
        return scene_count + shot_count
    finally:
        if close_conn:
            await conn.close()


async def sync_episodes(conn: asyncpg.Connection | None = None) -> int:
    """Sync episodes → Episode vertices."""
    close_conn = conn is None
    if conn is None:
        conn = await _get_conn()

    try:
        rows = await conn.fetch("""
            SELECT e.id::text as episode_id, e.title, e.episode_number, e.status,
                   p.name as project_name
            FROM episodes e
            JOIN projects p ON e.project_id = p.id
        """)

        count = 0
        for row in rows:
            query = f"""
                MERGE (ep:Episode {{episode_id: {_esc(row['episode_id'])}}})
                SET ep.title = {_esc(row['title'])},
                    ep.episode_number = {_esc(row['episode_number'])},
                    ep.status = {_esc(row['status'])}
                RETURN ep
            """
            await _cypher(conn, query)
            count += 1

        logger.info(f"graph_sync: synced {count} episodes")
        return count
    finally:
        if close_conn:
            await conn.close()


async def sync_feedback(conn: asyncpg.Connection | None = None) -> int:
    """Sync rejections → FeedbackCategory vertices + FEEDBACK_FOR edges."""
    close_conn = conn is None
    if conn is None:
        conn = await _get_conn()

    try:
        rows = await conn.fetch("""
            SELECT r.id, r.character_slug, r.image_name, r.categories,
                   r.feedback_text, r.quality_score, r.generation_history_id
            FROM rejections r
        """)

        count = 0
        for row in rows:
            categories = row["categories"] or []
            for cat in categories:
                # Merge FeedbackCategory vertex
                query = f"""
                    MERGE (fc:FeedbackCategory {{category: {_esc(cat)}}})
                    RETURN fc
                """
                await _cypher(conn, query)

                # Link to Image if generation_history_id exists
                if row["generation_history_id"]:
                    img_id = f"gh_{row['generation_history_id']}"
                    query = f"""
                        MATCH (fc:FeedbackCategory {{category: {_esc(cat)}}}),
                              (i:Image {{img_id: {_esc(img_id)}}})
                        MERGE (fc)-[r:FEEDBACK_FOR]->(i)
                        SET r.free_text = {_esc(row['feedback_text'])}
                        RETURN r
                    """
                    try:
                        await _cypher(conn, query)
                    except Exception:
                        pass  # image may not exist in graph

            count += 1

        logger.info(f"graph_sync: synced {count} feedback records")
        return count
    finally:
        if close_conn:
            await conn.close()


async def sync_approvals_rejections(conn: asyncpg.Connection | None = None) -> int:
    """Sync approvals + rejections into Image vertices with status + quality_score.

    These tables track image-level review outcomes independently of generation_history.
    Creates Image nodes keyed on image_name and links them to Characters + Checkpoints.
    """
    close_conn = conn is None
    if conn is None:
        conn = await _get_conn()

    try:
        # Approvals
        approved_rows = await conn.fetch("""
            SELECT a.id, a.character_slug, a.image_name, a.quality_score,
                   a.checkpoint_model, a.created_at
            FROM approvals a
            WHERE a.image_name IS NOT NULL
        """)

        count = 0
        for row in approved_rows:
            img_id = f"approved_{row['id']}"
            query = f"""
                MERGE (i:Image {{img_id: {_esc(img_id)}}})
                SET i.filename = {_esc(row['image_name'])},
                    i.status = 'approved',
                    i.quality_score = {_esc(row['quality_score'])},
                    i.character_slug = {_esc(row['character_slug'])},
                    i.checkpoint_model = {_esc(row['checkpoint_model'])}
                RETURN i
            """
            await _cypher(conn, query)

            # DEPICTS edge
            if row["character_slug"]:
                query = f"""
                    MATCH (i:Image {{img_id: {_esc(img_id)}}}),
                          (c:Character {{slug: {_esc(row['character_slug'])}}})
                    MERGE (i)-[r:DEPICTS]->(c)
                    RETURN r
                """
                try:
                    await _cypher(conn, query)
                except Exception:
                    pass

            # GENERATED_WITH edge if checkpoint known
            if row["checkpoint_model"]:
                query = f"""
                    MATCH (i:Image {{img_id: {_esc(img_id)}}}),
                          (ck:Checkpoint {{checkpoint_model: {_esc(row['checkpoint_model'])}}})
                    MERGE (i)-[r:GENERATED_WITH]->(ck)
                    RETURN r
                """
                try:
                    await _cypher(conn, query)
                except Exception:
                    pass

            count += 1

        # Rejections as Image nodes
        rejected_rows = await conn.fetch("""
            SELECT r.id, r.character_slug, r.image_name, r.quality_score,
                   r.checkpoint_model, r.created_at
            FROM rejections r
            WHERE r.image_name IS NOT NULL
        """)

        for row in rejected_rows:
            img_id = f"rejected_{row['id']}"
            query = f"""
                MERGE (i:Image {{img_id: {_esc(img_id)}}})
                SET i.filename = {_esc(row['image_name'])},
                    i.status = 'rejected',
                    i.quality_score = {_esc(row['quality_score'])},
                    i.character_slug = {_esc(row['character_slug'])},
                    i.checkpoint_model = {_esc(row['checkpoint_model'])}
                RETURN i
            """
            await _cypher(conn, query)

            if row["character_slug"]:
                query = f"""
                    MATCH (i:Image {{img_id: {_esc(img_id)}}}),
                          (c:Character {{slug: {_esc(row['character_slug'])}}})
                    MERGE (i)-[r:DEPICTS]->(c)
                    RETURN r
                """
                try:
                    await _cypher(conn, query)
                except Exception:
                    pass

            count += 1

        logger.info(f"graph_sync: synced {count} approval/rejection images")
        return count
    finally:
        if close_conn:
            await conn.close()


async def full_sync() -> dict:
    """Run all sync functions. Idempotent — safe to call repeatedly.

    Each sync function gets a fresh connection because AGE's internal planner
    accumulates state across many MERGE queries on different labels, leading
    to 'could not find rte for None' errors on long-lived connections.
    """
    results = {}
    for name, fn in [
        ("projects", sync_projects),
        ("characters", sync_characters),
        ("checkpoints", sync_checkpoints),
        ("episodes", sync_episodes),
        ("scenes", sync_scenes),
        ("generation_history", sync_generation_history),
        ("approvals_rejections", sync_approvals_rejections),
        ("feedback", sync_feedback),
    ]:
        results[name] = await fn()  # each creates+closes its own connection
    logger.info(f"graph_sync: full sync complete — {results}")
    return results


async def graph_stats() -> dict:
    """Return vertex and edge counts for the graph."""
    conn = await _get_conn()
    try:
        vertex_labels = [
            "Project", "Character", "Checkpoint", "Image",
            "Scene", "Shot", "Episode", "LoRA", "FeedbackCategory",
        ]
        edge_labels = [
            "BELONGS_TO", "GENERATED_WITH", "DEPICTS", "REVIEWED_AS",
            "FEEDBACK_FOR", "REGENERATED_FROM", "APPEARS_IN", "PART_OF",
            "SCENE_IN", "TRAINED_ON", "USES_LORA", "USES_CHECKPOINT",
        ]

        stats = {"vertices": {}, "edges": {}}

        for label in vertex_labels:
            try:
                result = await _cypher(conn, f"MATCH (n:{label}) RETURN count(n)")
                count_str = str(result[0]) if result else "0"
                stats["vertices"][label] = int(count_str)
            except Exception:
                stats["vertices"][label] = 0

        for label in edge_labels:
            try:
                result = await _cypher(conn, f"MATCH ()-[r:{label}]->() RETURN count(r)")
                count_str = str(result[0]) if result else "0"
                stats["edges"][label] = int(count_str)
            except Exception:
                stats["edges"][label] = 0

        stats["total_vertices"] = sum(stats["vertices"].values())
        stats["total_edges"] = sum(stats["edges"].values())
        return stats
    finally:
        await conn.close()


# ── EventBus Handlers (delegated to graph_events.py) ──────────────────
# Re-exported here so existing callers (e.g. events.py) don't break.
# Uses __getattr__ lazy loading to avoid circular import — graph_events
# imports _get_conn, _cypher, _esc from this module at load time.

_GRAPH_EVENT_NAMES = {
    "on_image_approved",
    "on_image_rejected",
    "on_generation_submitted",
    "on_regeneration_queued",
}


def __getattr__(name):
    if name in _GRAPH_EVENT_NAMES:
        from . import graph_events
        return getattr(graph_events, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
