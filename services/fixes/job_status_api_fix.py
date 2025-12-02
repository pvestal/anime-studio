#!/usr/bin/env python3
"""Fixed job status API implementation to replace broken endpoint in anime_api.py"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import redis
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)

# Import the job queue
from job_queue import AnimeJobQueue
job_queue = AnimeJobQueue()

@app.route('/api/anime/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    Fixed endpoint that returns actual job status from Redis
    Replace the broken endpoint in anime_api.py with this implementation
    """
    try:
        # Get job data from Redis
        job_data = job_queue.get_job_status(job_id)

        if not job_data:
            return jsonify({
                'error': 'Job not found',
                'job_id': job_id
            }), 404

        # Parse ComfyUI progress if available
        comfyui_progress = None
        if job_data.get('status') == 'processing':
            # Check for ComfyUI WebSocket progress data
            comfyui_key = f'comfyui:progress:{job_id}'
            comfyui_data = redis_client.get(comfyui_key)
            if comfyui_data:
                comfyui_progress = json.loads(comfyui_data)

        # Calculate ETA based on progress
        eta = None
        if job_data.get('progress'):
            progress = int(job_data['progress'])
            if progress > 0 and job_data.get('created_at'):
                created_at = datetime.fromisoformat(job_data['created_at'])
                elapsed = (datetime.now() - created_at).total_seconds()
                if progress < 100:
                    estimated_total = elapsed / (progress / 100)
                    eta = int(estimated_total - elapsed)

        # Build response
        response = {
            'job_id': job_id,
            'project_id': job_data.get('project_id'),
            'status': job_data.get('status', 'unknown'),
            'progress': int(job_data.get('progress', 0)),
            'type': job_data.get('type'),
            'created_at': job_data.get('created_at'),
            'updated_at': job_data.get('updated_at'),
            'eta_seconds': eta
        }

        # Add completion data if available
        if job_data.get('status') == 'completed':
            response['completed_at'] = job_data.get('completed_at')
            response['result'] = json.loads(job_data.get('result', '{}'))

        # Add error info if failed
        if job_data.get('status') == 'failed':
            response['error'] = job_data.get('error')
            response['failed_at'] = job_data.get('failed_at')

        # Add ComfyUI specific progress
        if comfyui_progress:
            response['comfyui'] = comfyui_progress

        return jsonify(response), 200

    except Exception as e:
        # Log the actual error for debugging
        print(f"Error in get_job_status: {e}")

        # Return a proper error response instead of Internal Server Error
        return jsonify({
            'error': 'Failed to retrieve job status',
            'job_id': job_id,
            'message': str(e)
        }), 500

@app.route('/api/anime/jobs', methods=['POST'])
def create_job():
    """Create a new anime generation job"""
    try:
        data = request.get_json()

        if not data.get('project_id'):
            return jsonify({'error': 'project_id is required'}), 400

        if not data.get('type'):
            return jsonify({'error': 'job type is required'}), 400

        # Add job to queue
        job_id = job_queue.add_job(
            project_id=data['project_id'],
            job_type=data['type'],
            params=data.get('params', {})
        )

        return jsonify({
            'job_id': job_id,
            'status': 'queued',
            'message': 'Job added to queue successfully'
        }), 201

    except Exception as e:
        return jsonify({
            'error': 'Failed to create job',
            'message': str(e)
        }), 500

@app.route('/api/anime/jobs/<job_id>/progress', methods=['POST'])
def update_job_progress(job_id):
    """Update job progress (called by worker processes)"""
    try:
        data = request.get_json()
        progress = data.get('progress', 0)
        status = data.get('status')

        job_queue.update_job_progress(job_id, progress, status)

        # Publish update for WebSocket clients
        redis_client.publish('anime:job:updates', json.dumps({
            'job_id': job_id,
            'progress': progress,
            'status': status
        }))

        return jsonify({'success': True}), 200

    except Exception as e:
        return jsonify({
            'error': 'Failed to update progress',
            'message': str(e)
        }), 500

@app.route('/api/anime/queue/status', methods=['GET'])
def get_queue_status():
    """Get overall queue status"""
    try:
        return jsonify({
            'queue_length': job_queue.get_queue_length(),
            'processing_count': job_queue.get_processing_count(),
            'redis_connected': redis_client.ping()
        }), 200

    except Exception as e:
        return jsonify({
            'error': 'Failed to get queue status',
            'message': str(e)
        }), 500

# HOW TO INTEGRATE THIS FIX INTO anime_api.py:
#
# 1. Import the job_queue at the top of anime_api.py:
#    from services.fixes.job_queue import AnimeJobQueue
#    job_queue = AnimeJobQueue()
#
# 2. Replace the broken get_job_status endpoint with the fixed version above
#
# 3. Add Redis connection:
#    import redis
#    redis_client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
#
# 4. Update any ComfyUI job creation to use job_queue.add_job()
#
# 5. Have ComfyUI workers call the progress update endpoint

if __name__ == '__main__':
    print("This is a reference implementation to fix anime_api.py")
    print("Copy the fixed endpoints into the main anime_api.py file")
    print("Or run this as a separate service on a different port for testing")