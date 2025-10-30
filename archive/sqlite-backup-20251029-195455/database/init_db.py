#!/usr/bin/env python3
"""
Anime Production Database Initialization
Creates SQLite database with git-like versioning support
"""

import sqlite3
import hashlib
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "anime.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

def generate_commit_hash(project_id: int, branch: str, message: str, timestamp: str) -> str:
    """Generate a git-style commit hash"""
    data = f"{project_id}{branch}{message}{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:40]

def init_database():
    """Initialize the database with schema and default data"""
    print(f"🗄️  Initializing anime production database at {DB_PATH}")
    
    # Check if schema file exists
    if not SCHEMA_PATH.exists():
        print(f"❌ Schema file not found: {SCHEMA_PATH}")
        return False
    
    # Remove existing database to start fresh
    if DB_PATH.exists():
        backup_path = DB_PATH.with_suffix(f".db.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        print(f"📦 Backing up existing database to {backup_path.name}")
        import shutil
        shutil.copy2(DB_PATH, backup_path)
        DB_PATH.unlink()
    
    # Create database and apply schema
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Read and execute schema
        with open(SCHEMA_PATH, 'r') as f:
            schema_sql = f.read()
        
        cursor.executescript(schema_sql)
        print("✅ Schema created successfully")
        
        # Create default project
        cursor.execute(
            "INSERT INTO projects (name, current_branch, description) VALUES (?, ?, ?)",
            ("default_project", "main", "Default anime production project")
        )
        project_id = cursor.lastrowid
        print(f"✅ Created default project (ID: {project_id})")
        
        # Create main branch
        cursor.execute(
            """INSERT INTO story_branches 
               (project_id, branch_name, description) 
               VALUES (?, ?, ?)""",
            (project_id, "main", "Main production branch")
        )
        print("✅ Created 'main' branch")
        
        # Create initial commit
        timestamp = datetime.now().isoformat()
        commit_hash = generate_commit_hash(project_id, "main", "Initial commit", timestamp)
        
        scene_snapshot = json.dumps({
            "scenes": [],
            "version": "1.0",
            "timestamp": timestamp
        })
        
        cursor.execute(
            """INSERT INTO story_commits 
               (commit_hash, project_id, branch_name, message, author, timestamp, scene_snapshot) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (commit_hash, project_id, "main", "Initial commit", "system", timestamp, scene_snapshot)
        )
        print(f"✅ Created initial commit ({commit_hash[:8]})")
        
        # Update project with last commit
        cursor.execute(
            "UPDATE projects SET last_commit_hash = ? WHERE id = ?",
            (commit_hash, project_id)
        )
        
        # Commit all changes
        conn.commit()
        
        # Verify tables were created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        
        print("\n📊 Database tables created:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   - {table} ({count} rows)")
        
        # Show database stats
        db_size = DB_PATH.stat().st_size / 1024  # KB
        print(f"\n💾 Database size: {db_size:.2f} KB")
        print(f"📍 Database location: {DB_PATH.absolute()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    success = init_database()
    exit(0 if success else 1)
