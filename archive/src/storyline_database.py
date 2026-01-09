#!/usr/bin/env python3
"""
Database persistence layer for Storyline Version Control
PostgreSQL backend for permanent story storage
"""
import asyncpg
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import os


class StorylineDatabase:
    """
    PostgreSQL persistence for storylines
    """

    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://patrick:tower_echo_brain_secret_key_2025@localhost:5433/anime_production"
        )
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """Initialize database connection and create tables"""
        self.pool = await asyncpg.create_pool(self.db_url, min_size=2, max_size=10)

        # Create tables if not exist
        await self.create_tables()

    async def cleanup(self):
        """Close database connections"""
        if self.pool:
            await self.pool.close()

    async def create_tables(self):
        """Create necessary tables for storyline persistence"""
        async with self.pool.acquire() as conn:
            # Stories table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stories (
                    story_id VARCHAR(255) PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    author VARCHAR(255),
                    current_branch VARCHAR(255) DEFAULT 'main',
                    head_commit VARCHAR(255),
                    working_story JSONB,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Commits table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS story_commits (
                    commit_hash VARCHAR(255) PRIMARY KEY,
                    story_id VARCHAR(255) REFERENCES stories(story_id) ON DELETE CASCADE,
                    parent_hash VARCHAR(255),
                    author VARCHAR(255),
                    message TEXT,
                    changes JSONB,
                    story_snapshot JSONB,
                    timestamp TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY (parent_hash) REFERENCES story_commits(commit_hash)
                )
            """)

            # Branches table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS story_branches (
                    branch_id SERIAL PRIMARY KEY,
                    story_id VARCHAR(255) REFERENCES stories(story_id) ON DELETE CASCADE,
                    branch_name VARCHAR(255) NOT NULL,
                    head_commit VARCHAR(255),
                    parent_branch VARCHAR(255),
                    description TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(story_id, branch_name)
                )
            """)

            # Character evolution table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS character_evolution (
                    evolution_id SERIAL PRIMARY KEY,
                    story_id VARCHAR(255) REFERENCES stories(story_id) ON DELETE CASCADE,
                    character_name VARCHAR(255) NOT NULL,
                    commit_hash VARCHAR(255) REFERENCES story_commits(commit_hash),
                    evolution_state JSONB,
                    emotional_state JSONB,
                    relationships JSONB,
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            """)

            # User interactions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_interactions (
                    interaction_id SERIAL PRIMARY KEY,
                    story_id VARCHAR(255) REFERENCES stories(story_id) ON DELETE CASCADE,
                    user_id VARCHAR(255),
                    interaction_type VARCHAR(50),
                    intent JSONB,
                    decision JSONB,
                    feedback JSONB,
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            """)

            # User preferences table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id VARCHAR(255) PRIMARY KEY,
                    preferred_styles JSONB,
                    avoided_styles JSONB,
                    interaction_history JSONB,
                    learned_patterns JSONB,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Create indexes for performance
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_commits_story ON story_commits(story_id);
                CREATE INDEX IF NOT EXISTS idx_branches_story ON story_branches(story_id);
                CREATE INDEX IF NOT EXISTS idx_evolution_story ON character_evolution(story_id);
                CREATE INDEX IF NOT EXISTS idx_interactions_story ON user_interactions(story_id);
                CREATE INDEX IF NOT EXISTS idx_commits_timestamp ON story_commits(timestamp DESC);
            """)

    # ==================== Story Operations ====================

    async def save_story(self, story_id: str, vcs_data: Dict) -> bool:
        """Save or update a story in the database"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO stories (
                    story_id, title, description, author,
                    current_branch, head_commit, working_story, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (story_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    current_branch = EXCLUDED.current_branch,
                    head_commit = EXCLUDED.head_commit,
                    working_story = EXCLUDED.working_story,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
            """,
                story_id,
                vcs_data.get("title", "Untitled"),
                vcs_data.get("description", ""),
                vcs_data.get("author", "Unknown"),
                vcs_data.get("current_branch", "main"),
                vcs_data.get("head_commit"),
                json.dumps(vcs_data.get("working_story", {})),
                json.dumps(vcs_data.get("metadata", {}))
            )
            return True

    async def load_story(self, story_id: str) -> Optional[Dict]:
        """Load a story from the database"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM stories WHERE story_id = $1
            """, story_id)

            if row:
                return {
                    "story_id": row["story_id"],
                    "title": row["title"],
                    "description": row["description"],
                    "author": row["author"],
                    "current_branch": row["current_branch"],
                    "head_commit": row["head_commit"],
                    "working_story": json.loads(row["working_story"]) if row["working_story"] else {},
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                }
            return None

    async def list_stories(self, limit: int = 50) -> List[Dict]:
        """List all stories"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT story_id, title, author, current_branch,
                       created_at, updated_at
                FROM stories
                ORDER BY updated_at DESC
                LIMIT $1
            """, limit)

            return [
                {
                    "story_id": row["story_id"],
                    "title": row["title"],
                    "author": row["author"],
                    "current_branch": row["current_branch"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                }
                for row in rows
            ]

    async def delete_story(self, story_id: str) -> bool:
        """Delete a story and all related data"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM stories WHERE story_id = $1
            """, story_id)
            return True

    # ==================== Commit Operations ====================

    async def save_commit(self, commit_data: Dict) -> bool:
        """Save a commit to the database"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO story_commits (
                    commit_hash, story_id, parent_hash, author,
                    message, changes, story_snapshot, timestamp
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (commit_hash) DO NOTHING
            """,
                commit_data["commit_hash"],
                commit_data["story_id"],
                commit_data.get("parent_hash"),
                commit_data["author"],
                commit_data["message"],
                json.dumps(commit_data.get("changes", [])),
                json.dumps(commit_data.get("story_snapshot", {})),
                commit_data.get("timestamp", datetime.utcnow())
            )
            return True

    async def load_commits(self, story_id: str) -> List[Dict]:
        """Load all commits for a story"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM story_commits
                WHERE story_id = $1
                ORDER BY timestamp DESC
            """, story_id)

            return [
                {
                    "commit_hash": row["commit_hash"],
                    "story_id": row["story_id"],
                    "parent_hash": row["parent_hash"],
                    "author": row["author"],
                    "message": row["message"],
                    "changes": json.loads(row["changes"]) if row["changes"] else [],
                    "story_snapshot": json.loads(row["story_snapshot"]) if row["story_snapshot"] else {},
                    "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None
                }
                for row in rows
            ]

    # ==================== Branch Operations ====================

    async def save_branch(self, story_id: str, branch_data: Dict) -> bool:
        """Save or update a branch"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO story_branches (
                    story_id, branch_name, head_commit,
                    parent_branch, description
                ) VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (story_id, branch_name) DO UPDATE SET
                    head_commit = EXCLUDED.head_commit,
                    description = EXCLUDED.description
            """,
                story_id,
                branch_data["name"],
                branch_data.get("head_commit"),
                branch_data.get("parent_branch"),
                branch_data.get("description", "")
            )
            return True

    async def load_branches(self, story_id: str) -> List[Dict]:
        """Load all branches for a story"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM story_branches
                WHERE story_id = $1
                ORDER BY created_at
            """, story_id)

            return [
                {
                    "name": row["branch_name"],
                    "head_commit": row["head_commit"],
                    "parent_branch": row["parent_branch"],
                    "description": row["description"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                }
                for row in rows
            ]

    # ==================== Character Evolution ====================

    async def save_character_evolution(self, story_id: str, character_data: Dict) -> bool:
        """Save character evolution state"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO character_evolution (
                    story_id, character_name, commit_hash,
                    evolution_state, emotional_state, relationships
                ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
                story_id,
                character_data["name"],
                character_data.get("commit_hash"),
                json.dumps(character_data.get("evolution_state", {})),
                json.dumps(character_data.get("emotional_state", {})),
                json.dumps(character_data.get("relationships", {}))
            )
            return True

    async def load_character_evolution(self, story_id: str, character_name: str) -> List[Dict]:
        """Load character evolution history"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM character_evolution
                WHERE story_id = $1 AND character_name = $2
                ORDER BY timestamp DESC
            """, story_id, character_name)

            return [
                {
                    "character_name": row["character_name"],
                    "commit_hash": row["commit_hash"],
                    "evolution_state": json.loads(row["evolution_state"]) if row["evolution_state"] else {},
                    "emotional_state": json.loads(row["emotional_state"]) if row["emotional_state"] else {},
                    "relationships": json.loads(row["relationships"]) if row["relationships"] else {},
                    "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None
                }
                for row in rows
            ]

    # ==================== User Interactions ====================

    async def save_interaction(self, interaction_data: Dict) -> bool:
        """Save user interaction"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_interactions (
                    story_id, user_id, interaction_type,
                    intent, decision, feedback
                ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
                interaction_data["story_id"],
                interaction_data.get("user_id", "anonymous"),
                interaction_data.get("interaction_type"),
                json.dumps(interaction_data.get("intent", {})),
                json.dumps(interaction_data.get("decision", {})),
                json.dumps(interaction_data.get("feedback", {}))
            )
            return True

    async def load_interactions(self, story_id: str, limit: int = 100) -> List[Dict]:
        """Load user interactions for a story"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM user_interactions
                WHERE story_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
            """, story_id, limit)

            return [
                {
                    "interaction_id": row["interaction_id"],
                    "user_id": row["user_id"],
                    "interaction_type": row["interaction_type"],
                    "intent": json.loads(row["intent"]) if row["intent"] else {},
                    "decision": json.loads(row["decision"]) if row["decision"] else {},
                    "feedback": json.loads(row["feedback"]) if row["feedback"] else {},
                    "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None
                }
                for row in rows
            ]

    # ==================== User Preferences ====================

    async def save_preferences(self, user_id: str, preferences: Dict) -> bool:
        """Save or update user preferences"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_preferences (
                    user_id, preferred_styles, avoided_styles,
                    interaction_history, learned_patterns
                ) VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO UPDATE SET
                    preferred_styles = EXCLUDED.preferred_styles,
                    avoided_styles = EXCLUDED.avoided_styles,
                    interaction_history = EXCLUDED.interaction_history,
                    learned_patterns = EXCLUDED.learned_patterns,
                    updated_at = NOW()
            """,
                user_id,
                json.dumps(preferences.get("preferred_styles", [])),
                json.dumps(preferences.get("avoided_styles", [])),
                json.dumps(preferences.get("interaction_history", [])),
                json.dumps(preferences.get("learned_patterns", {}))
            )
            return True

    async def load_preferences(self, user_id: str) -> Optional[Dict]:
        """Load user preferences"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM user_preferences WHERE user_id = $1
            """, user_id)

            if row:
                return {
                    "user_id": row["user_id"],
                    "preferred_styles": json.loads(row["preferred_styles"]) if row["preferred_styles"] else [],
                    "avoided_styles": json.loads(row["avoided_styles"]) if row["avoided_styles"] else [],
                    "interaction_history": json.loads(row["interaction_history"]) if row["interaction_history"] else [],
                    "learned_patterns": json.loads(row["learned_patterns"]) if row["learned_patterns"] else {},
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                }
            return None


# Example usage
async def test_database():
    """Test database operations"""
    db = StorylineDatabase()
    await db.initialize()

    try:
        # Test story save
        await db.save_story("test_story", {
            "title": "Test Story",
            "description": "A test story",
            "author": "Tester",
            "current_branch": "main",
            "head_commit": "abc123",
            "working_story": {"chapters": []},
            "metadata": {"genre": "adventure"}
        })

        # Test story load
        story = await db.load_story("test_story")
        print(f"Loaded story: {story}")

        # Test commit save
        await db.save_commit({
            "commit_hash": "abc123",
            "story_id": "test_story",
            "parent_hash": None,
            "author": "Tester",
            "message": "Initial commit",
            "changes": [],
            "story_snapshot": {"chapters": []}
        })

        print("✅ Database operations successful")

    finally:
        await db.cleanup()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_database())