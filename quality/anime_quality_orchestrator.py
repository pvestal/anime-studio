#!/usr/bin/env python3
"""
Anime Quality Orchestrator Service
Main service that coordinates all quality assessment components
Integrates with Tower infrastructure and provides unified API
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import our quality system components
from quality_assessment_agent import AnimeQualityAssessment
from comfyui_quality_integration import ComfyUIWorkflowInjector, QualityWorkflowManager
from auto_correction_system import AutoCorrectionSystem
from executive_quality_reporting import ExecutiveQualityReporting
from jellyfin_integration import JellyfinDeploymentPipeline

logger = logging.getLogger(__name__)

class AnimeQualityOrchestrator:
    """Main orchestrator for the anime quality assessment system"""
    
    def __init__(self):
        # Initialize all components
        self.quality_agent = AnimeQualityAssessment()
        self.workflow_manager = QualityWorkflowManager()
        self.correction_system = AutoCorrectionSystem()
        self.reporting_system = ExecutiveQualityReporting()
        self.jellyfin_pipeline = JellyfinDeploymentPipeline()
        
        # System status
        self.system_status = {
            'status': 'initializing',
            'components': {},
            'started_at': datetime.now().isoformat(),
            'version': '2.0.0'
        }
        
        # Background tasks
        self.background_tasks = []
    
    async def initialize_system(self):
        """Initialize all quality system components"""
        try:
            logger.info("Initializing Anime Quality Assessment System v2.0")
            
            # Initialize correction system database
            await self.correction_system.initialize_correction_system()
            self.system_status['components']['correction_system'] = 'initialized'
            
            # Start correction worker in background
            correction_task = asyncio.create_task(self.correction_system.start_correction_worker())
            self.background_tasks.append(correction_task)
            
            # Start Jellyfin processing pipeline
            jellyfin_task = asyncio.create_task(self._start_jellyfin_processor())
            self.background_tasks.append(jellyfin_task)
            
            # Mark system as ready
            self.system_status['status'] = 'ready'
            self.system_status['components']['quality_agent'] = 'ready'
            self.system_status['components']['workflow_manager'] = 'ready'
            self.system_status['components']['reporting_system'] = 'ready'
            self.system_status['components']['jellyfin_pipeline'] = 'ready'
            
            logger.info("Anime Quality Assessment System initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize system: {e}")
            self.system_status['status'] = 'error'
            self.system_status['error'] = str(e)
            raise
    
    async def _start_jellyfin_processor(self):
        """Background task for processing Jellyfin queue"""
        while True:
            try:
                await asyncio.sleep(300)  # Process every 5 minutes
                await self.jellyfin_pipeline.process_quality_queue()
            except Exception as e:
                logger.error(f"Jellyfin processor error: {e}")
                await asyncio.sleep(600)  # Wait 10 minutes on error
    
    async def process_video_complete_pipeline(self, video_path: str) -> Dict:
        """Complete quality assessment pipeline for a video"""
        try:
            logger.info(f"Starting complete quality pipeline for: {video_path}")
            
            pipeline_result = {
                'video_path': video_path,
                'pipeline_stages': {},
                'started_at': datetime.now().isoformat(),
                'status': 'processing'
            }
            
            # Stage 1: Quality Assessment
            logger.info("Stage 1: Quality Assessment")
            assessment_result = await self.quality_agent.analyze_video_quality(video_path)
            pipeline_result['pipeline_stages']['quality_assessment'] = assessment_result.dict()
            
            # Stage 2: Handle Failed Assessment (if needed)
            if not assessment_result.passes_standards:
                logger.info("Stage 2: Auto-Correction Processing")
                correction_task_id = await self.correction_system.process_failed_assessment(
                    assessment_result.dict()
                )
                
                pipeline_result['pipeline_stages']['auto_correction'] = {
                    'task_id': correction_task_id,
                    'status': 'queued' if correction_task_id else 'no_corrections_available'
                }
                
                pipeline_result['status'] = 'correction_pending'
                pipeline_result['completed_at'] = datetime.now().isoformat()
                
                return pipeline_result
            
            # Stage 3: Jellyfin Integration (for passed videos)
            logger.info("Stage 3: Jellyfin Integration")
            jellyfin_result = await self.jellyfin_pipeline.jellyfin.process_approved_video(
                assessment_result.dict()
            )
            
            pipeline_result['pipeline_stages']['jellyfin_integration'] = jellyfin_result
            
            # Stage 4: Final Status
            if jellyfin_result['status'] == 'success':
                pipeline_result['status'] = 'completed_successfully'
                pipeline_result['jellyfin_path'] = jellyfin_result.get('jellyfin_path')
            else:
                pipeline_result['status'] = 'jellyfin_failed'
                pipeline_result['error'] = jellyfin_result.get('error', 'Unknown Jellyfin error')
            
            pipeline_result['completed_at'] = datetime.now().isoformat()
            
            logger.info(f"Pipeline completed for {video_path}: {pipeline_result['status']}")
            return pipeline_result
            
        except Exception as e:
            logger.error(f"Pipeline failed for {video_path}: {e}")
            return {
                'video_path': video_path,
                'status': 'pipeline_error',
                'error': str(e),
                'failed_at': datetime.now().isoformat()
            }
    
    async def get_system_status(self) -> Dict:
        """Get comprehensive system status"""
        try:
            # Get component statuses
            correction_status = self.correction_system.get_system_status()
            
            # Aggregate system status
            status = {
                'system': self.system_status,
                'components': {
                    'quality_agent': {
                        'status': 'ready',
                        'active_connections': len(self.quality_agent.active_connections)
                    },
                    'correction_system': correction_status,
                    'workflow_manager': self.workflow_manager.get_quality_enforcement_status(),
                    'jellyfin_pipeline': {
                        'stats': self.jellyfin_pipeline.pipeline_stats
                    }
                },
                'quality_standards': {
                    'motion_smoothness_min': 7.0,
                    'duration_min_minutes': 10.0,
                    'resolution_4k_required': True,
                    'auto_rejection_enabled': True
                }
            }
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {
                'system': {'status': 'error', 'error': str(e)},
                'components': {},
                'timestamp': datetime.now().isoformat()
            }

# FastAPI Application
app = FastAPI(
    title="Anime Quality Assessment System",
    description="Comprehensive anime video quality assessment with auto-correction",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "https://localhost", "http://localhost:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize orchestrator
orchestrator = AnimeQualityOrchestrator()

@app.on_event("startup")
async def startup_event():
    """Initialize system on startup"""
    await orchestrator.initialize_system()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    for task in orchestrator.background_tasks:
        task.cancel()

# API Routes

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Anime Quality Assessment System",
        "version": "2.0.0",
        "status": "ready",
        "documentation": "/docs"
    }

@app.get("/system/status")
async def get_system_status():
    """Get comprehensive system status"""
    return await orchestrator.get_system_status()

@app.post("/assess/video")
async def assess_video_quality(video_path: str, background_tasks: BackgroundTasks):
    """Assess video quality with complete pipeline"""
    if not video_path:
        raise HTTPException(status_code=400, detail="Video path is required")
    
    # Start pipeline in background for long-running process
    background_tasks.add_task(
        orchestrator.process_video_complete_pipeline,
        video_path
    )
    
    return {
        "status": "pipeline_started",
        "video_path": video_path,
        "message": "Quality assessment pipeline started. Check /system/status for progress."
    }

@app.post("/assess/video/sync")
async def assess_video_quality_sync(video_path: str):
    """Assess video quality synchronously (for testing/small files)"""
    if not video_path:
        raise HTTPException(status_code=400, detail="Video path is required")
    
    return await orchestrator.process_video_complete_pipeline(video_path)

@app.get("/quality/standards")
async def get_quality_standards():
    """Get current quality standards"""
    return {
        "motion_smoothness": {
            "minimum": 7.0,
            "scale": "1-10",
            "description": "No slideshow effects, smooth animation"
        },
        "duration": {
            "minimum_minutes": 10.0,
            "description": "Minimum episode length requirement"
        },
        "resolution": {
            "minimum": "4K (3840x2160)",
            "description": "Ultra HD resolution requirement"
        },
        "frame_rate": {
            "range": "24-60 FPS",
            "description": "Consistent frame rate within acceptable range"
        },
        "overall": {
            "pass_threshold": 70.0,
            "auto_rejection": True,
            "jellyfin_integration": True
        }
    }

@app.get("/reports/daily")
async def generate_daily_report():
    """Generate daily quality report"""
    try:
        report = await orchestrator.reporting_system.generate_daily_quality_report()
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

@app.get("/reports/weekly")
async def generate_weekly_report():
    """Generate weekly executive summary"""
    try:
        report = await orchestrator.reporting_system.generate_weekly_executive_summary()
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

@app.get("/queue/correction")
async def get_correction_queue():
    """Get current correction queue status"""
    return orchestrator.correction_system.get_system_status()

@app.get("/jellyfin/stats")
async def get_jellyfin_stats():
    """Get Jellyfin integration statistics"""
    return {
        "pipeline_stats": orchestrator.jellyfin_pipeline.pipeline_stats,
        "media_directory": str(orchestrator.jellyfin_pipeline.jellyfin.anime_dir)
    }

@app.post("/workflow/create")
async def create_quality_workflow(base_workflow_path: str = None):
    """Create quality-enhanced ComfyUI workflow"""
    if not base_workflow_path:
        # Create default workflow
        base_workflow = {"nodes": {}, "version": "1.0"}
    else:
        try:
            with open(base_workflow_path, 'r') as f:
                base_workflow = json.load(f)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to load workflow: {str(e)}")
    
    try:
        result = await orchestrator.workflow_manager.create_anime_quality_workflow(base_workflow_path or "default")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    system_status = await orchestrator.get_system_status()
    
    if system_status['system']['status'] == 'ready':
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    else:
        raise HTTPException(
            status_code=503,
            detail=f"System not ready: {system_status['system'].get('error', 'Unknown error')}"
        )

# Background task for system maintenance
async def system_maintenance():
    """Periodic system maintenance"""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            
            # Cleanup old failed videos
            await orchestrator.jellyfin_pipeline.jellyfin.cleanup_failed_videos()
            
            # Log system statistics
            status = await orchestrator.get_system_status()
            logger.info(f"System status: {status['system']['status']}")
            
        except Exception as e:
            logger.error(f"Maintenance task error: {e}")

# Main execution
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Start maintenance task
    loop = asyncio.get_event_loop()
    loop.create_task(system_maintenance())
    
    # Run the FastAPI server
    uvicorn.run(
        "anime_quality_orchestrator:app",
        host="0.0.0.0",
        port=8308,
        reload=False,
        log_level="info"
    )