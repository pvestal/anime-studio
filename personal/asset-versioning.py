#!/usr/bin/env python3
"""
Creative Asset Versioning System

Implements git-like versioning for creative projects with support for:
- Story branches and narrative alternatives
- Character design iterations
- Scene composition variants
- Collaborative creative editing with merge conflict resolution
"""

import os
import json
import hashlib
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import shutil
from dataclasses import dataclass, asdict


@dataclass
class CreativeAsset:
    """Represents a versioned creative asset"""
    id: str
    name: str
    type: str  # story, character, scene, audio, etc.
    path: str
    hash: str
    created_at: str
    updated_at: str
    version: str
    branch: str
    parent_commit: Optional[str]
    metadata: Dict[str, Any]


@dataclass
class CreativeBranch:
    """Represents a creative development branch"""
    name: str
    created_at: str
    parent_branch: str
    description: str
    active: bool
    last_commit: Optional[str]


@dataclass
class CreativeCommit:
    """Represents a creative milestone commit"""
    id: str
    branch: str
    message: str
    timestamp: str
    author: str
    assets: List[str]
    parent: Optional[str]


class CreativeVersionControl:
    """Git-like version control system for creative assets"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.repo_path = self.project_path / ".creative"
        self.db_path = self.repo_path / "creative.db"
        self.objects_path = self.repo_path / "objects"
        self.refs_path = self.repo_path / "refs"

        self._init_repo()

    def _init_repo(self):
        """Initialize the creative repository structure"""
        self.repo_path.mkdir(exist_ok=True)
        self.objects_path.mkdir(exist_ok=True)
        (self.refs_path).mkdir(exist_ok=True)

        # Initialize SQLite database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create tables
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            path TEXT NOT NULL,
            hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            version TEXT NOT NULL,
            branch TEXT NOT NULL,
            parent_commit TEXT,
            metadata TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS branches (
            name TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            parent_branch TEXT,
            description TEXT,
            active INTEGER DEFAULT 0,
            last_commit TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS commits (
            id TEXT PRIMARY KEY,
            branch TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            author TEXT NOT NULL,
            assets TEXT,
            parent TEXT
        )
        ''')

        conn.commit()
        conn.close()

        # Initialize main branch if it doesn't exist
        if not self._branch_exists("story/main-timeline"):
            self.create_branch("story/main-timeline", "Main story timeline", None)
            self.checkout("story/main-timeline")

    def _branch_exists(self, branch_name: str) -> bool:
        """Check if branch exists"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM branches WHERE name = ?", (branch_name,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def _get_current_branch(self) -> Optional[str]:
        """Get the currently active branch"""
        head_file = self.refs_path / "HEAD"
        if head_file.exists():
            return head_file.read_text().strip()
        return None

    def _set_current_branch(self, branch_name: str):
        """Set the current active branch"""
        head_file = self.refs_path / "HEAD"
        head_file.write_text(branch_name)

    def _generate_hash(self, content: str) -> str:
        """Generate SHA256 hash for content"""
        return hashlib.sha256(content.encode()).hexdigest()

    def create_branch(self, name: str, description: str, parent_branch: Optional[str]):
        """Create a new creative branch"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        branch = CreativeBranch(
            name=name,
            created_at=datetime.utcnow().isoformat(),
            parent_branch=parent_branch or "",
            description=description,
            active=False,
            last_commit=None
        )

        cursor.execute('''
        INSERT INTO branches (name, created_at, parent_branch, description, active, last_commit)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (branch.name, branch.created_at, branch.parent_branch,
              branch.description, branch.active, branch.last_commit))

        conn.commit()
        conn.close()

        print(f"Created creative branch: {name}")
        return branch

    def checkout(self, branch_name: str):
        """Switch to a creative branch"""
        if not self._branch_exists(branch_name):
            raise ValueError(f"Branch '{branch_name}' does not exist")

        # Set as current branch
        self._set_current_branch(branch_name)

        # Update active status in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Deactivate all branches
        cursor.execute("UPDATE branches SET active = 0")

        # Activate target branch
        cursor.execute("UPDATE branches SET active = 1 WHERE name = ?", (branch_name,))

        conn.commit()
        conn.close()

        print(f"Switched to branch: {branch_name}")

    def add_asset(self, asset_path: str, asset_type: str, metadata: Dict[str, Any] = None):
        """Add a creative asset to version control"""
        current_branch = self._get_current_branch()
        if not current_branch:
            raise ValueError("No active branch")

        asset_path = Path(asset_path)
        if not asset_path.exists():
            raise ValueError(f"Asset does not exist: {asset_path}")

        # Calculate hash of file content
        with open(asset_path, 'rb') as f:
            content_hash = hashlib.sha256(f.read()).hexdigest()

        # Store object in objects directory
        object_dir = self.objects_path / content_hash[:2]
        object_dir.mkdir(exist_ok=True)
        object_file = object_dir / content_hash[2:]

        if not object_file.exists():
            shutil.copy2(asset_path, object_file)

        # Create asset record
        asset = CreativeAsset(
            id=content_hash,
            name=asset_path.name,
            type=asset_type,
            path=str(asset_path),
            hash=content_hash,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            version="1.0.0",
            branch=current_branch,
            parent_commit=None,
            metadata=metadata or {}
        )

        # Store in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
        INSERT OR REPLACE INTO assets
        (id, name, type, path, hash, created_at, updated_at, version, branch, parent_commit, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (asset.id, asset.name, asset.type, asset.path, asset.hash,
              asset.created_at, asset.updated_at, asset.version, asset.branch,
              asset.parent_commit, json.dumps(asset.metadata)))

        conn.commit()
        conn.close()

        print(f"Added asset: {asset.name} ({asset.type}) to {current_branch}")
        return asset

    def commit(self, message: str, author: str = "Creative Director"):
        """Create a creative milestone commit"""
        current_branch = self._get_current_branch()
        if not current_branch:
            raise ValueError("No active branch")

        # Get staged assets for current branch
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM assets WHERE branch = ?", (current_branch,))
        asset_ids = [row[0] for row in cursor.fetchall()]

        if not asset_ids:
            print("No assets to commit")
            return None

        # Generate commit ID
        commit_data = f"{current_branch}{message}{datetime.utcnow().isoformat()}{author}"
        commit_id = self._generate_hash(commit_data)

        # Get parent commit
        cursor.execute("SELECT last_commit FROM branches WHERE name = ?", (current_branch,))
        parent = cursor.fetchone()
        parent_commit = parent[0] if parent and parent[0] else None

        # Create commit
        commit = CreativeCommit(
            id=commit_id,
            branch=current_branch,
            message=message,
            timestamp=datetime.utcnow().isoformat(),
            author=author,
            assets=asset_ids,
            parent=parent_commit
        )

        cursor.execute('''
        INSERT INTO commits (id, branch, message, timestamp, author, assets, parent)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (commit.id, commit.branch, commit.message, commit.timestamp,
              commit.author, json.dumps(commit.assets), commit.parent))

        # Update branch's last commit
        cursor.execute("UPDATE branches SET last_commit = ? WHERE name = ?",
                      (commit.id, current_branch))

        conn.commit()
        conn.close()

        print(f"Creative commit created: {commit_id[:8]} - {message}")
        return commit

    def merge_branch(self, source_branch: str, target_branch: str, resolve_conflicts: Dict[str, str] = None):
        """Merge creative changes between branches"""
        if not self._branch_exists(source_branch):
            raise ValueError(f"Source branch '{source_branch}' does not exist")
        if not self._branch_exists(target_branch):
            raise ValueError(f"Target branch '{target_branch}' does not exist")

        # Switch to target branch
        self.checkout(target_branch)

        # Get assets from both branches
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM assets WHERE branch = ?", (source_branch,))
        source_assets = cursor.fetchall()

        cursor.execute("SELECT * FROM assets WHERE branch = ?", (target_branch,))
        target_assets = cursor.fetchall()

        # Simple merge strategy: copy new assets, detect conflicts
        conflicts = []
        merged_assets = []

        target_asset_names = {asset[1] for asset in target_assets}  # asset[1] is name

        for source_asset in source_assets:
            if source_asset[1] in target_asset_names:
                # Potential conflict - same asset name
                conflicts.append(source_asset[1])
            else:
                # New asset, safe to merge
                merged_assets.append(source_asset)

        if conflicts and not resolve_conflicts:
            print(f"Merge conflicts detected: {conflicts}")
            print("Please resolve conflicts and retry with resolve_conflicts parameter")
            return None

        # Apply merged assets to target branch
        for asset in merged_assets:
            # Update branch in asset record
            asset_data = list(asset)
            asset_data[8] = target_branch  # branch field

            cursor.execute('''
            INSERT OR REPLACE INTO assets
            (id, name, type, path, hash, created_at, updated_at, version, branch, parent_commit, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', asset_data)

        conn.commit()
        conn.close()

        # Create merge commit
        merge_message = f"Merge branch '{source_branch}' into '{target_branch}'"
        self.commit(merge_message, "Creative Merge Bot")

        print(f"Successfully merged {len(merged_assets)} assets from {source_branch} to {target_branch}")
        return True

    def list_branches(self):
        """List all creative branches"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM branches ORDER BY created_at DESC")
        branches = cursor.fetchall()

        conn.close()

        print("\nCreative Branches:")
        for branch in branches:
            active = "* " if branch[4] else "  "
            print(f"{active}{branch[0]} - {branch[3]}")

        return branches

    def log(self, branch: Optional[str] = None, limit: int = 10):
        """Show commit history"""
        if not branch:
            branch = self._get_current_branch()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
        SELECT * FROM commits WHERE branch = ?
        ORDER BY timestamp DESC LIMIT ?
        ''', (branch, limit))

        commits = cursor.fetchall()
        conn.close()

        print(f"\nCommit History for {branch}:")
        for commit in commits:
            print(f"commit {commit[0][:8]}")
            print(f"Date: {commit[3]}")
            print(f"Author: {commit[4]}")
            print(f"    {commit[2]}")
            print()

        return commits

    def status(self):
        """Show current repository status"""
        current_branch = self._get_current_branch()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Count assets in current branch
        cursor.execute("SELECT COUNT(*) FROM assets WHERE branch = ?", (current_branch,))
        asset_count = cursor.fetchone()[0]

        # Get latest commit
        cursor.execute('''
        SELECT id, message, timestamp FROM commits WHERE branch = ?
        ORDER BY timestamp DESC LIMIT 1
        ''', (current_branch,))
        latest_commit = cursor.fetchone()

        conn.close()

        print(f"On branch {current_branch}")
        print(f"Assets: {asset_count}")

        if latest_commit:
            print(f"Latest commit: {latest_commit[0][:8]} - {latest_commit[1]}")
            print(f"Commit date: {latest_commit[2]}")
        else:
            print("No commits yet")


def main():
    """CLI interface for creative version control"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: asset-versioning.py <command> [args...]")
        print("Commands: init, branch, checkout, add, commit, merge, log, status")
        return

    command = sys.argv[1]
    project_path = os.getcwd()

    if command == "init":
        repo = CreativeVersionControl(project_path)
        print("Initialized creative repository")

    elif command == "branch":
        repo = CreativeVersionControl(project_path)
        if len(sys.argv) == 2:
            repo.list_branches()
        else:
            name = sys.argv[2]
            description = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else f"New branch: {name}"
            parent = repo._get_current_branch()
            repo.create_branch(name, description, parent)

    elif command == "checkout":
        if len(sys.argv) < 3:
            print("Usage: asset-versioning.py checkout <branch>")
            return
        repo = CreativeVersionControl(project_path)
        repo.checkout(sys.argv[2])

    elif command == "add":
        if len(sys.argv) < 4:
            print("Usage: asset-versioning.py add <file> <type> [metadata]")
            return
        repo = CreativeVersionControl(project_path)
        asset_path = sys.argv[2]
        asset_type = sys.argv[3]
        repo.add_asset(asset_path, asset_type)

    elif command == "commit":
        if len(sys.argv) < 3:
            print("Usage: asset-versioning.py commit <message>")
            return
        repo = CreativeVersionControl(project_path)
        message = " ".join(sys.argv[2:])
        repo.commit(message)

    elif command == "merge":
        if len(sys.argv) < 3:
            print("Usage: asset-versioning.py merge <source-branch>")
            return
        repo = CreativeVersionControl(project_path)
        source = sys.argv[2]
        target = repo._get_current_branch()
        repo.merge_branch(source, target)

    elif command == "log":
        repo = CreativeVersionControl(project_path)
        repo.log()

    elif command == "status":
        repo = CreativeVersionControl(project_path)
        repo.status()

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()