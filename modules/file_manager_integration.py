#!/usr/bin/env python3
"""
FileManager Integration Example for Tower Anime Production API

Shows how to integrate FileManager with the existing anime production workflow.
Provides API endpoints for file management operations.

Author: Claude Code
Date: November 25, 2025
"""

import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import logging

from .file_manager import FileManager

logger = logging.getLogger(__name__)

class FileManagerAPI:
    """
    API integration layer for FileManager.
    Provides endpoints that can be added to the anime production API.
    """

    def __init__(self):
        self.file_manager = FileManager()

    def organize_job_files(self, job_id: str, project_id: str,
                          source_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        API endpoint to organize files for a specific job.

        Args:
            job_id: Unique job identifier
            project_id: Project identifier
            source_files: Optional list of specific files to organize

        Returns:
            API response with organized files and metadata
        """
        try:
            organized_files = self.file_manager.organize_output(
                job_id=job_id,
                project_id=project_id,
                source_files=source_files
            )

            return {
                "success": True,
                "job_id": job_id,
                "project_id": project_id,
                "organized_files": organized_files,
                "file_count": len(organized_files),
                "message": f"Successfully organized {len(organized_files)} files"
            }

        except Exception as e:
            logger.error(f"Failed to organize files for job {job_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "job_id": job_id,
                "project_id": project_id
            }

    def get_job_files_api(self, job_id: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        API endpoint to retrieve files for a specific job.

        Args:
            job_id: Job identifier
            project_id: Optional project filter

        Returns:
            API response with job files and metadata
        """
        try:
            job_files = self.file_manager.get_job_files(job_id=job_id, project_id=project_id)

            return {
                "success": True,
                "job_id": job_id,
                "project_id": project_id,
                "files": job_files,
                "file_count": len(job_files),
                "total_size_bytes": sum(f.get('file_size', 0) for f in job_files),
                "has_images": any(f.get('generation_type') == 'image' for f in job_files),
                "has_videos": any(f.get('generation_type') == 'video' for f in job_files)
            }

        except Exception as e:
            logger.error(f"Failed to get files for job {job_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "job_id": job_id
            }

    def cleanup_old_files_api(self, days: int = 30) -> Dict[str, Any]:
        """
        API endpoint to cleanup old files.

        Args:
            days: Age threshold in days

        Returns:
            API response with cleanup statistics
        """
        try:
            cleanup_stats = self.file_manager.cleanup_old_files(days=days)

            return {
                "success": True,
                "cleanup_stats": cleanup_stats,
                "message": f"Cleanup completed. Deleted {cleanup_stats['deleted_files']} files, "
                          f"freed {cleanup_stats['freed_bytes'] / (1024*1024):.1f} MB"
            }

        except Exception as e:
            logger.error(f"Failed to cleanup files: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_project_files_api(self, project_id: str) -> Dict[str, Any]:
        """
        API endpoint to get all files for a project.

        Args:
            project_id: Project identifier

        Returns:
            API response with project files and summary
        """
        try:
            # Get project summary
            summary = self.file_manager.get_project_summary(project_id)

            # Get all files for project
            all_files = []
            for file_path, metadata in self.file_manager.metadata.items():
                if metadata.project_id == str(project_id):
                    file_info = metadata.to_dict()
                    file_info['exists'] = Path(file_path).exists()
                    all_files.append(file_info)

            return {
                "success": True,
                "project_id": project_id,
                "summary": summary,
                "files": all_files,
                "file_count": len(all_files)
            }

        except Exception as e:
            logger.error(f"Failed to get project files for {project_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "project_id": project_id
            }

    def get_system_status_api(self) -> Dict[str, Any]:
        """
        API endpoint to get file system status and statistics.

        Returns:
            API response with system statistics
        """
        try:
            stats = self.file_manager.get_system_stats()

            # Add additional status information
            status_info = {
                "file_manager_version": "1.0.0",
                "last_updated": datetime.now().isoformat(),
                "directories": {
                    "base_path_exists": Path(stats['base_path']).exists(),
                    "projects_path_exists": Path(stats['projects_path']).exists(),
                    "legacy_path_exists": Path(stats['legacy_path']).exists()
                }
            }

            return {
                "success": True,
                "stats": stats,
                "status": status_info
            }

        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def migrate_legacy_files_api(self) -> Dict[str, Any]:
        """
        API endpoint to migrate legacy files to organized structure.

        Returns:
            API response with migration statistics
        """
        try:
            migration_stats = self.file_manager.migrate_legacy_files()

            return {
                "success": True,
                "migration_stats": migration_stats,
                "message": f"Migration completed. {migration_stats['migrated_files']} files migrated, "
                          f"{migration_stats['skipped_files']} moved to legacy, "
                          f"{migration_stats['errors']} errors"
            }

        except Exception as e:
            logger.error(f"Failed to migrate legacy files: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def delete_job_files_api(self, job_id: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        API endpoint to delete all files for a specific job.

        Args:
            job_id: Job identifier
            project_id: Optional project filter

        Returns:
            API response with deletion statistics
        """
        try:
            deleted_files = 0
            freed_bytes = 0
            errors = 0

            # Get job files
            job_files = self.file_manager.get_job_files(job_id=job_id, project_id=project_id)

            # Delete each file
            for file_info in job_files:
                file_path = file_info['file_path']
                try:
                    path_obj = Path(file_path)
                    if path_obj.exists():
                        file_size = path_obj.stat().st_size
                        path_obj.unlink()
                        freed_bytes += file_size
                        deleted_files += 1

                    # Remove from metadata
                    if file_path in self.file_manager.metadata:
                        del self.file_manager.metadata[file_path]

                except Exception as e:
                    logger.error(f"Failed to delete file {file_path}: {e}")
                    errors += 1

            # Save updated metadata
            self.file_manager._save_metadata()

            # Clean up empty directories
            self.file_manager._cleanup_empty_directories()

            return {
                "success": True,
                "job_id": job_id,
                "project_id": project_id,
                "deleted_files": deleted_files,
                "freed_bytes": freed_bytes,
                "freed_mb": round(freed_bytes / (1024*1024), 2),
                "errors": errors,
                "message": f"Deleted {deleted_files} files for job {job_id}"
            }

        except Exception as e:
            logger.error(f"Failed to delete job files for {job_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "job_id": job_id
            }

# Flask/FastAPI integration examples
def add_file_manager_routes(app, api_prefix="/api/files"):
    """
    Add FileManager routes to a Flask app.

    Args:
        app: Flask application instance
        api_prefix: API prefix for routes
    """
    file_api = FileManagerAPI()

    @app.route(f"{api_prefix}/organize", methods=['POST'])
    def organize_files():
        data = request.get_json()
        job_id = data.get('job_id')
        project_id = data.get('project_id')
        source_files = data.get('source_files')

        if not job_id or not project_id:
            return {"success": False, "error": "job_id and project_id are required"}, 400

        result = file_api.organize_job_files(job_id, project_id, source_files)
        return result, 200 if result['success'] else 500

    @app.route(f"{api_prefix}/jobs/<job_id>", methods=['GET'])
    def get_job_files(job_id):
        project_id = request.args.get('project_id')
        result = file_api.get_job_files_api(job_id, project_id)
        return result, 200 if result['success'] else 500

    @app.route(f"{api_prefix}/projects/<project_id>", methods=['GET'])
    def get_project_files(project_id):
        result = file_api.get_project_files_api(project_id)
        return result, 200 if result['success'] else 500

    @app.route(f"{api_prefix}/cleanup", methods=['POST'])
    def cleanup_files():
        data = request.get_json() or {}
        days = data.get('days', 30)
        result = file_api.cleanup_old_files_api(days)
        return result, 200 if result['success'] else 500

    @app.route(f"{api_prefix}/status", methods=['GET'])
    def get_status():
        result = file_api.get_system_status_api()
        return result, 200 if result['success'] else 500

    @app.route(f"{api_prefix}/migrate", methods=['POST'])
    def migrate_legacy():
        result = file_api.migrate_legacy_files_api()
        return result, 200 if result['success'] else 500

    @app.route(f"{api_prefix}/jobs/<job_id>", methods=['DELETE'])
    def delete_job_files(job_id):
        project_id = request.args.get('project_id')
        result = file_api.delete_job_files_api(job_id, project_id)
        return result, 200 if result['success'] else 500

# FastAPI integration example
def add_file_manager_fastapi_routes(app, api_prefix: str = "/api/files"):
    """
    Add FileManager routes to a FastAPI app.

    Args:
        app: FastAPI application instance
        api_prefix: API prefix for routes
    """
    from fastapi import HTTPException
    from pydantic import BaseModel

    class OrganizeRequest(BaseModel):
        job_id: str
        project_id: str
        source_files: Optional[List[str]] = None

    class CleanupRequest(BaseModel):
        days: int = 30

    file_api = FileManagerAPI()

    @app.post(f"{api_prefix}/organize")
    async def organize_files(request: OrganizeRequest):
        result = file_api.organize_job_files(
            request.job_id,
            request.project_id,
            request.source_files
        )
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['error'])
        return result

    @app.get(f"{api_prefix}/jobs/{{job_id}}")
    async def get_job_files(job_id: str, project_id: Optional[str] = None):
        result = file_api.get_job_files_api(job_id, project_id)
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['error'])
        return result

    @app.get(f"{api_prefix}/projects/{{project_id}}")
    async def get_project_files(project_id: str):
        result = file_api.get_project_files_api(project_id)
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['error'])
        return result

    @app.post(f"{api_prefix}/cleanup")
    async def cleanup_files(request: CleanupRequest):
        result = file_api.cleanup_old_files_api(request.days)
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['error'])
        return result

    @app.get(f"{api_prefix}/status")
    async def get_status():
        result = file_api.get_system_status_api()
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['error'])
        return result

    @app.post(f"{api_prefix}/migrate")
    async def migrate_legacy():
        result = file_api.migrate_legacy_files_api()
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['error'])
        return result

    @app.delete(f"{api_prefix}/jobs/{{job_id}}")
    async def delete_job_files(job_id: str, project_id: Optional[str] = None):
        result = file_api.delete_job_files_api(job_id, project_id)
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['error'])
        return result

if __name__ == "__main__":
    # Example usage
    api = FileManagerAPI()

    # Test organize files
    print("Testing FileManager API...")

    # Get system status
    status = api.get_system_status_api()
    print("System Status:", status['success'])

    # Get project files
    if status['success'] and status['stats']['total_projects'] > 0:
        project_files = api.get_project_files_api("legacy_migration")
        print(f"Project files: {project_files.get('file_count', 0)} files")