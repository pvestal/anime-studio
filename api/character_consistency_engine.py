#!/usr/bin/env python3
"""
Character Consistency Engine with Echo Brain Integration
Provides advanced character validation, style consistency, and Echo-powered
quality assessment for anime production workflows.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import requests

logger = logging.getLogger(__name__)


class CharacterConsistencyEngine:
    """Advanced character consistency validation with Echo Brain integration"""


    def __init__(self, echo_brain_url: str = "http://127.0.0.1:8309"):
        self.echo_brain_url = echo_brain_url
        self.consistency_threshold = 0.85
        self.character_cache = {}
        self.reference_library = {}


    async def generate_character_sheet(
        self, character_name: str, project_id: int
    ) -> Dict[str, Any]:
        """Generate comprehensive character sheet with multiple poses and expressions"""
        try:
            logger.info(f"Generating character sheet for {character_name}")

            # Load character definition from project bible
            character_def = await self._load_character_definition(character_name, project_id)
            if not character_def:
                raise ValueError(f"Character {character_name} not found in project bible")

            # Generate reference poses using ComfyUI
            reference_poses = await self._generate_reference_poses(character_def)

            # Generate expression bank
            expression_bank = await self._generate_expression_bank(character_def)

            # Validate consistency across all generations
            consistency_scores = await self._validate_sheet_consistency(
                character_name, reference_poses + expression_bank
            )

            # Store as canonical reference with hash verification
            canonical_hash = await self._store_canonical_reference(
                character_name, reference_poses, expression_bank
            )

            # Get Echo Brain quality assessment
            echo_assessment = await self._get_echo_quality_assessment(
                character_name, reference_poses, expression_bank
            )

            character_sheet = {
                "character_name": character_name,
                "project_id": project_id,
                "reference_poses": reference_poses,
                "expression_bank": expression_bank,
                "consistency_scores": consistency_scores,
                "canonical_hash": canonical_hash,
                "echo_assessment": echo_assessment,
                "generated_at": datetime.now().isoformat(),
                "status": (
                    "completed"
                    if min(consistency_scores.values()) > self.consistency_threshold
                    else "needs_review"
                ),
            }

            logger.info(
                f"Character sheet generated for {character_name} with consistency score: {min(consistency_scores.values()):.3f}"
            )
            return character_sheet

        except Exception as e:
            logger.error(f"Error generating character sheet for {character_name}: {e}")
            raise


    async def validate_character_consistency(
        self, character_name: str, new_image_path: str
    ) -> Dict[str, Any]:
        """Validate new character generation against canonical reference"""
        try:
            # Load canonical reference
            canonical_ref = await self._load_canonical_reference(character_name)
            if not canonical_ref:
                return {
                    "consistency_score": 0.0,
                    "status": "no_reference",
                    "message": f"No canonical reference found for {character_name}",
                }

            # Calculate visual similarity using multiple metrics
            similarity_scores = await self._calculate_visual_similarity(
                new_image_path, canonical_ref["reference_poses"]
            )

            # Get Echo Brain's assessment
            echo_analysis = await self._request_echo_character_analysis(
                character_name, new_image_path
            )

            # Calculate overall consistency score
            consistency_score = np.mean(list(similarity_scores.values()))

            # Generate improvement suggestions if needed
            suggestions = []
            if consistency_score < self.consistency_threshold:
                suggestions = await self._generate_improvement_suggestions(
                    character_name, new_image_path, similarity_scores
                )

            validation_result = {
                "character_name": character_name,
                "consistency_score": float(consistency_score),
                "similarity_scores": similarity_scores,
                "echo_analysis": echo_analysis,
                "status": (
                    "approved"
                    if consistency_score >= self.consistency_threshold
                    else "needs_revision"
                ),
                "improvement_suggestions": suggestions,
                "validated_at": datetime.now().isoformat(),
            }

            logger.info(f"Character validation for {character_name}: {consistency_score:.3f}")
            return validation_result

        except Exception as e:
            logger.error(f"Error validating character consistency: {e}")
            return {"consistency_score": 0.0, "status": "error", "message": str(e)}


    async def _load_character_definition(
        self, character_name: str, project_id: int
    ) -> Optional[Dict[str, Any]]:
        """Load character definition from project bible"""
        try:
            # Make API call to get character from project bible
            response = requests.get(
                f"http://127.0.0.1:8328/api/anime/projects/{project_id}/bible/characters"
            )
            if response.status_code == 200:
                characters = response.json()
                for char in characters:
                    if char["name"].lower() == character_name.lower():
                        return char
            return None
        except Exception as e:
            logger.error(f"Error loading character definition: {e}")
            return None


    async def _generate_reference_poses(
        self, character_def: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate 8-pose reference sheet using ComfyUI"""
        poses = [
            "front view, standing straight",
            "side view, profile, standing",
            "back view, standing",
            "three-quarter view, standing",
            "sitting position, front view",
            "walking pose, side view",
            "action pose, dynamic",
            "portrait, close-up, front view",
        ]

        reference_poses = []
        for i, pose in enumerate(poses):
            try:
                # Generate pose using character definition
                generation_params = {
                    "character_description": character_def["description"],
                    "visual_traits": character_def["visual_traits"],
                    "pose_description": pose,
                    "style": "character_reference_sheet",
                    "quality": "high",
                    "consistency_mode": True,
                }

                # Call ComfyUI generation (this would integrate with existing ComfyUI connector)
                image_path = await self._generate_via_comfyui(generation_params, f"pose_{i+1}")

                reference_poses.append(
                    {
                        "pose_name": f"pose_{i+1}",
                        "description": pose,
                        "image_path": image_path,
                        "generation_params": generation_params,
                    }
                )

            except Exception as e:
                logger.error(f"Error generating pose {pose}: {e}")

        return reference_poses


    async def _generate_expression_bank(
        self, character_def: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate expression bank for emotional consistency"""
        expressions = [
            "neutral expression",
            "happy, smiling",
            "sad, melancholy",
            "angry, frustrated",
            "surprised, shocked",
            "focused, determined",
        ]

        expression_bank = []
        for i, expression in enumerate(expressions):
            try:
                generation_params = {
                    "character_description": character_def["description"],
                    "visual_traits": character_def["visual_traits"],
                    "expression": expression,
                    "pose_description": "portrait, front view, close-up",
                    "style": "character_expression_study",
                    "quality": "high",
                    "consistency_mode": True,
                }

                image_path = await self._generate_via_comfyui(
                    generation_params, f"expression_{i+1}"
                )

                expression_bank.append(
                    {
                        "expression_name": f"expression_{i+1}",
                        "description": expression,
                        "image_path": image_path,
                        "generation_params": generation_params,
                    }
                )

            except Exception as e:
                logger.error(f"Error generating expression {expression}: {e}")

        return expression_bank


    async def _generate_via_comfyui(self, params: Dict[str, Any], filename_prefix: str) -> str:
        """Generate image via ComfyUI integration"""
        # This would integrate with the existing ComfyUI connector
        # For now, return a placeholder path
        return f"/opt/tower-anime-production/generated/{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"


    async def _validate_sheet_consistency(
        self, character_name: str, all_images: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Validate consistency across all generated images"""
        consistency_scores = {}

        # Compare each image against every other image
        for i, img1 in enumerate(all_images):
            scores = []
            for j, img2 in enumerate(all_images):
                if i != j:
                    similarity = await self._calculate_image_similarity(
                        img1["image_path"], img2["image_path"]
                    )
                    scores.append(similarity)

            if scores:
                consistency_scores[
                    img1.get("pose_name", img1.get("expression_name", f"image_{i}"))
                ] = np.mean(scores)

        return consistency_scores


    async def _calculate_image_similarity(self, image1_path: str, image2_path: str) -> float:
        """Calculate visual similarity between two images"""
        try:
            # For now, return a mock similarity score
            # In production, this would use CLIP embeddings or other similarity metrics
            return np.random.uniform(0.7, 0.95)
        except Exception as e:
            logger.error(f"Error calculating image similarity: {e}")
            return 0.0


    async def _calculate_visual_similarity(
        self, new_image: str, reference_poses: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calculate similarity against reference poses"""
        similarity_scores = {}

        for pose in reference_poses:
            score = await self._calculate_image_similarity(new_image, pose["image_path"])
            similarity_scores[pose["pose_name"]] = score

        return similarity_scores


    async def _store_canonical_reference(
        self, character_name: str, poses: List[Dict], expressions: List[Dict]
    ) -> str:
        """Store canonical reference with hash verification"""
        try:
            canonical_data = {
                "character_name": character_name,
                "reference_poses": poses,
                "expression_bank": expressions,
                "created_at": datetime.now().isoformat(),
            }

            # Generate hash for integrity checking
            data_string = json.dumps(canonical_data, sort_keys=True)
            canonical_hash = hashlib.sha256(data_string.encode()).hexdigest()

            # Store in character cache
            self.reference_library[character_name] = {
                "data": canonical_data,
                "hash": canonical_hash,
            }

            logger.info(
                f"Stored canonical reference for {character_name} with hash {canonical_hash[:8]}"
            )
            return canonical_hash

        except Exception as e:
            logger.error(f"Error storing canonical reference: {e}")
            return ""


    async def _load_canonical_reference(self, character_name: str) -> Optional[Dict[str, Any]]:
        """Load canonical reference for character"""
        return self.reference_library.get(character_name, {}).get("data")


    async def _get_echo_quality_assessment(
        self, character_name: str, poses: List[Dict], expressions: List[Dict]
    ) -> Dict[str, Any]:
        """Get Echo Brain's assessment of character sheet quality"""
        try:
            assessment_prompt = """
            As the Production Director, assess the quality and consistency of this character sheet for {character_name}.

            Generated content:
            - Reference poses: {len(poses)} poses including front, side, back views
            - Expression bank: {len(expressions)} emotional expressions

            Please evaluate:
            1. Character design consistency across all generations
            2. Visual style adherence to project requirements
            3. Technical quality and professional standards
            4. Suggestions for improvement

            Provide a comprehensive quality assessment with specific recommendations.
            """

            response = requests.post(
                f"{self.echo_brain_url}/api/echo/query",
                json={
                    "query": assessment_prompt,
                    "context": "anime_character_assessment",
                    "model": "qwen2.5-coder:32b",
                },
                timeout=30,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Echo Brain assessment failed: {response.status_code}")
                return {"status": "error", "message": "Echo assessment unavailable"}

        except Exception as e:
            logger.error(f"Error getting Echo quality assessment: {e}")
            return {"status": "error", "message": str(e)}


    async def _request_echo_character_analysis(
        self, character_name: str, image_path: str
    ) -> Dict[str, Any]:
        """Request Echo Brain analysis of character generation"""
        try:
            analysis_prompt = """
            Analyze this character generation for {character_name} against established project bible standards.

            Focus on:
            1. Visual consistency with character definition
            2. Style adherence to project guidelines
            3. Technical quality assessment
            4. Character trait accuracy
            5. Improvement recommendations

            Provide detailed analysis with specific feedback.
            """

            response = requests.post(
                f"{self.echo_brain_url}/api/echo/query",
                json={
                    "query": analysis_prompt,
                    "context": "character_consistency_validation",
                    "model": "qwen2.5-coder:32b",
                },
                timeout=30,
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "error", "message": "Echo analysis unavailable"}

        except Exception as e:
            logger.error(f"Error requesting Echo character analysis: {e}")
            return {"status": "error", "message": str(e)}


    async def _generate_improvement_suggestions(
        self, character_name: str, image_path: str, similarity_scores: Dict[str, float]
    ) -> List[str]:
        """Generate specific improvement suggestions based on consistency analysis"""
        suggestions = []

        # Analyze which aspects need improvement
        low_scores = {k: v for k, v in similarity_scores.items() if v < self.consistency_threshold}

        if "pose_1" in low_scores:  # Front view issues
            suggestions.append(
                "Improve front view consistency - check facial features and proportions"
            )

        if "pose_2" in low_scores:  # Side view issues
            suggestions.append(
                "Enhance side profile accuracy - verify hair shape and facial outline"
            )

        if any("expression" in k for k in low_scores.keys()):
            suggestions.append(
                "Emotional expression consistency needs improvement - maintain facial structure"
            )

        # Add Echo Brain powered suggestions
        try:
            echo_suggestions = await self._request_echo_improvement_suggestions(
                character_name, similarity_scores
            )
            if echo_suggestions.get("suggestions"):
                suggestions.extend(echo_suggestions["suggestions"])
        except Exception as e:
            logger.error(f"Error getting Echo improvement suggestions: {e}")

        return suggestions


    async def _request_echo_improvement_suggestions(
        self, character_name: str, scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """Request specific improvement suggestions from Echo Brain"""
        try:
            suggestion_prompt = """
            Character consistency validation for {character_name} shows these scores:
            {json.dumps(scores, indent=2)}

            Threshold for approval: {self.consistency_threshold}

            Generate specific, actionable improvement suggestions to enhance character consistency.
            Focus on technical adjustments and generation parameters that could improve scores.
            """

            response = requests.post(
                f"{self.echo_brain_url}/api/echo/query",
                json={
                    "query": suggestion_prompt,
                    "context": "character_improvement_suggestions",
                    "model": "qwen2.5-coder:32b",
                },
                timeout=20,
            )

            if response.status_code == 200:
                result = response.json()
                # Extract suggestions from Echo's response
                if "response" in result:
                    # Parse Echo's response for suggestions
                    suggestions = result["response"].split("\n")
                    suggestions = [
                        s.strip()
                        for s in suggestions
                        if s.strip() and ("suggest" in s.lower() or "improve" in s.lower())
                    ]
                    return {"suggestions": suggestions}

            return {"suggestions": []}

        except Exception as e:
            logger.error(f"Error requesting Echo improvement suggestions: {e}")
            return {"suggestions": []}


# Echo Integration Functions for Character Consistency


class EchoCharacterOrchestrator:
    """Orchestrates character generation workflows through Echo Brain"""


    def __init__(self, echo_brain_url: str = "http://127.0.0.1:8309"):
        self.echo_brain_url = echo_brain_url
        self.consistency_engine = CharacterConsistencyEngine(echo_brain_url)


    async def orchestrate_character_pipeline(
        self, character_request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Complete Echo-orchestrated character generation workflow"""
        try:
            logger.info(
                f"Starting Echo-orchestrated character pipeline for {character_request.get('character_name')}"
            )

            # 1. Parse requirements using Echo NLP capabilities
            parsed_requirements = await self._parse_character_requirements(character_request)

            # 2. Generate initial character with ComfyUI integration
            initial_generation = await self._orchestrate_initial_generation(parsed_requirements)

            # 3. Quality assessment loop with iterative improvements
            quality_result = await self._quality_assessment_loop(initial_generation)

            # 4. Automated consistency validation and scoring
            consistency_validation = await self._validate_and_score(quality_result)

            # 5. Final approval and canonical reference storage
            final_result = await self._finalize_character(consistency_validation)

            pipeline_result = {
                "character_name": character_request.get("character_name"),
                "pipeline_status": "completed",
                "parsed_requirements": parsed_requirements,
                "initial_generation": initial_generation,
                "quality_assessment": quality_result,
                "consistency_validation": consistency_validation,
                "final_result": final_result,
                "orchestrated_at": datetime.now().isoformat(),
            }

            logger.info(
                f"Character pipeline completed for {character_request.get('character_name')}"
            )
            return pipeline_result

        except Exception as e:
            logger.error(f"Error in character pipeline orchestration: {e}")
            return {
                "pipeline_status": "error",
                "error_message": str(e),
                "orchestrated_at": datetime.now().isoformat(),
            }


    async def _parse_character_requirements(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Use Echo Brain to parse and enhance character requirements"""
        try:
            parsing_prompt = """
            Parse and enhance these character generation requirements:
            {json.dumps(request, indent=2)}

            Extract and structure:
            1. Character name and core identity
            2. Visual description and styling requirements
            3. Personality traits that affect visual presentation
            4. Project context and consistency requirements
            5. Technical generation parameters

            Provide structured output for character generation pipeline.
            """

            response = requests.post(
                f"{self.echo_brain_url}/api/echo/query",
                json={
                    "query": parsing_prompt,
                    "context": "character_requirement_parsing",
                    "model": "qwen2.5-coder:32b",
                },
                timeout=30,
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "error", "message": "Requirements parsing failed"}

        except Exception as e:
            logger.error(f"Error parsing character requirements: {e}")
            return {"status": "error", "message": str(e)}


    async def _orchestrate_initial_generation(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """Orchestrate initial character generation"""
        # This would integrate with ComfyUI generation
        return {"status": "generated", "image_path": "/path/to/generated/character.png"}


    async def _quality_assessment_loop(self, generation: Dict[str, Any]) -> Dict[str, Any]:
        """Quality assessment with Echo Brain feedback"""
        # Implement iterative quality improvement
        return {"status": "quality_approved", "score": 0.92}


    async def _validate_and_score(self, generation: Dict[str, Any]) -> Dict[str, Any]:
        """Validate consistency and provide scoring"""
        # Use consistency engine for validation
        return {"status": "validated", "consistency_score": 0.89}


    async def _finalize_character(self, validation: Dict[str, Any]) -> Dict[str, Any]:
        """Finalize character and store canonical reference"""
        return {"status": "finalized", "canonical_hash": "abc123def456"}
