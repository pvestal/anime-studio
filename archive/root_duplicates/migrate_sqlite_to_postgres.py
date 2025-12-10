#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script
Migrates data from SQLite databases to PostgreSQL anime_production database
"""

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configurations
SQLITE_DB = "/opt/tower-anime-production/database/anime.db"
PG_CONFIG = {
    'host': 'localhost',
    'database': 'anime_production',
    'user': 'patrick',
    'port': 5432,
    'options': '-c search_path=anime_api,public'
}

def migrate_git_data():
    """Migrate git branches and commits from SQLite to PostgreSQL"""

    # Connect to databases
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(**PG_CONFIG)

    try:
        sqlite_cursor = sqlite_conn.cursor()
        pg_cursor = pg_conn.cursor()

        # Get the existing project ID in PostgreSQL
        pg_cursor.execute("SELECT id FROM projects ORDER BY id LIMIT 1")
        pg_project = pg_cursor.fetchone()
        if not pg_project:
            logger.error("No project found in PostgreSQL database")
            return False

        project_id = pg_project[0]
        logger.info(f"Using PostgreSQL project ID: {project_id}")

        # Migrate branches
        sqlite_cursor.execute("SELECT * FROM story_branches")
        sqlite_branches = sqlite_cursor.fetchall()

        logger.info(f"Migrating {len(sqlite_branches)} branches...")
        for branch in sqlite_branches:
            # Check if branch already exists
            pg_cursor.execute(
                "SELECT id FROM branches WHERE project_id = %s AND branch_name = %s",
                (project_id, branch['branch_name'])
            )
            if pg_cursor.fetchone():
                logger.info(f"Branch '{branch['branch_name']}' already exists, skipping")
                continue

            # Insert branch
            pg_cursor.execute("""
                INSERT INTO branches (project_id, branch_name, parent_branch, created_at)
                VALUES (%s, %s, %s, %s)
            """, (
                project_id,
                branch['branch_name'],
                branch['created_from_commit'],
                branch['created_at']
            ))
            logger.info(f"Migrated branch: {branch['branch_name']}")

        # Migrate commits
        sqlite_cursor.execute("SELECT * FROM story_commits")
        sqlite_commits = sqlite_cursor.fetchall()

        logger.info(f"Migrating {len(sqlite_commits)} commits...")
        for commit in sqlite_commits:
            # Check if commit already exists
            pg_cursor.execute(
                "SELECT id FROM commits WHERE commit_hash = %s",
                (commit['commit_hash'],)
            )
            if pg_cursor.fetchone():
                logger.info(f"Commit '{commit['commit_hash'][:8]}' already exists, skipping")
                continue

            # Insert commit
            pg_cursor.execute("""
                INSERT INTO commits (project_id, commit_hash, branch_name, message, author, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                project_id,
                commit['commit_hash'],
                commit['branch_name'],
                commit['message'],
                commit['author'],
                commit['timestamp']
            ))
            logger.info(f"Migrated commit: {commit['commit_hash'][:8]} - {commit['message']}")

        # Commit transaction
        pg_conn.commit()
        logger.info("✅ Migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        pg_conn.rollback()
        return False

    finally:
        sqlite_conn.close()
        pg_conn.close()

def verify_migration():
    """Verify that data was migrated correctly"""
    pg_conn = psycopg2.connect(**PG_CONFIG)

    try:
        cursor = pg_conn.cursor()

        # Check branches
        cursor.execute("SELECT COUNT(*) FROM branches")
        branch_count = cursor.fetchone()[0]

        # Check commits
        cursor.execute("SELECT COUNT(*) FROM commits")
        commit_count = cursor.fetchone()[0]

        logger.info(f"📊 Migration verification:")
        logger.info(f"   - Branches in PostgreSQL: {branch_count}")
        logger.info(f"   - Commits in PostgreSQL: {commit_count}")

        # Show sample data
        cursor.execute("SELECT branch_name, created_at FROM branches ORDER BY created_at")
        branches = cursor.fetchall()
        for branch in branches:
            logger.info(f"   - Branch: {branch[0]} (created: {branch[1]})")

        cursor.execute("SELECT commit_hash, message, author FROM commits ORDER BY created_at")
        commits = cursor.fetchall()
        for commit in commits:
            logger.info(f"   - Commit: {commit[0][:8]} - {commit[1]} by {commit[2]}")

        return True

    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False

    finally:
        pg_conn.close()

if __name__ == "__main__":
    logger.info("🚀 Starting SQLite to PostgreSQL migration...")

    # Check if SQLite database exists
    try:
        sqlite_conn = sqlite3.connect(SQLITE_DB)
        sqlite_conn.close()
        logger.info(f"✅ SQLite database found: {SQLITE_DB}")
    except Exception as e:
        logger.error(f"❌ SQLite database not accessible: {e}")
        exit(1)

    # Check PostgreSQL connection
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        pg_conn.close()
        logger.info("✅ PostgreSQL connection successful")
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection failed: {e}")
        exit(1)

    # Run migration
    if migrate_git_data():
        logger.info("🎉 Migration completed successfully!")
        verify_migration()
    else:
        logger.error("💥 Migration failed!")
        exit(1)