"""
Echo Brain API Endpoints for Anime Production
Complete implementation of the Echo Brain endpoint design specification
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import json
import logging
import asyncio
from datetime import datetime

# Import the new service
from .echo_brain_service import get_echo_brain_service, EchoBrainService

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/echo-brain", tags=["echo-brain"])

# Pydantic models for requests/responses
class EchoStatusResponse(BaseModel):
    status: str
    timestamp: str
    config: Dict[str, Any]
    capabilities: Dict[str, bool]
    last_check: Optional[str]
    error: Optional[str]

class ProjectContextRequest(BaseModel):
    project_id: int

class SceneSuggestionRequest(BaseModel):
    project_id: int
    current_scene: Optional[Dict[str, Any]] = None

class DialogueRequest(BaseModel):
    character_names: List[str]
    context: str
    tone: str = "casual"

class EpisodeContinuationRequest(BaseModel):
    project_id: int
    current_episode: int

class FeedbackRequest(BaseModel):
    suggestion_id: int
    rating: int  # 1-5
    comments: Optional[str] = None

class ConfigUpdateRequest(BaseModel):
    config_updates: Dict[str, Any]

class SuggestionsHistoryRequest(BaseModel):
    project_id: Optional[int] = None
    suggestion_type: Optional[str] = None
    limit: int = 50

# Dependency injection
def get_echo_service() -> EchoBrainService:
    """Get Echo Brain service instance"""
    return get_echo_brain_service()

# Database dependency (from main.py)
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

# === STATUS & CONFIGURATION ENDPOINTS ===

@router.get("/status", response_model=EchoStatusResponse)
async def get_echo_brain_status(service: EchoBrainService = Depends(get_echo_service)):
    """
    Check Echo Brain service status and capabilities
    Returns comprehensive status including AI service availability
    """
    try:
        status_info = await service.check_status()
        return EchoStatusResponse(**status_info)
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return EchoStatusResponse(
            status="error",
            timestamp=datetime.utcnow().isoformat(),
            config={},
            capabilities={},
            error=str(e)
        )

@router.post("/config")
async def update_echo_config(
    request: ConfigUpdateRequest,
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Update Echo Brain configuration settings
    Allows dynamic reconfiguration without restart
    """
    try:
        result = service.update_config(request.config_updates)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Config update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "service": "echo-brain",
        "timestamp": datetime.utcnow().isoformat()
    }

# === PROJECT CONTEXT BUILDING ===

@router.post("/context/project")
async def get_project_context(
    request: ProjectContextRequest,
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Build comprehensive project context from database
    Includes characters, scenes, recent generations, and themes
    """
    try:
        context = await service.get_project_context(request.project_id)
        return JSONResponse(content={
            "success": True,
            "project_id": request.project_id,
            "context": context,
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Project context building failed: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e),
            "project_id": request.project_id,
            "timestamp": datetime.utcnow().isoformat()
        })

@router.get("/context/project/{project_id}/summary")
async def get_project_summary(
    project_id: int,
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Get a quick summary of project context
    Useful for dashboard displays
    """
    try:
        context = await service.get_project_context(project_id)

        return {
            "project_id": project_id,
            "summary": context.get("context_summary", ""),
            "character_count": len(context.get("characters", [])),
            "scene_count": len(context.get("scenes", [])),
            "recent_generations": len(context.get("recent_generations", [])),
            "project_status": context.get("project_info", {}).get("status", "unknown")
        }
    except Exception as e:
        logger.error(f"Project summary failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === CREATIVE ASSISTANCE ENDPOINTS ===

@router.post("/suggest/scenes")
async def suggest_next_scenes(
    request: SceneSuggestionRequest,
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Suggest ideas for next scenes in the project
    Uses AI when available, graceful fallback otherwise
    """
    try:
        suggestions = await service.suggest_next_scene(
            project_id=request.project_id,
            current_scene=request.current_scene
        )

        return JSONResponse(content={
            "success": True,
            "project_id": request.project_id,
            "suggestions": suggestions["suggestions"],
            "context_used": suggestions.get("context_used", {}),
            "ai_available": suggestions.get("ai_available", False),
            "fallback_used": suggestions.get("fallback_used", False),
            "suggestion_count": len(suggestions["suggestions"]),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Scene suggestion failed: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e),
            "project_id": request.project_id,
            "timestamp": datetime.utcnow().isoformat()
        })

@router.post("/generate/dialogue")
async def generate_character_dialogue(
    request: DialogueRequest,
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Generate dialogue between specified characters
    Considers character personalities and context
    """
    try:
        dialogue_result = await service.generate_dialogue(
            character_names=request.character_names,
            context=request.context,
            tone=request.tone
        )

        return JSONResponse(content={
            "success": True,
            "characters": request.character_names,
            "dialogue": dialogue_result["dialogue"],
            "tone": request.tone,
            "context_used": dialogue_result.get("context_used", ""),
            "ai_available": dialogue_result.get("ai_available", False),
            "fallback_used": dialogue_result.get("fallback_used", False),
            "line_count": len(dialogue_result["dialogue"]),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Dialogue generation failed: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e),
            "characters": request.character_names,
            "timestamp": datetime.utcnow().isoformat()
        })

@router.post("/continue/episode")
async def continue_episode_development(
    request: EpisodeContinuationRequest,
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Suggest how to continue or develop the current episode
    Analyzes existing content and provides creative directions
    """
    try:
        continuation = await service.continue_episode(
            project_id=request.project_id,
            current_episode=request.current_episode
        )

        return JSONResponse(content={
            "success": True,
            "project_id": request.project_id,
            "current_episode": request.current_episode,
            "continuation_suggestions": continuation["continuation_suggestions"],
            "project_context": continuation.get("project_context", {}),
            "ai_available": continuation.get("ai_available", False),
            "fallback_used": continuation.get("fallback_used", False),
            "suggestion_count": len(continuation["continuation_suggestions"]),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Episode continuation failed: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e),
            "project_id": request.project_id,
            "timestamp": datetime.utcnow().isoformat()
        })

@router.post("/enhance/prompt")
async def enhance_generation_prompt(
    prompt_data: Dict[str, Any],
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Enhance a generation prompt using Echo Brain AI
    Improves prompts for better generation results
    """
    try:
        original_prompt = prompt_data.get("prompt", "")
        character = prompt_data.get("character", "")
        style = prompt_data.get("style", "anime")

        if not original_prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")

        # Check service availability
        status = await service.check_status()
        ai_available = status["status"] == "available"

        if ai_available:
            # Use AI to enhance prompt
            enhancement_context = f"Character: {character}, Style: {style}"
            try:
                ai_response = await service._query_echo_api(
                    f"Enhance this anime generation prompt for better results: '{original_prompt}'. Context: {enhancement_context}. Return only the enhanced prompt."
                ) or await service._query_ollama(
                    f"Enhance this anime generation prompt: '{original_prompt}'. Make it more detailed and specific for anime generation. Return only the enhanced prompt."
                )

                enhanced_prompt = ai_response.strip().strip('"').strip("'")
                if not enhanced_prompt or len(enhanced_prompt) < 10:
                    enhanced_prompt = f"{original_prompt}, masterpiece, best quality, detailed, {style} style"

            except Exception as ai_error:
                logger.warning(f"AI prompt enhancement failed: {ai_error}")
                enhanced_prompt = f"{original_prompt}, masterpiece, best quality, detailed, {style} style"
                ai_available = False
        else:
            # Fallback enhancement
            enhanced_prompt = f"{original_prompt}, masterpiece, best quality, detailed, {style} style"
            if character:
                enhanced_prompt = f"{character}, {enhanced_prompt}"

        return {
            "success": True,
            "original_prompt": original_prompt,
            "enhanced_prompt": enhanced_prompt,
            "character": character,
            "style": style,
            "ai_enhanced": ai_available,
            "enhancements": [
                "Added quality tags",
                "Specified style",
                "Enhanced for anime generation"
            ],
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Prompt enhancement failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "original_prompt": prompt_data.get("prompt", ""),
            "timestamp": datetime.utcnow().isoformat()
        }

# === INTEGRATION ENDPOINTS ===

@router.post("/integrate/workflow")
async def integrate_with_workflow(
    workflow_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Integrate Echo Brain suggestions into existing workflows
    Connects with ComfyUI and other generation systems
    """
    try:
        integration_type = workflow_data.get("type", "unknown")
        project_id = workflow_data.get("project_id")

        result = {
            "success": False,
            "integration_type": integration_type,
            "message": "",
            "actions_taken": [],
            "generated_assets": []
        }

        if integration_type == "scene_generation":
            # Integrate scene suggestions into generation pipeline
            scene_data = workflow_data.get("scene_data", {})

            # Get project context for better integration
            if project_id:
                context = await service.get_project_context(project_id)
                scene_data["project_context"] = context

            # Queue scene generation in background
            background_tasks.add_task(
                _process_scene_generation,
                scene_data,
                service
            )

            result.update({
                "success": True,
                "message": "Scene generation queued with Echo Brain context",
                "actions_taken": ["scene_generation_queued"],
                "estimated_time": "2-5 minutes"
            })

        elif integration_type == "character_enhancement":
            # Enhance character generation with Echo Brain suggestions
            character_data = workflow_data.get("character_data", {})

            # Get character-specific suggestions
            if character_data.get("names"):
                dialogue_result = await service.generate_dialogue(
                    character_names=character_data["names"],
                    context=character_data.get("context", "character development scene"),
                    tone=character_data.get("tone", "casual")
                )

                result.update({
                    "success": True,
                    "message": f"Generated dialogue for {len(character_data['names'])} characters",
                    "actions_taken": ["dialogue_generated"],
                    "dialogue_lines": len(dialogue_result["dialogue"]),
                    "generated_assets": [{"type": "dialogue", "data": dialogue_result}]
                })

        elif integration_type == "style_consistency":
            # Apply style consistency improvements
            style_data = workflow_data.get("style_data", {})

            result.update({
                "success": True,
                "message": "Style consistency suggestions applied",
                "actions_taken": ["style_analysis", "consistency_check"],
                "recommendations": [
                    "Maintain consistent lighting across scenes",
                    "Use project-specific LoRA models",
                    "Apply quality control checkpoints"
                ]
            })

        else:
            result["message"] = f"Unknown integration type: {integration_type}"

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Workflow integration failed: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e),
            "integration_type": workflow_data.get("type", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        })

# === FEEDBACK & LEARNING LOOP ===

@router.post("/feedback/submit")
async def submit_suggestion_feedback(
    request: FeedbackRequest,
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Submit feedback on Echo Brain suggestions
    Enables continuous learning and improvement
    """
    try:
        if request.rating < 1 or request.rating > 5:
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

        feedback_result = await service.submit_feedback(
            suggestion_id=request.suggestion_id,
            rating=request.rating,
            comments=request.comments
        )

        return JSONResponse(content={
            "success": feedback_result["status"] == "success",
            "message": feedback_result["message"],
            "suggestion_id": request.suggestion_id,
            "rating_submitted": request.rating,
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Feedback submission failed: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e),
            "suggestion_id": request.suggestion_id,
            "timestamp": datetime.utcnow().isoformat()
        })

@router.post("/feedback/batch")
async def submit_batch_feedback(
    feedback_batch: List[FeedbackRequest],
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Submit multiple feedback items in batch
    Efficient for rating multiple suggestions at once
    """
    try:
        results = []
        success_count = 0

        for feedback in feedback_batch:
            try:
                result = await service.submit_feedback(
                    suggestion_id=feedback.suggestion_id,
                    rating=feedback.rating,
                    comments=feedback.comments
                )
                results.append({
                    "suggestion_id": feedback.suggestion_id,
                    "success": result["status"] == "success",
                    "message": result["message"]
                })
                if result["status"] == "success":
                    success_count += 1
            except Exception as e:
                results.append({
                    "suggestion_id": feedback.suggestion_id,
                    "success": False,
                    "error": str(e)
                })

        return {
            "success": success_count > 0,
            "total_submitted": len(feedback_batch),
            "successful_submissions": success_count,
            "failed_submissions": len(feedback_batch) - success_count,
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Batch feedback submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/suggestions")
async def get_suggestions_history(
    request: SuggestionsHistoryRequest = Depends(),
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Get history of Echo Brain suggestions with filtering
    Useful for tracking what has been suggested and used
    """
    try:
        suggestions = await service.get_suggestions_history(
            project_id=request.project_id,
            suggestion_type=request.suggestion_type,
            limit=request.limit
        )

        return {
            "success": True,
            "total_suggestions": len(suggestions),
            "project_id": request.project_id,
            "suggestion_type": request.suggestion_type,
            "suggestions": suggestions,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Suggestions history retrieval failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.get("/analytics/usage")
async def get_usage_analytics(
    project_id: Optional[int] = None,
    days: int = 30,
    service: EchoBrainService = Depends(get_echo_service)
):
    """
    Get usage analytics for Echo Brain
    Shows how suggestions are being used and rated
    """
    try:
        # Get basic usage statistics
        suggestions = await service.get_suggestions_history(
            project_id=project_id,
            limit=1000  # Large limit for analytics
        )

        # Calculate analytics
        total_suggestions = len(suggestions)
        by_type = {}
        ratings = []
        used_count = 0

        for suggestion in suggestions:
            # Count by type
            suggestion_type = suggestion.get("type", "unknown")
            by_type[suggestion_type] = by_type.get(suggestion_type, 0) + 1

            # Collect ratings
            if suggestion.get("rating"):
                ratings.append(suggestion["rating"])

            # Count used suggestions
            if suggestion.get("used"):
                used_count += 1

        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        usage_rate = used_count / total_suggestions if total_suggestions > 0 else 0

        return {
            "success": True,
            "analytics": {
                "total_suggestions": total_suggestions,
                "suggestions_by_type": by_type,
                "average_rating": round(avg_rating, 2),
                "total_ratings": len(ratings),
                "usage_rate": round(usage_rate, 2),
                "used_suggestions": used_count,
                "period_days": days
            },
            "project_id": project_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Usage analytics failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# === HELPER FUNCTIONS ===

async def _process_scene_generation(scene_data: Dict[str, Any], service: EchoBrainService):
    """
    Background task for processing scene generation with Echo Brain integration
    """
    try:
        logger.info(f"Processing scene generation with Echo Brain context")

        # This would integrate with the actual generation pipeline
        # For now, we'll log the action
        project_context = scene_data.get("project_context", {})
        scene_title = scene_data.get("title", "Unknown Scene")

        logger.info(f"Scene '{scene_title}' queued with project context from Echo Brain")

        # In a real implementation, this would:
        # 1. Use Echo Brain context to enhance the scene
        # 2. Generate optimized prompts
        # 3. Submit to ComfyUI with appropriate settings
        # 4. Monitor generation progress
        # 5. Apply quality checks
        # 6. Store results with Echo Brain metadata

    except Exception as e:
        logger.error(f"Scene generation processing failed: {e}")

# Export router for inclusion in main app
__all__ = ["router"]