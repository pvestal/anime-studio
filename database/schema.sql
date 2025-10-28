-- Anime Production Database Schema with Git-like Versioning
-- Created: 2025-10-04

-- Projects table: Top-level anime projects
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    current_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_commit_hash TEXT,
    description TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived', 'completed')),
    FOREIGN KEY (last_commit_hash) REFERENCES story_commits(commit_hash)
);

-- Story branches: Git-like branching for alternative storylines
CREATE TABLE IF NOT EXISTS story_branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    branch_name TEXT NOT NULL,
    parent_branch TEXT,
    created_from_commit TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_merged BOOLEAN DEFAULT 0,
    merged_into_branch TEXT,
    merged_at TIMESTAMP,
    description TEXT,
    UNIQUE(project_id, branch_name),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (created_from_commit) REFERENCES story_commits(commit_hash)
);

-- Story commits: Version control for story changes
CREATE TABLE IF NOT EXISTS story_commits (
    commit_hash TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL,
    branch_name TEXT NOT NULL,
    parent_commit TEXT,
    message TEXT NOT NULL,
    author TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scene_snapshot TEXT NOT NULL, -- JSON snapshot of all scenes at this commit
    character_snapshot TEXT, -- JSON snapshot of character states
    metadata TEXT, -- JSON for additional metadata
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_commit) REFERENCES story_commits(commit_hash)
);

-- Scenes: Individual scenes in the anime
CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    branch_name TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    scene_number INTEGER NOT NULL,
    description TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    music_playlist_id INTEGER,
    music_sync_map TEXT, -- JSON: {track_id: {start: 0, markers: []}}
    generated_frames_path TEXT,
    video_path TEXT,
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'generated', 'rendered', 'final')),
    visual_style TEXT, -- JSON: camera angles, lighting, etc.
    dialogue TEXT, -- JSON: [{character_id, line, timestamp}]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, branch_name, commit_hash, scene_number),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (commit_hash) REFERENCES story_commits(commit_hash),
    FOREIGN KEY (music_playlist_id) REFERENCES music_playlists(id)
);

-- Characters: Character definitions with versioning
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL UNIQUE, -- Stable ID across versions (e.g., hero_001)
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    design_prompt TEXT NOT NULL,
    voice_id TEXT,
    personality TEXT, -- JSON: traits, speech patterns, relationships
    appearance_hash TEXT, -- Hash of visual design for cache lookup
    music_theme_id INTEGER, -- Character's theme music
    git_tag TEXT, -- Version tag (e.g., v1.0, redesign-2024)
    project_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    visual_reference_path TEXT, -- Path to generated reference images
    UNIQUE(character_id, version),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (music_theme_id) REFERENCES music_tracks(id)
);

-- Music playlists: Collections of tracks for scenes
CREATE TABLE IF NOT EXISTS music_playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_id INTEGER NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Music tracks: Individual music files
CREATE TABLE IF NOT EXISTS music_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    genre TEXT,
    mood TEXT, -- JSON: [emotional, energetic, etc.]
    bpm INTEGER,
    key_signature TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT -- JSON: additional track info
);

-- Playlist tracks: Many-to-many relationship
CREATE TABLE IF NOT EXISTS playlist_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL,
    track_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    UNIQUE(playlist_id, position),
    FOREIGN KEY (playlist_id) REFERENCES music_playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES music_tracks(id) ON DELETE CASCADE
);

-- Music scene sync: Precise synchronization between music and scenes
CREATE TABLE IF NOT EXISTS music_scene_sync (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL,
    playlist_id INTEGER,
    track_id INTEGER NOT NULL,
    start_time REAL NOT NULL, -- Start time in scene (seconds)
    duration REAL NOT NULL, -- Duration of music in scene (seconds)
    sync_markers TEXT, -- JSON: [{timestamp: 12.5, event: beat_drop, action: cut_to_closeup}]
    fade_in REAL DEFAULT 0, -- Fade in duration (seconds)
    fade_out REAL DEFAULT 0, -- Fade out duration (seconds)
    volume REAL DEFAULT 1.0 CHECK(volume >= 0 AND volume <= 1.0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
    FOREIGN KEY (playlist_id) REFERENCES music_playlists(id),
    FOREIGN KEY (track_id) REFERENCES music_tracks(id)
);

-- Voice assignments: Character voice lines for scenes
CREATE TABLE IF NOT EXISTS voice_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL,
    voice_id TEXT NOT NULL,
    dialogue_line_id TEXT, -- Reference to specific line in scene dialogue JSON
    scene_id INTEGER NOT NULL,
    audio_file_path TEXT,
    line_text TEXT NOT NULL,
    timestamp_in_scene REAL NOT NULL, -- When the line starts (seconds)
    duration REAL, -- Duration of audio (seconds)
    emotion TEXT, -- e.g., angry, sad, excited
    processing_status TEXT DEFAULT 'pending' CHECK(processing_status IN ('pending', 'generated', 'approved', 'rejected')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (character_id) REFERENCES characters(character_id),
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
);

-- Render queue: Track scene rendering progress
CREATE TABLE IF NOT EXISTS render_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL,
    status TEXT DEFAULT 'queued' CHECK(status IN ('queued', 'processing', 'completed', 'failed')),
    priority INTEGER DEFAULT 5,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    output_path TEXT,
    render_settings TEXT, -- JSON: resolution, fps, codec, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_commits_branch ON story_commits(branch_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_scenes_project_branch ON scenes(project_id, branch_name, scene_number);
CREATE INDEX IF NOT EXISTS idx_characters_active ON characters(character_id, is_active);
CREATE INDEX IF NOT EXISTS idx_voice_assignments_scene ON voice_assignments(scene_id);
CREATE INDEX IF NOT EXISTS idx_music_sync_scene ON music_scene_sync(scene_id);
CREATE INDEX IF NOT EXISTS idx_render_queue_status ON render_queue(status, priority DESC);
