"""Graph EventBus handlers — event-driven sync functions for real-time graph updates."""

import logging

from .graph_sync import _get_conn, _cypher, _esc

logger = logging.getLogger(__name__)


async def on_image_approved(data: dict):
    """Handle image.approved event — update Image vertex status + create REVIEWED_AS edge."""
    conn = await _get_conn()
    try:
        gh_id = data.get("generation_history_id")
        if not gh_id:
            return

        img_id = f"gh_{gh_id}"
        quality = data.get("quality_score", 0)

        query = f"""
            MATCH (i:Image {{img_id: {_esc(img_id)}}})
            SET i.status = 'approved', i.quality_score = {quality}
            RETURN i
        """
        await _cypher(conn, query)
    except Exception as e:
        logger.warning(f"graph_sync on_image_approved failed: {e}")
    finally:
        await conn.close()


async def on_image_rejected(data: dict):
    """Handle image.rejected event — update Image vertex + link feedback."""
    conn = await _get_conn()
    try:
        gh_id = data.get("generation_history_id")
        if not gh_id:
            return

        img_id = f"gh_{gh_id}"
        quality = data.get("quality_score", 0)
        categories = data.get("categories", [])

        query = f"""
            MATCH (i:Image {{img_id: {_esc(img_id)}}})
            SET i.status = 'rejected', i.quality_score = {quality}
            RETURN i
        """
        await _cypher(conn, query)

        for cat in categories:
            query = f"""
                MERGE (fc:FeedbackCategory {{category: {_esc(cat)}}})
                WITH fc
                MATCH (i:Image {{img_id: {_esc(img_id)}}})
                MERGE (fc)-[r:FEEDBACK_FOR]->(i)
                RETURN r
            """
            try:
                await _cypher(conn, query)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"graph_sync on_image_rejected failed: {e}")
    finally:
        await conn.close()


async def on_generation_submitted(data: dict):
    """Handle generation.submitted event — create Image vertex + GENERATED_WITH edge."""
    conn = await _get_conn()
    try:
        gh_id = data.get("generation_history_id")
        slug = data.get("character_slug")
        checkpoint = data.get("checkpoint_model")
        if not gh_id:
            return

        img_id = f"gh_{gh_id}"

        query = f"""
            MERGE (i:Image {{img_id: {_esc(img_id)}}})
            SET i.status = 'pending',
                i.character_slug = {_esc(slug)},
                i.checkpoint_model = {_esc(checkpoint)}
            RETURN i
        """
        await _cypher(conn, query)

        if slug:
            query = f"""
                MATCH (i:Image {{img_id: {_esc(img_id)}}}),
                      (c:Character {{slug: {_esc(slug)}}})
                MERGE (i)-[r:DEPICTS]->(c)
                RETURN r
            """
            try:
                await _cypher(conn, query)
            except Exception:
                pass

        if checkpoint:
            query = f"""
                MATCH (i:Image {{img_id: {_esc(img_id)}}}),
                      (ck:Checkpoint {{checkpoint_model: {_esc(checkpoint)}}})
                MERGE (i)-[r:GENERATED_WITH]->(ck)
                RETURN r
            """
            try:
                await _cypher(conn, query)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"graph_sync on_generation_submitted failed: {e}")
    finally:
        await conn.close()


async def on_regeneration_queued(data: dict):
    """Handle regeneration.queued event — create REGENERATED_FROM edge."""
    conn = await _get_conn()
    try:
        new_gh_id = data.get("new_generation_history_id")
        original_gh_id = data.get("original_generation_history_id")
        if not new_gh_id or not original_gh_id:
            return

        new_id = f"gh_{new_gh_id}"
        orig_id = f"gh_{original_gh_id}"

        query = f"""
            MATCH (child:Image {{img_id: {_esc(new_id)}}}),
                  (parent:Image {{img_id: {_esc(orig_id)}}})
            MERGE (child)-[r:REGENERATED_FROM]->(parent)
            RETURN r
        """
        try:
            await _cypher(conn, query)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"graph_sync on_regeneration_queued failed: {e}")
    finally:
        await conn.close()
