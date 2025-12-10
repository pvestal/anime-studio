#!/usr/bin/env python3
"""
Character Version Manager with Git-like capabilities.
Persists character definitions with version history using PostgreSQL and Echo Brain.
"""

import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "patrick",
    "password": "***REMOVED***",
    "database": "anime_production"
}

ECHO_URL = "http://localhost:8309"


class CharacterVersionManager:
    """Manages character definitions with git-like version control."""

    def __init__(self):
        self.setup_database()
        self.load_characters()

    def setup_database(self):
        """Create character versioning tables if they don't exist."""
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        try:
            # Main character table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS character_definitions (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) UNIQUE NOT NULL,
                    current_version VARCHAR(40) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Version history table (git-like commits)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS character_versions (
                    version_hash VARCHAR(40) PRIMARY KEY,
                    character_id INTEGER REFERENCES character_definitions(id),
                    parent_version VARCHAR(40),
                    definition JSONB NOT NULL,
                    commit_message TEXT,
                    author VARCHAR(100) DEFAULT 'system',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Character attributes for quick lookup
            cur.execute("""
                CREATE TABLE IF NOT EXISTS character_attributes (
                    id SERIAL PRIMARY KEY,
                    character_id INTEGER REFERENCES character_definitions(id),
                    attribute_key VARCHAR(100) NOT NULL,
                    attribute_value TEXT NOT NULL,
                    version_hash VARCHAR(40),
                    UNIQUE(character_id, attribute_key)
                )
            """)

            conn.commit()
            logger.info("✅ Character versioning database ready")

        except Exception as e:
            logger.error(f"Database setup error: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()

    def load_characters(self):
        """Load existing character definitions."""
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute("""
                SELECT cd.*, cv.definition
                FROM character_definitions cd
                JOIN character_versions cv ON cd.current_version = cv.version_hash
            """)

            characters = cur.fetchall()
            logger.info(f"📚 Loaded {len(characters)} character definitions")

            return characters

        except Exception as e:
            logger.error(f"Error loading characters: {e}")
            return []
        finally:
            cur.close()
            conn.close()

    def create_character(self, name: str, definition: Dict, message: str = None) -> str:
        """Create a new character with initial version."""

        # Generate version hash
        version_hash = self.generate_hash(definition)

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        try:
            # Create character entry
            cur.execute("""
                INSERT INTO character_definitions (name, current_version)
                VALUES (%s, %s)
                RETURNING id
            """, (name, version_hash))

            character_id = cur.fetchone()[0]

            # Create initial version
            cur.execute("""
                INSERT INTO character_versions
                (version_hash, character_id, definition, commit_message, author)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                version_hash,
                character_id,
                json.dumps(definition),
                message or f"Initial character: {name}",
                "system"
            ))

            # Store searchable attributes
            self.update_attributes(cur, character_id, definition, version_hash)

            conn.commit()
            logger.info(f"✅ Created character '{name}' with version {version_hash[:8]}")

            # Notify Echo Brain about new character
            self.notify_echo(name, definition, "character_created")

            return version_hash

        except psycopg2.IntegrityError:
            logger.error(f"Character '{name}' already exists")
            conn.rollback()
            return None
        except Exception as e:
            logger.error(f"Error creating character: {e}")
            conn.rollback()
            return None
        finally:
            cur.close()
            conn.close()

    def update_character(self, name: str, updates: Dict, message: str = None) -> str:
        """Update character with new version (git-like commit)."""

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get current version
            cur.execute("""
                SELECT cd.id, cd.current_version, cv.definition
                FROM character_definitions cd
                JOIN character_versions cv ON cd.current_version = cv.version_hash
                WHERE cd.name = %s
            """, (name,))

            result = cur.fetchone()
            if not result:
                logger.error(f"Character '{name}' not found")
                return None

            character_id = result['id']
            parent_version = result['current_version']
            current_def = result['definition']

            # Merge updates with current definition
            new_definition = {**current_def, **updates}
            new_version_hash = self.generate_hash(new_definition)

            # Create new version
            cur.execute("""
                INSERT INTO character_versions
                (version_hash, character_id, parent_version, definition, commit_message, author)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                new_version_hash,
                character_id,
                parent_version,
                json.dumps(new_definition),
                message or f"Updated {name}: {', '.join(updates.keys())}",
                "system"
            ))

            # Update current version pointer
            cur.execute("""
                UPDATE character_definitions
                SET current_version = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (new_version_hash, character_id))

            # Update attributes
            self.update_attributes(cur, character_id, new_definition, new_version_hash)

            conn.commit()
            logger.info(f"✅ Updated '{name}' to version {new_version_hash[:8]}")

            # Notify Echo Brain about update
            self.notify_echo(name, new_definition, "character_updated")

            return new_version_hash

        except Exception as e:
            logger.error(f"Error updating character: {e}")
            conn.rollback()
            return None
        finally:
            cur.close()
            conn.close()

    def get_character(self, name: str, version: Optional[str] = None) -> Dict:
        """Get character definition (optionally at specific version)."""

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            if version:
                # Get specific version
                cur.execute("""
                    SELECT cv.definition, cv.version_hash, cv.created_at
                    FROM character_versions cv
                    JOIN character_definitions cd ON cv.character_id = cd.id
                    WHERE cd.name = %s AND cv.version_hash LIKE %s
                """, (name, f"{version}%"))
            else:
                # Get current version
                cur.execute("""
                    SELECT cv.definition, cv.version_hash, cv.created_at
                    FROM character_definitions cd
                    JOIN character_versions cv ON cd.current_version = cv.version_hash
                    WHERE cd.name = %s
                """, (name,))

            result = cur.fetchone()
            if result:
                return {
                    "name": name,
                    "version": result['version_hash'],
                    "definition": result['definition'],
                    "created_at": result['created_at'].isoformat()
                }
            return None

        except Exception as e:
            logger.error(f"Error getting character: {e}")
            return None
        finally:
            cur.close()
            conn.close()

    def get_history(self, name: str) -> List[Dict]:
        """Get version history for a character (git log)."""

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute("""
                SELECT cv.version_hash, cv.parent_version, cv.commit_message,
                       cv.author, cv.created_at
                FROM character_versions cv
                JOIN character_definitions cd ON cv.character_id = cd.id
                WHERE cd.name = %s
                ORDER BY cv.created_at DESC
            """, (name,))

            return cur.fetchall()

        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return []
        finally:
            cur.close()
            conn.close()

    def diff_versions(self, name: str, version1: str, version2: str) -> Dict:
        """Compare two versions (git diff)."""

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get both versions
            cur.execute("""
                SELECT cv.version_hash, cv.definition
                FROM character_versions cv
                JOIN character_definitions cd ON cv.character_id = cd.id
                WHERE cd.name = %s AND
                      (cv.version_hash LIKE %s OR cv.version_hash LIKE %s)
            """, (name, f"{version1}%", f"{version2}%"))

            results = cur.fetchall()
            if len(results) != 2:
                return {"error": "Could not find both versions"}

            def1 = results[0]['definition']
            def2 = results[1]['definition']

            # Find differences
            added = {k: v for k, v in def2.items() if k not in def1}
            removed = {k: v for k, v in def1.items() if k not in def2}
            changed = {
                k: {"old": def1[k], "new": def2[k]}
                for k in def1 if k in def2 and def1[k] != def2[k]
            }

            return {
                "added": added,
                "removed": removed,
                "changed": changed
            }

        except Exception as e:
            logger.error(f"Error comparing versions: {e}")
            return {"error": str(e)}
        finally:
            cur.close()
            conn.close()

    def update_attributes(self, cur, character_id: int, definition: Dict, version_hash: str):
        """Update searchable attributes for a character."""

        # Clear old attributes
        cur.execute("DELETE FROM character_attributes WHERE character_id = %s", (character_id,))

        # Insert new attributes
        for key, value in definition.items():
            if isinstance(value, (str, int, float, bool)):
                cur.execute("""
                    INSERT INTO character_attributes
                    (character_id, attribute_key, attribute_value, version_hash)
                    VALUES (%s, %s, %s, %s)
                """, (character_id, key, str(value), version_hash))

    def generate_hash(self, definition: Dict) -> str:
        """Generate hash for a character definition."""
        json_str = json.dumps(definition, sort_keys=True)
        return hashlib.sha1(json_str.encode()).hexdigest()

    def notify_echo(self, name: str, definition: Dict, event_type: str):
        """Notify Echo Brain about character changes."""
        try:
            payload = {
                "query": f"Character {event_type}: {name}",
                "context": {
                    "character_name": name,
                    "definition": definition,
                    "event": event_type
                },
                "conversation_id": "character_management"
            }

            response = requests.post(
                f"{ECHO_URL}/api/echo/query",
                json=payload,
                timeout=5
            )

            if response.status_code == 200:
                logger.info(f"✅ Echo Brain notified about {event_type}")
        except Exception as e:
            logger.warning(f"Could not notify Echo: {e}")


# Initialize Kai Nakamura as definitively male
def initialize_kai_nakamura():
    """Initialize Kai Nakamura with correct male definition."""

    manager = CharacterVersionManager()

    kai_definition = {
        "gender": "male",
        "appearance": {
            "hair": "dark, slightly messy",
            "eyes": "sharp, intense dark eyes",
            "build": "lean, athletic",
            "height": "tall"
        },
        "personality": {
            "traits": ["serious", "determined", "strategic", "protective"],
            "role": "protagonist"
        },
        "outfit": {
            "default": "military-style uniform",
            "colors": ["black", "dark red accents"],
            "accessories": ["tactical belt", "fingerless gloves"]
        },
        "prompt_template": "Kai Nakamura, male anime protagonist, dark haired young man, serious expression, sharp eyes, military uniform with red accents"
    }

    # Create or update Kai
    existing = manager.get_character("Kai Nakamura")

    if existing:
        # Update to ensure male
        manager.update_character(
            "Kai Nakamura",
            {"gender": "male", **kai_definition},
            "Corrected gender to male as requested"
        )
    else:
        manager.create_character(
            "Kai Nakamura",
            kai_definition,
            "Initial creation of Kai Nakamura (male protagonist)"
        )

    print("✅ Kai Nakamura initialized as male with version control")
    return manager


if __name__ == "__main__":
    # Initialize Kai as male
    manager = initialize_kai_nakamura()

    # Show current definition
    kai = manager.get_character("Kai Nakamura")
    if kai:
        print(f"\n📋 Current Kai Nakamura (v{kai['version'][:8]})")
        print(json.dumps(kai['definition'], indent=2))

    # Show version history
    history = manager.get_history("Kai Nakamura")
    if history:
        print(f"\n📜 Version History:")
        for entry in history:
            print(f"  {entry['version_hash'][:8]} - {entry['commit_message']}")
            print(f"    by {entry['author']} at {entry['created_at']}")