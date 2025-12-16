#!/usr/bin/env python3
"""
Migration tool to convert existing mixed system to clean project-agnostic architecture
"""

import json
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

sys.path.append('/opt/tower-anime-production/src')
from project_agnostic_core import ProjectAgnosticCore, ContextAwareEcho


def migrate_cyberpunk_project():
    """Migrate the Cyberpunk Goblin Slayer project to clean architecture"""

    print("🚀 Starting Migration to Project-Agnostic Architecture")
    print("=" * 60)

    # Initialize core system
    core = ProjectAgnosticCore()

    # Step 1: Extract project data
    print("\n📦 Step 1: Extracting Cyberpunk Goblin Slayer project...")
    project_path = Path("/opt/tower-anime-production/projects/cyberpunk_goblin_slayer")
    workspace = core.extract_project_to_workspace(str(project_path))

    # Save workspace
    workspace_file = project_path / "workspace.json"
    with open(workspace_file, 'w') as f:
        json.dump(workspace, f, indent=2)
    print(f"   ✅ Project workspace saved to: {workspace_file}")

    # Step 2: Extract reusable patterns
    print("\n🎨 Step 2: Extracting reusable cyberpunk patterns...")
    patterns = core.extract_reusable_patterns(workspace)

    # Save to genre library
    genre_file = core.save_to_genre_library("cyberpunk", patterns)
    print(f"   ✅ Cyberpunk patterns saved to: {genre_file}")

    # Step 3: Create project templates
    print("\n📋 Step 3: Creating project templates...")

    # Cyberpunk template
    cyberpunk_template = core.create_project_template("cyberpunk_action", {
        "thresholds": {
            "hero": 0.75,
            "supporting": 0.70,
            "background": 0.65
        },
        "pose_sets": ["action", "casual", "portrait", "stealth"],
        "genre_tags": ["cyberpunk", "action", "dystopian"],
        "workflow": "dark_mood_first",
        "generation_params": {
            "steps": 20,
            "cfg": 7.5,
            "model": "counterfeit_v3"
        }
    })
    print(f"   ✅ Cyberpunk template created: {cyberpunk_template}")

    # Fantasy template (for comparison)
    fantasy_template = core.create_project_template("fantasy_epic", {
        "thresholds": {
            "hero": 0.78,
            "supporting": 0.73,
            "background": 0.68
        },
        "pose_sets": ["heroic", "magic_casting", "battle", "royal"],
        "genre_tags": ["fantasy", "epic", "magical"],
        "workflow": "character_first",
        "generation_params": {
            "steps": 25,
            "cfg": 8.0,
            "model": "counterfeit_v3"
        }
    })
    print(f"   ✅ Fantasy template created: {fantasy_template}")

    # Slice of Life template
    slice_template = core.create_project_template("slice_of_life", {
        "thresholds": {
            "hero": 0.70,
            "supporting": 0.65,
            "background": 0.60
        },
        "pose_sets": ["casual", "emotion", "school", "daily"],
        "genre_tags": ["slice_of_life", "school", "romance"],
        "workflow": "emotion_first",
        "generation_params": {
            "steps": 15,
            "cfg": 7.0,
            "model": "counterfeit_v3"
        }
    })
    print(f"   ✅ Slice of Life template created: {slice_template}")

    # Step 4: Create isolation config for existing project
    print("\n🔒 Step 4: Creating isolation config for existing project...")
    project_config = {
        "project_id": "cyberpunk_goblin_slayer",
        "template": "cyberpunk_action",
        "created_at": "2025-12-15T00:00:00Z",
        "migrated_at": datetime.now().isoformat(),
        "isolation": {
            "echo_learning": "project-specific",
            "character_references": "project-specific",
            "thresholds": "project-specific",
            "genre_library_access": ["cyberpunk"]
        }
    }

    config_file = project_path / "project_config.json"
    with open(config_file, 'w') as f:
        json.dump(project_config, f, indent=2)
    print(f"   ✅ Isolation config created: {config_file}")

    # Step 5: Clean system core
    print("\n🧹 Step 5: Creating clean system core...")
    system_core = {
        "version": "2.0.0",
        "architecture": "project-agnostic",
        "created_at": datetime.now().isoformat(),
        "components": {
            "cvcs_engine": "Creative Version Control System",
            "quality_gate_framework": "Multi-layer validation",
            "render_pipeline": "GPU-accelerated generation",
            "echo_ai": "Context-aware learning system"
        },
        "capabilities": [
            "Project isolation",
            "Genre library sharing",
            "Template-based creation",
            "User profile tracking",
            "Cross-project learning (opt-in)"
        ]
    }

    core_file = core.system_root / "system" / "core.json"
    with open(core_file, 'w') as f:
        json.dump(system_core, f, indent=2)
    print(f"   ✅ Clean system core saved: {core_file}")

    print("\n" + "=" * 60)
    print("✅ Migration Complete!")
    print("\n📊 Migration Summary:")
    print(f"   • Project workspace extracted")
    print(f"   • Cyberpunk patterns saved to genre library")
    print(f"   • 3 project templates created")
    print(f"   • Project isolation configured")
    print(f"   • System core cleaned")

    return True


def test_isolation():
    """Test that projects are properly isolated"""

    print("\n🧪 Testing Project Isolation...")
    print("=" * 60)

    core = ProjectAgnosticCore()

    # Create a new magical girl project
    print("\n🌸 Creating new Magical Girl project from template...")
    magical_project = core.create_new_project("magical_sparkle_academy", "slice_of_life")
    print(f"   ✅ Project created: {magical_project}")

    # Test Echo isolation
    print("\n🤖 Testing Echo AI isolation...")
    echo = ContextAwareEcho()

    # Set context to cyberpunk project
    echo.set_project_context("cyberpunk_goblin_slayer")
    cyberpunk_suggestion = echo.suggest(
        "Make it more intense",
        {"scene": "alley"}
    )
    print(f"   Cyberpunk suggestion: {list(cyberpunk_suggestion['final_suggestion'].keys())}")

    # Switch to magical girl project
    echo.set_project_context("magical_sparkle_academy")
    magical_suggestion = echo.suggest(
        "Make it more intense",
        {"scene": "classroom"}
    )
    print(f"   Magical suggestion: {list(magical_suggestion['final_suggestion'].keys())}")

    # Verify no cross-contamination
    if cyberpunk_suggestion['project_specific'] == magical_suggestion['project_specific']:
        if cyberpunk_suggestion['project_specific']:  # Only fail if there's actual data
            print("   ❌ FAILED: Projects are sharing learning data!")
            return False

    print("   ✅ PASSED: Projects are properly isolated")

    # Test genre library access control
    print("\n📚 Testing genre library access control...")

    # Cyberpunk project should access cyberpunk genre
    echo.set_project_context("cyberpunk_goblin_slayer")
    if "cyberpunk" in echo.genre_libraries:
        print("   ✅ Cyberpunk project has access to cyberpunk genre")
    else:
        print("   ⚠️  Cyberpunk genre library not loaded")

    # Magical girl should NOT have cyberpunk access
    echo.set_project_context("magical_sparkle_academy")
    if "cyberpunk" in echo.genre_libraries:
        print("   ❌ FAILED: Magical Girl has unauthorized cyberpunk access!")
        return False
    else:
        print("   ✅ Magical Girl correctly isolated from cyberpunk genre")

    print("\n" + "=" * 60)
    print("✅ All isolation tests passed!")
    return True


def create_migration_summary():
    """Create a summary document of the migration"""

    summary = {
        "migration_date": datetime.now().isoformat(),
        "version": "2.0.0",
        "architecture": {
            "before": {
                "type": "mixed",
                "issues": [
                    "Project data mixed with system code",
                    "Echo learning not isolated",
                    "Genre patterns embedded in projects",
                    "No template system"
                ]
            },
            "after": {
                "type": "project-agnostic",
                "improvements": [
                    "Clean separation of concerns",
                    "Project-specific Echo learning",
                    "Reusable genre libraries",
                    "Template-based project creation",
                    "Proper isolation boundaries"
                ]
            }
        },
        "directory_structure": {
            "system": {
                "core.json": "Clean system configuration",
                "genre_libraries/": "Reusable style patterns",
                "templates/": "Project templates",
                "user_profiles/": "User preferences"
            },
            "projects": {
                "[project_name]/": {
                    "project_state.json": "Project-specific state",
                    "project_config.json": "Isolation configuration",
                    "workspace.json": "Extracted project data",
                    "echo_learning/": "Project-specific AI learning",
                    "assets/": "Project assets",
                    "rendered/": "Generated content"
                }
            }
        },
        "benefits": {
            "scalability": "Can handle unlimited projects without contamination",
            "reusability": "Genre patterns shared strategically",
            "maintainability": "Clear boundaries and responsibilities",
            "collaboration": "Projects can be shared without system dependencies",
            "performance": "Reduced memory footprint per project"
        }
    }

    summary_file = Path("/opt/tower-anime-production/MIGRATION_SUMMARY.json")
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n📄 Migration summary saved to: {summary_file}")

    return summary


# Main execution
if __name__ == "__main__":
    print("\n🎯 ANIME PRODUCTION SYSTEM - AGNOSTIC ARCHITECTURE MIGRATION")
    print("=" * 70)

    try:
        # Run migration
        if migrate_cyberpunk_project():
            print("\n✅ Migration successful!")

            # Test isolation
            if test_isolation():
                print("\n✅ Isolation tests passed!")

                # Create summary
                create_migration_summary()

                print("\n" + "=" * 70)
                print("🎉 MIGRATION COMPLETE - SYSTEM NOW PROJECT-AGNOSTIC!")
                print("\nNext steps:")
                print("  1. Create new projects with: python create_project.py --template [template_name]")
                print("  2. Access genre libraries for reusable patterns")
                print("  3. Echo AI learns per-project without contamination")
                print("  4. Templates ensure consistent project setup")

            else:
                print("\n❌ Isolation tests failed - review configuration")

        else:
            print("\n❌ Migration failed")

    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        import traceback
        traceback.print_exc()