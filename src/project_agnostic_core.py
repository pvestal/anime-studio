#!/usr/bin/env python3
"""
Project-Agnostic Core System for Anime Production
Provides clean separation between system capabilities and project-specific data
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import shutil

class ProjectAgnosticCore:
    """Core system that remains clean of project-specific data"""

    def __init__(self, system_root: str = "/opt/tower-anime-production"):
        self.system_root = Path(system_root)
        self.core_version = "2.0.0"

        # System directories (agnostic)
        self.genre_library_path = self.system_root / "system" / "genre_libraries"
        self.templates_path = self.system_root / "system" / "templates"
        self.user_profiles_path = self.system_root / "system" / "user_profiles"
        self.projects_path = self.system_root / "projects"

        # Ensure system structure exists
        self._ensure_system_structure()

    def _ensure_system_structure(self):
        """Create clean system directory structure"""
        directories = [
            self.genre_library_path,
            self.templates_path,
            self.user_profiles_path,
            self.projects_path
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def extract_project_to_workspace(self, project_path: str) -> Dict:
        """Extract project-specific data from mixed system"""
        project_path = Path(project_path)
        project_name = project_path.name

        # Load current project state
        state_file = project_path / "project_state.json"
        if state_file.exists():
            with open(state_file, 'r') as f:
                project_state = json.load(f)
        else:
            project_state = {}

        # Create isolated workspace
        workspace = {
            "project_id": project_name,
            "created_at": datetime.now().isoformat(),
            "version": "2.0",
            "isolation": {
                "character_references": self._extract_character_refs(project_path),
                "project_thresholds": self._extract_thresholds(project_state),
                "project_echo_learning": self._extract_echo_learning(project_state),
                "assets": self._extract_assets(project_path),
                "project_state": project_state
            }
        }

        return workspace

    def _extract_character_refs(self, project_path: Path) -> Dict:
        """Extract character reference data"""
        refs = {
            "casual": [],
            "action": [],
            "portrait": []
        }

        assets_dir = project_path / "assets" / "characters"
        if assets_dir.exists():
            for ref_file in assets_dir.glob("*.png"):
                if "casual" in ref_file.name:
                    refs["casual"].append(str(ref_file))
                elif "action" in ref_file.name:
                    refs["action"].append(str(ref_file))
                elif "portrait" in ref_file.name:
                    refs["portrait"].append(str(ref_file))

        return refs

    def _extract_thresholds(self, project_state: Dict) -> Dict:
        """Extract project-specific quality thresholds"""
        thresholds = {
            "character_consistency": 0.75,  # Default hero threshold
            "technical_quality": 0.85,
            "visual_quality": 0.80
        }

        # Look for custom thresholds in assets
        for character in project_state.get("assets", {}).get("characters", []):
            if "consistency_threshold" in character:
                thresholds["character_consistency"] = character["consistency_threshold"]
                break

        return thresholds

    def _extract_echo_learning(self, project_state: Dict) -> List:
        """Extract Echo learning specific to this project"""
        echo_memory = project_state.get("echo_memory", {})
        return echo_memory.get("creative_decisions", [])

    def _extract_assets(self, project_path: Path) -> Dict:
        """Catalog all project assets"""
        assets = {
            "characters": [],
            "backgrounds": [],
            "shots": []
        }

        # Scan asset directories
        if (project_path / "assets").exists():
            for category in ["characters", "backgrounds"]:
                cat_dir = project_path / "assets" / category
                if cat_dir.exists():
                    assets[category] = [str(f) for f in cat_dir.glob("*")]

        if (project_path / "rendered" / "shots").exists():
            shots_dir = project_path / "rendered" / "shots"
            assets["shots"] = [str(f) for f in shots_dir.glob("*.png")]

        return assets

    def extract_reusable_patterns(self, workspace: Dict) -> Dict:
        """Extract patterns that can be reused in genre library"""
        patterns = {
            "style_modifiers": {},
            "composition_rules": [],
            "color_palettes": [],
            "technical_patterns": {}
        }

        # Extract from project state
        project_state = workspace["isolation"]["project_state"]

        # Extract style modifiers from shots
        for scene in project_state.get("timeline", {}).get("scenes", []):
            for shot in scene.get("shots", []):
                style_mods = shot.get("generation_params", {}).get("style_modifiers", {})
                for key, value in style_mods.items():
                    if key not in patterns["style_modifiers"]:
                        patterns["style_modifiers"][key] = []
                    patterns["style_modifiers"][key].append(value)

        # Extract color palettes
        for style_guide in project_state.get("assets", {}).get("style_guides", []):
            if "color_palette" in style_guide:
                patterns["color_palettes"].extend(style_guide["color_palette"])

        # Extract from Echo learning
        for decision in workspace["isolation"]["project_echo_learning"]:
            if decision.get("user_response") == "accepted":
                params = decision.get("final_params", {})
                for key, value in params.items():
                    if key not in patterns["technical_patterns"]:
                        patterns["technical_patterns"][key] = []
                    patterns["technical_patterns"][key].append(value)

        return patterns

    def save_to_genre_library(self, genre: str, patterns: Dict):
        """Save reusable patterns to genre library"""
        genre_file = self.genre_library_path / f"{genre}.json"

        # Load existing or create new
        if genre_file.exists():
            with open(genre_file, 'r') as f:
                genre_data = json.load(f)
        else:
            genre_data = {
                "genre": genre,
                "created_at": datetime.now().isoformat(),
                "projects_contributed": [],
                "patterns": {}
            }

        # Merge patterns
        for category, values in patterns.items():
            if category not in genre_data["patterns"]:
                genre_data["patterns"][category] = values
            else:
                # Merge intelligently (avoid duplicates)
                if isinstance(values, list):
                    genre_data["patterns"][category].extend(values)
                    genre_data["patterns"][category] = list(set(genre_data["patterns"][category]))
                elif isinstance(values, dict):
                    genre_data["patterns"][category].update(values)

        # Save updated genre library
        with open(genre_file, 'w') as f:
            json.dump(genre_data, f, indent=2)

        return genre_file

    def create_project_template(self, template_name: str, base_config: Dict) -> Path:
        """Create a reusable project template"""
        template = {
            "name": template_name,
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "base_thresholds": base_config.get("thresholds", {
                "hero": 0.75,
                "supporting": 0.70,
                "background": 0.65
            }),
            "default_pose_sets": base_config.get("pose_sets", ["casual", "action", "portrait"]),
            "genre_tags": base_config.get("genre_tags", []),
            "recommended_workflow": base_config.get("workflow", "standard"),
            "quality_gates": base_config.get("quality_gates", [
                "technical_validation",
                "character_consistency",
                "visual_quality",
                "creative_review"
            ]),
            "default_generation_params": base_config.get("generation_params", {
                "steps": 20,
                "cfg": 7.5,
                "model": "counterfeit_v3"
            })
        }

        template_file = self.templates_path / f"{template_name}.json"
        with open(template_file, 'w') as f:
            json.dump(template, f, indent=2)

        return template_file

    def create_new_project(self, project_name: str, template: str = None) -> Path:
        """Create a new project using clean architecture"""
        project_dir = self.projects_path / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create project structure
        (project_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
        (project_dir / "assets" / "backgrounds").mkdir(parents=True, exist_ok=True)
        (project_dir / "assets" / "styles").mkdir(parents=True, exist_ok=True)
        (project_dir / "rendered" / "shots").mkdir(parents=True, exist_ok=True)
        (project_dir / "rendered" / "thumbnails").mkdir(parents=True, exist_ok=True)
        (project_dir / ".history").mkdir(parents=True, exist_ok=True)
        (project_dir / "echo_learning").mkdir(parents=True, exist_ok=True)

        # Load template if specified
        if template:
            template_file = self.templates_path / f"{template}.json"
            if template_file.exists():
                with open(template_file, 'r') as f:
                    template_data = json.load(f)
            else:
                template_data = {}
        else:
            template_data = {}

        # Create initial project state (isolated from other projects)
        project_state = {
            "project": {
                "id": project_name,
                "name": project_name.replace("_", " ").title(),
                "created_at": datetime.now().isoformat(),
                "template_used": template,
                "isolation_version": "2.0"
            },
            "thresholds": template_data.get("base_thresholds", {}),
            "quality_gates": template_data.get("quality_gates", []),
            "generation_defaults": template_data.get("default_generation_params", {}),
            "echo_memory": {
                "creative_decisions": [],
                "style_preferences": {"learned_associations": []}
            },
            "version": {
                "commit_hash": "initial",
                "branch": "main",
                "message": f"Project {project_name} initialized from template {template}"
            }
        }

        # Save project state
        with open(project_dir / "project_state.json", 'w') as f:
            json.dump(project_state, f, indent=2)

        # Create project config
        project_config = {
            "project_id": project_name,
            "template": template,
            "created_at": datetime.now().isoformat(),
            "isolation": {
                "echo_learning": "project-specific",
                "character_references": "project-specific",
                "thresholds": "project-specific",
                "genre_library_access": template_data.get("genre_tags", [])
            }
        }

        with open(project_dir / "project_config.json", 'w') as f:
            json.dump(project_config, f, indent=2)

        return project_dir


class ContextAwareEcho:
    """Echo AI that maintains project isolation while leveraging genre knowledge"""

    def __init__(self, system_root: str = "/opt/tower-anime-production"):
        self.system_root = Path(system_root)
        self.current_project = None
        self.project_learning = None
        self.genre_libraries = {}
        self.user_profile = None

    def set_project_context(self, project_name: str):
        """Switch Echo context to specific project"""
        self.current_project = project_name
        project_dir = self.system_root / "projects" / project_name

        # Clear previous context
        self.genre_libraries = {}  # Clear previous project's genres

        # Load project-specific learning
        learning_file = project_dir / "echo_learning" / "decisions.json"
        if learning_file.exists():
            with open(learning_file, 'r') as f:
                self.project_learning = json.load(f)
        else:
            self.project_learning = {"decisions": [], "patterns": {}}

        # Load allowed genre libraries
        config_file = project_dir / "project_config.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = json.load(f)
                allowed_genres = config.get("isolation", {}).get("genre_library_access", [])

                # Load only permitted genre libraries
                for genre in allowed_genres:
                    genre_file = self.system_root / "system" / "genre_libraries" / f"{genre}.json"
                    if genre_file.exists():
                        with open(genre_file, 'r') as f:
                            self.genre_libraries[genre] = json.load(f)

    def suggest(self, instruction: str, context: Dict) -> Dict:
        """Make suggestions with project isolation"""
        if not self.current_project:
            raise ValueError("No project context set")

        suggestions = {
            "source": "multi-layer",
            "project_specific": {},
            "genre_patterns": {},
            "final_suggestion": {}
        }

        # Layer 1: Project-specific learning (highest priority)
        if self.project_learning:
            for decision in self.project_learning.get("decisions", []):
                if self._similarity(instruction, decision.get("instruction", "")) > 0.7:
                    if decision.get("user_response") == "accepted":
                        suggestions["project_specific"] = decision.get("final_params", {})
                        break

        # Layer 2: Genre patterns (if allowed)
        for genre, library in self.genre_libraries.items():
            patterns = library.get("patterns", {})
            for pattern_type, values in patterns.items():
                if pattern_type.lower() in instruction.lower():
                    suggestions["genre_patterns"][pattern_type] = values

        # Combine suggestions with appropriate weighting
        final = {}

        # 60% weight to project-specific
        final.update(suggestions["project_specific"])

        # 40% weight to genre patterns (only if no conflict)
        for key, value in suggestions["genre_patterns"].items():
            if key not in final:
                final[key] = value

        suggestions["final_suggestion"] = final

        return suggestions

    def _similarity(self, text1: str, text2: str) -> float:
        """Simple text similarity (would use embeddings in production)"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)

    def learn(self, instruction: str, context: Dict, suggestion: Dict,
              user_response: str, final_params: Dict):
        """Learn from user decision (project-isolated)"""
        if not self.current_project:
            return

        project_dir = self.system_root / "projects" / self.current_project
        learning_file = project_dir / "echo_learning" / "decisions.json"

        # Add new decision
        decision = {
            "timestamp": datetime.now().isoformat(),
            "instruction": instruction,
            "context": context,
            "suggestion": suggestion,
            "user_response": user_response,
            "final_params": final_params
        }

        self.project_learning["decisions"].append(decision)

        # Update patterns if accepted
        if user_response == "accepted":
            for key, value in final_params.items():
                if key not in self.project_learning["patterns"]:
                    self.project_learning["patterns"][key] = []
                self.project_learning["patterns"][key].append(value)

        # Save learning
        learning_file.parent.mkdir(parents=True, exist_ok=True)
        with open(learning_file, 'w') as f:
            json.dump(self.project_learning, f, indent=2)


# Testing the system
if __name__ == "__main__":
    print("Initializing Project-Agnostic Core System...")
    core = ProjectAgnosticCore()

    print("\n✅ Core system initialized with clean architecture")
    print(f"   Genre Libraries: {core.genre_library_path}")
    print(f"   Templates: {core.templates_path}")
    print(f"   Projects: {core.projects_path}")

    print("\n📦 Ready for project isolation and strategic reuse")