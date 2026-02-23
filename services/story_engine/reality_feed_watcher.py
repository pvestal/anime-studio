"""
Reality Feed Watcher
Scans real-world events (git commits, logs, errors) and feeds them into the story bible
as meta-narrative material for Echo Chamber.
"""

import json
import logging
import subprocess
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

import sys
import os
sys.path.insert(0, '/opt/anime-studio')

from services.story_engine.story_manager import StoryManager

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "RP78eIrW7cI2jYvL5akt1yurE",
}

# Echo Brain DB config for scanning errors
ECHO_BRAIN_CONFIG = {
    "host": "localhost",
    "database": "echo_brain",
    "user": "patrick",
    "password": "RP78eIrW7cI2jYvL5akt1yurE",
}


class RealityFeedWatcher:
    """
    Scans real-world development events and classifies them as story material.

    Sources:
    1. Git commits from tower repos
    2. Echo Brain logs and errors
    3. ComfyUI generation failures
    4. System journal events

    Classification:
    - bug_fix: Commits fixing issues
    - architecture_change: Major refactoring
    - eureka_moment: Breakthrough implementations
    - desperation_commit: 3am commits with curse words
    - generation_failure: Failed image/video generations
    """

    def __init__(self, project_id: int = 43):  # Default to Echo Chamber
        self.story_manager = StoryManager()
        self.project_id = project_id
        self.repos = [
            "/opt/tower-echo-brain",
            "/opt/anime-studio",
        ]

    def run_full_scan(self, hours_back: int = 24) -> Dict:
        """Run complete scan of all sources."""
        results = {
            "git_commits": 0,
            "echo_logs": 0,
            "comfyui_errors": 0,
            "total_events": 0,
            "events": []
        }

        # Scan git commits
        git_events = self.scan_git_commits(hours_back)
        results["git_commits"] = len(git_events)
        results["events"].extend(git_events)

        # Scan Echo Brain logs
        echo_events = self.scan_echo_brain_logs(hours_back)
        results["echo_logs"] = len(echo_events)
        results["events"].extend(echo_events)

        # Scan ComfyUI errors
        comfy_events = self.scan_comfyui_failures(hours_back)
        results["comfyui_errors"] = len(comfy_events)
        results["events"].extend(comfy_events)

        # Store all events in reality_feed table
        for event in results["events"]:
            self._store_reality_event(event)

        results["total_events"] = len(results["events"])
        logger.info(f"Reality feed scan complete: {results['total_events']} events captured")

        return results

    def scan_git_commits(self, hours_back: int = 24) -> List[Dict]:
        """Scan git commits from tower repos."""
        events = []
        since_date = (datetime.now() - timedelta(hours=hours_back)).isoformat()

        for repo in self.repos:
            if not os.path.exists(os.path.join(repo, ".git")):
                continue

            try:
                # Get recent commits
                cmd = [
                    "git", "-C", repo, "log",
                    f"--since={since_date}",
                    "--pretty=format:%H|%ae|%ai|%s|%b",
                    "--no-merges"
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0 and result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue

                        parts = line.split("|", 4)
                        if len(parts) >= 4:
                            commit_hash = parts[0]
                            author = parts[1]
                            timestamp = parts[2]
                            subject = parts[3]
                            body = parts[4] if len(parts) > 4 else ""

                            # Classify commit
                            event_type = self._classify_commit(subject, body)

                            # Check time of day for desperation commits
                            commit_hour = datetime.fromisoformat(timestamp.replace(" ", "T")).hour
                            if commit_hour >= 2 and commit_hour <= 5:
                                if any(word in subject.lower() for word in ["fix", "fuck", "broken", "why", "please"]):
                                    event_type = "desperation_commit"

                            events.append({
                                "source": "git_commit",
                                "event_type": event_type,
                                "content": f"{subject}\n{body}",
                                "metadata": {
                                    "repo": repo.split("/")[-1],
                                    "commit": commit_hash,
                                    "author": author,
                                    "timestamp": timestamp
                                },
                                "tags": self._extract_tags(subject + " " + body)
                            })

            except Exception as e:
                logger.error(f"Failed to scan git commits in {repo}: {e}")

        return events

    def scan_echo_brain_logs(self, hours_back: int = 24) -> List[Dict]:
        """Scan Echo Brain database for errors and interesting events."""
        events = []

        try:
            with psycopg2.connect(**ECHO_BRAIN_CONFIG) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Look for recent conversations with interesting titles or summaries
                    cur.execute("""
                        SELECT id, title, summary, created_at
                        FROM conversations
                        WHERE created_at > NOW() - INTERVAL '%s hours'
                        AND (
                            title ILIKE '%%error%%' OR
                            title ILIKE '%%failed%%' OR
                            title ILIKE '%%debug%%' OR
                            summary ILIKE '%%error%%' OR
                            summary ILIKE '%%failed%%' OR
                            summary ILIKE '%%breakthrough%%' OR
                            summary ILIKE '%%finally%%' OR
                            summary ILIKE '%%eureka%%'
                        )
                        ORDER BY created_at DESC
                        LIMIT 100
                    """, (hours_back,))

                    for row in cur.fetchall():
                        content = f"{row.get('title', '')} {row.get('summary', '')}"
                        event_type = "echo_brain_log"

                        # Classify based on content
                        if any(word in content.lower() for word in ["error", "failed", "exception"]):
                            event_type = "generation_failure"
                        elif any(word in content.lower() for word in ["breakthrough", "eureka", "finally works"]):
                            event_type = "eureka_moment"

                        events.append({
                            "source": "echo_brain_log",
                            "event_type": event_type,
                            "content": content[:500],  # Truncate long content
                            "metadata": {
                                "conversation_id": str(row["id"]),
                                "timestamp": row["created_at"].isoformat()
                            },
                            "tags": self._extract_tags(content)
                        })

        except Exception as e:
            logger.error(f"Failed to scan Echo Brain logs: {e}")

        return events

    def scan_comfyui_failures(self, hours_back: int = 24) -> List[Dict]:
        """Scan system journal for ComfyUI errors."""
        events = []

        try:
            # Get ComfyUI logs from journalctl
            cmd = [
                "sudo", "journalctl", "-u", "comfyui",
                "--since", f"{hours_back} hours ago",
                "--no-pager", "--output=json"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                        message = entry.get("MESSAGE", "")

                        # Look for errors
                        if any(word in message.lower() for word in ["error", "exception", "failed", "cuda out of memory"]):
                            events.append({
                                "source": "comfyui_error",
                                "event_type": "generation_failure",
                                "content": message[:500],
                                "metadata": {
                                    "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                                    "priority": entry.get("PRIORITY", "")
                                },
                                "tags": ["comfyui", "generation", "error"]
                            })
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            # journalctl might not be available or ComfyUI might not be a systemd service
            logger.debug(f"Could not scan ComfyUI logs: {e}")

        return events

    def _classify_commit(self, subject: str, body: str) -> str:
        """Classify a git commit based on its message."""
        full_message = (subject + " " + body).lower()

        if any(word in full_message for word in ["fix", "bug", "patch", "resolve", "repair"]):
            return "bug_fix"
        elif any(word in full_message for word in ["refactor", "architecture", "redesign", "restructure"]):
            return "architecture_change"
        elif any(word in full_message for word in ["breakthrough", "eureka", "finally", "works!", "success"]):
            return "eureka_moment"
        elif any(word in full_message for word in ["wip", "test", "experiment", "trying"]):
            return "experiment"
        else:
            return "development"

    def _extract_tags(self, text: str) -> List[str]:
        """Extract relevant tags from text."""
        tags = []

        # Look for common development terms
        patterns = {
            "anime": r"\b(anime|animation|video|scene|episode)\b",
            "ai": r"\b(claude|gpt|llm|ai|model)\b",
            "error": r"\b(error|exception|failed|broken)\b",
            "success": r"\b(works|success|fixed|resolved)\b",
            "comfyui": r"\b(comfyui|workflow|node|generation)\b",
            "database": r"\b(database|postgres|sql|query)\b",
        }

        for tag, pattern in patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                tags.append(tag)

        return tags

    def _store_reality_event(self, event: Dict) -> None:
        """Store an event in the reality_feed table."""
        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cur:
                    # Combine metadata into the raw_content
                    metadata = event.get("metadata", {})
                    content_with_metadata = event["content"]
                    if metadata:
                        content_with_metadata += f"\n\n[Metadata: {json.dumps(metadata)}]"

                    cur.execute("""
                        INSERT INTO reality_feed
                        (source, event_type, raw_content, tags, project_id)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (
                        event["source"],
                        event["event_type"],
                        content_with_metadata,
                        event.get("tags", []),
                        self.project_id
                    ))
                    conn.commit()
        except Exception as e:
            logger.error(f"Failed to store reality event: {e}")

    def get_recent_events(self, limit: int = 20) -> List[Dict]:
        """Get recent reality feed events."""
        events = []

        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM reality_feed
                        WHERE project_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (self.project_id, limit))

                    events = [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get recent events: {e}")

        return events


# CLI runner
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Reality Feed Watcher")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back")
    parser.add_argument("--project-id", type=int, default=43, help="Project ID (default: Echo Chamber)")

    args = parser.parse_args()

    watcher = RealityFeedWatcher(project_id=args.project_id)
    results = watcher.run_full_scan(hours_back=args.hours)

    print(f"Reality Feed Scan Results:")
    print(f"  Git commits: {results['git_commits']}")
    print(f"  Echo logs: {results['echo_logs']}")
    print(f"  ComfyUI errors: {results['comfyui_errors']}")
    print(f"  Total events: {results['total_events']}")

    if results["events"]:
        print("\nRecent events:")
        for event in results["events"][:5]:
            print(f"  - {event['event_type']}: {event['content'][:100]}...")