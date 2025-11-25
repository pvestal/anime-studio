#!/usr/bin/env python3
"""
FileManager Module for Tower Anime Production System

Manages output file organization, tracking, and cleanup for generated content.
Addresses the chaotic file organization in ComfyUI output directory.

Author: Claude Code
Date: November 25, 2025
"""

import os
import shutil
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import logging
from dataclasses import dataclass, asdict
import hashlib
import mimetypes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class FileMetadata:
    """Metadata for generated files"""
    file_path: str
    job_id: str
    project_id: str
    timestamp: str
    file_type: str
    file_size: int
    file_extension: str
    checksum: str
    generation_type: str  # 'image', 'video', 'gif'
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileMetadata':
        """Create from dictionary"""
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)

class FileManager:
    """
    Comprehensive file management system for anime production output.

    Handles:
    - Project-based folder organization
    - File tracking and metadata
    - Automatic cleanup of old files
    - File naming conventions
    - Migration from chaotic output structure
    """

    def __init__(self, base_output_path: str = "/mnt/1TB-storage/ComfyUI/output"):
        self.base_output_path = Path(base_output_path)
        self.projects_path = self.base_output_path / "projects"
        self.legacy_path = self.base_output_path / "legacy"
        self.metadata_file = self.base_output_path / "file_metadata.json"
        self.cleanup_days = 30

        # Supported file types
        self.image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.tiff'}
        self.video_extensions = {'.mp4', '.avi', '.mov', '.webm', '.gif'}
        self.all_extensions = self.image_extensions | self.video_extensions

        # Initialize directory structure
        self._initialize_directories()

        # Load existing metadata
        self.metadata = self._load_metadata()

    def _initialize_directories(self) -> None:
        """Initialize the organized directory structure"""
        try:
            self.projects_path.mkdir(parents=True, exist_ok=True)
            self.legacy_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Initialized directories at {self.base_output_path}")
        except Exception as e:
            logger.error(f"Failed to initialize directories: {e}")
            raise

    def _load_metadata(self) -> Dict[str, FileMetadata]:
        """Load file metadata from JSON file"""
        if not self.metadata_file.exists():
            return {}

        try:
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)

            metadata = {}
            for file_path, meta_dict in data.items():
                try:
                    metadata[file_path] = FileMetadata.from_dict(meta_dict)
                except Exception as e:
                    logger.warning(f"Failed to load metadata for {file_path}: {e}")

            logger.info(f"Loaded metadata for {len(metadata)} files")
            return metadata
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            return {}

    def _save_metadata(self) -> None:
        """Save file metadata to JSON file"""
        try:
            data = {path: meta.to_dict() for path, meta in self.metadata.items()}

            with open(self.metadata_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            logger.debug(f"Saved metadata for {len(self.metadata)} files")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file"""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate checksum for {file_path}: {e}")
            return ""

    def _get_file_type(self, file_path: Path) -> Tuple[str, str]:
        """Determine file type and generation type"""
        extension = file_path.suffix.lower()

        if extension in self.image_extensions:
            return 'image', extension
        elif extension in self.video_extensions:
            if extension == '.gif':
                return 'gif', extension
            else:
                return 'video', extension
        else:
            return 'unknown', extension

    def _generate_organized_filename(self, job_id: str, timestamp: str,
                                   generation_type: str, extension: str) -> str:
        """Generate standardized filename"""
        return f"{job_id}_{timestamp}_{generation_type}{extension}"

    def organize_output(self, job_id: str, project_id: str,
                       source_files: List[str] = None) -> List[str]:
        """
        Organize output files into project structure.

        Args:
            job_id: Unique job identifier
            project_id: Project identifier
            source_files: Specific files to organize (if None, finds recent files)

        Returns:
            List of organized file paths
        """
        try:
            # Create project and job directories
            project_dir = self.projects_path / str(project_id)
            job_dir = project_dir / str(job_id)
            job_dir.mkdir(parents=True, exist_ok=True)

            organized_files = []
            timestamp = str(int(time.time()))

            # If no source files specified, find recent files
            if source_files is None:
                source_files = self._find_recent_files()

            for source_file in source_files:
                source_path = Path(source_file)

                # Skip if file doesn't exist or is already organized
                if not source_path.exists() or str(source_path).startswith(str(self.projects_path)):
                    continue

                # Determine file type
                generation_type, extension = self._get_file_type(source_path)

                if generation_type == 'unknown':
                    logger.warning(f"Unknown file type: {source_path}")
                    continue

                # Generate organized filename
                organized_filename = self._generate_organized_filename(
                    job_id, timestamp, generation_type, extension
                )

                # Move file to organized location
                target_path = job_dir / organized_filename

                try:
                    shutil.move(str(source_path), str(target_path))
                    organized_files.append(str(target_path))

                    # Create metadata
                    file_stats = target_path.stat()
                    metadata = FileMetadata(
                        file_path=str(target_path),
                        job_id=job_id,
                        project_id=str(project_id),
                        timestamp=timestamp,
                        file_type=generation_type,
                        file_size=file_stats.st_size,
                        file_extension=extension,
                        checksum=self._calculate_checksum(target_path),
                        generation_type=generation_type,
                        created_at=datetime.now()
                    )

                    self.metadata[str(target_path)] = metadata
                    logger.info(f"Organized: {source_path} -> {target_path}")

                except Exception as e:
                    logger.error(f"Failed to move {source_path} to {target_path}: {e}")

            # Save updated metadata
            self._save_metadata()

            logger.info(f"Organized {len(organized_files)} files for job {job_id}")
            return organized_files

        except Exception as e:
            logger.error(f"Failed to organize output for job {job_id}: {e}")
            return []

    def _find_recent_files(self, minutes: int = 5) -> List[str]:
        """Find files created in the last N minutes"""
        recent_files = []
        cutoff_time = time.time() - (minutes * 60)

        try:
            for file_path in self.base_output_path.glob('*'):
                if (file_path.is_file() and
                    file_path.stat().st_mtime > cutoff_time and
                    file_path.suffix.lower() in self.all_extensions):
                    recent_files.append(str(file_path))

            logger.info(f"Found {len(recent_files)} recent files")
            return recent_files

        except Exception as e:
            logger.error(f"Failed to find recent files: {e}")
            return []

    def get_job_files(self, job_id: str, project_id: str = None) -> List[Dict[str, Any]]:
        """
        Get all files for a specific job.

        Args:
            job_id: Job identifier
            project_id: Optional project filter

        Returns:
            List of file information dictionaries
        """
        job_files = []

        try:
            for file_path, metadata in self.metadata.items():
                if metadata.job_id == job_id:
                    if project_id is None or metadata.project_id == str(project_id):
                        file_info = metadata.to_dict()
                        file_info['exists'] = Path(file_path).exists()
                        job_files.append(file_info)

            logger.info(f"Found {len(job_files)} files for job {job_id}")
            return job_files

        except Exception as e:
            logger.error(f"Failed to get files for job {job_id}: {e}")
            return []

    def get_file_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific file"""
        try:
            metadata = self.metadata.get(file_path)
            if metadata:
                file_info = metadata.to_dict()
                file_info['exists'] = Path(file_path).exists()
                return file_info
            else:
                logger.warning(f"No metadata found for {file_path}")
                return None
        except Exception as e:
            logger.error(f"Failed to get metadata for {file_path}: {e}")
            return None

    def cleanup_old_files(self, days: int = None) -> Dict[str, int]:
        """
        Clean up files older than specified days.

        Args:
            days: Age threshold in days (default: 30)

        Returns:
            Dictionary with cleanup statistics
        """
        if days is None:
            days = self.cleanup_days

        cutoff_date = datetime.now() - timedelta(days=days)
        stats = {'deleted_files': 0, 'freed_bytes': 0, 'errors': 0}

        try:
            files_to_delete = []

            # Find old files
            for file_path, metadata in self.metadata.items():
                if metadata.created_at < cutoff_date:
                    files_to_delete.append((file_path, metadata))

            logger.info(f"Found {len(files_to_delete)} files older than {days} days")

            # Delete files
            for file_path, metadata in files_to_delete:
                try:
                    path_obj = Path(file_path)
                    if path_obj.exists():
                        file_size = path_obj.stat().st_size
                        path_obj.unlink()
                        stats['freed_bytes'] += file_size
                        logger.info(f"Deleted old file: {file_path}")

                    # Remove from metadata
                    del self.metadata[file_path]
                    stats['deleted_files'] += 1

                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")
                    stats['errors'] += 1

            # Clean up empty directories
            self._cleanup_empty_directories()

            # Save updated metadata
            self._save_metadata()

            logger.info(f"Cleanup complete: {stats['deleted_files']} files deleted, "
                       f"{stats['freed_bytes'] / (1024*1024):.1f} MB freed")

            return stats

        except Exception as e:
            logger.error(f"Failed to cleanup old files: {e}")
            stats['errors'] += 1
            return stats

    def _cleanup_empty_directories(self) -> None:
        """Remove empty project directories"""
        try:
            for project_dir in self.projects_path.iterdir():
                if project_dir.is_dir():
                    for job_dir in project_dir.iterdir():
                        if job_dir.is_dir() and not any(job_dir.iterdir()):
                            job_dir.rmdir()
                            logger.info(f"Removed empty job directory: {job_dir}")

                    if not any(project_dir.iterdir()):
                        project_dir.rmdir()
                        logger.info(f"Removed empty project directory: {project_dir}")
        except Exception as e:
            logger.error(f"Failed to cleanup empty directories: {e}")

    def migrate_legacy_files(self) -> Dict[str, int]:
        """
        Migrate existing chaotic files to organized structure.

        Returns:
            Dictionary with migration statistics
        """
        stats = {'migrated_files': 0, 'errors': 0, 'skipped_files': 0}

        try:
            # Find all files in root output directory
            legacy_files = []
            for file_path in self.base_output_path.glob('*'):
                if (file_path.is_file() and
                    file_path.suffix.lower() in self.all_extensions and
                    not str(file_path).startswith(str(self.projects_path)) and
                    not str(file_path).startswith(str(self.legacy_path))):
                    legacy_files.append(file_path)

            logger.info(f"Found {len(legacy_files)} legacy files to migrate")

            for file_path in legacy_files:
                try:
                    # Parse filename to extract information
                    job_info = self._parse_legacy_filename(file_path.name)

                    if job_info:
                        # Organize using extracted information
                        self.organize_output(
                            job_id=job_info['job_id'],
                            project_id=job_info['project_id'],
                            source_files=[str(file_path)]
                        )
                        stats['migrated_files'] += 1
                    else:
                        # Move to legacy directory with timestamp
                        timestamp = str(int(file_path.stat().st_mtime))
                        legacy_filename = f"legacy_{timestamp}_{file_path.name}"
                        legacy_target = self.legacy_path / legacy_filename

                        shutil.move(str(file_path), str(legacy_target))
                        logger.info(f"Moved to legacy: {file_path} -> {legacy_target}")
                        stats['skipped_files'] += 1

                except Exception as e:
                    logger.error(f"Failed to migrate {file_path}: {e}")
                    stats['errors'] += 1

            logger.info(f"Migration complete: {stats['migrated_files']} migrated, "
                       f"{stats['skipped_files']} moved to legacy, {stats['errors']} errors")

            return stats

        except Exception as e:
            logger.error(f"Failed to migrate legacy files: {e}")
            stats['errors'] += 1
            return stats

    def _parse_legacy_filename(self, filename: str) -> Optional[Dict[str, str]]:
        """
        Parse legacy filename to extract job and project information.

        Handles formats like:
        - animatediff_context_120frames_1762406010_00001.mp4
        - animatediff_2sec_test_00001.mp4
        """
        try:
            # Remove extension
            name_without_ext = filename.rsplit('.', 1)[0]

            # Look for timestamp patterns
            parts = name_without_ext.split('_')

            # Try to find timestamp (usually 10 digits)
            timestamp = None
            for part in parts:
                if part.isdigit() and len(part) >= 10:
                    timestamp = part
                    break

            if timestamp:
                job_id = f"legacy_{timestamp}"
                project_id = "legacy_migration"
                return {
                    'job_id': job_id,
                    'project_id': project_id,
                    'timestamp': timestamp
                }
            else:
                # Use file modification time as fallback
                return {
                    'job_id': f"legacy_{int(time.time())}",
                    'project_id': "legacy_migration",
                    'timestamp': str(int(time.time()))
                }

        except Exception as e:
            logger.error(f"Failed to parse legacy filename {filename}: {e}")
            return None

    def get_project_summary(self, project_id: str) -> Dict[str, Any]:
        """Get summary statistics for a project"""
        try:
            project_files = []
            total_size = 0
            file_types = {'image': 0, 'video': 0, 'gif': 0}

            for file_path, metadata in self.metadata.items():
                if metadata.project_id == str(project_id):
                    project_files.append(metadata)
                    total_size += metadata.file_size
                    file_types[metadata.generation_type] = file_types.get(metadata.generation_type, 0) + 1

            return {
                'project_id': project_id,
                'total_files': len(project_files),
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'file_types': file_types,
                'jobs': len(set(f.job_id for f in project_files)),
                'oldest_file': min(f.created_at for f in project_files) if project_files else None,
                'newest_file': max(f.created_at for f in project_files) if project_files else None
            }

        except Exception as e:
            logger.error(f"Failed to get project summary for {project_id}: {e}")
            return {}

    def get_system_stats(self) -> Dict[str, Any]:
        """Get overall file management system statistics"""
        try:
            total_files = len(self.metadata)
            total_size = sum(m.file_size for m in self.metadata.values())

            file_types = {}
            projects = set()
            jobs = set()

            for metadata in self.metadata.values():
                file_types[metadata.generation_type] = file_types.get(metadata.generation_type, 0) + 1
                projects.add(metadata.project_id)
                jobs.add(metadata.job_id)

            return {
                'total_files': total_files,
                'total_size_bytes': total_size,
                'total_size_gb': round(total_size / (1024 * 1024 * 1024), 2),
                'file_types': file_types,
                'total_projects': len(projects),
                'total_jobs': len(jobs),
                'base_path': str(self.base_output_path),
                'projects_path': str(self.projects_path),
                'legacy_path': str(self.legacy_path)
            }

        except Exception as e:
            logger.error(f"Failed to get system stats: {e}")
            return {}

# Convenience functions for common operations
def organize_job_output(job_id: str, project_id: str, source_files: List[str] = None) -> List[str]:
    """Convenience function to organize job output"""
    manager = FileManager()
    return manager.organize_output(job_id, project_id, source_files)

def cleanup_old_files(days: int = 30) -> Dict[str, int]:
    """Convenience function to cleanup old files"""
    manager = FileManager()
    return manager.cleanup_old_files(days)

def migrate_legacy_files() -> Dict[str, int]:
    """Convenience function to migrate legacy files"""
    manager = FileManager()
    return manager.migrate_legacy_files()

if __name__ == "__main__":
    # Example usage and testing
    manager = FileManager()

    print("File Manager System Stats:")
    stats = manager.get_system_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\nMigrating legacy files...")
    migration_stats = manager.migrate_legacy_files()
    print(f"Migration results: {migration_stats}")

    print("\nCleaning up files older than 30 days...")
    cleanup_stats = manager.cleanup_old_files(30)
    print(f"Cleanup results: {cleanup_stats}")