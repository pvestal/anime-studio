#!/usr/bin/env python3
"""
REST API endpoints for Storyline Version Control System
Provides HTTP interface for git-like story management
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import asyncio
from pathlib import Path

# Import our storyline systems
from storyline_version_control import StorylineVersionControl, StoryBranch
from user_interaction_system import UserInteractionSystem

app = FastAPI(title="Anime Storyline API", version="1.0.0")

# Global storage for active storylines
storylines: Dict[str, StorylineVersionControl] = {}
user_system = UserInteractionSystem()

# WebSocket connections for real-time collaboration
active_connections: Dict[str, List[WebSocket]] = {}


class StoryCreateRequest(BaseModel):
    """Request to create a new story"""
    story_id: str
    title: str
    description: Optional[str] = ""
    author: str = "User"


class CommitRequest(BaseModel):
    """Request to commit story changes"""
    message: str
    author: str = "User"
    changes: Optional[Dict[str, Any]] = None


class BranchRequest(BaseModel):
    """Request to create a new branch"""
    branch_name: str
    description: str = ""


class ChapterRequest(BaseModel):
    """Request to add/edit a chapter"""
    title: str
    content: str
    metadata: Optional[Dict[str, Any]] = {}


class MergeRequest(BaseModel):
    """Request to merge branches"""
    source_branch: str
    target_branch: Optional[str] = None


class UserIntentRequest(BaseModel):
    """User input for intent analysis"""
    input_text: str
    context: Optional[Dict[str, Any]] = {}


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await user_system.initialize()
    print("📚 Storyline API initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await user_system.cleanup()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "active_stories": len(storylines),
        "timestamp": datetime.utcnow().isoformat()
    }


# ==================== Story Management ====================

@app.post("/api/stories/create")
async def create_story(request: StoryCreateRequest):
    """Create a new story with version control"""
    if request.story_id in storylines:
        raise HTTPException(400, "Story already exists")

    # Create new storyline
    vcs = StorylineVersionControl(request.story_id)
    vcs.working_story["title"] = request.title
    vcs.working_story["metadata"] = {
        "description": request.description,
        "created_at": datetime.utcnow().isoformat(),
        "author": request.author
    }

    # Initial commit
    commit_hash = vcs.commit(f"Created story: {request.title}", request.author)

    # Store in memory (TODO: persist to database)
    storylines[request.story_id] = vcs

    return {
        "story_id": request.story_id,
        "title": request.title,
        "initial_commit": commit_hash,
        "branches": list(vcs.branches.keys())
    }


@app.get("/api/stories/{story_id}")
async def get_story(story_id: str):
    """Get current story state"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]
    return {
        "story_id": story_id,
        "current_branch": vcs.current_branch,
        "head_commit": vcs.head_commit,
        "story": vcs.working_story,
        "branches": list(vcs.branches.keys()),
        "total_commits": len(vcs.commits)
    }


@app.get("/api/stories")
async def list_stories():
    """List all active stories"""
    return {
        "stories": [
            {
                "story_id": sid,
                "title": vcs.working_story.get("title", "Untitled"),
                "branches": len(vcs.branches),
                "commits": len(vcs.commits)
            }
            for sid, vcs in storylines.items()
        ]
    }


# ==================== Version Control ====================

@app.post("/api/stories/{story_id}/commit")
async def commit_changes(story_id: str, request: CommitRequest):
    """Commit current story changes"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]

    # Apply changes if provided
    if request.changes:
        for key, value in request.changes.items():
            vcs.working_story[key] = value

    # Commit
    commit_hash = vcs.commit(request.message, request.author)

    # Notify WebSocket clients
    await notify_clients(story_id, {
        "type": "commit",
        "commit_hash": commit_hash,
        "message": request.message,
        "author": request.author
    })

    return {
        "commit_hash": commit_hash,
        "branch": vcs.current_branch,
        "message": request.message
    }


@app.post("/api/stories/{story_id}/branch")
async def create_branch(story_id: str, request: BranchRequest):
    """Create a new story branch"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]

    try:
        branch_name = vcs.create_branch(request.branch_name, request.description)

        # Notify clients
        await notify_clients(story_id, {
            "type": "branch_created",
            "branch": branch_name,
            "description": request.description
        })

        return {
            "branch": branch_name,
            "parent": vcs.current_branch,
            "head_commit": vcs.head_commit
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/stories/{story_id}/switch/{branch_name}")
async def switch_branch(story_id: str, branch_name: str):
    """Switch to different branch"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]

    try:
        vcs.switch_branch(branch_name)

        await notify_clients(story_id, {
            "type": "branch_switched",
            "branch": branch_name
        })

        return {
            "current_branch": vcs.current_branch,
            "head_commit": vcs.head_commit,
            "story": vcs.working_story
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/stories/{story_id}/merge")
async def merge_branches(story_id: str, request: MergeRequest):
    """Merge story branches"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]

    try:
        success, conflicts = vcs.merge_branches(
            request.source_branch,
            request.target_branch
        )

        result = {
            "success": success,
            "source": request.source_branch,
            "target": request.target_branch or vcs.current_branch,
            "conflicts": conflicts
        }

        if success:
            await notify_clients(story_id, {
                "type": "branches_merged",
                **result
            })

        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/stories/{story_id}/history")
async def get_history(story_id: str, branch: Optional[str] = None, limit: int = 10):
    """Get commit history"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]
    history = vcs.get_history(branch, limit)

    return {
        "branch": branch or vcs.current_branch,
        "commits": [
            {
                "hash": commit.commit_hash,
                "parent": commit.parent_hash,
                "author": commit.author,
                "message": commit.message,
                "timestamp": commit.timestamp.isoformat(),
                "changes": commit.changes
            }
            for commit in history
        ]
    }


@app.get("/api/stories/{story_id}/diff")
async def diff_versions(story_id: str, commit1: str, commit2: Optional[str] = None):
    """Get differences between story versions"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]

    try:
        diff = vcs.diff_stories(commit1, commit2)
        return {
            "commit1": commit1,
            "commit2": commit2 or vcs.head_commit,
            "diff": diff
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


# ==================== Story Content ====================

@app.post("/api/stories/{story_id}/chapters")
async def add_chapter(story_id: str, request: ChapterRequest):
    """Add a new chapter to the story"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]

    # Add chapter
    if "chapters" not in vcs.working_story:
        vcs.working_story["chapters"] = []

    chapter = {
        "title": request.title,
        "content": request.content,
        "metadata": request.metadata,
        "created_at": datetime.utcnow().isoformat()
    }

    vcs.working_story["chapters"].append(chapter)

    # Auto-commit
    commit_hash = vcs.commit(f"Added chapter: {request.title}", "System")

    await notify_clients(story_id, {
        "type": "chapter_added",
        "chapter": chapter
    })

    return {
        "chapter_index": len(vcs.working_story["chapters"]) - 1,
        "commit_hash": commit_hash
    }


@app.put("/api/stories/{story_id}/chapters/{chapter_index}")
async def update_chapter(story_id: str, chapter_index: int, request: ChapterRequest):
    """Update an existing chapter"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]

    if "chapters" not in vcs.working_story:
        raise HTTPException(400, "Story has no chapters")

    if chapter_index >= len(vcs.working_story["chapters"]):
        raise HTTPException(404, "Chapter not found")

    # Update chapter
    vcs.working_story["chapters"][chapter_index].update({
        "title": request.title,
        "content": request.content,
        "metadata": request.metadata,
        "updated_at": datetime.utcnow().isoformat()
    })

    # Auto-commit
    commit_hash = vcs.commit(f"Updated chapter {chapter_index}: {request.title}", "System")

    await notify_clients(story_id, {
        "type": "chapter_updated",
        "chapter_index": chapter_index
    })

    return {
        "chapter_index": chapter_index,
        "commit_hash": commit_hash
    }


# ==================== User Interaction ====================

@app.post("/api/stories/{story_id}/intent")
async def analyze_intent(story_id: str, request: UserIntentRequest):
    """Analyze user intent for story interaction"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]

    # Add story context
    context = request.context or {}
    context["story_id"] = story_id
    context["current_branch"] = vcs.current_branch
    context["chapters"] = len(vcs.working_story.get("chapters", []))

    # Analyze intent
    intent = await user_system.capture_intent(request.input_text, context)

    return {
        "action": intent.action,
        "target": intent.target,
        "parameters": intent.parameters,
        "confidence": intent.confidence
    }


@app.post("/api/stories/{story_id}/suggestions")
async def get_suggestions(story_id: str):
    """Get AI suggestions for next story actions"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    vcs = storylines[story_id]

    # Build story context
    context = {
        "story": vcs.working_story,
        "current_branch": vcs.current_branch,
        "total_commits": len(vcs.commits)
    }

    # Get suggestions
    suggestions = await user_system.suggest_next_action(context)

    return {"suggestions": suggestions}


@app.post("/api/stories/{story_id}/feedback")
async def submit_feedback(story_id: str, rating: int, comments: str = ""):
    """Submit feedback on story generation"""
    if story_id not in storylines:
        raise HTTPException(404, "Story not found")

    # Capture feedback
    await user_system.capture_feedback(story_id, rating, comments)

    return {"status": "feedback_recorded", "rating": rating}


# ==================== WebSocket for Real-time Collaboration ====================

@app.websocket("/ws/stories/{story_id}")
async def websocket_endpoint(websocket: WebSocket, story_id: str):
    """WebSocket for real-time story collaboration"""
    await websocket.accept()

    # Add to active connections
    if story_id not in active_connections:
        active_connections[story_id] = []
    active_connections[story_id].append(websocket)

    try:
        # Send initial state
        if story_id in storylines:
            await websocket.send_json({
                "type": "initial_state",
                "story": storylines[story_id].working_story,
                "branch": storylines[story_id].current_branch
            })

        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed

    except WebSocketDisconnect:
        # Remove from active connections
        active_connections[story_id].remove(websocket)
        if not active_connections[story_id]:
            del active_connections[story_id]


async def notify_clients(story_id: str, message: Dict):
    """Notify all connected clients of story changes"""
    if story_id in active_connections:
        disconnected = []
        for websocket in active_connections[story_id]:
            try:
                await websocket.send_json(message)
            except:
                disconnected.append(websocket)

        # Remove disconnected clients
        for ws in disconnected:
            active_connections[story_id].remove(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8329)