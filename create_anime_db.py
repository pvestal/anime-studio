#!/usr/bin/env python3
"""Create anime database with proper persistence"""

import sqlite3
import os

db_path = "/opt/tower-anime-production/database/anime.db"
os.makedirs(os.path.dirname(db_path), exist_ok=True)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Projects table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        style TEXT DEFAULT 'anime',
        status TEXT DEFAULT 'created',
        frames_dir TEXT,
        video_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# Characters table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER,
        name TEXT NOT NULL,
        description TEXT,
        design_prompt TEXT,
        voice_id TEXT,
        model_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
''')

# Scenes table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS scenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER,
        scene_number INTEGER,
        description TEXT,
        duration_seconds REAL,
        frame_count INTEGER,
        workflow_json TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
''')

# Frames table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS frames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scene_id INTEGER,
        frame_number INTEGER,
        file_path TEXT,
        prompt_used TEXT,
        generation_time REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (scene_id) REFERENCES scenes(id)
    )
''')

# Generation jobs table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS generation_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER,
        job_type TEXT,
        status TEXT DEFAULT 'queued',
        progress INTEGER DEFAULT 0,
        result_path TEXT,
        error_message TEXT,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
''')

conn.commit()
print(f"✅ Created anime database at {db_path}")

# Verify tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print(f"📊 Tables created: {[t[0] for t in tables]}")

conn.close()
