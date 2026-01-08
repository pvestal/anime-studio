#!/usr/bin/env python3
"""
Git-like Version Control System for Storylines
Enables branching, merging, and versioning of narrative paths
"""
import json
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
import difflib
from dataclasses import dataclass, asdict
from enum import Enum


class ChangeType(Enum):
    """Types of changes in story"""
    ADD_SCENE = "add_scene"
    EDIT_SCENE = "edit_scene"
    DELETE_SCENE = "delete_scene"
    ADD_CHARACTER = "add_character"
    EDIT_CHARACTER = "edit_character"
    EDIT_DIALOGUE = "edit_dialogue"
    BRANCH_PLOT = "branch_plot"


@dataclass
class StoryCommit:
    """Represents a commit in story history"""
    commit_hash: str
    parent_hash: Optional[str]
    author: str
    message: str
    timestamp: datetime
    changes: List[Dict[str, Any]]
    story_snapshot: Dict[str, Any]


@dataclass
class StoryBranch:
    """Represents a story branch"""
    name: str
    head_commit: str
    created_at: datetime
    description: str
    parent_branch: Optional[str] = None


class StorylineVersionControl:
    """
    Git-like version control for storylines
    """

    def __init__(self, story_id: str, storage_path: Path = Path("/tmp/storylines")):
        self.story_id = story_id
        self.storage_path = storage_path / story_id
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Version control metadata
        self.commits: Dict[str, StoryCommit] = {}
        self.branches: Dict[str, StoryBranch] = {}
        self.current_branch = "main"
        self.head_commit: Optional[str] = None

        # Story data
        self.working_story: Dict[str, Any] = {
            "title": "",
            "chapters": [],
            "characters": {},
            "settings": {},
            "metadata": {}
        }

        self._load_or_init()

    def _load_or_init(self):
        """Load existing repo or initialize new one"""
        repo_file = self.storage_path / "repository.json"

        if repo_file.exists():
            with open(repo_file, 'r') as f:
                data = json.load(f)
                self._deserialize_repo(data)
        else:
            # Initialize with empty commit
            self._init_repository()

    def _init_repository(self):
        """Initialize new repository"""
        # Create main branch
        self.branches["main"] = StoryBranch(
            name="main",
            head_commit="",
            created_at=datetime.utcnow(),
            description="Main storyline"
        )

        # Create initial commit
        initial_commit = self.commit(
            "Initial story commit",
            author="System"
        )

        self.branches["main"].head_commit = initial_commit
        self._save_repo()

    def _calculate_hash(self, content: str) -> str:
        """Calculate hash for content"""
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def commit(self, message: str, author: str = "User") -> str:
        """
        Commit current story state
        Returns: commit hash
        """
        # Calculate changes from parent
        changes = self._calculate_changes()

        # Create commit hash
        commit_content = json.dumps({
            "story": self.working_story,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }, sort_keys=True)
        commit_hash = self._calculate_hash(commit_content)

        # Create commit object
        commit = StoryCommit(
            commit_hash=commit_hash,
            parent_hash=self.head_commit,
            author=author,
            message=message,
            timestamp=datetime.utcnow(),
            changes=changes,
            story_snapshot=json.loads(json.dumps(self.working_story))  # Deep copy
        )

        # Store commit
        self.commits[commit_hash] = commit
        self.head_commit = commit_hash

        # Update branch head
        if self.current_branch in self.branches:
            self.branches[self.current_branch].head_commit = commit_hash

        self._save_repo()
        return commit_hash

    def _calculate_changes(self) -> List[Dict[str, Any]]:
        """Calculate changes from parent commit"""
        changes = []

        if not self.head_commit or self.head_commit not in self.commits:
            # First commit, everything is new
            changes.append({
                "type": ChangeType.ADD_SCENE.value,
                "description": "Initial story creation"
            })
            return changes

        parent = self.commits[self.head_commit].story_snapshot

        # Compare chapters
        parent_chapters = parent.get("chapters", [])
        current_chapters = self.working_story.get("chapters", [])

        if len(current_chapters) > len(parent_chapters):
            changes.append({
                "type": ChangeType.ADD_SCENE.value,
                "count": len(current_chapters) - len(parent_chapters)
            })
        elif len(current_chapters) < len(parent_chapters):
            changes.append({
                "type": ChangeType.DELETE_SCENE.value,
                "count": len(parent_chapters) - len(current_chapters)
            })

        # Compare characters
        parent_chars = set(parent.get("characters", {}).keys())
        current_chars = set(self.working_story.get("characters", {}).keys())

        new_chars = current_chars - parent_chars
        for char in new_chars:
            changes.append({
                "type": ChangeType.ADD_CHARACTER.value,
                "character": char
            })

        return changes

    def create_branch(self, branch_name: str, description: str = "") -> str:
        """
        Create new story branch from current position
        """
        if branch_name in self.branches:
            raise ValueError(f"Branch {branch_name} already exists")

        new_branch = StoryBranch(
            name=branch_name,
            head_commit=self.head_commit or "",
            created_at=datetime.utcnow(),
            description=description,
            parent_branch=self.current_branch
        )

        self.branches[branch_name] = new_branch
        self._save_repo()

        return branch_name

    def switch_branch(self, branch_name: str):
        """
        Switch to different story branch
        """
        if branch_name not in self.branches:
            raise ValueError(f"Branch {branch_name} does not exist")

        # Save current work if dirty
        if self._is_dirty():
            self.commit(f"Auto-save before switching to {branch_name}")

        # Switch branch
        self.current_branch = branch_name
        self.head_commit = self.branches[branch_name].head_commit

        # Load story state from branch head
        if self.head_commit and self.head_commit in self.commits:
            self.working_story = json.loads(
                json.dumps(self.commits[self.head_commit].story_snapshot)
            )

        self._save_repo()

    def merge_branches(self, source_branch: str, target_branch: str = None) -> Tuple[bool, List[str]]:
        """
        Merge source branch into target (or current) branch
        Returns: (success, conflicts)
        """
        target_branch = target_branch or self.current_branch

        if source_branch not in self.branches:
            raise ValueError(f"Source branch {source_branch} does not exist")

        source_commit = self.branches[source_branch].head_commit
        target_commit = self.branches[target_branch].head_commit

        if not source_commit or not target_commit:
            return False, ["Cannot merge: missing commits"]

        # Find common ancestor
        common_ancestor = self._find_common_ancestor(source_commit, target_commit)

        if not common_ancestor:
            return False, ["No common ancestor found"]

        # Three-way merge
        conflicts = self._three_way_merge(
            self.commits[common_ancestor].story_snapshot,
            self.commits[source_commit].story_snapshot,
            self.commits[target_commit].story_snapshot
        )

        if not conflicts:
            # Successful merge
            self.commit(
                f"Merge {source_branch} into {target_branch}",
                author="System"
            )
            return True, []

        return False, conflicts

    def _find_common_ancestor(self, commit1: str, commit2: str) -> Optional[str]:
        """Find common ancestor of two commits"""
        ancestors1 = self._get_ancestors(commit1)
        ancestors2 = self._get_ancestors(commit2)

        # Find first common ancestor
        for ancestor in ancestors1:
            if ancestor in ancestors2:
                return ancestor

        return None

    def _get_ancestors(self, commit_hash: str) -> List[str]:
        """Get all ancestors of a commit"""
        ancestors = []
        current = commit_hash

        while current and current in self.commits:
            ancestors.append(current)
            current = self.commits[current].parent_hash

        return ancestors

    def _three_way_merge(self, base: Dict, source: Dict, target: Dict) -> List[str]:
        """
        Perform three-way merge
        Returns: list of conflicts
        """
        conflicts = []
        merged = {}

        # Merge chapters
        base_chapters = base.get("chapters", [])
        source_chapters = source.get("chapters", [])
        target_chapters = target.get("chapters", [])

        if source_chapters != base_chapters and target_chapters != base_chapters:
            # Both modified chapters
            if source_chapters != target_chapters:
                conflicts.append("Chapter conflict: both branches modified chapters differently")

        # Merge characters
        base_chars = base.get("characters", {})
        source_chars = source.get("characters", {})
        target_chars = target.get("characters", {})

        all_chars = set(base_chars.keys()) | set(source_chars.keys()) | set(target_chars.keys())

        for char in all_chars:
            base_char = base_chars.get(char)
            source_char = source_chars.get(char)
            target_char = target_chars.get(char)

            if source_char != base_char and target_char != base_char:
                if source_char != target_char:
                    conflicts.append(f"Character conflict: {char} modified in both branches")

        if not conflicts:
            # Apply merge
            self.working_story = source  # Simple strategy: take source

        return conflicts

    def diff_stories(self, commit1: str, commit2: str = None) -> Dict[str, Any]:
        """
        Show differences between two story versions
        """
        commit2 = commit2 or self.head_commit

        if commit1 not in self.commits or commit2 not in self.commits:
            raise ValueError("Invalid commit hash")

        story1 = self.commits[commit1].story_snapshot
        story2 = self.commits[commit2].story_snapshot

        diff = {
            "chapters": self._diff_chapters(
                story1.get("chapters", []),
                story2.get("chapters", [])
            ),
            "characters": self._diff_characters(
                story1.get("characters", {}),
                story2.get("characters", {})
            )
        }

        return diff

    def _diff_chapters(self, chapters1: List, chapters2: List) -> Dict:
        """Calculate chapter differences"""
        diff = {
            "added": [],
            "removed": [],
            "modified": []
        }

        # Simple diff - in production would be more sophisticated
        if len(chapters2) > len(chapters1):
            diff["added"] = chapters2[len(chapters1):]
        elif len(chapters1) > len(chapters2):
            diff["removed"] = chapters1[len(chapters2):]

        # Check for modifications
        min_len = min(len(chapters1), len(chapters2))
        for i in range(min_len):
            if chapters1[i] != chapters2[i]:
                diff["modified"].append(i)

        return diff

    def _diff_characters(self, chars1: Dict, chars2: Dict) -> Dict:
        """Calculate character differences"""
        diff = {
            "added": list(set(chars2.keys()) - set(chars1.keys())),
            "removed": list(set(chars1.keys()) - set(chars2.keys())),
            "modified": []
        }

        # Check for modifications
        common_chars = set(chars1.keys()) & set(chars2.keys())
        for char in common_chars:
            if chars1[char] != chars2[char]:
                diff["modified"].append(char)

        return diff

    def revert_to_checkpoint(self, commit_hash: str):
        """
        Revert story to specific checkpoint
        """
        if commit_hash not in self.commits:
            raise ValueError(f"Commit {commit_hash} does not exist")

        # Load story from commit
        self.working_story = json.loads(
            json.dumps(self.commits[commit_hash].story_snapshot)
        )

        # Create revert commit
        self.commit(
            f"Revert to {commit_hash[:8]}",
            author="System"
        )

    def get_history(self, branch: str = None, limit: int = 10) -> List[StoryCommit]:
        """Get commit history for branch"""
        branch = branch or self.current_branch

        if branch not in self.branches:
            return []

        history = []
        current = self.branches[branch].head_commit

        while current and current in self.commits and len(history) < limit:
            history.append(self.commits[current])
            current = self.commits[current].parent_hash

        return history

    def _is_dirty(self) -> bool:
        """Check if working story has uncommitted changes"""
        if not self.head_commit or self.head_commit not in self.commits:
            return True

        current_snapshot = self.commits[self.head_commit].story_snapshot
        return self.working_story != current_snapshot

    def _save_repo(self):
        """Save repository to disk"""
        repo_data = {
            "story_id": self.story_id,
            "current_branch": self.current_branch,
            "head_commit": self.head_commit,
            "commits": {
                hash: {
                    "commit_hash": c.commit_hash,
                    "parent_hash": c.parent_hash,
                    "author": c.author,
                    "message": c.message,
                    "timestamp": c.timestamp.isoformat(),
                    "changes": c.changes,
                    "story_snapshot": c.story_snapshot
                }
                for hash, c in self.commits.items()
            },
            "branches": {
                name: {
                    "name": b.name,
                    "head_commit": b.head_commit,
                    "created_at": b.created_at.isoformat(),
                    "description": b.description,
                    "parent_branch": b.parent_branch
                }
                for name, b in self.branches.items()
            },
            "working_story": self.working_story
        }

        repo_file = self.storage_path / "repository.json"
        with open(repo_file, 'w') as f:
            json.dump(repo_data, f, indent=2)

    def _deserialize_repo(self, data: Dict):
        """Load repository from data"""
        self.story_id = data["story_id"]
        self.current_branch = data["current_branch"]
        self.head_commit = data["head_commit"]
        self.working_story = data["working_story"]

        # Load commits
        for hash, commit_data in data["commits"].items():
            self.commits[hash] = StoryCommit(
                commit_hash=commit_data["commit_hash"],
                parent_hash=commit_data["parent_hash"],
                author=commit_data["author"],
                message=commit_data["message"],
                timestamp=datetime.fromisoformat(commit_data["timestamp"]),
                changes=commit_data["changes"],
                story_snapshot=commit_data["story_snapshot"]
            )

        # Load branches
        for name, branch_data in data["branches"].items():
            self.branches[name] = StoryBranch(
                name=branch_data["name"],
                head_commit=branch_data["head_commit"],
                created_at=datetime.fromisoformat(branch_data["created_at"]),
                description=branch_data["description"],
                parent_branch=branch_data.get("parent_branch")
            )


# Example usage
def example_usage():
    """Demonstrate storyline version control"""

    # Create a new story repository
    vcs = StorylineVersionControl("my_story")

    # Add initial content
    vcs.working_story["title"] = "The Adventure Begins"
    vcs.working_story["chapters"] = [
        {"title": "Chapter 1", "content": "Once upon a time..."}
    ]
    vcs.commit("Added first chapter")

    # Create alternative branch
    vcs.create_branch("alternative_ending", "Exploring different ending")
    vcs.switch_branch("alternative_ending")

    # Modify in branch
    vcs.working_story["chapters"].append(
        {"title": "Chapter 2 - Alt", "content": "The hero chose differently..."}
    )
    vcs.commit("Added alternative chapter 2")

    # Switch back to main
    vcs.switch_branch("main")

    # Continue main story
    vcs.working_story["chapters"].append(
        {"title": "Chapter 2 - Main", "content": "The hero continued..."}
    )
    vcs.commit("Added main chapter 2")

    # Show history
    print("Main branch history:")
    for commit in vcs.get_history("main"):
        print(f"  {commit.commit_hash[:8]}: {commit.message}")

    print("\nAlternative branch history:")
    for commit in vcs.get_history("alternative_ending"):
        print(f"  {commit.commit_hash[:8]}: {commit.message}")

    # Show diff
    diff = vcs.diff_stories(
        vcs.branches["alternative_ending"].head_commit,
        vcs.branches["main"].head_commit
    )
    print(f"\nDifferences: {diff}")


if __name__ == "__main__":
    example_usage()