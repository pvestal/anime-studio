"""
Modular Anime Production System
Inspired by Echo Brain's architecture
"""

from .comfyui_connector import ComfyUIConnector
from .job_manager import JobManager
from .workflow_generator import WorkflowGenerator
from .database_manager import DatabaseManager
from .status_monitor import StatusMonitor, ProgressUpdate, ProgressStatus, GenerationStats
from .file_manager import FileManager, organize_job_output, cleanup_old_files, migrate_legacy_files
from .file_manager_integration import FileManagerAPI, add_file_manager_routes, add_file_manager_fastapi_routes

__all__ = [
    'ComfyUIConnector',
    'JobManager',
    'WorkflowGenerator',
    'DatabaseManager',
    'StatusMonitor',
    'ProgressUpdate',
    'ProgressStatus',
    'GenerationStats',
    'FileManager',
    'organize_job_output',
    'cleanup_old_files',
    'migrate_legacy_files',
    'FileManagerAPI',
    'add_file_manager_routes',
    'add_file_manager_fastapi_routes'
]