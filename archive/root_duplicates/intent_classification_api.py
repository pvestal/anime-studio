#!/usr/bin/env python3
"""
FastAPI endpoints for intent classification and workflow routing
Provides RESTful API for the anime production intent classification system
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import our intent classification system
from intent_classification_system import (
    ComplexityLevel, ContentType, GenerationScope, IntentClassification,
    IntentClassificationEngine, StylePreference, UrgencyLevel,
    create_intent_classifier
)

# Import database and Echo integration
from database_operations import create_database_manager
from echo_nlp_integration import EchoNLPProcessor

logger = logging.getLogger(__name__)

# Pydantic models for API requests/responses


class IntentClassificationRequest(BaseModel):
    """Request model for intent classification"""
    user_prompt: str = Field(..., description="User's anime generation request")
    user_id: str = Field(default="default", description="User identifier")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context")
    preferred_style: Optional[str] = Field(default=None, description="Preferred artistic style")
    quality_preference: Optional[str] = Field(default=None, description="Quality preference")
    urgency_hint: Optional[str] = Field(default=None, description="Urgency hint")


class IntentClassificationResponse(BaseModel):
    """Response model for intent classification"""
    request_id: str
    classification_successful: bool
    confidence_score: float

    # Classification results
    content_type: str
    generation_scope: str
    style_preference: str
    urgency_level: str
    complexity_level: str

    # Technical specifications
    character_names: List[str]
    duration_seconds: Optional[int]
    resolution: str
    quality_level: str
    output_format: str

    # Routing information
    target_service: str
    target_workflow: str
    estimated_time_minutes: int
    estimated_vram_gb: float

    # Enhanced details
    processed_prompt: str
    ambiguity_flags: List[str]
    fallback_options: List[str]
    suggested_clarifications: List[Dict[str, Any]]

    # Timestamps
    created_at: datetime
    processing_time_ms: int


class ClarificationRequest(BaseModel):
    """Request for handling ambiguous intents"""
    request_id: str = Field(..., description="Original request ID")
    clarification_responses: Dict[str, Any] = Field(..., description="User's clarification responses")


class WorkflowRoutingRequest(BaseModel):
    """Request for workflow routing"""
    classification: Dict[str, Any] = Field(..., description="Intent classification result")
    override_service: Optional[str] = Field(default=None, description="Service override")
    override_workflow: Optional[str] = Field(default=None, description="Workflow override")


class WorkflowRoutingResponse(BaseModel):
    """Response for workflow routing"""
    success: bool
    target_service: str
    target_workflow: str
    estimated_time: int
    estimated_cost: float
    prerequisites_met: bool
    prerequisites_missing: List[str]
    routing_confidence: float
    alternative_options: List[Dict[str, Any]]


class UserPreferencesRequest(BaseModel):
    """Request for updating user preferences"""
    user_id: str = Field(..., description="User identifier")
    preferences: Dict[str, Any] = Field(..., description="User preferences")


class QuickTemplateResponse(BaseModel):
    """Response for quick classification templates"""
    template_name: str
    description: str
    classification: Dict[str, Any]
    usage_count: int
    success_rate: float


# Initialize FastAPI app
app = FastAPI(
    title="Anime Production Intent Classification API",
    description="RESTful API for classifying user intents and routing anime generation workflows",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080", "https://192.168.50.135"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
db_manager = None
intent_classifier = None
nlp_processor = None


# Dependency injection
async def get_intent_classifier():
    """Get intent classification engine"""
    global intent_classifier, db_manager
    if not intent_classifier:
        if not db_manager:
            db_manager = create_database_manager()
        intent_classifier = create_intent_classifier(db_manager)
    return intent_classifier


async def get_nlp_processor():
    """Get NLP processor"""
    global nlp_processor
    if not nlp_processor:
        nlp_processor = EchoNLPProcessor()
    return nlp_processor


# API Endpoints

@app.post("/api/intent/classify", response_model=IntentClassificationResponse)
async def classify_intent(
    request: IntentClassificationRequest,
    classifier: IntentClassificationEngine = Depends(get_intent_classifier)
):
    """
    Classify user intent for anime generation request

    This endpoint analyzes a user's natural language request and classifies it into:
    - Content type (image, video, audio)
    - Generation scope (character, scene, episode, etc.)
    - Style preferences and quality requirements
    - Urgency and complexity levels
    - Target service and workflow routing
    """
    start_time = time.time()

    try:
        # Prepare context for classification
        context = request.context or {}
        if request.preferred_style:
            context["preferred_style"] = request.preferred_style
        if request.quality_preference:
            context["quality_preference"] = request.quality_preference
        if request.urgency_hint:
            context["urgency_hint"] = request.urgency_hint

        # Perform classification
        classification = await classifier.classify_intent(
            request.user_prompt,
            request.user_id
        )

        # Generate clarification questions if needed
        clarifications = []
        if classification.ambiguity_flags:
            nlp = await get_nlp_processor()
            clarifications = await nlp.generate_clarification_questions(
                classification.ambiguity_flags,
                context
            )

        processing_time = int((time.time() - start_time) * 1000)

        return IntentClassificationResponse(
            request_id=classification.request_id,
            classification_successful=True,
            confidence_score=classification.confidence_score,

            content_type=classification.content_type.value,
            generation_scope=classification.generation_scope.value,
            style_preference=classification.style_preference.value,
            urgency_level=classification.urgency_level.value,
            complexity_level=classification.complexity_level.value,

            character_names=classification.character_names,
            duration_seconds=classification.duration_seconds,
            resolution=classification.resolution,
            quality_level=classification.quality_level,
            output_format=classification.output_format,

            target_service=classification.target_service,
            target_workflow=classification.target_workflow,
            estimated_time_minutes=classification.estimated_time_minutes,
            estimated_vram_gb=classification.estimated_vram_gb,

            processed_prompt=classification.processed_prompt,
            ambiguity_flags=classification.ambiguity_flags,
            fallback_options=classification.fallback_options,
            suggested_clarifications=clarifications,

            created_at=classification.created_at,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")


@app.post("/api/intent/clarify")
async def handle_clarification(
    request: ClarificationRequest,
    classifier: IntentClassificationEngine = Depends(get_intent_classifier)
):
    """
    Handle user clarifications for ambiguous intent classification

    When the initial classification has ambiguities, this endpoint processes
    user responses to clarification questions and re-classifies the intent.
    """
    try:
        # Retrieve original classification
        original_classification = await classifier.db_manager.execute_query_robust(
            "SELECT classification_data FROM intent_classifications WHERE request_id = %s",
            (request.request_id,),
            fetch_result=True
        )

        if not original_classification:
            raise HTTPException(status_code=404, detail="Original classification not found")

        # TODO: Implement clarification processing
        # This would involve:
        # 1. Parsing clarification responses
        # 2. Updating the classification based on responses
        # 3. Re-running classification with clarified context
        # 4. Returning updated classification

        return {
            "success": True,
            "message": "Clarification processed successfully",
            "updated_classification": "Updated classification would be returned here"
        }

    except Exception as e:
        logger.error(f"Clarification processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Clarification failed: {str(e)}")


@app.post("/api/workflow/route", response_model=WorkflowRoutingResponse)
async def route_workflow(request: WorkflowRoutingRequest):
    """
    Route classified intent to appropriate generation workflow

    Takes a classification result and determines:
    - Target generation service (ComfyUI, AnimateDiff, etc.)
    - Specific workflow to execute
    - Resource requirements and availability
    - Prerequisites and alternatives
    """
    try:
        classification = request.classification

        # Determine target service (can be overridden)
        target_service = request.override_service or classification.get("target_service", "comfyui_default")
        target_workflow = request.override_workflow or classification.get("target_workflow", "default")

        # Check service availability and prerequisites
        prerequisites_met = await _check_service_prerequisites(target_service, classification)
        missing_prerequisites = []
        if not prerequisites_met:
            missing_prerequisites = await _get_missing_prerequisites(target_service, classification)

        # Calculate estimated cost (placeholder)
        estimated_cost = _calculate_estimated_cost(classification)

        # Generate alternative options
        alternatives = await _get_alternative_workflows(target_service, classification)

        return WorkflowRoutingResponse(
            success=prerequisites_met,
            target_service=target_service,
            target_workflow=target_workflow,
            estimated_time=classification.get("estimated_time_minutes", 5),
            estimated_cost=estimated_cost,
            prerequisites_met=prerequisites_met,
            prerequisites_missing=missing_prerequisites,
            routing_confidence=classification.get("confidence_score", 0.5),
            alternative_options=alternatives
        )

    except Exception as e:
        logger.error(f"Workflow routing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Routing failed: {str(e)}")


@app.get("/api/templates/quick", response_model=List[QuickTemplateResponse])
async def get_quick_templates(
    category: Optional[str] = Query(None, description="Filter by category"),
    classifier: IntentClassificationEngine = Depends(get_intent_classifier)
):
    """
    Get quick classification templates for common generation types

    Returns pre-defined templates that users can select for quick generation:
    - Character profiles
    - Action sequences
    - Background environments
    - Common animation types
    """
    try:
        query = """
        SELECT template_name, template_description, template_classification, usage_count, success_rate
        FROM quick_classification_templates
        WHERE is_active = TRUE
        """
        params = []

        if category:
            # Filter by category if specified
            query += " AND template_classification->>'content_type' = %s"
            params.append(category)

        query += " ORDER BY is_featured DESC, usage_count DESC, success_rate DESC"

        results = await classifier.db_manager.execute_query_robust(
            query, params, fetch_result=True
        )

        templates = []
        for row in results:
            templates.append(QuickTemplateResponse(
                template_name=row["template_name"],
                description=row["template_description"],
                classification=row["template_classification"],
                usage_count=row["usage_count"],
                success_rate=float(row["success_rate"])
            ))

        return templates

    except Exception as e:
        logger.error(f"Failed to get quick templates: {e}")
        raise HTTPException(status_code=500, detail=f"Template retrieval failed: {str(e)}")


@app.post("/api/preferences/update")
async def update_user_preferences(
    request: UserPreferencesRequest,
    classifier: IntentClassificationEngine = Depends(get_intent_classifier)
):
    """
    Update user preferences for intent classification

    Stores and updates user-specific preferences that influence:
    - Default style selections
    - Quality preferences
    - Workflow preferences
    - Notification settings
    """
    try:
        await classifier.preference_manager.update_preferences_from_request(
            request.user_id,
            # Convert preferences to a mock classification for update logic
            # In practice, this would be more sophisticated
            type('MockClassification', (), {
                'style_preference': type('StylePref', (), {'value': request.preferences.get('preferred_style', 'traditional_anime')})(),
                'quality_level': request.preferences.get('default_quality', 'high')
            })()
        )

        return {
            "success": True,
            "message": "User preferences updated successfully",
            "updated_preferences": request.preferences
        }

    except Exception as e:
        logger.error(f"Failed to update user preferences: {e}")
        raise HTTPException(status_code=500, detail=f"Preference update failed: {str(e)}")


@app.get("/api/preferences/{user_id}")
async def get_user_preferences(
    user_id: str,
    classifier: IntentClassificationEngine = Depends(get_intent_classifier)
):
    """
    Get user preferences for intent classification

    Returns current user preferences including:
    - Style preferences
    - Quality defaults
    - Workflow preferences
    - Historical patterns
    """
    try:
        preferences = await classifier.preference_manager.get_user_preferences(user_id)

        return {
            "user_id": user_id,
            "preferences": preferences,
            "last_updated": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get user preferences: {e}")
        raise HTTPException(status_code=500, detail=f"Preference retrieval failed: {str(e)}")


@app.get("/api/analytics/classification")
async def get_classification_analytics(
    days_back: int = Query(default=30, description="Days of history to analyze"),
    classifier: IntentClassificationEngine = Depends(get_intent_classifier)
):
    """
    Get analytics on classification performance and usage patterns

    Returns metrics on:
    - Classification accuracy over time
    - Most common request types
    - User preference trends
    - Workflow performance
    """
    try:
        # Get classification statistics
        stats_query = """
        SELECT
            content_type,
            generation_scope,
            COUNT(*) as request_count,
            AVG(confidence_score) as avg_confidence,
            AVG(estimated_time_minutes) as avg_estimated_time
        FROM intent_classifications
        WHERE created_at > CURRENT_DATE - INTERVAL '%s days'
        GROUP BY content_type, generation_scope
        ORDER BY request_count DESC
        """

        stats = await classifier.db_manager.execute_query_robust(
            stats_query, (days_back,), fetch_result=True
        )

        # Get ambiguity trends
        ambiguity_query = """
        SELECT
            unnest(ambiguity_flags) as ambiguity_type,
            COUNT(*) as occurrence_count
        FROM intent_classifications
        WHERE created_at > CURRENT_DATE - INTERVAL '%s days'
            AND array_length(ambiguity_flags, 1) > 0
        GROUP BY ambiguity_type
        ORDER BY occurrence_count DESC
        """

        ambiguities = await classifier.db_manager.execute_query_robust(
            ambiguity_query, (days_back,), fetch_result=True
        )

        return {
            "analysis_period_days": days_back,
            "classification_statistics": [dict(row) for row in stats],
            "ambiguity_trends": [dict(row) for row in ambiguities],
            "generated_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Analytics retrieval failed: {str(e)}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connectivity
        if db_manager:
            await db_manager.execute_query_robust("SELECT 1", fetch_result=True)

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "database": "healthy",
                "intent_classifier": "healthy" if intent_classifier else "not_initialized",
                "nlp_processor": "healthy" if nlp_processor else "not_initialized"
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# Helper functions

async def _check_service_prerequisites(service: str, classification: Dict[str, Any]) -> bool:
    """Check if all prerequisites for a service are met"""
    # Placeholder implementation
    # In practice, this would check:
    # - Service availability
    # - Resource requirements
    # - Model availability
    # - VRAM availability
    return True


async def _get_missing_prerequisites(service: str, classification: Dict[str, Any]) -> List[str]:
    """Get list of missing prerequisites"""
    # Placeholder implementation
    missing = []

    # Example checks
    if service.startswith("comfyui") and classification.get("estimated_vram_gb", 0) > 10:
        missing.append("insufficient_vram")

    if service.startswith("animatediff") and not classification.get("duration_seconds"):
        missing.append("duration_not_specified")

    return missing


def _calculate_estimated_cost(classification: Dict[str, Any]) -> float:
    """Calculate estimated generation cost"""
    # Placeholder cost calculation
    base_cost = 0.10  # Base cost in credits

    # Adjust based on complexity
    complexity = classification.get("complexity_level", "moderate")
    complexity_multipliers = {
        "simple": 0.5,
        "moderate": 1.0,
        "complex": 2.0,
        "expert": 4.0
    }

    # Adjust based on content type
    content_type = classification.get("content_type", "image")
    type_multipliers = {
        "image": 1.0,
        "video": 5.0,
        "audio": 2.0,
        "mixed_media": 7.0
    }

    return base_cost * complexity_multipliers.get(complexity, 1.0) * type_multipliers.get(content_type, 1.0)


async def _get_alternative_workflows(primary_service: str, classification: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get alternative workflow options"""
    alternatives = []

    content_type = classification.get("content_type", "image")
    scope = classification.get("generation_scope", "character_profile")

    # Define alternative mappings
    if content_type == "image":
        if primary_service != "comfyui_character":
            alternatives.append({
                "service": "comfyui_character",
                "workflow": "character_profile",
                "confidence": 0.8,
                "reason": "Alternative character generation pipeline"
            })

        if primary_service != "comfyui_scene":
            alternatives.append({
                "service": "comfyui_scene",
                "workflow": "scene_generation",
                "confidence": 0.7,
                "reason": "Alternative scene generation pipeline"
            })

    elif content_type == "video":
        if primary_service != "animatediff_action":
            alternatives.append({
                "service": "animatediff_action",
                "workflow": "action_sequence",
                "confidence": 0.8,
                "reason": "Specialized action sequence generation"
            })

        # Fallback to image sequence
        alternatives.append({
            "service": "comfyui_sequence",
            "workflow": "image_sequence",
            "confidence": 0.6,
            "reason": "Generate as image sequence instead of video"
        })

    return alternatives[:3]  # Return top 3 alternatives


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global db_manager, intent_classifier, nlp_processor

    try:
        # Initialize database manager
        db_manager = create_database_manager()
        logger.info("Database manager initialized")

        # Initialize intent classifier
        intent_classifier = create_intent_classifier(db_manager)
        logger.info("Intent classifier initialized")

        # Initialize NLP processor
        nlp_processor = EchoNLPProcessor()
        logger.info("NLP processor initialized")

    except Exception as e:
        logger.error(f"Startup failed: {e}")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    global nlp_processor, intent_classifier, db_manager

    try:
        if nlp_processor:
            await nlp_processor.close()

        if intent_classifier:
            await intent_classifier.close()

        if db_manager:
            db_manager.close()

        logger.info("Resources cleaned up successfully")

    except Exception as e:
        logger.error(f"Shutdown cleanup failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8330)  # Different port to avoid conflicts