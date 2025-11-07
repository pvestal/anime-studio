#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime

# Database configuration
DB_CONFIG = {
    'host': '192.168.50.135',
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'tower_echo_brain_secret_key_2025',
    'port': 5432
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def check_file_exists(output_path):
    if not output_path:
        return None

    # Extract timestamp from output path for the correct pattern
    timestamp = None
    if '_' in output_path:
        parts = output_path.split('_')
        for part in parts:
            if part.isdigit() and len(part) == 10:  # Unix timestamp
                timestamp = part
                break

    if not timestamp:
        return None

    # ComfyUI actually generates files with these patterns:
    potential_files = [
        f"/mnt/1TB-storage/ComfyUI/output/animatediff_context_120frames_{timestamp}_00001.mp4",
        f"/mnt/1TB-storage/ComfyUI/output/animatediff_context_72frames_{timestamp}_00001.mp4",
        f"/mnt/1TB-storage/ComfyUI/output/animatediff_simple_24frames_{timestamp}_00001.mp4",
        f"/mnt/1TB-storage/ComfyUI/output/fixed_anime_{timestamp}_00001.mp4",
        f"/mnt/1TB-storage/ComfyUI/output/animatediff_5sec_120frames_{timestamp}_00001.mp4",
        f"/mnt/1TB-storage/ComfyUI/output/animatediff_5sec_72frames_{timestamp}_00001.mp4"
    ]

    for file_path in potential_files:
        try:
            if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                return file_path
        except:
            continue

    return None

def main():
    print("Emergency Fix for Stuck Anime Production Jobs")
    print("=" * 50)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Get all stuck jobs
            cursor.execute("""
                SELECT id, output_path, created_at, prompt
                FROM anime_api.production_jobs
                WHERE status = 'processing'
                ORDER BY created_at ASC
            """)

            stuck_jobs = cursor.fetchall()
            print(f"Found {len(stuck_jobs)} stuck jobs")

            if not stuck_jobs:
                print("No stuck jobs found!")
                return 0

            fixed_count = 0

            for job in stuck_jobs:
                job_id = job['id']
                output_path = job['output_path']
                age_hours = (datetime.now() - job['created_at']).total_seconds() / 3600

                print(f"\nJob {job_id} (age: {age_hours:.1f}h)")

                actual_file = check_file_exists(output_path)
                if actual_file:
                    print(f"  FOUND: {actual_file}")
                    cursor.execute("""
                        UPDATE anime_api.production_jobs
                        SET status = 'completed', output_path = %s
                        WHERE id = %s
                    """, (actual_file, job_id))
                    fixed_count += 1
                else:
                    print(f"  NOT FOUND: {output_path}")

            conn.commit()
            print(f"\nFixed {fixed_count} out of {len(stuck_jobs)} stuck jobs")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())