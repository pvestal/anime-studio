#!/usr/bin/env python3
"""
LoRA Training Manager
Command-line tool for managing LoRA training operations
"""

import asyncio
import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.append('/opt/anime-studio')
from lora_training_pipeline import LoRATrainingPipeline

async def list_characters(pipeline):
    """List all characters and their training status"""
    print("=== Character LoRA Training Status ===\n")

    characters = await pipeline.get_characters_needing_training()
    trained_characters = []

    # Get all characters
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = pipeline.get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT
                c.id,
                c.name,
                c.description,
                ctj.status as training_status,
                ctj.trained_model_path,
                ctj.created_at as training_started
            FROM characters c
            LEFT JOIN character_training_jobs ctj ON c.id = ctj.character_id
                AND ctj.target_asset_type = 'lora_v1'
            ORDER BY c.id
        """

        cursor.execute(query)
        all_characters = cursor.fetchall()

        for char in all_characters:
            status_icon = "✅" if char['trained_model_path'] else "❌"
            status = char['training_status'] or 'not_started'

            print(f"{status_icon} ID: {char['id']} | Name: {char['name'] or 'Unnamed'}")
            print(f"   Status: {status}")

            if char['trained_model_path']:
                model_path = Path(char['trained_model_path'])
                print(f"   LoRA Model: {model_path.name}")

            if char['training_started']:
                print(f"   Training Started: {char['training_started']}")

            print()

        # Summary
        total_chars = len(all_characters)
        trained_count = sum(1 for c in all_characters if c['trained_model_path'])
        untrained_count = total_chars - trained_count

        print(f"Summary: {trained_count}/{total_chars} characters have trained LoRA models")
        print(f"         {untrained_count} characters need training")

    finally:
        conn.close()

async def train_character(pipeline, character_id):
    """Train LoRA for specific character"""
    print(f"Starting LoRA training for character ID {character_id}...")

    # Get character info
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = pipeline.get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, name, description, design_prompt
            FROM characters WHERE id = %s
        """, (character_id,))

        character = cursor.fetchone()
        if not character:
            print(f"Error: Character with ID {character_id} not found")
            return

        character_name = character['name'] or f"Character_{character_id}"
        design_prompt = character['design_prompt'] or character['description'] or f"anime character named {character_name}"

        print(f"Training: {character_name}")
        print(f"Prompt: {design_prompt}")
        print()

        # Check if already trained
        cursor.execute("""
            SELECT status, trained_model_path FROM character_training_jobs
            WHERE character_id = %s AND target_asset_type = 'lora_v1'
            ORDER BY created_at DESC LIMIT 1
        """, (character_id,))

        existing_job = cursor.fetchone()
        if existing_job and existing_job['status'] == 'completed':
            print(f"Warning: Character {character_name} already has a trained LoRA model")
            print(f"Model path: {existing_job['trained_model_path']}")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                return

    finally:
        conn.close()

    # Start training
    print("Generating training images...")
    training_images = await pipeline.generate_training_images(
        character_id, character_name, design_prompt
    )

    if not training_images:
        print("Error: Failed to generate training images")
        return

    print(f"Generated {len(training_images)} training images")
    print("Starting LoRA training (this may take a while)...")

    success = await pipeline.start_lora_training(character_id, character_name, training_images)

    if success:
        print(f"✅ LoRA training completed successfully for {character_name}")

        # Show model location
        model_path = pipeline.models_dir / f"{character_name.lower().replace(' ', '_')}_lora_v1.safetensors"
        if model_path.exists():
            print(f"Model saved to: {model_path}")
    else:
        print(f"❌ LoRA training failed for {character_name}")

async def train_all_characters(pipeline):
    """Train LoRA for all untrained characters"""
    print("Starting batch LoRA training for all untrained characters...")

    characters = await pipeline.get_characters_needing_training()

    if not characters:
        print("All characters already have LoRA models trained")
        return

    print(f"Found {len(characters)} characters needing training:")
    for char in characters:
        print(f"  - {char['name']} (ID: {char['id']})")

    response = input(f"\nProceed with training {len(characters)} characters? (y/n): ")
    if response.lower() != 'y':
        print("Training cancelled")
        return

    print("\nStarting batch training...")
    await pipeline.process_character_queue()
    print("✅ Batch training completed")

async def check_status(pipeline):
    """Check overall system status"""
    print("=== LoRA Training System Status ===\n")

    # Check ComfyUI connection
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8188", timeout=5) as response:
                if response.status == 200:
                    print("✅ ComfyUI: Connected (localhost:8188)")
                else:
                    print(f"⚠️  ComfyUI: Responding with status {response.status}")
    except Exception as e:
        print(f"❌ ComfyUI: Connection failed - {e}")

    # Check database connection
    try:
        conn = pipeline.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        print("✅ Database: Connected")
    except Exception as e:
        print(f"❌ Database: Connection failed - {e}")

    # Check storage directories
    storage_paths = [
        pipeline.models_dir,
        pipeline.training_data_dir,
        pipeline.output_dir
    ]

    for path in storage_paths:
        if path.exists():
            print(f"✅ Storage: {path} (exists)")
        else:
            print(f"⚠️  Storage: {path} (missing, will be created)")

    # Check Kohya training scripts
    kohya_script = Path("/opt/anime-studio/training/kohya_real/train_network.py")
    if kohya_script.exists():
        print("✅ Kohya Scripts: Available")
    else:
        print("❌ Kohya Scripts: Not found")

    print()

    # Get recent training activity
    try:
        conn = pipeline.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                   COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress,
                   COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM character_training_jobs
            WHERE target_asset_type = 'lora_v1'
        """)

        stats = cursor.fetchone()
        print("Training Statistics:")
        print(f"  Total Jobs: {stats[0]}")
        print(f"  Completed: {stats[1]}")
        print(f"  In Progress: {stats[2]}")
        print(f"  Failed: {stats[3]}")

        conn.close()
    except Exception as e:
        print(f"Could not retrieve training statistics: {e}")

async def main():
    """Main CLI function"""
    parser = argparse.ArgumentParser(description="LoRA Training Manager")
    parser.add_argument(
        'command',
        choices=['list', 'train', 'train-all', 'status'],
        help='Command to execute'
    )
    parser.add_argument(
        '--character-id',
        type=int,
        help='Character ID for train command'
    )

    args = parser.parse_args()

    # Initialize pipeline
    pipeline = LoRATrainingPipeline()

    if args.command == 'list':
        await list_characters(pipeline)

    elif args.command == 'train':
        if not args.character_id:
            print("Error: --character-id is required for train command")
            return
        await train_character(pipeline, args.character_id)

    elif args.command == 'train-all':
        await train_all_characters(pipeline)

    elif args.command == 'status':
        await check_status(pipeline)

if __name__ == "__main__":
    asyncio.run(main())