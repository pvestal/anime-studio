# Anime Production Database - Git-like Versioning

## Database Location
- **Path**: /opt/tower-anime-production/database/anime.db
- **Size**: 116 KB
- **Created**: October 5, 2025

## Tables Created (12 total)

### Core Tables
- projects (1 row) - Top-level anime projects
- story_branches (1 row) - Git-like branching for storylines
- story_commits (1 row) - Version control for story changes
- scenes (0 rows) - Individual scenes in the anime
- characters (0 rows) - Character definitions with versioning

### Music & Audio
- music_playlists (0 rows) - Collections of tracks
- music_tracks (0 rows) - Individual music files
- playlist_tracks (0 rows) - Many-to-many playlist relationship
- music_scene_sync (0 rows) - Precise music-to-scene synchronization
- voice_assignments (0 rows) - Character voice lines

### Production
- render_queue (0 rows) - Scene rendering progress tracking

## Initial Setup

### Default Project
- Name: default_project
- Current Branch: main
- Status: active
- Initial Commit: f98ce38c

### Main Branch
- Branch Name: main
- Description: Main production branch
- Created: October 5, 2025

## Git-like Features

### Branching
Create alternative storylines without affecting main production.

### Commits
Track every change to scenes, characters, and story elements.

### Version Control
Full history of all changes with rollback capability.

## Database Schema
See schema.sql for complete table definitions with:
- Foreign key relationships
- CHECK constraints for data validation
- Indexes for performance
- JSON fields for flexible metadata

## Backups
Automatic backups created on re-initialization:
- anime.db.backup.20251004_215206 (52 KB - old schema)
- anime.db.backup.20251005_045210 (52 KB - old schema)

## Re-initialization
To recreate database from scratch:

