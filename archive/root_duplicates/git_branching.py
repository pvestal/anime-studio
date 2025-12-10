#!/usr/bin/env python3
"""
Git-like Branching System for Anime Storylines
Location: /opt/tower-anime-production/git_branching.py

Implements version control for anime scenes with:
- Branch creation and management
- Commit history tracking
- Scene snapshots with SHA-256 hashing
- Branch comparison and merging
- Rollback capabilities
- Milestone tagging
"""

import asyncio
import hashlib
import json
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "***REMOVED***",
    "port": 5432,
    "options": "-c search_path=anime_api,public",
}


@contextmanager
def get_db():
    """Database connection manager"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def init_git_schema():
    """Verify git-like tables exist in PostgreSQL database"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Check if required tables exist in anime_api schema
        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'anime_api'
            AND table_name IN ('branches', 'commits', 'tags')
        """
        )

        existing_tables = [row[0] for row in cursor.fetchall()]
        required_tables = ["branches", "commits", "tags"]

        missing_tables = set(required_tables) - set(existing_tables)
        if missing_tables:
            logger.warning(
                f"Missing git tables in PostgreSQL: {missing_tables}")
            return False

        logger.info("All git tables verified in PostgreSQL anime_api schema")
        return True


def generate_commit_hash(
    branch_name: str, author: str, message: str, scene_data: Dict, timestamp: str
) -> str:
    """Generate SHA-256 hash for commit"""
    content = f"{branch_name}{author}{message}{json.dumps(scene_data, sort_keys=True)}{timestamp}"
    return hashlib.sha256(content.encode()).hexdigest()[
        :16
    ]  # Use first 16 chars like git short hash


def create_branch(
    project_id: int,
    new_branch: str,
    from_branch: str = "main",
    from_commit: Optional[str] = None,
    description: str = "",
) -> Dict[str, Any]:
    """
    Create a new branch from an existing branch or commit

    Args:
        project_id: Project ID
        new_branch: Name of new branch
        from_branch: Source branch (default: 'main')
        from_commit: Specific commit to branch from (optional)
        description: Branch description

    Returns:
        Dict with branch details
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Check if project exists
        cursor.execute("SELECT id FROM projects WHERE id = %s", (project_id,))
        if not cursor.fetchone():
            raise ValueError(f"Project {project_id} not found")

        # Check if branch already exists
        cursor.execute(
            "SELECT id FROM branches WHERE project_id = %s AND branch_name = %s",
            (project_id, new_branch),
        )
        if cursor.fetchone():
            raise ValueError(f"Branch '{new_branch}' already exists")

        # Create main branch if it doesn't exist
        cursor.execute(
            "SELECT id FROM branches WHERE project_id = %s AND branch_name = %s",
            (project_id, "main"),
        )
        main_branch = cursor.fetchone()
        if not main_branch and from_branch == "main":
            cursor.execute(
                "INSERT INTO branches (project_id, branch_name) VALUES (%s, %s) RETURNING id",
                (project_id, "main"),
            )
            logger.info(f"Created main branch for project {project_id}")

        # Create the new branch
        created_from = from_commit if from_commit else from_branch
        cursor.execute(
            "INSERT INTO branches (project_id, branch_name, parent_branch) VALUES (%s, %s, %s) RETURNING id",
            (project_id, new_branch, created_from),
        )

        branch_id = cursor.fetchone()[0]

        logger.info(
            f"Created branch '{new_branch}' from '{created_from}' for project {project_id}"
        )

        return {
            "branch_id": branch_id,
            "branch_name": new_branch,
            "project_id": project_id,
            "created_from": created_from,
            "created_at": datetime.now().isoformat(),
        }


def create_commit(
    project_id: int,
    branch_name: str,
    message: str,
    author: str,
    scene_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a commit with scene snapshot

    Args:
        project_id: Project ID
        branch_name: Branch to commit to
        message: Commit message
        author: Author name
        scene_data: Scene data to snapshot

    Returns:
        Dict with commit details including hash
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Get branch
        cursor.execute(
            "SELECT id FROM branches WHERE project_id = %s AND branch_name = %s",
            (project_id, branch_name),
        )
        branch = cursor.fetchone()
        if not branch:
            raise ValueError(
                f"Branch '{branch_name}' not found for project {project_id}"
            )

        branch_id = branch[0]

        # Get parent commit (latest on branch)
        cursor.execute(
            "SELECT commit_hash FROM commits WHERE branch_name = %s ORDER BY created_at DESC LIMIT 1",
            (branch_name,),
        )
        parent = cursor.fetchone()
        parent_hash = parent[0] if parent else None

        # Generate commit hash
        timestamp = datetime.now().isoformat()
        commit_hash = generate_commit_hash(
            branch_name, author, message, scene_data, timestamp
        )

        # Store commit
        scene_snapshot = json.dumps(scene_data, indent=2)
        cursor.execute(
            """INSERT INTO commits (project_id, commit_hash, branch_name, message, author, created_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (project_id, commit_hash, branch_name, message, author, timestamp),
        )

        logger.info(f"Created commit {commit_hash} on branch '{branch_name}'")

        return {
            "commit_hash": commit_hash,
            "branch_name": branch_name,
            "parent_hash": parent_hash,
            "author": author,
            "message": message,
            "timestamp": timestamp,
            "scene_data": scene_data,
        }


def get_commit_history(
    project_id: int, branch_name: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get commit history for a branch

    Args:
        project_id: Project ID
        branch_name: Branch name
        limit: Maximum number of commits to return

    Returns:
        List of commits in reverse chronological order
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Get branch
        cursor.execute(
            "SELECT id FROM branches WHERE project_id = %s AND branch_name = %s",
            (project_id, branch_name),
        )
        branch = cursor.fetchone()
        if not branch:
            raise ValueError(f"Branch '{branch_name}' not found")

        branch_id = branch[0]

        # Get commits
        cursor.execute(
            """SELECT commit_hash, author, message, created_at
               FROM commits WHERE project_id = %s AND branch_name = %s
               ORDER BY created_at DESC LIMIT %s""",
            (project_id, branch_name, limit),
        )

        commits = []
        for row in cursor.fetchall():
            commits.append(
                {
                    "commit_hash": row[0],
                    "author": row[1],
                    "message": row[2],
                    "timestamp": row[3],
                }
            )

        return commits


def compare_branches(project_id: int, branch_a: str, branch_b: str) -> Dict[str, Any]:
    """
    Compare two branches

    Args:
        project_id: Project ID
        branch_a: First branch name
        branch_b: Second branch name

    Returns:
        Dict with comparison results
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Get latest commits from both branches
        def get_latest_commit(branch_name):
            cursor.execute(
                """SELECT commit_hash, created_at
                   FROM commits
                   WHERE project_id = %s AND branch_name = %s
                   ORDER BY created_at DESC LIMIT 1""",
                (project_id, branch_name),
            )
            return cursor.fetchone()

        commit_a = get_latest_commit(branch_a)
        commit_b = get_latest_commit(branch_b)

        if not commit_a:
            raise ValueError(f"No commits found on branch '{branch_a}'")
        if not commit_b:
            raise ValueError(f"No commits found on branch '{branch_b}'")

        # Since scene_snapshot doesn't exist in current schema, compare commit hashes
        has_conflicts = commit_a[0] != commit_b[0]

        return {
            "branch_a": {
                "name": branch_a,
                "commit": commit_a[0],
                "timestamp": commit_a[1],
            },
            "branch_b": {
                "name": branch_b,
                "commit": commit_b[0],
                "timestamp": commit_b[1],
            },
            "differences": (
                {"commit_hash": "Different commits"} if has_conflicts else {}
            ),
            "has_conflicts": has_conflicts,
        }


def merge_branches(
    project_id: int,
    from_branch: str,
    to_branch: str,
    strategy: str = "ours",
    author: str = "system",
) -> Dict[str, Any]:
    """
    Merge one branch into another

    Args:
        project_id: Project ID
        from_branch: Source branch
        to_branch: Target branch
        strategy: Merge strategy ('ours', 'theirs', 'manual')
        author: Author of merge commit

    Returns:
        Dict with merge commit details
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Get latest commits
        def get_latest_scene(branch_name):
            cursor.execute(
                """SELECT c.scene_snapshot
                   FROM commits c
                   JOIN branches b ON c.branch_id = b.id
                   WHERE b.project_id = %s AND b.branch_name = %s
                   ORDER BY c.timestamp DESC LIMIT 1""",
                (project_id, branch_name),
            )
            result = cursor.fetchone()
            return json.loads(result[0]) if result else None

        scene_from = get_latest_scene(from_branch)
        scene_to = get_latest_scene(to_branch)

        if not scene_from:
            raise ValueError(f"No commits found on branch '{from_branch}'")
        if not scene_to:
            raise ValueError(f"No commits found on branch '{to_branch}'")

        # Apply merge strategy
        if strategy == "ours":
            merged_scene = scene_to
        elif strategy == "theirs":
            merged_scene = scene_from
        else:
            # Manual merge - combine both
            merged_scene = {**scene_to, **scene_from}

        # Create merge commit
        message = (
            f"Merge '{from_branch}' into '{to_branch}' using strategy '{strategy}'"
        )
        merge_commit = create_commit(
            project_id, to_branch, message, author, merged_scene
        )

        logger.info(
            f"Merged '{from_branch}' into '{to_branch}' with strategy '{strategy}'"
        )

        return merge_commit


def revert_to_commit(
    project_id: int, branch_name: str, commit_hash: str, author: str = "system"
) -> Dict[str, Any]:
    """
    Revert branch to a previous commit

    Args:
        project_id: Project ID
        branch_name: Branch name
        commit_hash: Commit to revert to
        author: Author of revert commit

    Returns:
        Dict with revert commit details
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Get the commit
        cursor.execute(
            """SELECT c.scene_snapshot
               FROM commits c
               JOIN branches b ON c.branch_id = b.id
               WHERE b.project_id = %s AND b.branch_name = %s AND c.commit_hash = %s""",
            (project_id, branch_name, commit_hash),
        )

        commit = cursor.fetchone()
        if not commit:
            raise ValueError(
                f"Commit {commit_hash} not found on branch '{branch_name}'"
            )

        # Create revert commit
        scene_data = json.loads(commit[0])
        message = f"Revert to commit {commit_hash}"
        revert_commit = create_commit(
            project_id, branch_name, message, author, scene_data
        )

        logger.info(f"Reverted branch '{branch_name}' to commit {commit_hash}")

        return revert_commit


def tag_commit(
    commit_hash: str, tag_name: str, description: str = ""
) -> Dict[str, Any]:
    """
    Create a milestone tag for a commit

    Args:
        commit_hash: Commit hash to tag
        tag_name: Tag name
        description: Tag description

    Returns:
        Dict with tag details
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Verify commit exists
        cursor.execute(
            "SELECT id FROM commits WHERE commit_hash = %s", (commit_hash,))
        if not cursor.fetchone():
            raise ValueError(f"Commit {commit_hash} not found")

        # Create tag
        try:
            cursor.execute(
                "INSERT INTO tags (tag_name, commit_hash, description) VALUES (%s, %s, %s)",
                (tag_name, commit_hash, description),
            )
        except psycopg2.IntegrityError:
            raise ValueError(f"Tag '{tag_name}' already exists")

        logger.info(f"Created tag '{tag_name}' for commit {commit_hash}")

        return {
            "tag_name": tag_name,
            "commit_hash": commit_hash,
            "description": description,
            "created_at": datetime.now().isoformat(),
        }


def get_commit_details(commit_hash: str) -> Dict[str, Any]:
    """Get full details of a commit including scene snapshot"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT commit_hash, parent_hash, author, message, scene_snapshot, timestamp
               FROM commits WHERE commit_hash = %s""",
            (commit_hash,),
        )

        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Commit {commit_hash} not found")

        return {
            "commit_hash": row[0],
            "parent_hash": row[1],
            "author": row[2],
            "message": row[3],
            "scene_snapshot": json.loads(row[4]),
            "timestamp": row[5],
        }


def list_branches(project_id: int) -> List[Dict[str, Any]]:
    """List all branches for a project"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT branch_name, parent_branch, created_at
               FROM branches WHERE project_id = %s
               ORDER BY created_at DESC""",
            (project_id,),
        )

        branches = []
        for row in cursor.fetchall():
            # Get commit count
            cursor.execute(
                """SELECT COUNT(*) FROM commits
                   WHERE project_id = %s AND branch_name = %s""",
                (project_id, row[0]),
            )
            commit_count = cursor.fetchone()[0]

            branches.append(
                {
                    "branch_name": row[0],
                    "parent_branch": row[1],
                    "created_at": row[2],
                    "commit_count": commit_count,
                }
            )

        return branches


# === ECHO BRAIN COORDINATION ===


async def echo_analyze_storyline(
    project_id: int, branch_name: str = "main"
) -> Dict[str, Any]:
    """
    Get Echo Brain's analysis of storyline progression for a branch

    Args:
        project_id: Project ID
        branch_name: Branch to analyze

    Returns:
        Dict with Echo's storyline analysis
    """
    try:
        # Get branch commits and scene data
        commits = get_commit_history(project_id, branch_name)

        if not commits:
            return {
                "analysis": "No commits found for storyline analysis",
                "recommendations": [],
            }

        # Prepare storyline data for Echo
        storyline_data = {
            "project_id": project_id,
            "branch": branch_name,
            "total_commits": len(commits),
            "scenes": [],
        }

        for commit in commits:
            scene_data = json.loads(commit["scene_data"])
            storyline_data["scenes"].append(
                {
                    "commit_hash": commit["commit_hash"],
                    "timestamp": commit["created_at"].isoformat(),
                    "message": commit["message"],
                    "scene_data": scene_data,
                }
            )

        # Send to Echo Brain for analysis
        analysis_prompt = f"""
        Analyze this anime storyline progression for narrative continuity and quality:

        Project ID: {project_id}
        Branch: {branch_name}
        Total Scenes: {len(commits)}

        Scene Progression:
        {json.dumps(storyline_data, indent=2)}

        Please analyze:
        1. Narrative flow and story coherence
        2. Character development consistency
        3. Visual continuity between scenes
        4. Pacing and rhythm
        5. Potential plot holes or inconsistencies
        6. Recommendations for improvement

        Provide specific, actionable feedback for anime production.
        """

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8309/api/echo/analyze",
                json={
                    "query": analysis_prompt,
                    "context": {"type": "anime_storyline", "project_id": project_id},
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "analysis": result.get("analysis", "Analysis completed"),
                        "recommendations": result.get("recommendations", []),
                        "analyzed_at": datetime.now().isoformat(),
                        "model_used": result.get("model", "echo-brain"),
                        "commit_count": len(commits),
                    }
                else:
                    logger.warning(
                        f"Echo analysis failed with status {response.status}"
                    )
                    return {
                        "analysis": "Echo analysis unavailable",
                        "recommendations": [],
                    }

    except Exception as e:
        logger.error(f"Echo storyline analysis failed: {e}")
        return {"analysis": f"Analysis error: {str(e)}", "recommendations": []}


async def echo_guided_branch_creation(
    project_id: int,
    base_branch: str,
    new_branch_name: str,
    storyline_goal: str,
    author: str = "echo-guided",
) -> Dict[str, Any]:
    """
    Create a new branch with Echo Brain's guidance for storyline direction

    Args:
        project_id: Project ID
        base_branch: Source branch
        new_branch_name: New branch name
        storyline_goal: What this branch should achieve narratively
        author: Author name

    Returns:
        Dict with branch creation result and Echo guidance
    """
    try:
        # Get Echo's analysis of the base branch
        base_analysis = await echo_analyze_storyline(project_id, base_branch)

        # Ask Echo for branching strategy
        branching_prompt = f"""
        Based on this anime storyline analysis, provide guidance for creating a new branch:

        Base Branch: {base_branch}
        New Branch Goal: {storyline_goal}
        Current Analysis: {base_analysis.get('analysis', 'No analysis')}

        Please recommend:
        1. Key narrative elements to focus on in this branch
        2. Character arcs to develop
        3. Visual themes and consistency requirements
        4. Pacing considerations
        5. How this branch should diverge from the main storyline
        6. Success metrics for this narrative direction

        Provide concrete guidance for anime production team.
        """

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8309/api/echo/analyze",
                json={
                    "query": branching_prompt,
                    "context": {"type": "branch_strategy", "project_id": project_id},
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                echo_guidance = {}
                if response.status == 200:
                    result = await response.json()
                    echo_guidance = {
                        "narrative_focus": result.get("narrative_focus", []),
                        "character_arcs": result.get("character_arcs", []),
                        "visual_themes": result.get("visual_themes", []),
                        "pacing_notes": result.get("pacing_notes", ""),
                        "success_metrics": result.get("success_metrics", []),
                    }

        # Create the branch with Echo's guidance documented
        branch_description = f"Echo-guided branch: {storyline_goal}\n\nEcho Guidance: {json.dumps(echo_guidance, indent=2)}"

        branch_result = create_branch(
            project_id=project_id,
            new_branch=new_branch_name,
            from_branch=base_branch,
            description=branch_description,
        )

        # Combine results
        return {
            "branch": branch_result,
            "echo_guidance": echo_guidance,
            "base_analysis": base_analysis,
            "created_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Echo-guided branch creation failed: {e}")
        # Fallback to normal branch creation
        return create_branch(
            project_id,
            new_branch_name,
            base_branch,
            description=f"Branch for: {storyline_goal}",
        )


def echo_commit_with_analysis(
    project_id: int,
    branch_name: str,
    message: str,
    author: str,
    scene_data: Dict,
    analyze_impact: bool = True,
) -> Dict[str, Any]:
    """
    Create a commit with optional Echo Brain impact analysis

    Args:
        project_id: Project ID
        branch_name: Branch name
        message: Commit message
        author: Author name
        scene_data: Scene data to commit
        analyze_impact: Whether to get Echo's analysis of this commit's impact

    Returns:
        Dict with commit result and optional Echo analysis
    """
    # Create the commit first
    commit_result = create_commit(
        project_id, branch_name, message, author, scene_data)

    if not analyze_impact:
        return {"commit": commit_result, "echo_analysis": None}

    try:
        # Get Echo's analysis of this commit's impact (async in background)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def get_commit_analysis():
            analysis_prompt = f"""
            Analyze the impact of this new anime scene commit:

            Commit: {commit_result['commit_hash']}
            Message: {message}
            Author: {author}
            Scene Data: {json.dumps(scene_data, indent=2)}

            How does this commit affect:
            1. Overall narrative flow
            2. Character development
            3. Visual consistency
            4. Story pacing
            5. Future scene possibilities

            Rate the impact (1-10) and provide specific feedback.
            """

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "http://localhost:8309/api/echo/analyze",
                        json={
                            "query": analysis_prompt,
                            "context": {
                                "type": "commit_impact",
                                "commit_hash": commit_result["commit_hash"],
                            },
                        },
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        return {"analysis": "Echo analysis unavailable"}
            except:
                return {"analysis": "Echo analysis failed"}

        echo_analysis = loop.run_until_complete(get_commit_analysis())
        loop.close()

        return {
            "commit": commit_result,
            "echo_analysis": echo_analysis,
            "analyzed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Echo commit analysis failed: {e}")
        return {"commit": commit_result, "echo_analysis": {"error": str(e)}}


# Initialize schema on import
init_git_schema()
