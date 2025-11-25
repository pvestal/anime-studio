#!/usr/bin/env python3
"""
FileManager Usage Examples for Tower Anime Production System

Demonstrates how to integrate the FileManager module with existing
anime production workflows to handle file organization and cleanup.

Author: Claude Code
Date: November 25, 2025
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.file_manager import FileManager, organize_job_output
from modules.file_manager_integration import FileManagerAPI
from datetime import datetime

def example_workflow_integration():
    """Example of integrating FileManager with anime generation workflow"""

    print("=== FileManager Integration Example ===")

    # Initialize FileManager
    file_manager = FileManager()

    # Example: Organize files after a generation job completes
    job_id = "anime_gen_001"
    project_id = "tokyo_debt_series"

    print(f"\n1. Organizing files for job: {job_id}")

    # This would normally be called after ComfyUI generation completes
    organized_files = file_manager.organize_output(
        job_id=job_id,
        project_id=project_id
        # source_files would be auto-detected from recent files
    )

    if organized_files:
        print(f"   Successfully organized {len(organized_files)} files")
        for file_path in organized_files[:3]:  # Show first 3
            print(f"   - {file_path}")
        if len(organized_files) > 3:
            print(f"   ... and {len(organized_files) - 3} more files")
    else:
        print("   No files to organize (or no recent files found)")

    # Example: Get files for a job (for API response)
    print(f"\n2. Retrieving files for job: {job_id}")
    job_files = file_manager.get_job_files(job_id, project_id)

    if job_files:
        print(f"   Found {len(job_files)} files for job {job_id}")
        total_size = sum(f['file_size'] for f in job_files)
        print(f"   Total size: {total_size / (1024*1024):.1f} MB")

        # Show file types
        file_types = {}
        for f in job_files:
            file_types[f['generation_type']] = file_types.get(f['generation_type'], 0) + 1
        print(f"   File types: {file_types}")
    else:
        print("   No files found for this job")

    # Example: Get project summary
    print(f"\n3. Project summary for: {project_id}")
    summary = file_manager.get_project_summary(project_id)

    if summary:
        print(f"   Total files: {summary['total_files']}")
        print(f"   Total jobs: {summary['jobs']}")
        print(f"   Storage used: {summary['total_size_mb']} MB")
        print(f"   File types: {summary['file_types']}")
    else:
        print("   No data found for this project")

def example_api_integration():
    """Example of using the API integration layer"""

    print("\n=== API Integration Example ===")

    # Initialize API
    api = FileManagerAPI()

    # Example: API call to get system status
    print("\n1. System Status API:")
    status_response = api.get_system_status_api()

    if status_response['success']:
        stats = status_response['stats']
        print(f"   Total files: {stats['total_files']}")
        print(f"   Total projects: {stats['total_projects']}")
        print(f"   Storage used: {stats['total_size_gb']} GB")
    else:
        print(f"   Error: {status_response['error']}")

    # Example: API call to organize files
    print("\n2. Organize Files API:")
    organize_response = api.organize_job_files(
        job_id="api_test_job",
        project_id="api_test_project"
    )

    if organize_response['success']:
        print(f"   Organized {organize_response['file_count']} files")
        print(f"   Message: {organize_response['message']}")
    else:
        print(f"   Error: {organize_response['error']}")

    # Example: API call to get project files
    print("\n3. Project Files API:")
    if status_response['success'] and stats['total_projects'] > 0:
        # Use the legacy_migration project we know exists
        project_response = api.get_project_files_api("legacy_migration")

        if project_response['success']:
            print(f"   Project files: {project_response['file_count']}")
            summary = project_response['summary']
            print(f"   Total size: {summary['total_size_mb']} MB")
            print(f"   File types: {summary['file_types']}")
        else:
            print(f"   Error: {project_response['error']}")

def example_cleanup_workflow():
    """Example of file cleanup workflow"""

    print("\n=== Cleanup Workflow Example ===")

    file_manager = FileManager()

    # Get current stats
    print("\n1. Current System Stats:")
    stats = file_manager.get_system_stats()
    print(f"   Total files: {stats['total_files']}")
    print(f"   Storage used: {stats['total_size_gb']} GB")

    # Simulate cleanup (we'll use a very high number so nothing gets deleted)
    print("\n2. Cleanup Simulation (files older than 365 days):")
    cleanup_stats = file_manager.cleanup_old_files(days=365)

    print(f"   Files deleted: {cleanup_stats['deleted_files']}")
    print(f"   Space freed: {cleanup_stats['freed_bytes'] / (1024*1024):.1f} MB")
    print(f"   Errors: {cleanup_stats['errors']}")

def example_job_lifecycle():
    """Example of complete job lifecycle with FileManager"""

    print("\n=== Complete Job Lifecycle Example ===")

    # Step 1: Job starts - no file management needed yet
    job_id = "lifecycle_example_001"
    project_id = "example_project"

    print(f"\n1. Job Started: {job_id}")
    print("   ComfyUI generation in progress...")

    # Step 2: Job completes - organize generated files
    print(f"\n2. Job Completed: {job_id}")
    print("   Organizing generated files...")

    # In real workflow, this would be called by the job completion handler
    organized_files = organize_job_output(job_id, project_id)
    print(f"   Organized {len(organized_files)} files")

    # Step 3: API request for job results
    print(f"\n3. Client Requests Job Results: {job_id}")

    api = FileManagerAPI()
    job_response = api.get_job_files_api(job_id, project_id)

    if job_response['success']:
        print(f"   Found {job_response['file_count']} files")
        print(f"   Has images: {job_response['has_images']}")
        print(f"   Has videos: {job_response['has_videos']}")
        print(f"   Total size: {job_response['total_size_bytes']} bytes")
    else:
        print(f"   Error retrieving files: {job_response['error']}")

    # Step 4: Cleanup old files periodically
    print(f"\n4. Periodic Cleanup:")
    print("   Running cleanup for files older than 30 days...")

    cleanup_response = api.cleanup_old_files_api(days=30)
    if cleanup_response['success']:
        print(f"   {cleanup_response['message']}")
    else:
        print(f"   Cleanup error: {cleanup_response['error']}")

def example_integration_with_existing_api():
    """Example of integrating with existing anime_api.py"""

    print("\n=== Integration with Existing API Example ===")

    # This shows how you would modify existing anime_api.py endpoints

    integration_code = '''
# Add to anime_api.py imports:
from modules.file_manager_integration import FileManagerAPI

# Initialize FileManager API
file_api = FileManagerAPI()

# Modify existing job completion endpoint:
@app.route('/api/jobs/<job_id>/complete', methods=['POST'])
def complete_job(job_id):
    # Existing job completion logic...

    # NEW: Organize generated files
    project_id = request.json.get('project_id', 'default')
    organize_result = file_api.organize_job_files(job_id, project_id)

    if not organize_result['success']:
        logger.error(f"Failed to organize files for job {job_id}: {organize_result['error']}")

    # Include organized files in response
    return {
        'status': 'completed',
        'job_id': job_id,
        'organized_files': organize_result.get('organized_files', []),
        'file_count': organize_result.get('file_count', 0)
    }

# Add new file management endpoints:
@app.route('/api/jobs/<job_id>/files', methods=['GET'])
def get_job_files(job_id):
    project_id = request.args.get('project_id')
    return file_api.get_job_files_api(job_id, project_id)

@app.route('/api/projects/<project_id>/files', methods=['GET'])
def get_project_files(project_id):
    return file_api.get_project_files_api(project_id)

@app.route('/api/files/cleanup', methods=['POST'])
def cleanup_files():
    days = request.json.get('days', 30)
    return file_api.cleanup_old_files_api(days)
    '''

    print("Example integration code for anime_api.py:")
    print(integration_code)

def main():
    """Run all examples"""

    print("FileManager Usage Examples")
    print("=" * 50)

    try:
        example_workflow_integration()
        example_api_integration()
        example_cleanup_workflow()
        example_job_lifecycle()
        example_integration_with_existing_api()

        print("\n" + "=" * 50)
        print("All examples completed successfully!")

    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()