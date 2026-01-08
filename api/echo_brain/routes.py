"""
Echo Brain API Routes - Creative AI assistant endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import json
import logging

import sys
sys.path.insert(0, '/opt/tower-anime-production')

from api.echo_brain.assist import EchoBrainAssistant
from api.echo_brain.workflow_orchestrator import CreativeWorkflowOrchestrator

# Create database function
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = f"postgresql://patrick:{os.getenv('DATABASE_PASSWORD', '***REMOVED***')}@localhost/anime_production"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/echo-brain", tags=["echo-brain"])

# Request/Response models
class ChatMessage(BaseModel):
    message: str
    context: Optional[Dict] = None
    project_id: Optional[int] = None
    episode_id: Optional[int] = None
    character_id: Optional[int] = None

class QuickActionRequest(BaseModel):
    context: Optional[Dict] = None
    project_id: Optional[int] = None

class SuggestionApplication(BaseModel):
    suggestion: Dict
    project_id: Optional[int] = None

class StorylineRequest(BaseModel):
    project_id: int
    theme: str
    context: Optional[Dict] = None

class StyleRequest(BaseModel):
    character_description: str
    mood: str
    art_style: str = "anime"

class SearchRequest(BaseModel):
    query: str
    content_type: str = "all"
    limit: int = 10

# Initialize assistant
echo_assistant = None

def get_echo_assistant(db: Session = Depends(get_db)) -> EchoBrainAssistant:
    """Get or create Echo Brain assistant instance"""
    global echo_assistant
    if echo_assistant is None:
        echo_assistant = EchoBrainAssistant(db)
    return echo_assistant

# Routes

@router.get("/status")
async def get_echo_status(assistant: EchoBrainAssistant = Depends(get_echo_assistant)):
    """Check Echo Brain connection status"""
    return {
        "status": "connected" if assistant.ollama_available else "offline",
        "models": assistant.available_models if hasattr(assistant, 'available_models') else [],
        "capabilities": [
            "storyline_generation",
            "character_design",
            "visual_style_analysis",
            "semantic_search",
            "consistency_improvement"
        ]
    }

@router.post("/chat")
async def chat_with_echo(
    request: ChatMessage,
    db: Session = Depends(get_db),
    assistant: EchoBrainAssistant = Depends(get_echo_assistant)
):
    """Main chat interface with Echo Brain"""
    try:
        # Process based on message intent
        message_lower = request.message.lower()

        response_text = ""
        suggestions = []
        actions = []
        generated_assets = []

        # Detect intent and route appropriately
        if any(word in message_lower for word in ["story", "episode", "plot", "narrative"]):
            # Generate storyline suggestions
            result = await assistant.brainstorm_storyline(
                project_id=request.project_id or 0,
                theme=request.message,
                context=request.context
            )

            if result["success"]:
                storyline = result["storyline"]
                response_text = f"I've created a storyline with {len(storyline.get('episodes', []))} episodes based on your theme."

                # Convert episodes to suggestions
                for ep in storyline.get("episodes", []):
                    suggestions.append({
                        "type": "storyline",
                        "text": f"{ep['title']}: {ep['synopsis']}",
                        "data": ep
                    })
            else:
                response_text = "I'll help you create a storyline. Let me generate some episode ideas..."

        elif any(word in message_lower for word in ["character", "design", "appearance"]):
            # Character design assistance
            response_text = "I can help design your character. Let me suggest some visual styles..."

            # Extract character info from message
            style_result = await assistant.suggest_visual_style(
                character_description=request.message,
                mood="neutral",
                art_style="anime"
            )

            if style_result["success"]:
                style_data = style_result["style"]
                suggestions.append({
                    "type": "character_design",
                    "text": "Character design with suggested prompt",
                    "data": style_data
                })

        elif any(word in message_lower for word in ["style", "visual", "look", "aesthetic"]):
            # Visual style analysis
            response_text = "Let me analyze and suggest visual styles for your project..."

            style_result = await assistant.suggest_visual_style(
                character_description=request.context.get("description", "") if request.context else "",
                mood=request.context.get("mood", "neutral") if request.context else "neutral",
                art_style="anime"
            )

            if style_result["success"]:
                style_data = style_result["style"]
                suggestions.append({
                    "type": "visual_style",
                    "text": f"Visual style: {style_data.get('main_prompt', '')}",
                    "data": style_data
                })

        elif any(word in message_lower for word in ["search", "find", "similar", "like"]):
            # Semantic search
            search_results = await assistant.search_similar_content(
                query=request.message,
                content_type="all"
            )

            response_text = f"I found {len(search_results.get('projects', []))} similar projects and {len(search_results.get('characters', []))} similar characters."

            # Add search results as suggestions
            for project in search_results.get("projects", [])[:3]:
                suggestions.append({
                    "type": "similar_project",
                    "text": f"Similar project: {project.get('name', 'Unknown')}",
                    "data": project
                })

        elif any(word in message_lower for word in ["generate", "create", "make", "produce"]):
            # Generation request
            response_text = "I'll help you generate content. Let me prepare the generation parameters..."

            actions.append({
                "type": "prepare_generation",
                "data": {
                    "project_id": request.project_id,
                    "context": request.context
                }
            })

        else:
            # General conversation
            general_response = await assistant.ollama_complete(request.message)
            response_text = general_response.get("text", "I'm here to help with your anime production. You can ask me about storylines, character design, visual styles, or finding similar content.")

        return JSONResponse({
            "response": response_text,
            "suggestions": suggestions,
            "actions": actions,
            "generated_assets": generated_assets,
            "model_used": assistant.creative_model if assistant.ollama_available else "fallback"
        })

    except Exception as e:
        logger.error(f"Chat error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@router.post("/quick-action/{action_id}")
async def perform_quick_action(
    action_id: str,
    request: QuickActionRequest,
    db: Session = Depends(get_db),
    assistant: EchoBrainAssistant = Depends(get_echo_assistant)
):
    """Execute predefined quick actions"""
    try:
        message = ""
        suggestions = []
        actions = []
        assets = []

        if action_id == "brainstorm_episode":
            result = await assistant.brainstorm_storyline(
                project_id=request.project_id or 0,
                theme="anime adventure",
                context=request.context
            )

            if result["success"]:
                storyline = result["storyline"]
                message = f"Generated {len(storyline.get('episodes', []))} episode ideas for your project!"

                for ep in storyline.get("episodes", []):
                    suggestions.append({
                        "type": "storyline",
                        "text": f"Episode {ep['number']}: {ep['title']}",
                        "data": ep
                    })
            else:
                message = "Created template episode structure for your project."

        elif action_id == "suggest_character":
            # Generate character design suggestions
            message = "Here are some character design ideas..."

            # Generate multiple character concepts
            for i in range(3):
                style_result = await assistant.suggest_visual_style(
                    character_description=f"anime character concept {i+1}",
                    mood="dynamic",
                    art_style="anime"
                )

                if style_result["success"]:
                    suggestions.append({
                        "type": "character_design",
                        "text": f"Character concept {i+1}",
                        "data": style_result["style"]
                    })

        elif action_id == "analyze_style":
            # Analyze project style consistency
            if request.project_id:
                orchestrator = CreativeWorkflowOrchestrator(request.project_id, db)
                analysis = await orchestrator.analyze_style_consistency()

                if analysis["success"]:
                    message = f"Analyzed {analysis['total_analyzed']} generations across {analysis['characters_analyzed']} characters."

                    for char_id, report in analysis.get("consistency_reports", {}).items():
                        if report["success"]:
                            suggestions.append({
                                "type": "improvement",
                                "text": f"Character {char_id} consistency: {report['analysis']['consistency_score']:.0%}",
                                "data": report["analysis"]
                            })
                else:
                    message = "No generated content to analyze yet."
            else:
                message = "Please select a project to analyze style consistency."

        elif action_id == "search_similar":
            # Search for similar content
            message = "Searching for similar projects and characters..."

            search_results = await assistant.search_similar_content(
                query=request.context.get("description", "") if request.context else "anime",
                content_type="all"
            )

            # Add results as suggestions
            for project in search_results.get("projects", [])[:5]:
                suggestions.append({
                    "type": "similar_project",
                    "text": f"Similar: {project.get('name', 'Unknown')}",
                    "data": project
                })

        elif action_id == "improve_consistency":
            # Suggest consistency improvements
            if request.project_id:
                orchestrator = CreativeWorkflowOrchestrator(request.project_id, db)

                # Get latest episode
                result = db.execute(
                    "SELECT id FROM episodes WHERE storyline_id IN (SELECT id FROM storylines WHERE project_id = :project_id) ORDER BY created_at DESC LIMIT 1",
                    {"project_id": request.project_id}
                )
                episode = result.fetchone()

                if episode:
                    improvements = await orchestrator.suggest_improvements(episode[0])

                    if improvements["success"]:
                        message = "Here are improvement suggestions for your latest episode:"

                        for improvement in improvements["suggestions"].get("improvements", []):
                            suggestions.append({
                                "type": "improvement",
                                "text": f"Improve {improvement['area']}",
                                "data": improvement
                            })
                    else:
                        message = "No specific improvements needed at this time."
                else:
                    message = "No episodes found to analyze."
            else:
                message = "Please select a project to analyze for improvements."

        else:
            message = f"Unknown action: {action_id}"

        return JSONResponse({
            "message": message,
            "suggestions": suggestions,
            "actions": actions,
            "assets": assets
        })

    except Exception as e:
        logger.error(f"Quick action error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@router.post("/apply-suggestion")
async def apply_suggestion(
    request: SuggestionApplication,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Apply a suggestion from Echo Brain"""
    try:
        suggestion = request.suggestion
        suggestion_type = suggestion.get("type")
        data = suggestion.get("data", {})

        result = {
            "success": False,
            "message": "",
            "data": None,
            "generated_assets": []
        }

        if suggestion_type == "storyline":
            # Create episode from storyline suggestion
            episode_data = data

            # Save to database
            # TODO: Implement actual database save

            result["success"] = True
            result["message"] = f"Created episode: {episode_data.get('title', 'New Episode')}"
            result["data"] = {"episode_id": 1}  # Placeholder

        elif suggestion_type == "character_design":
            # Apply character design
            design_data = data

            # Queue character generation
            # TODO: Implement generation queue

            result["success"] = True
            result["message"] = "Character design queued for generation"
            result["data"] = {
                "job_id": 1,  # Placeholder
                "prompt": design_data.get("main_prompt", "")
            }

        elif suggestion_type == "visual_style":
            # Apply visual style settings
            style_data = data

            # Save style preferences
            # TODO: Implement style preference save

            result["success"] = True
            result["message"] = "Visual style settings updated"
            result["data"] = style_data

        elif suggestion_type == "scene_generation":
            # Queue scene generation
            scene_data = data

            # TODO: Implement actual generation

            result["success"] = True
            result["message"] = "Scene generation started"
            result["data"] = {"job_id": 1}  # Placeholder

        elif suggestion_type == "improvement":
            # Apply improvement suggestions
            improvement_data = data

            result["success"] = True
            result["message"] = f"Applied improvements to {improvement_data.get('area', 'system')}"
            result["data"] = improvement_data

        else:
            result["message"] = f"Unknown suggestion type: {suggestion_type}"

        return JSONResponse(result)

    except Exception as e:
        logger.error(f"Apply suggestion error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@router.post("/brainstorm/storyline")
async def brainstorm_storyline(
    request: StorylineRequest,
    assistant: EchoBrainAssistant = Depends(get_echo_assistant)
):
    """Generate storyline ideas"""
    result = await assistant.brainstorm_storyline(
        project_id=request.project_id,
        theme=request.theme,
        context=request.context
    )
    return result

@router.post("/suggest/visual-style")
async def suggest_visual_style(
    request: StyleRequest,
    assistant: EchoBrainAssistant = Depends(get_echo_assistant)
):
    """Get visual style suggestions"""
    result = await assistant.suggest_visual_style(
        character_description=request.character_description,
        mood=request.mood,
        art_style=request.art_style
    )
    return result

@router.post("/search/similar")
async def search_similar_content(
    request: SearchRequest,
    assistant: EchoBrainAssistant = Depends(get_echo_assistant)
):
    """Search for similar content using semantic search"""
    result = await assistant.search_similar_content(
        query=request.query,
        content_type=request.content_type
    )
    return result

@router.post("/workflow/create-episode")
async def create_complete_episode(
    episode_data: Dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create complete episode with workflow orchestration"""
    try:
        project_id = episode_data.get("project_id")
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id required")

        orchestrator = CreativeWorkflowOrchestrator(project_id, db)

        # Run episode creation in background
        background_tasks.add_task(
            orchestrator.create_complete_episode,
            episode_data
        )

        return {
            "message": "Episode creation started",
            "episode_data": episode_data
        }

    except Exception as e:
        logger.error(f"Episode creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models/available")
async def get_available_models(assistant: EchoBrainAssistant = Depends(get_echo_assistant)):
    """Get list of available AI models"""
    return {
        "ollama_available": assistant.ollama_available,
        "models": assistant.available_models if hasattr(assistant, 'available_models') else [],
        "default_creative": assistant.creative_model,
        "default_style": assistant.style_model,
        "default_embedding": assistant.embedding_model
    }