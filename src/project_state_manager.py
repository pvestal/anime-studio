#!/usr/bin/env python3
"""
Project State Manager - The heart of the Creative Version Control System
Manages the single source of truth for anime production projects
"""

import json
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import copy
import logging

logger = logging.getLogger(__name__)


class ProjectStateManager:
    """Manages project state with Git-like versioning"""

    def __init__(self, project_path: str):
        """Initialize project state manager

        Args:
            project_path: Path to project directory
        """
        self.project_path = Path(project_path)
        self.state_file = self.project_path / "project_state.json"
        self.history_dir = self.project_path / ".history"
        self.history_dir.mkdir(exist_ok=True)

        self.current_state = self._load_state()
        self.working_changes = []

    def _load_state(self) -> Dict:
        """Load current project state from disk"""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_state(self, state: Dict, commit_hash: str = None):
        """Save project state to disk

        Args:
            state: Project state dictionary
            commit_hash: Optional commit hash for history
        """
        # Save current state
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

        # Save to history if commit hash provided
        if commit_hash:
            history_file = self.history_dir / f"{commit_hash}.json"
            with open(history_file, 'w') as f:
                json.dump(state, f, indent=2)

    def _generate_commit_hash(self, state: Dict) -> str:
        """Generate deterministic commit hash from state"""
        state_str = json.dumps(state, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()[:12]

    def _calculate_diff(self, before: Any, after: Any, path: str = "") -> List[Dict]:
        """Calculate diff between two states

        Args:
            before: State before changes
            after: State after changes
            path: JSON path to current location

        Returns:
            List of change objects
        """
        changes = []

        if before == after:
            return changes

        if type(before) != type(after):
            changes.append({
                "type": "modify",
                "path": path,
                "before": before,
                "after": after
            })
            return changes

        if isinstance(after, dict):
            all_keys = set(before.keys() if before else []) | set(after.keys())
            for key in all_keys:
                key_path = f"{path}/{key}" if path else key
                if key not in before:
                    changes.append({
                        "type": "add",
                        "path": key_path,
                        "before": None,
                        "after": after[key]
                    })
                elif key not in after:
                    changes.append({
                        "type": "delete",
                        "path": key_path,
                        "before": before[key],
                        "after": None
                    })
                else:
                    changes.extend(self._calculate_diff(before[key], after[key], key_path))

        elif isinstance(after, list):
            # Simple list diff (could be enhanced)
            if before != after:
                changes.append({
                    "type": "modify",
                    "path": path,
                    "before": before,
                    "after": after
                })

        else:
            # Primitive values
            if before != after:
                changes.append({
                    "type": "modify",
                    "path": path,
                    "before": before,
                    "after": after
                })

        return changes

    def commit(self, message: str, author: str = "system") -> str:
        """Commit current changes to history

        Args:
            message: Commit message
            author: Author of the commit

        Returns:
            Commit hash
        """
        # Calculate diff from parent
        parent_hash = self.current_state.get("version", {}).get("commit_hash")
        parent_state = self._load_commit(parent_hash) if parent_hash else {}

        changes = self._calculate_diff(parent_state, self.current_state)

        if not changes:
            logger.info("No changes to commit")
            return parent_hash

        # Generate commit hash
        commit_hash = self._generate_commit_hash(self.current_state)

        # Update version info
        self.current_state["version"] = {
            "commit_hash": commit_hash,
            "branch": self.current_state.get("version", {}).get("branch", "main"),
            "parent_commit": parent_hash,
            "message": message,
            "author": author,
            "timestamp": datetime.now().isoformat(),
            "tags": []
        }

        # Add to history
        if "history" not in self.current_state:
            self.current_state["history"] = {"commits": [], "branches": []}

        self.current_state["history"]["commits"].append({
            "hash": commit_hash,
            "parent": parent_hash,
            "timestamp": datetime.now().isoformat(),
            "author": author,
            "message": message,
            "changes": changes
        })

        # Save state
        self._save_state(self.current_state, commit_hash)

        logger.info(f"Committed: {commit_hash[:8]} - {message}")
        return commit_hash

    def _load_commit(self, commit_hash: str) -> Dict:
        """Load a specific commit from history"""
        if not commit_hash:
            return {}

        history_file = self.history_dir / f"{commit_hash}.json"
        if history_file.exists():
            with open(history_file, 'r') as f:
                return json.load(f)
        return {}

    def checkout(self, commit_hash: str) -> bool:
        """Checkout a specific commit

        Args:
            commit_hash: Commit to checkout

        Returns:
            Success status
        """
        state = self._load_commit(commit_hash)
        if state:
            self.current_state = state
            self._save_state(state)
            logger.info(f"Checked out commit: {commit_hash[:8]}")
            return True

        logger.error(f"Commit not found: {commit_hash}")
        return False

    def branch(self, branch_name: str, from_commit: str = None) -> bool:
        """Create a new branch

        Args:
            branch_name: Name of the new branch
            from_commit: Starting commit (default: current)

        Returns:
            Success status
        """
        from_commit = from_commit or self.current_state.get("version", {}).get("commit_hash")

        if "history" not in self.current_state:
            self.current_state["history"] = {"commits": [], "branches": []}

        # Check if branch exists
        branches = self.current_state["history"].get("branches", [])
        if any(b["name"] == branch_name for b in branches):
            logger.error(f"Branch already exists: {branch_name}")
            return False

        # Create branch
        branches.append({
            "name": branch_name,
            "created_from": from_commit,
            "head": from_commit,
            "description": f"Branch created from {from_commit[:8]}"
        })

        logger.info(f"Created branch: {branch_name}")
        return True

    def update_shot(self, scene_id: str, shot_id: str, updates: Dict) -> bool:
        """Update a specific shot in the timeline

        Args:
            scene_id: Scene identifier
            shot_id: Shot identifier
            updates: Dictionary of updates to apply

        Returns:
            Success status
        """
        # Find the shot
        for scene in self.current_state.get("timeline", {}).get("scenes", []):
            if scene["id"] == scene_id:
                for shot in scene.get("shots", []):
                    if shot["id"] == shot_id:
                        # Deep merge updates
                        self._deep_merge(shot, updates)

                        # Update timestamps
                        self.current_state["project"]["updated_at"] = datetime.now().isoformat()

                        logger.info(f"Updated shot: {scene_id}/{shot_id}")
                        return True

        logger.error(f"Shot not found: {scene_id}/{shot_id}")
        return False

    def _deep_merge(self, target: Dict, source: Dict):
        """Deep merge source into target dictionary"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value

    def add_echo_decision(self, instruction: str, context: Dict,
                         suggestion: Dict, user_response: str,
                         final_params: Dict):
        """Record an Echo creative decision for learning

        Args:
            instruction: User's instruction to Echo
            context: Context when instruction was given
            suggestion: Echo's suggestion
            user_response: User's response (accepted/modified/rejected)
            final_params: Final parameters applied
        """
        if "echo_memory" not in self.current_state:
            self.current_state["echo_memory"] = {
                "creative_decisions": [],
                "style_preferences": {"learned_associations": []}
            }

        decision = {
            "instruction": instruction,
            "context": context,
            "suggestion": suggestion,
            "user_response": user_response,
            "final_params": final_params,
            "timestamp": datetime.now().isoformat()
        }

        self.current_state["echo_memory"]["creative_decisions"].append(decision)

        # Learn from acceptance
        if user_response == "accepted":
            self._learn_style_preference(instruction, final_params)

        logger.info(f"Recorded Echo decision: {instruction[:50]}... -> {user_response}")

    def _learn_style_preference(self, instruction: str, params: Dict):
        """Learn style preferences from accepted decisions"""
        # Extract key terms from instruction
        key_terms = ["oppressive", "bright", "moody", "cinematic", "dynamic"]

        for term in key_terms:
            if term.lower() in instruction.lower():
                # Update or add association
                associations = self.current_state["echo_memory"]["style_preferences"]["learned_associations"]

                existing = next((a for a in associations if a["term"] == term), None)
                if existing:
                    # Merge parameters and increase confidence
                    existing["parameters"] = params
                    existing["confidence"] = min(1.0, existing["confidence"] + 0.1)
                else:
                    associations.append({
                        "term": term,
                        "parameters": params,
                        "confidence": 0.5
                    })

    def get_shot_by_id(self, shot_id: str) -> Optional[Dict]:
        """Get shot by ID from any scene

        Args:
            shot_id: Shot identifier

        Returns:
            Shot dictionary or None
        """
        for scene in self.current_state.get("timeline", {}).get("scenes", []):
            for shot in scene.get("shots", []):
                if shot["id"] == shot_id:
                    return shot
        return None

    def get_render_queue(self) -> List[Dict]:
        """Get list of shots that need rendering

        Returns:
            List of shots with pending render status
        """
        queue = []
        for scene in self.current_state.get("timeline", {}).get("scenes", []):
            for shot in scene.get("shots", []):
                if shot.get("render_state", {}).get("status") == "pending":
                    queue.append({
                        "scene_id": scene["id"],
                        "shot_id": shot["id"],
                        "shot": shot
                    })
        return queue

    def update_render_state(self, shot_id: str, status: str,
                           asset_path: str = None, quality_scores: Dict = None):
        """Update render state for a shot

        Args:
            shot_id: Shot identifier
            status: New render status
            asset_path: Path to rendered asset
            quality_scores: Quality gate scores
        """
        shot = self.get_shot_by_id(shot_id)
        if shot:
            shot["render_state"]["status"] = status
            shot["render_state"]["last_rendered"] = datetime.now().isoformat()

            if asset_path:
                shot["render_state"]["asset_path"] = asset_path

            if quality_scores:
                shot["render_state"]["quality_scores"] = quality_scores

            logger.info(f"Updated render state for {shot_id}: {status}")


# Test the MVP structure
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize project
    manager = ProjectStateManager("/opt/tower-anime-production/projects/solitude_of_dawn")

    # Simulate a creative change: "Make the alley feel more oppressive"
    print("\n=== Simulating Creative Change ===")
    print("Instruction: 'Make the alley feel more oppressive'")

    # Echo would analyze and suggest parameters
    echo_suggestion = {
        "contrast": "+0.15",
        "saturation": "-0.1",
        "tint_shadow": "+0.05blue",
        "fog_density": "+0.2"
    }

    # Apply the change
    manager.update_shot("scene_002", "shot_002_010", {
        "generation_params": {
            "style_modifiers": {
                "mood": "oppressive",
                "atmosphere": "foggy"
            }
        }
    })

    # Record Echo's learning
    manager.add_echo_decision(
        instruction="Make the alley feel more oppressive",
        context={"scene": "city_alley", "time": "morning"},
        suggestion=echo_suggestion,
        user_response="accepted",
        final_params=echo_suggestion
    )

    # Commit the change
    commit_hash = manager.commit("Applied oppressive mood to alley scene")
    print(f"Committed change: {commit_hash}")

    # Show render queue
    print("\n=== Render Queue ===")
    queue = manager.get_render_queue()
    for item in queue:
        print(f"- {item['scene_id']}/{item['shot_id']}: {item['shot']['composition']['characters'][0]['action']}")

    print("\n=== Project State Saved ===")
    print(f"State file: {manager.state_file}")
    print(f"History: {len(manager.current_state['history']['commits'])} commits")