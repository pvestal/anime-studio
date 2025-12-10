#!/usr/bin/env python3
"""
Comprehensive Intent Classification System for Anime Production Pipeline
Addresses critical routing failures by properly classifying user requests
between image and video generation workflows.

This system solves the CRITICAL PROBLEMS:
- No intent classification - all requests go to same broken pipeline
- Users can't specify image vs video generation
- No character vs scene distinction
- No style preference handling (photorealistic vs cartoon)
- No timeline or urgency classification
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import aiohttp

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Primary content type classification"""
    IMAGE = "image"  # Single frame generation
    VIDEO = "video"  # Animated sequence generation
    AUDIO = "audio"  # Voice/music generation
    MIXED_MEDIA = "mixed_media"  # Multiple content types


class GenerationScope(Enum):
    """Scope and complexity of generation request"""
    CHARACTER_PROFILE = "character_profile"  # Single character image/design
    CHARACTER_SCENE = "character_scene"  # Character in specific scene
    ENVIRONMENT = "environment"  # Background/location without characters
    ACTION_SEQUENCE = "action_sequence"  # Short action scene (5-30 seconds)
    DIALOGUE_SCENE = "dialogue_scene"  # Conversation/dialogue scene
    FULL_EPISODE = "full_episode"  # Complete episode (1-10 minutes)
    BATCH_GENERATION = "batch_generation"  # Multiple related items


class StylePreference(Enum):
    """Visual style preferences for generation"""
    PHOTOREALISTIC_ANIME = "photorealistic_anime"  # High-detail, realistic anime style
    TRADITIONAL_ANIME = "traditional_anime"  # Classic 2D anime style
    CARTOON = "cartoon"  # Western cartoon style
    ARTISTIC = "artistic"  # Artistic/experimental style
    CHIBI = "chibi"  # Cute/chibi style
    CINEMATIC = "cinematic"  # Movie-like quality
    SKETCH = "sketch"  # Hand-drawn sketch style


class UrgencyLevel(Enum):
    """Timeline and priority classification"""
    IMMEDIATE = "immediate"  # Generate now, highest priority
    URGENT = "urgent"  # Within 1 hour
    STANDARD = "standard"  # Within 24 hours
    SCHEDULED = "scheduled"  # Specific time/date
    BATCH_PROCESSING = "batch_processing"  # Low priority, batch with others


class ComplexityLevel(Enum):
    """Technical complexity assessment"""
    SIMPLE = "simple"  # Basic generation, fast models
    MODERATE = "moderate"  # Standard complexity
    COMPLEX = "complex"  # Advanced features, quality models
    EXPERT = "expert"  # Maximum quality, multiple passes


@dataclass
class IntentClassification:
    """Complete intent classification result"""
    request_id: str
    content_type: ContentType
    generation_scope: GenerationScope
    style_preference: StylePreference
    urgency_level: UrgencyLevel
    complexity_level: ComplexityLevel

    # Specific parameters
    character_names: List[str]
    duration_seconds: Optional[int]
    frame_count: Optional[int]
    resolution: Optional[str]
    aspect_ratio: Optional[str]

    # Quality and processing preferences
    quality_level: str  # "draft", "standard", "high", "maximum"
    post_processing: List[str]  # ["upscale", "enhance", "color_correct"]
    output_format: str  # "mp4", "png", "jpg", "gif"

    # Routing information
    target_service: str  # "comfyui", "animatediff", "stable_video"
    target_workflow: str  # Specific workflow/pipeline
    estimated_time_minutes: int
    estimated_vram_gb: float

    # Context and metadata
    user_prompt: str
    processed_prompt: str
    confidence_score: float
    ambiguity_flags: List[str]
    fallback_options: List[str]

    # Learning data
    user_preferences: Dict[str, Any]
    historical_patterns: Dict[str, Any]

    created_at: datetime
    updated_at: datetime


class PatternMatcher:
    """Pattern matching for intent classification"""

    def __init__(self):
        self.content_type_patterns = {
            ContentType.IMAGE: [
                r'\b(image|picture|photo|portrait|artwork|design|concept art)\b',
                r'\b(character design|reference sheet|profile)\b',
                r'\b(still|static|frame)\b'
            ],
            ContentType.VIDEO: [
                r'\b(video|animation|animated|sequence|scene|episode)\b',
                r'\b(movie|clip|trailer|action)\b',
                r'\b(\d+\s*(second|minute|sec|min))\b',
                r'\b(movement|walking|fighting|dancing)\b'
            ],
            ContentType.AUDIO: [
                r'\b(voice|audio|sound|music|dialogue)\b',
                r'\b(speak|say|talking|singing)\b'
            ]
        }

        self.scope_patterns = {
            GenerationScope.CHARACTER_PROFILE: [
                r'\b(character|profile|design|reference|bio)\b',
                r'\bnamed?\s+(\w+)\b',
                r'\b(appearance|looks like|description)\b'
            ],
            GenerationScope.CHARACTER_SCENE: [
                r'\b(\w+)\s+(in|at|during|while)\b',
                r'\b(character|person)\s+.*(scene|situation|location)\b'
            ],
            GenerationScope.ENVIRONMENT: [
                r'\b(background|environment|location|setting|place)\b',
                r'\b(cityscape|landscape|room|building|forest)\b'
            ],
            GenerationScope.ACTION_SEQUENCE: [
                r'\b(action|fight|battle|chase|combat)\b',
                r'\b(fighting|running|jumping|attacking)\b'
            ],
            GenerationScope.DIALOGUE_SCENE: [
                r'\b(dialogue|conversation|talking|speaking)\b',
                r'\b(says?|speaks?|tells?)\b'
            ],
            GenerationScope.FULL_EPISODE: [
                r'\b(episode|full|complete|story)\b',
                r'\b(\d+\s*minute|long|series)\b'
            ]
        }

        self.style_patterns = {
            StylePreference.PHOTOREALISTIC_ANIME: [
                r'\b(photorealistic|realistic|detailed|high.?quality)\b',
                r'\b(3d|rendered|lifelike)\b'
            ],
            StylePreference.TRADITIONAL_ANIME: [
                r'\b(anime|manga|japanese|traditional)\b',
                r'\b(2d|classic|cel.?shaded)\b'
            ],
            StylePreference.CARTOON: [
                r'\b(cartoon|western|disney|pixar)\b'
            ],
            StylePreference.ARTISTIC: [
                r'\b(artistic|experimental|abstract|creative)\b'
            ],
            StylePreference.CHIBI: [
                r'\b(chibi|cute|kawaii|small)\b'
            ],
            StylePreference.CINEMATIC: [
                r'\b(cinematic|movie|film|dramatic)\b'
            ]
        }

        self.urgency_patterns = {
            UrgencyLevel.IMMEDIATE: [
                r'\b(now|immediately|urgent|asap|right away)\b'
            ],
            UrgencyLevel.URGENT: [
                r'\b(urgent|soon|quickly|within.*hour)\b'
            ],
            UrgencyLevel.SCHEDULED: [
                r'\b(schedule|later|tomorrow|next|at \d+)\b'
            ],
            UrgencyLevel.BATCH_PROCESSING: [
                r'\b(batch|multiple|series|collection)\b'
            ]
        }

    def extract_patterns(self, text: str, patterns: Dict) -> List[str]:
        """Extract matching patterns from text"""
        text_lower = text.lower()
        matches = []

        for category, pattern_list in patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, text_lower):
                    matches.append(category)
                    break

        return matches

    def extract_character_names(self, text: str) -> List[str]:
        """Extract character names from text"""
        # Common patterns for character names
        patterns = [
            r'\b(?:character|person)\s+named\s+(\w+)\b',
            r'\b(\w+)\s+(?:is|was|will be)\b',
            r'\bcreate.*?(\w+)\b',
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:with|having|in)\b'
        ]

        names = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            names.extend([match.strip() for match in matches if len(match.strip()) > 2])

        return list(set(names))

    def extract_duration(self, text: str) -> Optional[int]:
        """Extract duration in seconds"""
        patterns = [
            r'(\d+)\s*(?:second|sec)s?',
            r'(\d+)\s*(?:minute|min)s?',
            r'(\d+):(\d+)'  # MM:SS format
        ]

        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                if len(match.groups()) == 1:
                    duration = int(match.group(1))
                    if 'min' in pattern:
                        return duration * 60
                    return duration
                elif len(match.groups()) == 2:  # MM:SS
                    minutes = int(match.group(1))
                    seconds = int(match.group(2))
                    return minutes * 60 + seconds

        return None


class EchoBrainIntegrator:
    """Integration with Echo Brain for natural language understanding"""

    def __init__(self, echo_base_url: str = "http://localhost:8309"):
        self.echo_base_url = echo_base_url
        self.session = None

    async def analyze_intent(self, user_prompt: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Use Echo Brain for deep intent analysis"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            analysis_prompt = f"""
Analyze this anime production request for intent classification:

User Request: "{user_prompt}"

Classify the request and respond with JSON containing:
1. content_type: "image", "video", "audio", or "mixed_media"
2. generation_scope: "character_profile", "character_scene", "environment", "action_sequence", "dialogue_scene", "full_episode", or "batch_generation"
3. style_preference: "photorealistic_anime", "traditional_anime", "cartoon", "artistic", "chibi", "cinematic", or "sketch"
4. urgency_level: "immediate", "urgent", "standard", "scheduled", or "batch_processing"
5. complexity_level: "simple", "moderate", "complex", or "expert"
6. character_names: array of character names mentioned
7. duration_seconds: estimated duration if video (null for images)
8. quality_level: "draft", "standard", "high", or "maximum"
9. confidence_score: 0.0-1.0 confidence in classification
10. ambiguity_flags: array of unclear aspects
11. processed_prompt: optimized prompt for generation
12. target_workflow: recommended workflow ("comfyui_image", "animatediff_video", "stable_video", etc.)

Context: {json.dumps(context or {}, default=str)}

Respond only with valid JSON.
"""

            payload = {
                "query": analysis_prompt,
                "context": "anime_intent_classification",
                "intelligence_level": "expert",
                "model": "qwen2.5-coder:32b"
            }

            async with self.session.post(
                f"{self.echo_base_url}/api/echo/query",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    response_text = result.get("response", "{}")

                    try:
                        # Parse JSON response from Echo
                        analysis_result = json.loads(response_text)
                        return analysis_result
                    except json.JSONDecodeError:
                        logger.warning(f"Echo returned non-JSON response: {response_text}")
                        return {"error": "invalid_json", "raw_response": response_text}
                else:
                    logger.error(f"Echo Brain request failed: {response.status}")
                    return {"error": "echo_request_failed", "status": response.status}

        except Exception as e:
            logger.error(f"Echo Brain integration error: {e}")
            return {"error": "echo_integration_failed", "details": str(e)}

    async def close(self):
        """Clean up session"""
        if self.session:
            await self.session.close()


class UserPreferenceManager:
    """Manages user preferences and historical patterns"""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    async def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get user's stored preferences"""
        try:
            query = """
            SELECT preferences_data FROM user_preferences
            WHERE user_id = %s AND is_active = TRUE
            """
            result = await self.db_manager.execute_query_robust(
                query, (user_id,), fetch_result=True
            )

            if result:
                return result[0]['preferences_data']
            else:
                return self._get_default_preferences()

        except Exception as e:
            logger.error(f"Failed to get user preferences: {e}")
            return self._get_default_preferences()

    def _get_default_preferences(self) -> Dict[str, Any]:
        """Default user preferences"""
        return {
            "preferred_style": "traditional_anime",
            "default_quality": "high",
            "preferred_duration": 5,
            "auto_upscale": True,
            "notification_preferences": {
                "completion": True,
                "progress": False,
                "errors": True
            },
            "workflow_preferences": {
                "fast_preview": True,
                "quality_over_speed": False
            }
        }

    async def update_preferences_from_request(self, user_id: str, classification: IntentClassification):
        """Learn from user requests to update preferences"""
        try:
            # Get current preferences
            current_prefs = await self.get_user_preferences(user_id)

            # Update based on this request
            updates = {}
            if classification.style_preference:
                updates["preferred_style"] = classification.style_preference.value
            if classification.quality_level:
                updates["default_quality"] = classification.quality_level

            # Store updated preferences
            query = """
            INSERT INTO user_preferences (user_id, preferences_data, updated_at, is_active)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (user_id) DO UPDATE SET
                preferences_data = EXCLUDED.preferences_data,
                updated_at = EXCLUDED.updated_at
            """

            merged_prefs = {**current_prefs, **updates}
            await self.db_manager.execute_query_robust(
                query, (user_id, json.dumps(merged_prefs), datetime.utcnow()),
                fetch_result=False
            )

            logger.info(f"Updated preferences for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to update user preferences: {e}")


class IntentClassificationEngine:
    """Main intent classification engine"""

    def __init__(self, db_manager, echo_integration=None):
        self.db_manager = db_manager
        self.pattern_matcher = PatternMatcher()
        self.echo_integration = echo_integration or EchoBrainIntegrator()
        self.preference_manager = UserPreferenceManager(db_manager)

        # Service routing configuration
        self.service_routing = {
            ContentType.IMAGE: {
                GenerationScope.CHARACTER_PROFILE: "comfyui_character",
                GenerationScope.CHARACTER_SCENE: "comfyui_scene",
                GenerationScope.ENVIRONMENT: "comfyui_background",
            },
            ContentType.VIDEO: {
                GenerationScope.ACTION_SEQUENCE: "animatediff_action",
                GenerationScope.DIALOGUE_SCENE: "animatediff_dialogue",
                GenerationScope.FULL_EPISODE: "animatediff_episode",
                GenerationScope.CHARACTER_SCENE: "animatediff_scene"
            }
        }

        # Quality and complexity mapping
        self.complexity_mapping = {
            ComplexityLevel.SIMPLE: {"models": ["fast"], "passes": 1, "quality": "draft"},
            ComplexityLevel.MODERATE: {"models": ["standard"], "passes": 1, "quality": "standard"},
            ComplexityLevel.COMPLEX: {"models": ["advanced"], "passes": 2, "quality": "high"},
            ComplexityLevel.EXPERT: {"models": ["expert"], "passes": 3, "quality": "maximum"}
        }

    async def classify_intent(self, user_prompt: str, user_id: str = "default") -> IntentClassification:
        """Main intent classification method"""
        request_id = f"intent_{int(time.time())}_{hash(user_prompt) % 10000}"

        try:
            # Get user preferences
            user_preferences = await self.preference_manager.get_user_preferences(user_id)

            # Pattern-based initial classification
            pattern_classification = self._classify_with_patterns(user_prompt)

            # Echo Brain advanced analysis
            echo_analysis = await self.echo_integration.analyze_intent(
                user_prompt, {"user_preferences": user_preferences}
            )

            # Combine pattern and Echo analysis
            final_classification = self._merge_classifications(
                pattern_classification, echo_analysis, user_preferences
            )

            # Build complete IntentClassification object
            classification = IntentClassification(
                request_id=request_id,
                content_type=final_classification["content_type"],
                generation_scope=final_classification["generation_scope"],
                style_preference=final_classification["style_preference"],
                urgency_level=final_classification["urgency_level"],
                complexity_level=final_classification["complexity_level"],

                character_names=final_classification.get("character_names", []),
                duration_seconds=final_classification.get("duration_seconds"),
                frame_count=self._calculate_frame_count(final_classification.get("duration_seconds")),
                resolution=self._get_resolution(final_classification["complexity_level"]),
                aspect_ratio="16:9",

                quality_level=final_classification["quality_level"],
                post_processing=self._get_post_processing(final_classification["complexity_level"]),
                output_format=self._get_output_format(final_classification["content_type"]),

                target_service=self._get_target_service(final_classification),
                target_workflow=final_classification.get("target_workflow", "default"),
                estimated_time_minutes=self._estimate_time(final_classification),
                estimated_vram_gb=self._estimate_vram(final_classification),

                user_prompt=user_prompt,
                processed_prompt=final_classification.get("processed_prompt", user_prompt),
                confidence_score=final_classification.get("confidence_score", 0.5),
                ambiguity_flags=final_classification.get("ambiguity_flags", []),
                fallback_options=self._generate_fallback_options(final_classification),

                user_preferences=user_preferences,
                historical_patterns={},

                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            # Store classification for learning
            await self._store_classification(classification)

            # Update user preferences
            await self.preference_manager.update_preferences_from_request(user_id, classification)

            return classification

        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return self._create_fallback_classification(user_prompt, request_id)

    def _classify_with_patterns(self, user_prompt: str) -> Dict[str, Any]:
        """Pattern-based classification"""
        content_types = self.pattern_matcher.extract_patterns(
            user_prompt, self.pattern_matcher.content_type_patterns
        )
        scopes = self.pattern_matcher.extract_patterns(
            user_prompt, self.pattern_matcher.scope_patterns
        )
        styles = self.pattern_matcher.extract_patterns(
            user_prompt, self.pattern_matcher.style_patterns
        )
        urgencies = self.pattern_matcher.extract_patterns(
            user_prompt, self.pattern_matcher.urgency_patterns
        )

        return {
            "content_types": content_types,
            "scopes": scopes,
            "styles": styles,
            "urgencies": urgencies,
            "character_names": self.pattern_matcher.extract_character_names(user_prompt),
            "duration_seconds": self.pattern_matcher.extract_duration(user_prompt)
        }

    def _merge_classifications(self, pattern_result: Dict, echo_result: Dict, user_prefs: Dict) -> Dict[str, Any]:
        """Merge pattern and Echo Brain classifications"""
        # Use Echo Brain results as primary, pattern results as fallback
        merged = {}

        # Content type
        merged["content_type"] = ContentType(
            echo_result.get("content_type") or
            (pattern_result["content_types"][0] if pattern_result["content_types"] else "image")
        )

        # Generation scope
        merged["generation_scope"] = GenerationScope(
            echo_result.get("generation_scope") or
            (pattern_result["scopes"][0] if pattern_result["scopes"] else "character_profile")
        )

        # Style preference
        merged["style_preference"] = StylePreference(
            echo_result.get("style_preference") or
            user_prefs.get("preferred_style", "traditional_anime")
        )

        # Urgency level
        merged["urgency_level"] = UrgencyLevel(
            echo_result.get("urgency_level") or
            (pattern_result["urgencies"][0] if pattern_result["urgencies"] else "standard")
        )

        # Complexity level
        merged["complexity_level"] = ComplexityLevel(
            echo_result.get("complexity_level", "moderate")
        )

        # Other fields
        merged.update({
            "character_names": echo_result.get("character_names", pattern_result.get("character_names", [])),
            "duration_seconds": echo_result.get("duration_seconds") or pattern_result.get("duration_seconds"),
            "quality_level": echo_result.get("quality_level", user_prefs.get("default_quality", "high")),
            "confidence_score": echo_result.get("confidence_score", 0.7),
            "ambiguity_flags": echo_result.get("ambiguity_flags", []),
            "processed_prompt": echo_result.get("processed_prompt", ""),
            "target_workflow": echo_result.get("target_workflow", "")
        })

        return merged

    def _calculate_frame_count(self, duration_seconds: Optional[int]) -> Optional[int]:
        """Calculate frame count for video generation"""
        if duration_seconds:
            return duration_seconds * 24  # 24 FPS
        return None

    def _get_resolution(self, complexity: ComplexityLevel) -> str:
        """Get resolution based on complexity"""
        resolution_map = {
            ComplexityLevel.SIMPLE: "512x512",
            ComplexityLevel.MODERATE: "768x768",
            ComplexityLevel.COMPLEX: "1024x1024",
            ComplexityLevel.EXPERT: "1536x1536"
        }
        return resolution_map.get(complexity, "768x768")

    def _get_post_processing(self, complexity: ComplexityLevel) -> List[str]:
        """Get post-processing steps"""
        if complexity in [ComplexityLevel.COMPLEX, ComplexityLevel.EXPERT]:
            return ["upscale", "enhance", "color_correct"]
        elif complexity == ComplexityLevel.MODERATE:
            return ["upscale"]
        return []

    def _get_output_format(self, content_type: ContentType) -> str:
        """Get output format based on content type"""
        format_map = {
            ContentType.IMAGE: "png",
            ContentType.VIDEO: "mp4",
            ContentType.AUDIO: "wav"
        }
        return format_map.get(content_type, "png")

    def _get_target_service(self, classification: Dict) -> str:
        """Determine target service"""
        content_type = classification["content_type"]
        scope = classification["generation_scope"]

        routing = self.service_routing.get(content_type, {})
        return routing.get(scope, "comfyui_default")

    def _estimate_time(self, classification: Dict) -> int:
        """Estimate generation time in minutes"""
        base_times = {
            ContentType.IMAGE: 2,
            ContentType.VIDEO: 8
        }

        complexity_multipliers = {
            ComplexityLevel.SIMPLE: 0.5,
            ComplexityLevel.MODERATE: 1.0,
            ComplexityLevel.COMPLEX: 2.0,
            ComplexityLevel.EXPERT: 4.0
        }

        base = base_times.get(classification["content_type"], 2)
        multiplier = complexity_multipliers.get(classification["complexity_level"], 1.0)

        return max(1, int(base * multiplier))

    def _estimate_vram(self, classification: Dict) -> float:
        """Estimate VRAM usage in GB"""
        base_vram = {
            ContentType.IMAGE: 4.0,
            ContentType.VIDEO: 8.0
        }

        complexity_multipliers = {
            ComplexityLevel.SIMPLE: 0.5,
            ComplexityLevel.MODERATE: 1.0,
            ComplexityLevel.COMPLEX: 1.5,
            ComplexityLevel.EXPERT: 2.0
        }

        base = base_vram.get(classification["content_type"], 4.0)
        multiplier = complexity_multipliers.get(classification["complexity_level"], 1.0)

        return min(12.0, base * multiplier)  # Max 12GB (RTX 3060 limit)

    def _generate_fallback_options(self, classification: Dict) -> List[str]:
        """Generate fallback options for ambiguous requests"""
        options = []

        if classification.get("confidence_score", 1.0) < 0.7:
            if classification["content_type"] == ContentType.IMAGE:
                options.append("video_alternative")
            elif classification["content_type"] == ContentType.VIDEO:
                options.append("image_sequence")

            options.append("simplified_request")
            options.append("guided_workflow")

        return options

    async def _store_classification(self, classification: IntentClassification):
        """Store classification for learning and analytics"""
        try:
            query = """
            INSERT INTO intent_classifications
            (request_id, user_prompt, classification_data, confidence_score, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """

            await self.db_manager.execute_query_robust(
                query,
                (
                    classification.request_id,
                    classification.user_prompt,
                    json.dumps(asdict(classification), default=str),
                    classification.confidence_score,
                    classification.created_at
                ),
                fetch_result=False
            )
        except Exception as e:
            logger.error(f"Failed to store classification: {e}")

    def _create_fallback_classification(self, user_prompt: str, request_id: str) -> IntentClassification:
        """Create fallback classification when analysis fails"""
        return IntentClassification(
            request_id=request_id,
            content_type=ContentType.IMAGE,
            generation_scope=GenerationScope.CHARACTER_PROFILE,
            style_preference=StylePreference.TRADITIONAL_ANIME,
            urgency_level=UrgencyLevel.STANDARD,
            complexity_level=ComplexityLevel.MODERATE,

            character_names=[],
            duration_seconds=None,
            frame_count=None,
            resolution="768x768",
            aspect_ratio="16:9",

            quality_level="standard",
            post_processing=[],
            output_format="png",

            target_service="comfyui_default",
            target_workflow="default",
            estimated_time_minutes=5,
            estimated_vram_gb=4.0,

            user_prompt=user_prompt,
            processed_prompt=user_prompt,
            confidence_score=0.3,
            ambiguity_flags=["classification_failed"],
            fallback_options=["guided_workflow", "manual_selection"],

            user_preferences={},
            historical_patterns={},

            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    async def close(self):
        """Clean up resources"""
        await self.echo_integration.close()


# Factory function
def create_intent_classifier(db_manager) -> IntentClassificationEngine:
    """Create configured intent classification engine"""
    return IntentClassificationEngine(db_manager)


# Test scenarios
async def test_intent_classification():
    """Test the intent classification system with user scenarios"""

    # Mock database manager for testing
    class MockDBManager:
        async def execute_query_robust(self, *args, **kwargs):
            return []

    classifier = IntentClassificationEngine(MockDBManager())

    test_scenarios = [
        "Create a character named Kai with silver hair and blue eyes",
        "Generate a 30-second action scene with Kai fighting robots",
        "Make a full 5-minute episode about Kai's backstory",
        "Create background art for a cyberpunk city",
        "Generate profile pictures for all characters in photorealistic style"
    ]

    for scenario in test_scenarios:
        print(f"\n--- Testing: {scenario} ---")
        try:
            classification = await classifier.classify_intent(scenario)
            print(f"Content Type: {classification.content_type.value}")
            print(f"Scope: {classification.generation_scope.value}")
            print(f"Style: {classification.style_preference.value}")
            print(f"Urgency: {classification.urgency_level.value}")
            print(f"Complexity: {classification.complexity_level.value}")
            print(f"Target Service: {classification.target_service}")
            print(f"Estimated Time: {classification.estimated_time_minutes} minutes")
            print(f"Confidence: {classification.confidence_score}")
            print(f"Characters: {classification.character_names}")
        except Exception as e:
            print(f"Classification failed: {e}")

    await classifier.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_intent_classification())