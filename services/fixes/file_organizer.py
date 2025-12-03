#!/usr/bin/env python3
"""File organizer service for anime production output files"""

import os
import shutil
import json
import time
import logging
import psycopg2
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnimeFileOrganizer(FileSystemEventHandler):
    """Monitors ComfyUI output and organizes files by project"""

    def __init__(self):
        self.source_dir = Path('/mnt/1TB-storage/ComfyUI/output')
        self.target_base = Path('/mnt/1TB-storage/anime-projects')
        self.metadata_file = 'job_metadata.json'

        # Database connection
        self.db_config = {
            'host': 'localhost',
            'database': 'anime_production',
            'user': 'patrick',
            'password': '***REMOVED***'
        }

        # Ensure target directory exists
        self.target_base.mkdir(parents=True, exist_ok=True)

    def extract_project_id(self, filename: str) -> Optional[str]:
        """Extract project ID from filename or metadata"""
        # Check for metadata file in the same directory
        file_path = Path(filename)
        metadata_path = file_path.parent / self.metadata_file

        if metadata_path.exists():
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    return metadata.get('project_id')
            except Exception as e:
                logger.error(f"Error reading metadata: {e}")

        # Try to extract from filename pattern
        # Expected pattern: projectid_timestamp_*.mp4 or *.png
        parts = file_path.stem.split('_')
        if len(parts) >= 2:
            # First part might be project ID
            potential_id = parts[0]
            if len(potential_id) == 36:  # UUID length
                return potential_id

        # Default to 'unorganized' if no project ID found
        return 'unorganized'

    def update_database(self, file_path: Path, project_id: str, new_location: Path):
        """Update database with file location"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Insert file record
            cursor.execute("""
                INSERT INTO anime_api.anime_files (
                    project_id,
                    filename,
                    file_path,
                    file_type,
                    file_size,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (filename, file_path) DO UPDATE
                SET organized_at = CURRENT_TIMESTAMP
            """, (
                None if project_id == 'unorganized' else project_id,
                file_path.name,
                str(new_location),
                file_path.suffix[1:] if file_path.suffix else 'unknown',
                file_path.stat().st_size,
                datetime.now()
            ))

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"Updated database for file: {file_path.name}")

        except psycopg2.Error as e:
            logger.error(f"Database error: {e}")
        except Exception as e:
            logger.error(f"Error updating database: {e}")

    def organize_file(self, file_path: Path):
        """Move file to organized project directory"""
        try:
            # Extract project ID
            project_id = self.extract_project_id(str(file_path))

            # Create project directory structure
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_type = 'videos' if file_path.suffix in ['.mp4', '.webm', '.avi'] else 'images'

            target_dir = self.target_base / project_id / file_type / timestamp[:8]  # Date folder
            target_dir.mkdir(parents=True, exist_ok=True)

            # Generate unique filename if needed
            target_file = target_dir / file_path.name
            if target_file.exists():
                base_name = file_path.stem
                extension = file_path.suffix
                counter = 1
                while target_file.exists():
                    target_file = target_dir / f"{base_name}_{counter}{extension}"
                    counter += 1

            # Copy file to organized location (keep original for ComfyUI Manager)
            shutil.copy2(str(file_path), str(target_file))
            logger.info(f"Copied {file_path.name} to {target_file}")

            # Update database with both locations
            self.update_database(file_path, project_id, target_file)

        except Exception as e:
            logger.error(f"Error organizing file {file_path}: {e}")

    def on_created(self, event):
        """Handle new file creation events"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Filter for relevant file types
        valid_extensions = {'.png', '.jpg', '.jpeg', '.mp4', '.webm', '.gif'}
        if file_path.suffix.lower() not in valid_extensions:
            return

        # Skip temporary files
        if file_path.name.startswith('.') or file_path.name.startswith('tmp'):
            return

        logger.info(f"New file detected: {file_path.name}")

        # Wait a moment for file to finish writing
        time.sleep(2)

        # Check if file still exists and is complete
        if file_path.exists() and file_path.stat().st_size > 0:
            self.organize_file(file_path)

    def scan_existing_files(self):
        """Scan and organize existing unorganized files"""
        logger.info(f"Scanning existing files in {self.source_dir}")

        if not self.source_dir.exists():
            logger.warning(f"Source directory {self.source_dir} does not exist")
            return

        organized_count = 0
        for file_path in self.source_dir.iterdir():
            if file_path.is_file() and not file_path.is_symlink():
                valid_extensions = {'.png', '.jpg', '.jpeg', '.mp4', '.webm', '.gif'}
                if file_path.suffix.lower() in valid_extensions:
                    self.organize_file(file_path)
                    organized_count += 1

        logger.info(f"Organized {organized_count} existing files")

def create_database_schema():
    """Create necessary database tables if they don't exist"""
    try:
        conn = psycopg2.connect(
            host='***REMOVED***',
            database='anime_production',
            user='patrick',
            password='***REMOVED***'
        )
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anime_files (
                id SERIAL PRIMARY KEY,
                project_id VARCHAR(255),
                filename VARCHAR(500),
                file_path TEXT UNIQUE,
                file_type VARCHAR(50),
                file_size BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_anime_files_project_id
            ON anime_files(project_id)
        """)

        conn.commit()
        cursor.close()
        conn.close()

        logger.info("Database schema ready")

    except Exception as e:
        logger.error(f"Error creating database schema: {e}")

def main():
    """Run the file organizer service"""
    # Create database schema
    create_database_schema()

    # Initialize organizer
    organizer = AnimeFileOrganizer()

    # Scan existing files first
    organizer.scan_existing_files()

    # Set up file system observer
    observer = Observer()
    observer.schedule(organizer, str(organizer.source_dir), recursive=False)
    observer.start()

    logger.info(f"File organizer monitoring {organizer.source_dir}")

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("File organizer stopped")

    observer.join()

if __name__ == '__main__':
    main()