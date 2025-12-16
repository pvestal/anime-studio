#!/usr/bin/env python3
"""
CLIP-based Character Consistency API
Production-grade API endpoints for CLIP embeddings, quality gates, and character analysis
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Import our CLIP consistency modules
from clip_consistency import CLIPCharacterConsistency, analyze_character_consistency_clip
from quality_gates import QualityGateValidator, validate_anime_asset, quick_character_check

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CLIP Character Consistency API",
    description="Production-grade CLIP-based character consistency and quality validation",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize CLIP components
clip_checker = None  # Lazy initialization
quality_validator = QualityGateValidator()

def get_clip_checker(model_name: str = "ViT-B/32") -> CLIPCharacterConsistency:
    """Get or create CLIP checker instance"""
    global clip_checker
    if clip_checker is None or clip_checker.clip_model_name != model_name:
        clip_checker = CLIPCharacterConsistency(clip_model=model_name)
    return clip_checker

# Pydantic models for CLIP API

class CharacterConsistencyRequest(BaseModel):
    image_path: str = Field(..., description="Path to image file for analysis")
    character_name: str = Field(..., description="Character name to check consistency against")
    clip_model: Optional[str] = Field("ViT-B/32", description="CLIP model to use")
    consistency_threshold: Optional[float] = Field(0.8, description="Minimum consistency threshold")
    auto_add_reference: Optional[bool] = Field(True, description="Automatically add as reference if above threshold")

class QualityGatesRequest(BaseModel):
    image_path: str = Field(..., description="Path to image file for validation")
    character_name: str = Field(..., description="Character name for consistency check")
    config_name: Optional[str] = Field("default_production", description="Quality gate configuration to use")

class AddReferenceRequest(BaseModel):
    image_path: str = Field(..., description="Path to reference image")
    character_name: str = Field(..., description="Character name")
    reference_type: Optional[str] = Field("manual", description="Reference type: manual, auto, canonical, style_guide")
    weight: Optional[float] = Field(1.0, description="Reference weight (0.0-2.0)")
    created_by: Optional[str] = Field(None, description="User who added this reference")

class CLIPModelRequest(BaseModel):
    model_name: str = Field(..., description="CLIP model name (ViT-B/32, ViT-B/16, ViT-L/14)")

class CharacterStatsRequest(BaseModel):
    character_name: str = Field(..., description="Character name to get statistics for")

class ConfigUpdateRequest(BaseModel):
    config_name: str = Field(..., description="Configuration name")
    updates: Dict[str, Any] = Field(..., description="Configuration updates")

# Health and Info Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test CLIP model loading
        checker = get_clip_checker()

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "clip_model": checker.clip_model_name,
            "embedding_dimension": checker.embedding_dim,
            "device": checker.device
        }
    except Exception as e:
        return JSONResponse(
            {"status": "unhealthy", "error": str(e)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

@app.get("/api/info")
async def get_system_info():
    """Get system information and available models"""
    try:
        checker = get_clip_checker()

        return {
            "system_info": {
                "clip_model": checker.clip_model_name,
                "embedding_dimension": checker.embedding_dim,
                "device": checker.device,
                "database_path": checker.db_path
            },
            "available_models": [
                "ViT-B/32",
                "ViT-B/16",
                "ViT-L/14"
            ],
            "quality_gate_configs": [
                "default_production",
                "hero_character_strict"
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# CLIP Consistency Endpoints

@app.post("/api/clip/analyze-consistency")
async def analyze_consistency(request: CharacterConsistencyRequest):
    """Analyze character consistency using CLIP embeddings"""
    try:
        logger.info(f"🎭 Analyzing consistency for {request.character_name}: {request.image_path}")

        # Check if file exists
        if not os.path.exists(request.image_path):
            raise HTTPException(
                status_code=404,
                detail=f"Image file not found: {request.image_path}"
            )

        # Run CLIP analysis
        result = await analyze_character_consistency_clip(
            image_path=request.image_path,
            character_name=request.character_name,
            clip_model=request.clip_model,
            consistency_threshold=request.consistency_threshold,
            auto_add_reference=request.auto_add_reference
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "success": True,
            "result": result,
            "message": f"Consistency analysis completed for {request.character_name}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Consistency analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clip/quick-check")
async def quick_consistency_check(request: CharacterConsistencyRequest):
    """Quick consistency check returning only pass/fail status"""
    try:
        passed = await quick_character_check(
            image_path=request.image_path,
            character_name=request.character_name,
            threshold=request.consistency_threshold
        )

        return {
            "character_name": request.character_name,
            "image_path": request.image_path,
            "passed": passed,
            "threshold": request.consistency_threshold,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clip/add-reference")
async def add_character_reference(request: AddReferenceRequest):
    """Add image as character reference"""
    try:
        logger.info(f"📚 Adding {request.reference_type} reference for {request.character_name}")

        # Check if file exists
        if not os.path.exists(request.image_path):
            raise HTTPException(
                status_code=404,
                detail=f"Image file not found: {request.image_path}"
            )

        # Get CLIP checker
        checker = get_clip_checker()

        # Add reference
        success = checker.add_character_reference(
            image_path=request.image_path,
            character_name=request.character_name,
            reference_type=request.reference_type,
            weight=request.weight,
            created_by=request.created_by
        )

        if success:
            return {
                "success": True,
                "message": f"Added {request.reference_type} reference for {request.character_name}",
                "character_name": request.character_name,
                "reference_type": request.reference_type,
                "weight": request.weight
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add reference")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add reference failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/clip/character-stats/{character_name}")
async def get_character_statistics(character_name: str):
    """Get comprehensive statistics for a character"""
    try:
        checker = get_clip_checker()
        stats = checker.get_character_stats(character_name)

        if "error" in stats:
            raise HTTPException(status_code=500, detail=stats["error"])

        return {
            "success": True,
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Quality Gates Endpoints

@app.post("/api/quality/validate-asset")
async def validate_asset(request: QualityGatesRequest):
    """Run complete quality gate pipeline on asset"""
    try:
        logger.info(f"🚦 Running quality gates for {request.character_name}: {request.image_path}")

        # Check if file exists
        if not os.path.exists(request.image_path):
            raise HTTPException(
                status_code=404,
                detail=f"Image file not found: {request.image_path}"
            )

        # Run quality gates
        result = await validate_anime_asset(
            image_path=request.image_path,
            character_name=request.character_name,
            config_name=request.config_name
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "success": True,
            "validation_result": result,
            "message": f"Quality validation completed with status: {result.get('overall_status', 'unknown')}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quality validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/quality/configs")
async def get_quality_configs():
    """Get available quality gate configurations"""
    try:
        # Get default configs
        default_config = quality_validator.get_quality_gate_config("default_production")
        hero_config = quality_validator.get_quality_gate_config("hero_character_strict")

        return {
            "configs": {
                "default_production": default_config,
                "hero_character_strict": hero_config
            },
            "available_clip_models": ["ViT-B/32", "ViT-B/16", "ViT-L/14"],
            "supported_formats": ["png", "jpg", "jpeg", "webp"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/quality/config/{config_name}")
async def update_quality_config(config_name: str, request: ConfigUpdateRequest):
    """Update quality gate configuration (placeholder for future implementation)"""
    # This would require implementing config update functionality in quality_gates.py
    return {
        "message": "Configuration update endpoint not yet implemented",
        "config_name": config_name,
        "updates": request.updates
    }

# Batch Operations

@app.post("/api/batch/analyze-directory")
async def analyze_directory_batch(
    directory_path: str = Form(...),
    character_name: str = Form(...),
    file_pattern: Optional[str] = Form("*.png"),
    config_name: Optional[str] = Form("default_production")
):
    """Batch analyze all images in a directory"""
    try:
        directory = Path(directory_path)
        if not directory.exists() or not directory.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"Directory not found: {directory_path}"
            )

        # Find matching files
        image_files = list(directory.glob(file_pattern))

        if not image_files:
            return {
                "message": f"No files matching pattern {file_pattern} found in {directory_path}",
                "files_processed": 0,
                "results": []
            }

        # Process files
        results = []
        for image_file in image_files[:20]:  # Limit to 20 files for safety
            try:
                result = await validate_anime_asset(
                    image_path=str(image_file),
                    character_name=character_name,
                    config_name=config_name
                )
                results.append({
                    "file": str(image_file.name),
                    "result": result
                })
            except Exception as e:
                results.append({
                    "file": str(image_file.name),
                    "error": str(e)
                })

        # Summary statistics
        passed_count = sum(1 for r in results if r.get("result", {}).get("overall_passed", False))

        return {
            "directory": directory_path,
            "character_name": character_name,
            "files_found": len(image_files),
            "files_processed": len(results),
            "passed_count": passed_count,
            "failed_count": len(results) - passed_count,
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Database and Management Endpoints

@app.post("/api/database/initialize")
async def initialize_database():
    """Initialize or recreate the database schema"""
    try:
        checker = get_clip_checker()
        checker._init_database()

        return {
            "success": True,
            "message": "Database schema initialized successfully",
            "database_path": checker.db_path
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/database/stats")
async def get_database_stats():
    """Get database statistics"""
    try:
        checker = get_clip_checker()

        with checker._get_db_connection() as conn:
            cursor = conn.cursor()

            # Get table counts
            stats = {}
            tables = [
                "asset_metadata",
                "clip_embeddings",
                "character_references",
                "quality_gate_results",
                "character_consistency_history"
            ]

            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    stats[table] = count
                except:
                    stats[table] = "N/A"

            # Get character counts
            cursor.execute("SELECT COUNT(DISTINCT character_name) FROM character_references WHERE is_active = 1")
            active_characters = cursor.fetchone()[0]

            return {
                "table_counts": stats,
                "active_characters": active_characters,
                "database_path": checker.db_path,
                "timestamp": datetime.now().isoformat()
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/characters")
async def list_characters():
    """List all characters with reference counts"""
    try:
        checker = get_clip_checker()

        with checker._get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    character_name,
                    COUNT(*) as reference_count,
                    MAX(created_at) as last_updated
                FROM character_references
                WHERE is_active = 1
                GROUP BY character_name
                ORDER BY last_updated DESC
            """)

            characters = []
            for row in cursor.fetchall():
                characters.append({
                    "name": row[0],
                    "reference_count": row[1],
                    "last_updated": row[2]
                })

            return {
                "characters": characters,
                "total_characters": len(characters),
                "timestamp": datetime.now().isoformat()
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# File Upload Endpoint

@app.post("/api/upload-and-analyze")
async def upload_and_analyze(
    file: UploadFile = File(...),
    character_name: str = Form(...),
    config_name: Optional[str] = Form("default_production")
):
    """Upload image file and run complete analysis"""
    try:
        # Save uploaded file
        upload_dir = Path("/tmp/claude/clip_uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"

        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Run analysis
        result = await validate_anime_asset(
            image_path=str(file_path),
            character_name=character_name,
            config_name=config_name
        )

        return {
            "success": True,
            "uploaded_file": str(file_path),
            "character_name": character_name,
            "analysis_result": result
        }

    except Exception as e:
        # Clean up file on error
        if 'file_path' in locals():
            try:
                file_path.unlink()
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))

# Error handlers

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

# Development and Testing

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CLIP Character Consistency API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8329, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--log-level", default="info", help="Log level")

    args = parser.parse_args()

    uvicorn.run(
        "clip_consistency_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level
    )