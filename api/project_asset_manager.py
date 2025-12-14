"""
Project-Aware Asset Management System
Handles file organization, character consistency, and project-specific integration
"""

import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


class ProjectAssetManager:
    """Manages asset organization and project-specific file structure"""

    def __init__(self, project_id: int, db_session=None):
        self.project_id = project_id
        self.project_root = Path(
            f"/mnt/1TB-storage/anime-projects/project_{project_id}"
        )
        self.db_session = db_session
        self.ensure_project_structure()

    def ensure_project_structure(self):
        """Create standard project directory structure"""
        directories = [
            "assets/characters",
            "assets/scenes",
            "assets/backgrounds",
            "assets/props",
            "references/character_refs",
            "references/style_guides",
            "output/final",
            "output/drafts",
            "metadata",
            "workflows",
        ]

        for directory in directories:
            (self.project_root / directory).mkdir(parents=True, exist_ok=True)

        # Create project metadata file if it doesn't exist
        metadata_file = self.project_root / "metadata" / "project_info.json"
        if not metadata_file.exists():
            initial_metadata = {
                "project_id": self.project_id,
                "created_at": datetime.now().isoformat(),
                "characters": {},
                "scenes": {},
                "style_guide": {},
                "generation_history": [],
            }
            with open(metadata_file, "w") as f:
                json.dump(initial_metadata, f, indent=2)

    def organize_generated_file(
        self,
        source_path: str,
        asset_type: str,
        prompt: str,
        job_id: int,
        character_name: Optional[str] = None,
        scene_id: Optional[int] = None,
        generation_metadata: Optional[Dict] = None,
    ) -> str:
        """
        Move and organize generated files into proper project structure

        Args:
            source_path: Path to generated file in ComfyUI output
            asset_type: 'character', 'scene', 'background', 'prop'
            prompt: Original generation prompt
            job_id: Database job ID
            character_name: Character name if applicable
            scene_id: Scene ID if applicable
            generation_metadata: Additional metadata from generation

        Returns:
            New organized file path
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Generate organized filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if character_name:
            filename_base = f"{character_name}_{asset_type}_{job_id}_{timestamp}"
        elif scene_id:
            filename_base = f"scene_{scene_id}_{asset_type}_{job_id}_{timestamp}"
        else:
            filename_base = f"{asset_type}_{job_id}_{timestamp}"

        # Determine destination directory
        if asset_type == "character" and character_name:
            dest_dir = self.project_root / "assets" / "characters" / character_name
        elif asset_type == "scene":
            dest_dir = self.project_root / "assets" / "scenes"
        elif asset_type in ["background", "prop"]:
            dest_dir = self.project_root / "assets" / asset_type
        else:
            dest_dir = self.project_root / "output" / "drafts"

        dest_dir.mkdir(parents=True, exist_ok=True)

        # Copy file to organized location
        dest_path = dest_dir / f"{filename_base}{source.suffix}"
        shutil.copy2(source, dest_path)

        # Create metadata file
        metadata = {
            "job_id": job_id,
            "original_path": str(source),
            "organized_path": str(dest_path),
            "prompt": prompt,
            "asset_type": asset_type,
            "character_name": character_name,
            "scene_id": scene_id,
            "generated_at": timestamp,
            "file_size": dest_path.stat().st_size,
            "file_hash": self._calculate_file_hash(dest_path),
            "generation_metadata": generation_metadata or {},
        }

        metadata_path = dest_path.with_suffix(".json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Update project metadata
        self._update_project_metadata(metadata)

        # Store in database
        if self.db_session:
            self._store_asset_in_db(metadata)

        logger.info(f"Organized file: {source_path} -> {dest_path}")
        return str(dest_path)

    def get_character_references(self, character_name: str) -> List[str]:
        """Get all reference images for character consistency"""
        char_dir = self.project_root / "assets" / "characters" / character_name
        ref_dir = self.project_root / "references" / "character_refs" / character_name

        reference_files = []

        # Get existing character assets
        if char_dir.exists():
            for ext in ["*.png", "*.jpg", "*.jpeg"]:
                reference_files.extend(char_dir.glob(ext))

        # Get dedicated reference images
        if ref_dir.exists():
            for ext in ["*.png", "*.jpg", "*.jpeg"]:
                reference_files.extend(ref_dir.glob(ext))

        return [str(f) for f in reference_files]

    def get_project_style_guide(self) -> Dict:
        """Get project-specific style parameters"""
        metadata_file = self.project_root / "metadata" / "project_info.json"
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                project_data = json.load(f)
                return project_data.get("style_guide", {})
        return {}

    def save_character_reference(
        self, character_name: str, reference_path: str, is_primary: bool = False
    ):
        """Save character reference image for consistency"""
        ref_dir = self.project_root / "references" / "character_refs" / character_name
        ref_dir.mkdir(parents=True, exist_ok=True)

        source = Path(reference_path)
        if not source.exists():
            raise FileNotFoundError(f"Reference file not found: {reference_path}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ref_name = "primary" if is_primary else f"ref_{timestamp}"
        dest_path = ref_dir / f"{ref_name}{source.suffix}"

        shutil.copy2(source, dest_path)

        # Update project metadata
        metadata_file = self.project_root / "metadata" / "project_info.json"
        with open(metadata_file, "r") as f:
            project_data = json.load(f)

        if character_name not in project_data["characters"]:
            project_data["characters"][character_name] = {"references": []}

        project_data["characters"][character_name]["references"].append(
            {"path": str(dest_path), "is_primary": is_primary, "added_at": timestamp}
        )

        with open(metadata_file, "w") as f:
            json.dump(project_data, f, indent=2)

        logger.info(f"Saved character reference: {character_name} -> {dest_path}")
        return str(dest_path)

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate file hash for integrity checking"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _update_project_metadata(self, asset_metadata: Dict):
        """Update project metadata with new asset information"""
        metadata_file = self.project_root / "metadata" / "project_info.json"

        with open(metadata_file, "r") as f:
            project_data = json.load(f)

        project_data["generation_history"].append(asset_metadata)

        # Update character or scene info
        if asset_metadata.get("character_name"):
            char_name = asset_metadata["character_name"]
            if char_name not in project_data["characters"]:
                project_data["characters"][char_name] = {"assets": [], "references": []}
            project_data["characters"][char_name]["assets"].append(
                asset_metadata["organized_path"]
            )

        if asset_metadata.get("scene_id"):
            scene_id = str(asset_metadata["scene_id"])
            if scene_id not in project_data["scenes"]:
                project_data["scenes"][scene_id] = {"assets": []}
            project_data["scenes"][scene_id]["assets"].append(
                asset_metadata["organized_path"]
            )

        with open(metadata_file, "w") as f:
            json.dump(project_data, f, indent=2)

    def _store_asset_in_db(self, metadata: Dict):
        """Store asset metadata in database"""
        try:
            query = text(
                """
                INSERT INTO anime_api.project_assets
                (project_id, file_path, asset_type, character_name, scene_id,
                 generation_metadata, job_id, file_hash, file_size)
                VALUES
                (:project_id, :file_path, :asset_type, :character_name, :scene_id,
                 :generation_metadata, :job_id, :file_hash, :file_size)
            """
            )

            self.db_session.execute(
                query,
                {
                    "project_id": self.project_id,
                    "file_path": metadata["organized_path"],
                    "asset_type": metadata["asset_type"],
                    "character_name": metadata.get("character_name"),
                    "scene_id": metadata.get("scene_id"),
                    "generation_metadata": json.dumps(
                        metadata.get("generation_metadata", {})
                    ),
                    "job_id": metadata["job_id"],
                    "file_hash": metadata["file_hash"],
                    "file_size": metadata["file_size"],
                },
            )
            self.db_session.commit()

        except Exception as e:
            logger.error(f"Failed to store asset in database: {e}")
            self.db_session.rollback()


class CharacterConsistencyManager:
    """Manages character consistency across generations"""

    def __init__(self, project_asset_manager: ProjectAssetManager):
        self.asset_manager = project_asset_manager

    def prepare_character_workflow(
        self,
        character_name: str,
        base_workflow: Dict,
        scene_context: Optional[Dict] = None,
    ) -> Dict:
        """
        Generate ComfyUI workflow with character-specific parameters

        Args:
            character_name: Name of character to maintain consistency
            base_workflow: Base ComfyUI workflow JSON
            scene_context: Additional scene-specific parameters

        Returns:
            Enhanced workflow with character consistency parameters
        """
        # Get character references
        self.asset_manager.get_character_references(character_name)
        style_guide = self.asset_manager.get_project_style_guide()

        # Clone base workflow
        enhanced_workflow = base_workflow.copy()

        # Add character-specific prompt enhancements (node 1 is positive prompt)
        if "1" in enhanced_workflow and "inputs" in enhanced_workflow["1"]:
            current_prompt = enhanced_workflow["1"]["inputs"]["text"]

            # Add character consistency tags
            character_tags = self._get_character_tags(character_name, style_guide)
            enhanced_prompt = f"{current_prompt}, {character_tags}"

            enhanced_workflow["1"]["inputs"]["text"] = enhanced_prompt

        # Add negative prompt enhancements (node 2 is negative prompt)
        if "2" in enhanced_workflow and "inputs" in enhanced_workflow["2"]:
            current_negative = enhanced_workflow["2"]["inputs"]["text"]
            consistency_negative = "inconsistent character design, different character, character variation"
            enhanced_workflow["2"]["inputs"][
                "text"
            ] = f"{current_negative}, {consistency_negative}"

        # If we have reference images, we could add ControlNet or other consistency nodes here
        # This would require more complex workflow modification

        return enhanced_workflow

    def _get_character_tags(self, character_name: str, style_guide: Dict) -> str:
        """Generate character-specific prompt tags"""
        # This could be enhanced with actual character analysis
        # For now, return basic consistency tags
        base_tags = "consistent character design, same character"

        if character_name in style_guide:
            char_style = style_guide[character_name]
            if "hair_color" in char_style:
                base_tags += f", {char_style['hair_color']} hair"
            if "eye_color" in char_style:
                base_tags += f", {char_style['eye_color']} eyes"
            if "clothing_style" in char_style:
                base_tags += f", {char_style['clothing_style']}"

        return base_tags
