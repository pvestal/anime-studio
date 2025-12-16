#!/usr/bin/env python3
"""

import os
import sys
from datetime import datetime
from models import Character, GeneratedAsset, ProductionJob, Project
from database import DatabaseHealth, SessionLocal, init_database

Test script for database integration with SQLAlchemy models.
This will verify that our models work with the existing database schema.
"""

import sys

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def test_database_connection():
    """Test basic database connection"""
    """Test basic database connection"""
    print("Testing database connection...")

    try:
        # Initialize database
        init_database()
        print("✅ Database initialization successful")

        # Check health
        health_info = DatabaseHealth.get_connection_info()
        print(f"✅ Database health: {health_info['status']}")
        print(
            f"   Pool info: {health_info.get('pool_size', 'unknown')} size, "
            f"{health_info.get('checked_out', 'unknown')} checked out"
        )

        return True

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


def test_models_crud():
    """Test CRUD operations with our models"""
    print("\nTesting model CRUD operations...")

    db = SessionLocal()
    try:
        # Test Project creation
        print("Creating test project...")
        test_project = Project(
            name=f"Test Project {datetime.now().strftime('%H%M%S')}",
            description="Test project for database integration",
            type="anime",
            status="active",
            metadata_={"test": True, "created_by": "test_script"},
        )

        db.add(test_project)
        db.commit()
        db.refresh(test_project)
        print(f"✅ Created project with ID: {test_project.id}")

        # Test Character creation
        print("Creating test character...")
        test_character = Character(
            name=f"Test Character {datetime.now().strftime('%H%M%S')}",
            project_id=test_project.id,
            description="Test character for database integration",
            visual_traits={"hair_color": "blue", "eye_color": "green"},
            base_prompt="anime character with blue hair",
            status="draft",
            metadata_={"test": True},
        )

        db.add(test_character)
        db.commit()
        db.refresh(test_character)
        print(f"✅ Created character with ID: {test_character.id}")

        # Test ProductionJob creation
        print("Creating test production job...")
        test_job = ProductionJob(
            project_id=test_project.id,
            character_id=test_character.id,
            job_type="test_generation",
            status="pending",
            prompt="test prompt for anime character",
            negative_prompt="low quality, blurry",
            metadata_={"test": True, "width": 512, "height": 768},
        )

        db.add(test_job)
        db.commit()
        db.refresh(test_job)
        print(f"✅ Created production job with ID: {test_job.id}")

        # Test GeneratedAsset creation
        print("Creating test generated asset...")
        test_asset = GeneratedAsset(
            job_id=test_job.id,
            file_path="/test/path/test_image.png",
            file_type="image",
            file_size=1024000,
            metadata={"test": True, "format": "PNG"},
            quality_metrics={"resolution": "512x768", "score": 85},
        )

        db.add(test_asset)
        db.commit()
        db.refresh(test_asset)
        print(f"✅ Created generated asset with ID: {test_asset.id}")

        # Test querying with relationships
        print("\nTesting relationship queries...")

        # Get project with all related data
        project_with_data = (
            db.query(Project).filter(Project.id == test_project.id).first()
        )
        print(
            f"✅ Project '{project_with_data.name}' has {len(project_with_data.jobs)} jobs and {len(project_with_data.characters)} characters"
        )

        # Get character with jobs
        character_with_jobs = (
            db.query(Character).filter(Character.id == test_character.id).first()
        )
        print(
            f"✅ Character '{character_with_jobs.name}' has {len(character_with_jobs.jobs)} jobs"
        )

        # Get job with assets
        job_with_assets = (
            db.query(ProductionJob).filter(ProductionJob.id == test_job.id).first()
        )
        print(f"✅ Job {job_with_assets.id} has {len(job_with_assets.assets)} assets")

        # Skip generation_params test for now due to different schema structure

        # Cleanup test data
        print("\nCleaning up test data...")
        db.delete(test_asset)
        db.delete(test_job)
        db.delete(test_character)
        db.delete(test_project)
        db.commit()
        print("✅ Test data cleaned up successfully")

        return True

    except Exception as e:
        print(f"❌ Model CRUD test failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def test_existing_data():
    """Test reading existing data from database"""
    print("\nTesting existing data access...")

    db = SessionLocal()
    try:
        # Count existing records
        project_count = db.query(Project).count()
        character_count = db.query(Character).count()
        job_count = db.query(ProductionJob).count()

        print(f"✅ Found {project_count} existing projects")
        print(f"✅ Found {character_count} existing characters")
        print(f"✅ Found {job_count} existing jobs")

        # Show some recent data if it exists
        if project_count > 0:
            recent_projects = (
                db.query(Project).order_by(Project.created_at.desc()).limit(3).all()
            )
            print("Recent projects:")
            for p in recent_projects:
                print(f"   - {p.name} (ID: {p.id}, Status: {p.status})")

        if character_count > 0:
            recent_characters = (
                db.query(Character).order_by(Character.created_at.desc()).limit(3).all()
            )
            print("Recent characters:")
            for c in recent_characters:
                print(f"   - {c.name} (ID: {c.id}, Project: {c.project_id})")

        if job_count > 0:
            recent_jobs = (
                db.query(ProductionJob)
                .order_by(ProductionJob.created_at.desc())
                .limit(3)
                .all()
            )
            print("Recent jobs:")
            for j in recent_jobs:
                print(f"   - {j.job_type} (ID: {j.id}, Status: {j.status})")

        return True

    except Exception as e:
        print(f"❌ Existing data test failed: {e}")
        return False
    finally:
        db.close()


def main():
    """Run all tests"""
    print("🧪 Testing Anime Production Database Integration")
    print("=" * 50)

    all_passed = True

    # Test database connection
    if not test_database_connection():
        all_passed = False

    # Test model CRUD operations
    if not test_models_crud():
        all_passed = False

    # Test existing data access
    if not test_existing_data():
        all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 All database integration tests passed!")
        print("✅ The SQLAlchemy models are ready for production use.")
    else:
        print("❌ Some tests failed. Please check the errors above.")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
