#!/usr/bin/env python3
"""
Migrate bible.json files into world_settings and enhanced storyline DB tables.

Reads from /opt/anime-studio/workflows/projects/*/bible.json
and populates world_settings rows for matching projects in the DB.

Run once after schema migration. Bible files stay as reference docs.
"""

import json
import os
import sys
from pathlib import Path
from glob import glob

import psycopg2
import psycopg2.extras


BIBLE_GLOB = "/opt/anime-studio/workflows/projects/*/bible.json"


def get_db_connection():
    """Connect to anime_production DB via Vault."""
    try:
        import hvac
        token_file = os.path.expanduser("~/.vault-token")
        if os.path.exists(token_file):
            vault_token = open(token_file).read().strip()
            client = hvac.Client(url="http://127.0.0.1:8200", token=vault_token)
            if client.is_authenticated():
                resp = client.secrets.kv.v2.read_secret_version(
                    path="anime/database", mount_point="secret",
                    raise_on_deleted_version=True,
                )
                return psycopg2.connect(
                    host="localhost", database="anime_production",
                    user="patrick", password=resp["data"]["data"]["password"],
                )
    except Exception as e:
        print(f"  Vault: {e}")
    return psycopg2.connect(
        host="localhost", database="anime_production",
        user="patrick", password=os.getenv("PGPASSWORD", ""),
    )


def find_project_id(cur, project_name: str) -> int | None:
    """Find a project ID by name (case-insensitive partial match)."""
    cur.execute("SELECT id, name FROM projects ORDER BY name")
    projects = cur.fetchall()
    # Exact match first
    for pid, pname in projects:
        if pname.lower() == project_name.lower():
            return pid
    # Partial match
    for pid, pname in projects:
        if project_name.lower() in pname.lower() or pname.lower() in project_name.lower():
            return pid
    return None


def migrate_bible(bible_path: Path, conn) -> bool:
    """Migrate a single bible.json into DB. Returns True if migrated."""
    with open(bible_path) as f:
        bible = json.load(f)

    project_name = bible.get("project_name", "")
    if not project_name:
        print(f"  SKIP: No project_name in {bible_path}")
        return False

    cur = conn.cursor()
    project_id = find_project_id(cur, project_name)
    if not project_id:
        print(f"  SKIP: Project '{project_name}' not found in DB")
        return False

    print(f"  Matched: '{project_name}' -> project_id={project_id}")

    # --- World Settings ---
    visual = bible.get("visual_style", {})
    world = bible.get("world_setting", {})
    production = bible.get("production_notes", {})
    visual_dir = bible.get("visual_direction", {})

    # Build style_preamble from art_style + aesthetic
    preamble_parts = []
    if visual.get("art_style"):
        preamble_parts.append(visual["art_style"])
    if visual.get("aesthetic"):
        preamble_parts.append(visual["aesthetic"])
    style_preamble = ", ".join(preamble_parts) if preamble_parts else None

    # Build world_location from world_setting.location
    location = world.get("location", {})
    world_location = None
    if location:
        world_location = {
            "primary": location.get("primary", ""),
            "areas": location.get("areas", []),
            "atmosphere": location.get("atmosphere", ""),
        }

    # Build cinematography
    cinematography = None
    if visual.get("cinematography"):
        cin = visual["cinematography"]
        cinematography = {
            "shot_types": cin.get("shot_types", []),
            "camera_angles": cin.get("camera_angles", []),
            "lighting": cin.get("lighting", ""),
        }

    # Known issues
    known_issues = None
    if isinstance(production, dict) and production.get("known_accuracy_issues"):
        known_issues = production["known_accuracy_issues"]

    # Negative prompt guidance
    neg_guidance = None
    if isinstance(production, dict) and production.get("negative_prompt_guidance"):
        neg_guidance = production["negative_prompt_guidance"]

    # Production notes text
    prod_notes_parts = []
    if visual_dir.get("character_design"):
        prod_notes_parts.append(f"Character design: {visual_dir['character_design']}")
    if visual_dir.get("environment_design"):
        prod_notes_parts.append(f"Environment: {visual_dir['environment_design']}")
    if visual_dir.get("action_choreography"):
        prod_notes_parts.append(f"Action: {visual_dir['action_choreography']}")
    prod_notes = "\n".join(prod_notes_parts) if prod_notes_parts else None

    # Check if world_settings already exists
    cur.execute("SELECT id FROM world_settings WHERE project_id = %s", (project_id,))
    existing = cur.fetchone()
    if existing:
        print(f"  UPDATE world_settings for project {project_id}")
        cur.execute("""
            UPDATE world_settings SET
                style_preamble = %s, art_style = %s, aesthetic = %s,
                color_palette = %s, cinematography = %s, world_location = %s,
                time_period = %s, production_notes = %s, known_issues = %s,
                negative_prompt_guidance = %s, updated_at = NOW()
            WHERE project_id = %s
        """, (
            style_preamble,
            visual.get("art_style"),
            visual.get("aesthetic"),
            json.dumps(visual.get("color_palette")) if visual.get("color_palette") else None,
            json.dumps(cinematography) if cinematography else None,
            json.dumps(world_location) if world_location else None,
            world.get("time_period"),
            prod_notes,
            json.dumps(known_issues) if known_issues else None,
            neg_guidance,
            project_id,
        ))
    else:
        print(f"  INSERT world_settings for project {project_id}")
        cur.execute("""
            INSERT INTO world_settings
                (project_id, style_preamble, art_style, aesthetic, color_palette,
                 cinematography, world_location, time_period, production_notes,
                 known_issues, negative_prompt_guidance)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            project_id,
            style_preamble,
            visual.get("art_style"),
            visual.get("aesthetic"),
            json.dumps(visual.get("color_palette")) if visual.get("color_palette") else None,
            json.dumps(cinematography) if cinematography else None,
            json.dumps(world_location) if world_location else None,
            world.get("time_period"),
            prod_notes,
            json.dumps(known_issues) if known_issues else None,
            neg_guidance,
        ))

    # --- Enhanced Storyline ---
    narrative = bible.get("narrative_guidelines", {})
    if narrative:
        tone = narrative.get("tone")
        # Flatten dict/complex types to strings for TEXT columns
        if isinstance(tone, dict):
            tone = tone.get("primary", json.dumps(tone))
        themes = narrative.get("themes")
        if isinstance(themes, list):
            # Ensure all elements are strings for TEXT[] column
            themes = [str(t) if not isinstance(t, str) else t for t in themes]
        humor_style = narrative.get("humor_style")
        if isinstance(humor_style, dict):
            humor_style = humor_style.get("primary", json.dumps(humor_style))
        # story_arcs can come from either "story_arc" (singular) or "story_arcs" (plural)
        raw_arcs = narrative.get("story_arcs") or narrative.get("story_arc")
        story_arcs = None
        if raw_arcs:
            if not isinstance(raw_arcs, list):
                raw_arcs = [raw_arcs]
            story_arcs = raw_arcs

        cur.execute("SELECT id FROM storylines WHERE project_id = %s", (project_id,))
        storyline_exists = cur.fetchone()
        if storyline_exists:
            updates = []
            params = []
            if tone:
                updates.append("tone = %s")
                params.append(tone)
            if themes:
                updates.append("themes = %s")
                params.append(themes)
            if humor_style:
                updates.append("humor_style = %s")
                params.append(humor_style)
            if story_arcs:
                updates.append("story_arcs = %s")
                params.append(json.dumps(story_arcs))
            if updates:
                params.append(project_id)
                cur.execute(
                    f"UPDATE storylines SET {', '.join(updates)} WHERE project_id = %s",
                    params,
                )
                print(f"  UPDATE storyline with: {', '.join(u.split('=')[0].strip() for u in updates)}")
        else:
            cur.execute("""
                INSERT INTO storylines (project_id, title, tone, themes, humor_style, story_arcs)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (project_id, project_name, tone, themes, humor_style,
                  json.dumps(story_arcs) if story_arcs else None))
            print(f"  INSERT storyline with narrative guidelines")

    # --- Project enhancements ---
    premise = bible.get("premise")
    content_rating = bible.get("content_rating")
    # Flatten complex types to strings for TEXT columns
    if isinstance(premise, dict):
        premise = premise.get("summary", json.dumps(premise))
    if isinstance(content_rating, dict):
        content_rating = content_rating.get("rating", json.dumps(content_rating))
    if premise or content_rating:
        updates = []
        params = []
        if premise:
            updates.append("premise = %s")
            params.append(premise)
        if content_rating:
            updates.append("content_rating = %s")
            params.append(content_rating)
        params.append(project_id)
        cur.execute(
            f"UPDATE projects SET {', '.join(updates)} WHERE id = %s",
            params,
        )
        print(f"  UPDATE project with: {', '.join(u.split('=')[0].strip() for u in updates)}")

    conn.commit()
    return True


def main():
    bible_files = sorted(glob(BIBLE_GLOB))
    if not bible_files:
        print(f"No bible.json files found matching {BIBLE_GLOB}")
        sys.exit(1)

    print(f"Found {len(bible_files)} bible.json file(s)")
    conn = get_db_connection()
    migrated = 0

    for bf in bible_files:
        print(f"\nProcessing: {bf}")
        try:
            if migrate_bible(Path(bf), conn):
                migrated += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            conn.rollback()

    conn.close()
    print(f"\nDone. Migrated {migrated}/{len(bible_files)} bible files.")


if __name__ == "__main__":
    main()
