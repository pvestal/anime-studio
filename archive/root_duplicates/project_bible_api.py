#!/usr/bin/env python3
"""
Project Bible API Endpoints for Anime Production System
Provides comprehensive project bible management with character definitions,
world building, story arcs, and Echo Brain integration.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import HTTPException
from pydantic import BaseModel, Field
from markupsafe import escape

logger = logging.getLogger(__name__)

class ProjectBibleCreate(BaseModel):
    """Model for creating a new project bible"""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    visual_style: Dict[str, Any] = Field(default_factory=dict)
    world_setting: Dict[str, Any] = Field(default_factory=dict)
    narrative_guidelines: Dict[str, Any] = Field(default_factory=dict)

class ProjectBibleUpdate(BaseModel):
    """Model for updating project bible"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=2000)
    visual_style: Optional[Dict[str, Any]] = None
    world_setting: Optional[Dict[str, Any]] = None
    narrative_guidelines: Optional[Dict[str, Any]] = None

class CharacterDefinition(BaseModel):
    """Model for character definitions within project bible"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=1000)
    visual_traits: Dict[str, Any] = Field(default_factory=dict)
    personality_traits: Dict[str, Any] = Field(default_factory=dict)
    relationships: Dict[str, str] = Field(default_factory=dict)
    evolution_arc: List[Dict[str, Any]] = Field(default_factory=list)

class ProjectBibleAPI:
    """API handler for project bible operations"""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    async def create_project_bible(self, project_id: int, bible_data: ProjectBibleCreate) -> Dict[str, Any]:
        """Create a new project bible for a project"""
        try:
            # Sanitize input to prevent XSS
            sanitized_title = escape(bible_data.title)
            sanitized_description = escape(bible_data.description)

            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Check if project exists
                cursor.execute("SELECT id FROM anime_api.projects WHERE id = %s", (project_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="Project not found")

                # Insert project bible
                cursor.execute("""
                    INSERT INTO anime_api.project_bibles
                    (project_id, title, description, visual_style, world_setting, narrative_guidelines, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, title, description, created_at
                """, (
                    project_id,
                    str(sanitized_title),
                    str(sanitized_description),
                    json.dumps(bible_data.visual_style),
                    json.dumps(bible_data.world_setting),
                    json.dumps(bible_data.narrative_guidelines),
                    datetime.now(),
                    datetime.now()
                ))

                result = cursor.fetchone()
                conn.commit()

                logger.info(f"Created project bible for project {project_id}")

                return {
                    "id": result[0],
                    "project_id": project_id,
                    "title": result[1],
                    "description": result[2],
                    "created_at": str(result[3])
                }

        except Exception as e:
            logger.error(f"Error creating project bible: {e}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    async def get_project_bible(self, project_id: int) -> Dict[str, Any]:
        """Get project bible for a project"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, title, description, visual_style, world_setting,
                           narrative_guidelines, created_at, updated_at
                    FROM anime_api.project_bibles
                    WHERE project_id = %s
                """, (project_id,))

                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=404, detail="Project bible not found")

                return {
                    "id": result[0],
                    "project_id": project_id,
                    "title": result[1],
                    "description": result[2],
                    "visual_style": result[3],
                    "world_setting": result[4],
                    "narrative_guidelines": result[5],
                    "created_at": str(result[6]),
                    "updated_at": str(result[7])
                }

        except Exception as e:
            logger.error(f"Error getting project bible: {e}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    async def update_project_bible(self, project_id: int, bible_update: ProjectBibleUpdate) -> Dict[str, Any]:
        """Update project bible"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Build dynamic update query
                update_fields = []
                update_values = []

                if bible_update.title is not None:
                    update_fields.append("title = %s")
                    update_values.append(str(escape(bible_update.title)))

                if bible_update.description is not None:
                    update_fields.append("description = %s")
                    update_values.append(str(escape(bible_update.description)))

                if bible_update.visual_style is not None:
                    update_fields.append("visual_style = %s")
                    update_values.append(bible_update.visual_style)

                if bible_update.world_setting is not None:
                    update_fields.append("world_setting = %s")
                    update_values.append(bible_update.world_setting)

                if bible_update.narrative_guidelines is not None:
                    update_fields.append("narrative_guidelines = %s")
                    update_values.append(bible_update.narrative_guidelines)

                if not update_fields:
                    raise HTTPException(status_code=400, detail="No fields to update")

                update_fields.append("updated_at = %s")
                update_values.append(datetime.now())
                update_values.append(project_id)

                query = f"""
                    UPDATE anime_api.project_bibles
                    SET {', '.join(update_fields)}
                    WHERE project_id = %s
                    RETURNING id, title, description, updated_at
                """

                cursor.execute(query, update_values)
                result = cursor.fetchone()

                if not result:
                    raise HTTPException(status_code=404, detail="Project bible not found")

                conn.commit()
                logger.info(f"Updated project bible for project {project_id}")

                return {
                    "id": result[0],
                    "project_id": project_id,
                    "title": result[1],
                    "description": result[2],
                    "updated_at": str(result[3])
                }

        except Exception as e:
            logger.error(f"Error updating project bible: {e}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    async def add_character_to_bible(self, project_id: int, character: CharacterDefinition) -> Dict[str, Any]:
        """Add character definition to project bible"""
        try:
            # Sanitize character data
            sanitized_name = escape(character.name)
            sanitized_description = escape(character.description)

            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Check if project bible exists
                cursor.execute("SELECT id FROM anime_api.project_bibles WHERE project_id = %s", (project_id,))
                bible = cursor.fetchone()
                if not bible:
                    raise HTTPException(status_code=404, detail="Project bible not found")

                # Insert character definition
                cursor.execute("""
                    INSERT INTO anime_api.bible_characters
                    (bible_id, name, description, visual_traits, personality_traits, relationships, evolution_arc, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, name, created_at
                """, (
                    bible[0],
                    str(sanitized_name),
                    str(sanitized_description),
                    json.dumps(character.visual_traits),
                    json.dumps(character.personality_traits),
                    json.dumps(character.relationships),
                    json.dumps(character.evolution_arc),
                    datetime.now()
                ))

                result = cursor.fetchone()
                conn.commit()

                logger.info(f"Added character {character.name} to project bible {bible[0]}")

                return {
                    "id": result[0],
                    "bible_id": bible[0],
                    "name": result[1],
                    "created_at": str(result[2])
                }

        except Exception as e:
            logger.error(f"Error adding character to bible: {e}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    async def get_bible_characters(self, project_id: int) -> List[Dict[str, Any]]:
        """Get all characters from project bible"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT bc.id, bc.name, bc.description, bc.visual_traits,
                           bc.personality_traits, bc.relationships, bc.evolution_arc, bc.created_at
                    FROM anime_api.bible_characters bc
                    JOIN anime_api.project_bibles pb ON bc.bible_id = pb.id
                    WHERE pb.project_id = %s
                    ORDER BY bc.name
                """, (project_id,))

                results = cursor.fetchall()

                characters = []
                for row in results:
                    characters.append({
                        "id": row[0],
                        "name": row[1],
                        "description": row[2],
                        "visual_traits": row[3],
                        "personality_traits": row[4],
                        "relationships": row[5],
                        "evolution_arc": row[6],
                        "created_at": str(row[7])
                    })

                return characters

        except Exception as e:
            logger.error(f"Error getting bible characters: {e}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    async def get_bible_history(self, project_id: int) -> List[Dict[str, Any]]:
        """Get revision history for project bible"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT version, title, description, updated_at, change_summary
                    FROM anime_api.bible_history
                    WHERE project_id = %s
                    ORDER BY version DESC
                """, (project_id,))

                results = cursor.fetchall()

                history = []
                for row in results:
                    history.append({
                        "version": row[0],
                        "title": row[1],
                        "description": row[2],
                        "updated_at": str(row[3]),
                        "change_summary": row[4]
                    })

                return history

        except Exception as e:
            logger.error(f"Error getting bible history: {e}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Database schema creation for project bible tables
BIBLE_SCHEMA_SQL = """
-- Project Bible main table
CREATE TABLE IF NOT EXISTS anime_api.project_bibles (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES anime_api.projects(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    visual_style JSONB DEFAULT '{}',
    world_setting JSONB DEFAULT '{}',
    narrative_guidelines JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id)
);

-- Bible Characters table
CREATE TABLE IF NOT EXISTS anime_api.bible_characters (
    id SERIAL PRIMARY KEY,
    bible_id INTEGER REFERENCES anime_api.project_bibles(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    visual_traits JSONB DEFAULT '{}',
    personality_traits JSONB DEFAULT '{}',
    relationships JSONB DEFAULT '{}',
    evolution_arc JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bible_id, name)
);

-- Bible History table for versioning
CREATE TABLE IF NOT EXISTS anime_api.bible_history (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES anime_api.projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    title VARCHAR(200),
    description TEXT,
    change_summary TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_project_bibles_project_id ON anime_api.project_bibles(project_id);
CREATE INDEX IF NOT EXISTS idx_bible_characters_bible_id ON anime_api.bible_characters(bible_id);
CREATE INDEX IF NOT EXISTS idx_bible_history_project_id ON anime_api.bible_history(project_id);
"""