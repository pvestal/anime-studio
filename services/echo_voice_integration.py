#!/usr/bin/env python3
"""
Echo Brain Integration for Voice AI Assessment
Provides intelligent voice quality analysis and character consistency validation
Integrates with Echo Brain system for advanced AI orchestration
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import asyncpg
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class VoiceQualityMetrics(BaseModel):
    """Voice quality assessment metrics"""
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Overall quality score")
    character_consistency: float = Field(..., ge=0.0, le=1.0, description="Character voice consistency")
    emotion_accuracy: float = Field(..., ge=0.0, le=1.0, description="Emotion expression accuracy")
    audio_clarity: float = Field(..., ge=0.0, le=1.0, description="Audio clarity and quality")
    lip_sync_compatibility: float = Field(..., ge=0.0, le=1.0, description="Lip sync compatibility")
    naturalness: float = Field(..., ge=0.0, le=1.0, description="Voice naturalness")

class VoiceAssessmentRequest(BaseModel):
    """Request for voice quality assessment"""
    job_id: str = Field(..., description="Voice generation job ID")
    audio_file_path: str = Field(..., description="Path to generated audio file")
    character_name: str = Field(..., description="Character name")
    original_text: str = Field(..., description="Original text that was spoken")
    emotion: str = Field(default="neutral", description="Intended emotion")
    voice_settings: Dict = Field(default_factory=dict, description="Voice generation settings")
    compare_with_profile: bool = Field(default=True, description="Compare with character profile")

class EchoBrainVoiceIntegration:
    """Integration with Echo Brain for advanced voice analysis"""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        echo_brain_url: str = "http://localhost:8309"
    ):
        self.db_pool = db_pool
        self.echo_brain_url = echo_brain_url
        self.assessment_cache = {}

    async def assess_voice_quality(self, request: VoiceAssessmentRequest) -> Dict:
        """Comprehensive voice quality assessment using Echo Brain"""
        try:
            logger.info(f"Assessing voice quality for job: {request.job_id}")

            # Step 1: Basic audio analysis
            audio_metrics = await self.analyze_audio_properties(request.audio_file_path)

            # Step 2: Character consistency check
            consistency_metrics = None
            if request.compare_with_profile:
                consistency_metrics = await self.check_character_consistency(
                    request.character_name,
                    request.audio_file_path,
                    request.voice_settings
                )

            # Step 3: Echo Brain intelligent assessment
            echo_assessment = await self.query_echo_brain_assessment(
                request, audio_metrics, consistency_metrics
            )

            # Step 4: Compile final assessment
            final_assessment = await self.compile_assessment(
                request, audio_metrics, consistency_metrics, echo_assessment
            )

            # Step 5: Store assessment in database
            await self.store_assessment(request.job_id, final_assessment)

            return {
                "success": True,
                "job_id": request.job_id,
                "assessment": final_assessment,
                "recommendations": final_assessment.get("recommendations", []),
                "approved": final_assessment.get("overall_score", 0.0) > 0.7
            }

        except Exception as e:
            logger.error(f"Voice quality assessment error: {e}")
            return {
                "success": False,
                "error": str(e),
                "job_id": request.job_id
            }

    async def analyze_audio_properties(self, audio_file_path: str) -> Dict:
        """Analyze basic audio properties (duration, quality, etc.)"""
        try:
            # Basic audio analysis
            if not os.path.exists(audio_file_path):
                raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

            file_size = os.path.getsize(audio_file_path)

            # Mock audio analysis (replace with actual audio processing)
            # In production, use librosa, scipy, or similar for audio analysis

            return {
                "file_size_bytes": file_size,
                "estimated_duration": file_size / 16000,  # Rough estimate
                "audio_quality_score": 0.85,  # Mock score
                "noise_level": 0.02,
                "dynamic_range": 0.75,
                "spectral_balance": 0.8
            }

        except Exception as e:
            logger.error(f"Audio analysis error: {e}")
            return {
                "file_size_bytes": 0,
                "estimated_duration": 0,
                "audio_quality_score": 0.0,
                "error": str(e)
            }

    async def check_character_consistency(
        self,
        character_name: str,
        audio_file_path: str,
        voice_settings: Dict
    ) -> Dict:
        """Check consistency with character's established voice profile"""
        try:
            async with self.db_pool.acquire() as conn:
                # Get character's voice profile
                profile = await conn.fetchrow(
                    "SELECT * FROM voice_profiles WHERE character_name = $1",
                    character_name
                )

                if not profile:
                    return {
                        "consistency_score": 0.5,  # Neutral score for new characters
                        "profile_exists": False,
                        "message": "No established voice profile for character"
                    }

                # Get recent voice generations for this character
                recent_voices = await conn.fetch("""
                    SELECT audio_file_path, voice_settings FROM voice_generation_jobs
                    WHERE character_name = $1 AND status = 'completed' AND audio_file_path IS NOT NULL
                    ORDER BY created_at DESC LIMIT 5
                """, character_name)

                profile_settings = profile["voice_settings"] or {}
                consistency_scores = []

                # Compare voice settings
                settings_similarity = self.calculate_settings_similarity(
                    voice_settings, profile_settings
                )

                # Mock voice comparison (replace with actual voice fingerprinting)
                voice_similarity = 0.85  # Mock similarity score

                consistency_score = (settings_similarity + voice_similarity) / 2

                return {
                    "consistency_score": consistency_score,
                    "profile_exists": True,
                    "settings_similarity": settings_similarity,
                    "voice_similarity": voice_similarity,
                    "reference_count": len(recent_voices),
                    "profile_usage_count": profile["usage_count"]
                }

        except Exception as e:
            logger.error(f"Character consistency check error: {e}")
            return {
                "consistency_score": 0.0,
                "error": str(e)
            }

    def calculate_settings_similarity(self, settings1: Dict, settings2: Dict) -> float:
        """Calculate similarity between voice settings"""
        try:
            if not settings1 or not settings2:
                return 0.5  # Neutral score if missing settings

            # Key voice parameters
            params = ["stability", "similarity_boost", "style", "use_speaker_boost"]
            similarities = []

            for param in params:
                val1 = settings1.get(param, 0.5)
                val2 = settings2.get(param, 0.5)

                if isinstance(val1, bool) and isinstance(val2, bool):
                    similarity = 1.0 if val1 == val2 else 0.0
                else:
                    # Calculate numerical similarity (1.0 - normalized difference)
                    diff = abs(float(val1) - float(val2))
                    similarity = max(0.0, 1.0 - diff)

                similarities.append(similarity)

            return sum(similarities) / len(similarities) if similarities else 0.5

        except Exception as e:
            logger.error(f"Settings similarity calculation error: {e}")
            return 0.0

    async def query_echo_brain_assessment(
        self,
        request: VoiceAssessmentRequest,
        audio_metrics: Dict,
        consistency_metrics: Optional[Dict]
    ) -> Dict:
        """Query Echo Brain for intelligent voice assessment"""
        try:
            # Prepare data for Echo Brain analysis
            assessment_prompt = self.create_assessment_prompt(
                request, audio_metrics, consistency_metrics
            )

            query_data = {
                "query": assessment_prompt,
                "conversation_id": f"voice_assessment_{request.job_id}",
                "context": {
                    "character_name": request.character_name,
                    "emotion": request.emotion,
                    "audio_file_path": request.audio_file_path,
                    "audio_metrics": audio_metrics,
                    "consistency_metrics": consistency_metrics
                }
            }

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.echo_brain_url}/api/echo/query",
                    json=query_data
                )

                if response.status_code == 200:
                    result = response.json()
                    return self.parse_echo_brain_response(result.get("response", ""))
                else:
                    logger.warning(f"Echo Brain query failed: {response.status_code}")
                    return self.generate_fallback_assessment(audio_metrics, consistency_metrics)

        except Exception as e:
            logger.error(f"Echo Brain query error: {e}")
            return self.generate_fallback_assessment(audio_metrics, consistency_metrics)

    def create_assessment_prompt(
        self,
        request: VoiceAssessmentRequest,
        audio_metrics: Dict,
        consistency_metrics: Optional[Dict]
    ) -> str:
        """Create detailed prompt for Echo Brain voice assessment"""

        prompt = f"""
        Analyze the voice generation quality for character '{request.character_name}':

        Text spoken: "{request.original_text}"
        Intended emotion: {request.emotion}
        Voice settings: {json.dumps(request.voice_settings, indent=2)}

        Audio metrics:
        - File size: {audio_metrics.get('file_size_bytes', 0)} bytes
        - Estimated duration: {audio_metrics.get('estimated_duration', 0):.2f} seconds
        - Quality score: {audio_metrics.get('audio_quality_score', 0):.2f}
        - Noise level: {audio_metrics.get('noise_level', 0):.3f}

        Character consistency:"""

        if consistency_metrics:
            prompt += f"""
        - Profile exists: {consistency_metrics.get('profile_exists', False)}
        - Consistency score: {consistency_metrics.get('consistency_score', 0):.2f}
        - Settings similarity: {consistency_metrics.get('settings_similarity', 0):.2f}
        - Voice similarity: {consistency_metrics.get('voice_similarity', 0):.2f}
        """
        else:
            prompt += "\n        - No consistency check performed"

        prompt += """
        Please assess:
        1. Overall voice quality (0.0-1.0)
        2. Character consistency (0.0-1.0)
        3. Emotion accuracy (0.0-1.0)
        4. Audio clarity (0.0-1.0)
        5. Naturalness (0.0-1.0)

        Provide specific recommendations for improvement and whether this voice generation
        should be approved for production use.

        Format your response as JSON with the following structure:
        {
            "overall_score": <float>,
            "character_consistency": <float>,
            "emotion_accuracy": <float>,
            "audio_clarity": <float>,
            "naturalness": <float>,
            "recommendations": ["<recommendation1>", "<recommendation2>"],
            "approved": <boolean>,
            "reasoning": "<detailed_reasoning>"
        }
        """

        return prompt

    def parse_echo_brain_response(self, response_text: str) -> Dict:
        """Parse Echo Brain response and extract assessment data"""
        try:
            # Try to extract JSON from response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')

            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
                assessment = json.loads(json_str)

                # Validate required fields
                required_fields = [
                    "overall_score", "character_consistency", "emotion_accuracy",
                    "audio_clarity", "naturalness"
                ]

                for field in required_fields:
                    if field not in assessment:
                        assessment[field] = 0.5  # Default neutral score

                return assessment

            else:
                # Fallback parsing for unstructured response
                return self.extract_scores_from_text(response_text)

        except Exception as e:
            logger.error(f"Echo Brain response parsing error: {e}")
            return {
                "overall_score": 0.5,
                "character_consistency": 0.5,
                "emotion_accuracy": 0.5,
                "audio_clarity": 0.5,
                "naturalness": 0.5,
                "recommendations": ["Unable to parse Echo Brain assessment"],
                "approved": False,
                "reasoning": "Assessment parsing failed"
            }

    def extract_scores_from_text(self, text: str) -> Dict:
        """Extract scores from unstructured text response"""
        # Simple text parsing for scores (improve as needed)
        default_assessment = {
            "overall_score": 0.6,
            "character_consistency": 0.6,
            "emotion_accuracy": 0.6,
            "audio_clarity": 0.6,
            "naturalness": 0.6,
            "recommendations": ["Text-based assessment performed"],
            "approved": True,
            "reasoning": "Fallback text parsing assessment"
        }

        # Look for score indicators in text
        if "excellent" in text.lower() or "outstanding" in text.lower():
            for key in default_assessment:
                if isinstance(default_assessment[key], float):
                    default_assessment[key] = 0.9

        elif "poor" in text.lower() or "bad" in text.lower():
            for key in default_assessment:
                if isinstance(default_assessment[key], float):
                    default_assessment[key] = 0.3

        return default_assessment

    def generate_fallback_assessment(
        self,
        audio_metrics: Dict,
        consistency_metrics: Optional[Dict]
    ) -> Dict:
        """Generate fallback assessment when Echo Brain is unavailable"""

        # Base assessment on available metrics
        audio_quality = audio_metrics.get("audio_quality_score", 0.5)
        consistency_score = consistency_metrics.get("consistency_score", 0.5) if consistency_metrics else 0.5

        overall_score = (audio_quality + consistency_score) / 2

        return {
            "overall_score": overall_score,
            "character_consistency": consistency_score,
            "emotion_accuracy": 0.7,  # Conservative estimate
            "audio_clarity": audio_quality,
            "naturalness": 0.6,
            "recommendations": [
                "Fallback assessment performed - Echo Brain unavailable",
                "Consider manual review for production use"
            ],
            "approved": overall_score > 0.6,
            "reasoning": "Automatic fallback assessment based on basic metrics"
        }

    async def compile_assessment(
        self,
        request: VoiceAssessmentRequest,
        audio_metrics: Dict,
        consistency_metrics: Optional[Dict],
        echo_assessment: Dict
    ) -> Dict:
        """Compile comprehensive assessment from all sources"""

        try:
            # Weight different assessment sources
            echo_weight = 0.7
            metrics_weight = 0.3

            # Calculate weighted scores
            overall_score = (
                echo_assessment.get("overall_score", 0.5) * echo_weight +
                audio_metrics.get("audio_quality_score", 0.5) * metrics_weight
            )

            character_consistency = echo_assessment.get("character_consistency", 0.5)
            if consistency_metrics:
                character_consistency = (
                    character_consistency * 0.6 +
                    consistency_metrics.get("consistency_score", 0.5) * 0.4
                )

            # Generate comprehensive recommendations
            recommendations = echo_assessment.get("recommendations", [])

            # Add metric-based recommendations
            if audio_metrics.get("noise_level", 0) > 0.1:
                recommendations.append("Consider noise reduction in audio processing")

            if consistency_metrics and consistency_metrics.get("consistency_score", 1.0) < 0.7:
                recommendations.append("Voice differs from character profile - review settings")

            if overall_score < 0.6:
                recommendations.append("Overall quality below threshold - consider regeneration")

            final_assessment = {
                "overall_score": min(1.0, max(0.0, overall_score)),
                "character_consistency": min(1.0, max(0.0, character_consistency)),
                "emotion_accuracy": echo_assessment.get("emotion_accuracy", 0.5),
                "audio_clarity": echo_assessment.get("audio_clarity", audio_metrics.get("audio_quality_score", 0.5)),
                "lip_sync_compatibility": 0.8,  # Mock score for lip sync compatibility
                "naturalness": echo_assessment.get("naturalness", 0.5),
                "recommendations": recommendations,
                "approved": overall_score > 0.7 and character_consistency > 0.6,
                "reasoning": echo_assessment.get("reasoning", "Comprehensive multi-source assessment"),
                "audio_metrics": audio_metrics,
                "consistency_metrics": consistency_metrics,
                "echo_brain_assessment": echo_assessment,
                "assessment_timestamp": datetime.now().isoformat()
            }

            return final_assessment

        except Exception as e:
            logger.error(f"Assessment compilation error: {e}")
            return {
                "overall_score": 0.0,
                "error": str(e),
                "approved": False
            }

    async def store_assessment(self, job_id: str, assessment: Dict):
        """Store voice quality assessment in database"""
        try:
            async with self.db_pool.acquire() as conn:
                # Get voice job details
                voice_job = await conn.fetchrow(
                    "SELECT character_name, audio_file_path FROM voice_generation_jobs WHERE job_id = $1",
                    job_id
                )

                if voice_job:
                    await conn.execute("""
                        INSERT INTO voice_quality_assessments (
                            voice_job_id, character_name, audio_file_path,
                            echo_brain_response, quality_score, consistency_score,
                            emotion_accuracy, recommendations, approved
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    job_id, voice_job["character_name"], voice_job["audio_file_path"],
                    json.dumps(assessment), assessment.get("overall_score"),
                    assessment.get("character_consistency"), assessment.get("emotion_accuracy"),
                    assessment.get("recommendations", []), assessment.get("approved", False)
                    )

                    logger.info(f"Stored voice quality assessment for job: {job_id}")

        except Exception as e:
            logger.error(f"Error storing assessment: {e}")

    async def get_character_voice_analytics(self, character_name: str) -> Dict:
        """Get comprehensive voice analytics for a character"""
        try:
            async with self.db_pool.acquire() as conn:
                # Get character profile
                profile = await conn.fetchrow(
                    "SELECT * FROM voice_profiles WHERE character_name = $1",
                    character_name
                )

                # Get voice generation statistics
                voice_stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_generations,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                        AVG(generation_time_ms) as avg_generation_time
                    FROM voice_generation_jobs WHERE character_name = $1
                """, character_name)

                # Get quality assessments
                quality_stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_assessments,
                        AVG(quality_score) as avg_quality_score,
                        AVG(consistency_score) as avg_consistency_score,
                        AVG(emotion_accuracy) as avg_emotion_accuracy,
                        COUNT(CASE WHEN approved THEN 1 END) as approved_count
                    FROM voice_quality_assessments WHERE character_name = $1
                """, character_name)

                return {
                    "character_name": character_name,
                    "profile_exists": profile is not None,
                    "voice_profile": {
                        "voice_id": profile["voice_id"] if profile else None,
                        "voice_name": profile["voice_name"] if profile else None,
                        "usage_count": profile["usage_count"] if profile else 0,
                        "created_at": profile["created_at"].isoformat() if profile and profile["created_at"] else None
                    },
                    "generation_stats": {
                        "total_generations": voice_stats["total_generations"] or 0,
                        "completed": voice_stats["completed"] or 0,
                        "failed": voice_stats["failed"] or 0,
                        "success_rate": (voice_stats["completed"] or 0) / max(1, voice_stats["total_generations"] or 1),
                        "avg_generation_time_ms": voice_stats["avg_generation_time"] or 0
                    },
                    "quality_stats": {
                        "total_assessments": quality_stats["total_assessments"] or 0,
                        "avg_quality_score": quality_stats["avg_quality_score"] or 0,
                        "avg_consistency_score": quality_stats["avg_consistency_score"] or 0,
                        "avg_emotion_accuracy": quality_stats["avg_emotion_accuracy"] or 0,
                        "approval_rate": (quality_stats["approved_count"] or 0) / max(1, quality_stats["total_assessments"] or 1)
                    }
                }

        except Exception as e:
            logger.error(f"Error getting character analytics: {e}")
            return {
                "character_name": character_name,
                "error": str(e)
            }

    async def optimize_voice_settings_for_character(self, character_name: str) -> Dict:
        """Use Echo Brain to optimize voice settings based on assessment history"""
        try:
            # Get character's assessment history
            analytics = await self.get_character_voice_analytics(character_name)

            if analytics["quality_stats"]["total_assessments"] < 3:
                return {
                    "success": False,
                    "message": "Insufficient assessment data for optimization",
                    "min_assessments_required": 3
                }

            # Query Echo Brain for optimization recommendations
            optimization_prompt = f"""
            Analyze voice generation data for character '{character_name}' and recommend optimal settings:

            Current Performance:
            - Average quality score: {analytics['quality_stats']['avg_quality_score']:.2f}
            - Average consistency score: {analytics['quality_stats']['avg_consistency_score']:.2f}
            - Approval rate: {analytics['quality_stats']['approval_rate']:.2f}
            - Success rate: {analytics['generation_stats']['success_rate']:.2f}

            Based on this data, recommend optimal voice settings (stability, similarity_boost, style, use_speaker_boost)
            to improve quality and consistency.

            Return optimized settings as JSON: {{"stability": <float>, "similarity_boost": <float>, "style": <float>, "use_speaker_boost": <boolean>}}
            """

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.echo_brain_url}/api/echo/query",
                    json={
                        "query": optimization_prompt,
                        "conversation_id": f"voice_optimization_{character_name}"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    optimized_settings = self.parse_optimization_response(result.get("response", ""))

                    return {
                        "success": True,
                        "character_name": character_name,
                        "optimized_settings": optimized_settings,
                        "current_analytics": analytics,
                        "echo_brain_response": result.get("response")
                    }

                return {
                    "success": False,
                    "error": "Echo Brain optimization failed"
                }

        except Exception as e:
            logger.error(f"Voice optimization error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def parse_optimization_response(self, response_text: str) -> Dict:
        """Parse optimization response from Echo Brain"""
        try:
            # Extract JSON from response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')

            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
                settings = json.loads(json_str)

                # Validate settings
                default_settings = {
                    "stability": 0.5,
                    "similarity_boost": 0.8,
                    "style": 0.0,
                    "use_speaker_boost": True
                }

                for key, default_value in default_settings.items():
                    if key not in settings:
                        settings[key] = default_value
                    else:
                        # Validate ranges
                        if isinstance(default_value, float):
                            settings[key] = max(0.0, min(1.0, float(settings[key])))

                return settings

            return {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.0,
                "use_speaker_boost": True
            }

        except Exception as e:
            logger.error(f"Optimization parsing error: {e}")
            return {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.0,
                "use_speaker_boost": True
            }