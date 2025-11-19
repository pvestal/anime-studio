#!/usr/bin/env python3
"""
Ambiguity Resolution System for Intent Classification
Handles unclear, ambiguous, or incomplete user requests through intelligent
clarification strategies, fallback options, and guided user interactions.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class AmbiguityType(Enum):
    """Types of ambiguities that can occur in user requests"""

    CONTENT_TYPE_UNCLEAR = "content_type_unclear"  # Image vs video vs audio
    SCOPE_AMBIGUOUS = "scope_ambiguous"  # Character vs scene vs episode
    STYLE_CONFLICTING = "style_conflicting"  # Multiple style indicators
    CHARACTER_UNDEFINED = "character_undefined"  # Character mentioned but undefined
    DURATION_MISSING = "duration_missing"  # Video requested but no duration
    QUALITY_VAGUE = "quality_vague"  # Quality requirements unclear
    URGENCY_UNCLEAR = "urgency_unclear"  # Timeline requirements unclear
    TECHNICAL_INCOMPLETE = "technical_incomplete"  # Missing technical specs
    CONTRADICTORY_REQUIREMENTS = (
        "contradictory_requirements"  # Conflicting requirements
    )
    INSUFFICIENT_DETAIL = "insufficient_detail"  # Too vague overall


class ResolutionStrategy(Enum):
    """Strategies for resolving ambiguities"""

    USER_CLARIFICATION = "user_clarification"  # Ask user directly
    INTELLIGENT_DEFAULT = "intelligent_default"  # Use smart defaults
    CONTEXT_INFERENCE = "context_inference"  # Infer from context
    TEMPLATE_SUGGESTION = "template_suggestion"  # Suggest predefined templates
    PROGRESSIVE_REFINEMENT = "progressive_refinement"  # Iterative clarification
    FALLBACK_WORKFLOW = "fallback_workflow"  # Use fallback generation method
    HYBRID_APPROACH = "hybrid_approach"  # Combine multiple strategies


@dataclass
class AmbiguityDetection:
    """Detected ambiguity in user request"""

    ambiguity_type: AmbiguityType
    confidence: float  # Confidence that this is an ambiguity (0.0-1.0)
    description: str
    affected_fields: List[str]
    evidence: List[str]  # Evidence supporting this ambiguity
    severity: str  # "low", "medium", "high"
    blocking: bool  # Whether this blocks generation
    context_clues: Dict[str, Any]  # Additional context for resolution


@dataclass
class ResolutionAction:
    """Action to resolve an ambiguity"""

    strategy: ResolutionStrategy
    action_type: str  # "question", "suggestion", "default", "inference"
    priority: int  # 1-10, lower is higher priority
    timeout_seconds: int  # How long to wait for user response
    fallback_action: Optional["ResolutionAction"] = None

    # Question-based resolution
    question: Optional[str] = None
    options: Optional[List[str]] = None
    default_answer: Optional[str] = None
    validation_pattern: Optional[str] = None

    # Default-based resolution
    default_value: Optional[Any] = None
    confidence_threshold: float = 0.7

    # Template-based resolution
    suggested_templates: Optional[List[Dict[str, Any]]] = None

    # Inference-based resolution
    inference_rules: Optional[List[str]] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolutionResult:
    """Result of ambiguity resolution"""

    ambiguity_type: AmbiguityType
    resolution_strategy: ResolutionStrategy
    resolved_value: Any
    confidence: float
    user_interaction_required: bool
    resolution_time_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class AmbiguityDetector:
    """Detects ambiguities in user requests and classification results"""

    def __init__(self):
        self.detection_rules = self._initialize_detection_rules()
        self.context_patterns = self._initialize_context_patterns()

    def _initialize_detection_rules(self) -> Dict[AmbiguityType, List[Dict[str, Any]]]:
        """Initialize ambiguity detection rules"""
        return {
            AmbiguityType.CONTENT_TYPE_UNCLEAR: [
                {
                    "pattern": r"\b(image|picture)\b.*\b(video|animation|movie)\b",
                    "evidence": "Both image and video indicators present",
                    "severity": "high",
                    "blocking": True,
                },
                {
                    "pattern": r"\b(create|make|generate)\b(?!.*\b(image|video|animation)\b)",
                    "evidence": "Generic creation request without content type",
                    "severity": "medium",
                    "blocking": False,
                },
            ],
            AmbiguityType.SCOPE_AMBIGUOUS: [
                {
                    "pattern": r"\b(character|person)\b.*\b(scene|environment|background)\b",
                    "evidence": "Both character and scene elements mentioned",
                    "severity": "medium",
                    "blocking": False,
                },
                {
                    "pattern": r"\b(full|complete|entire)\b.*\b(episode|series|movie)\b",
                    "evidence": "Full episode request may be too complex",
                    "severity": "high",
                    "blocking": True,
                },
            ],
            AmbiguityType.CHARACTER_UNDEFINED: [
                {
                    "pattern": r"\b(character|person|girl|boy|man|woman)\b(?!.*\b[A-Z][a-z]+\b)",
                    "evidence": "Character mentioned without specific name or clear description",
                    "severity": "medium",
                    "blocking": False,
                },
                {
                    "pattern": r"\bnamed?\s+(\w+)\b.*\bbut\b",
                    "evidence": "Character name mentioned with contradictory information",
                    "severity": "medium",
                    "blocking": False,
                },
            ],
            AmbiguityType.DURATION_MISSING: [
                {
                    "pattern": r"\b(video|animation|scene|sequence)\b(?!.*\d+\s*(second|minute|sec|min)\b)",
                    "evidence": "Video request without duration specification",
                    "severity": "medium",
                    "blocking": False,
                },
                {
                    "pattern": r"\blong\b|\bshort\b(?!\s+\d+)",
                    "evidence": "Relative duration without specific time",
                    "severity": "low",
                    "blocking": False,
                },
            ],
            AmbiguityType.STYLE_CONFLICTING: [
                {
                    "pattern": r"\b(realistic|photorealistic)\b.*\b(cartoon|anime)\b",
                    "evidence": "Conflicting style requirements (realistic and cartoon)",
                    "severity": "high",
                    "blocking": True,
                },
                {
                    "pattern": r"\b(2d|flat)\b.*\b(3d|dimensional)\b",
                    "evidence": "Conflicting dimensionality requirements",
                    "severity": "high",
                    "blocking": True,
                },
            ],
            AmbiguityType.QUALITY_VAGUE: [
                {
                    "pattern": r"\b(good|nice|beautiful|amazing)\b(?!\s+(quality|resolution))",
                    "evidence": "Subjective quality descriptors without technical specification",
                    "severity": "low",
                    "blocking": False,
                }
            ],
            AmbiguityType.URGENCY_UNCLEAR: [
                {
                    "pattern": r"\b(soon|later|sometime|eventually)\b",
                    "evidence": "Vague timing requirements",
                    "severity": "low",
                    "blocking": False,
                }
            ],
            AmbiguityType.INSUFFICIENT_DETAIL: [
                {
                    "pattern": r"^.{1,20}$",  # Very short requests
                    "evidence": "Request is very brief and may lack detail",
                    "severity": "medium",
                    "blocking": False,
                }
            ],
            AmbiguityType.CONTRADICTORY_REQUIREMENTS: [
                {
                    "pattern": r"\b(fast|quick|immediate)\b.*\b(high|maximum|best)\s+quality\b",
                    "evidence": "Fast delivery requested with high quality (may be contradictory)",
                    "severity": "medium",
                    "blocking": False,
                }
            ],
        }

    def _initialize_context_patterns(self) -> Dict[str, List[str]]:
        """Initialize context detection patterns"""
        return {
            "anime_context": [
                r"\b(anime|manga|japanese|otaku|kawaii|senpai|chan|kun)\b",
                r"\b(studio ghibli|dragon ball|naruto|one piece|attack on titan)\b",
            ],
            "artistic_context": [
                r"\b(art|artistic|painting|drawing|sketch|digital art)\b",
                r"\b(style of|inspired by|in the style)\b",
            ],
            "technical_context": [
                r"\b(4k|8k|hd|resolution|dpi|pixels|render|gpu)\b",
                r"\b(blender|maya|photoshop|after effects)\b",
            ],
            "commercial_context": [
                r"\b(commercial|business|marketing|advertisement|brand)\b",
                r"\b(client|customer|deadline|budget)\b",
            ],
        }

    def detect_ambiguities(
        self, user_prompt: str, classification_result: Dict[str, Any] = None
    ) -> List[AmbiguityDetection]:
        """Detect ambiguities in user prompt and classification"""
        ambiguities = []

        # Text-based pattern detection
        text_ambiguities = self._detect_text_ambiguities(user_prompt)
        ambiguities.extend(text_ambiguities)

        # Classification-based detection
        if classification_result:
            classification_ambiguities = self._detect_classification_ambiguities(
                classification_result, user_prompt
            )
            ambiguities.extend(classification_ambiguities)

        # Context-based detection
        context_ambiguities = self._detect_context_ambiguities(user_prompt)
        ambiguities.extend(context_ambiguities)

        # Remove duplicates and sort by severity
        unique_ambiguities = self._deduplicate_ambiguities(ambiguities)
        return sorted(unique_ambiguities, key=lambda x: (x.severity, -x.confidence))

    def _detect_text_ambiguities(self, user_prompt: str) -> List[AmbiguityDetection]:
        """Detect ambiguities through text pattern analysis"""
        ambiguities = []

        for ambiguity_type, rules in self.detection_rules.items():
            for rule in rules:
                pattern = rule["pattern"]
                if re.search(pattern, user_prompt, re.IGNORECASE):
                    # Calculate confidence based on pattern match strength
                    confidence = self._calculate_pattern_confidence(
                        pattern, user_prompt
                    )

                    ambiguity = AmbiguityDetection(
                        ambiguity_type=ambiguity_type,
                        confidence=confidence,
                        description=rule["evidence"],
                        affected_fields=self._get_affected_fields(
                            ambiguity_type),
                        evidence=[f"Pattern match: {pattern}"],
                        severity=rule["severity"],
                        blocking=rule["blocking"],
                        context_clues=self._extract_context_clues(
                            user_prompt, ambiguity_type
                        ),
                    )
                    ambiguities.append(ambiguity)

        return ambiguities

    def _detect_classification_ambiguities(
        self, classification: Dict[str, Any], user_prompt: str
    ) -> List[AmbiguityDetection]:
        """Detect ambiguities in classification results"""
        ambiguities = []

        # Low confidence classification
        confidence = classification.get("confidence_score", 1.0)
        if confidence < 0.7:
            ambiguity = AmbiguityDetection(
                ambiguity_type=AmbiguityType.INSUFFICIENT_DETAIL,
                confidence=1.0 - confidence,
                description=f"Classification confidence is low ({confidence:.2f})",
                affected_fields=["overall_classification"],
                evidence=["Low confidence score from classification engine"],
                severity="medium" if confidence < 0.5 else "low",
                blocking=confidence < 0.4,
                context_clues={"confidence_score": confidence},
            )
            ambiguities.append(ambiguity)

        # Missing required fields
        required_fields = {
            "character_names": AmbiguityType.CHARACTER_UNDEFINED,
            "duration_seconds": AmbiguityType.DURATION_MISSING,
        }

        for field, ambiguity_type in required_fields.items():
            if (
                classification.get("content_type") == "video"
                and field == "duration_seconds"
                and not classification.get(field)
            ):

                ambiguity = AmbiguityDetection(
                    ambiguity_type=ambiguity_type,
                    confidence=0.8,
                    description=f"Required field '{field}' is missing for video generation",
                    affected_fields=[field],
                    evidence=[
                        f"Content type is video but {field} is not specified"],
                    severity="medium",
                    blocking=False,
                    context_clues={
                        "content_type": classification.get("content_type")},
                )
                ambiguities.append(ambiguity)

        return ambiguities

    def _detect_context_ambiguities(self, user_prompt: str) -> List[AmbiguityDetection]:
        """Detect ambiguities based on contextual analysis"""
        ambiguities = []

        # Detect context strength
        context_scores = {}
        for context_type, patterns in self.context_patterns.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, user_prompt, re.IGNORECASE))
                score += matches
            context_scores[context_type] = score

        # If multiple strong contexts exist, it may indicate ambiguity
        strong_contexts = [ctx for ctx,
                           score in context_scores.items() if score >= 2]
        if len(strong_contexts) > 1:
            ambiguity = AmbiguityDetection(
                ambiguity_type=AmbiguityType.SCOPE_AMBIGUOUS,
                confidence=0.6,
                description=f"Multiple strong contexts detected: {', '.join(strong_contexts)}",
                affected_fields=["generation_scope", "style_preference"],
                evidence=[f"Strong indicators for: {strong_contexts}"],
                severity="low",
                blocking=False,
                context_clues={"context_scores": context_scores},
            )
            ambiguities.append(ambiguity)

        return ambiguities

    def _calculate_pattern_confidence(self, pattern: str, text: str) -> float:
        """Calculate confidence score for pattern match"""
        matches = len(re.findall(pattern, text, re.IGNORECASE))
        text_length = len(text.split())

        # Base confidence from match count
        base_confidence = min(0.9, matches * 0.3)

        # Adjust based on text length (shorter text = higher confidence in pattern)
        length_factor = max(0.1, 1.0 - (text_length - 10) * 0.02)

        return min(0.95, base_confidence * length_factor)

    def _get_affected_fields(self, ambiguity_type: AmbiguityType) -> List[str]:
        """Get fields affected by ambiguity type"""
        field_mapping = {
            AmbiguityType.CONTENT_TYPE_UNCLEAR: ["content_type", "output_format"],
            AmbiguityType.SCOPE_AMBIGUOUS: ["generation_scope"],
            AmbiguityType.STYLE_CONFLICTING: ["style_preference"],
            AmbiguityType.CHARACTER_UNDEFINED: ["character_names"],
            AmbiguityType.DURATION_MISSING: ["duration_seconds", "frame_count"],
            AmbiguityType.QUALITY_VAGUE: ["quality_level", "complexity_level"],
            AmbiguityType.URGENCY_UNCLEAR: ["urgency_level"],
            AmbiguityType.TECHNICAL_INCOMPLETE: ["resolution", "output_format"],
            AmbiguityType.CONTRADICTORY_REQUIREMENTS: [
                "urgency_level",
                "quality_level",
            ],
            AmbiguityType.INSUFFICIENT_DETAIL: ["overall_classification"],
        }
        return field_mapping.get(ambiguity_type, ["general"])

    def _extract_context_clues(
        self, text: str, ambiguity_type: AmbiguityType
    ) -> Dict[str, Any]:
        """Extract context clues for ambiguity resolution"""
        clues = {}

        # Extract mentioned elements
        if "character" in text.lower():
            names = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", text)
            clues["potential_names"] = names

        # Extract timing indicators
        time_matches = re.findall(
            r"(\d+)\s*(second|minute|hour|sec|min)", text, re.IGNORECASE
        )
        if time_matches:
            clues["time_indicators"] = time_matches

        # Extract quality indicators
        quality_words = re.findall(
            r"\b(high|low|good|bad|best|worst|amazing|terrible|quality|hd|4k|8k)\b",
            text,
            re.IGNORECASE,
        )
        if quality_words:
            clues["quality_indicators"] = quality_words

        return clues

    def _deduplicate_ambiguities(
        self, ambiguities: List[AmbiguityDetection]
    ) -> List[AmbiguityDetection]:
        """Remove duplicate ambiguities"""
        seen = set()
        unique = []

        for ambiguity in ambiguities:
            key = (ambiguity.ambiguity_type, ambiguity.description)
            if key not in seen:
                seen.add(key)
                unique.append(ambiguity)

        return unique


class AmbiguityResolver:
    """Resolves detected ambiguities through various strategies"""

    def __init__(self, db_manager, echo_integration=None):
        self.db_manager = db_manager
        self.echo_integration = echo_integration
        self.resolution_strategies = self._initialize_resolution_strategies()
        self.resolution_cache = {}

    def _initialize_resolution_strategies(
        self,
    ) -> Dict[AmbiguityType, List[ResolutionAction]]:
        """Initialize resolution strategies for each ambiguity type"""
        return {
            AmbiguityType.CONTENT_TYPE_UNCLEAR: [
                ResolutionAction(
                    strategy=ResolutionStrategy.USER_CLARIFICATION,
                    action_type="question",
                    priority=1,
                    timeout_seconds=30,
                    question="What type of content would you like to create?",
                    options=[
                        "Image (still picture)",
                        "Video (animated sequence)",
                        "Both (image and video)",
                    ],
                    default_answer="Image (still picture)",
                ),
                ResolutionAction(
                    strategy=ResolutionStrategy.INTELLIGENT_DEFAULT,
                    action_type="default",
                    priority=5,
                    timeout_seconds=0,
                    default_value="image",
                    confidence_threshold=0.6,
                ),
            ],
            AmbiguityType.CHARACTER_UNDEFINED: [
                ResolutionAction(
                    strategy=ResolutionStrategy.USER_CLARIFICATION,
                    action_type="question",
                    priority=2,
                    timeout_seconds=45,
                    question="What would you like to name this character?",
                    validation_pattern=r"^[A-Za-z\s]{2,30}$",
                    default_answer="Unnamed Character",
                ),
                ResolutionAction(
                    strategy=ResolutionStrategy.INTELLIGENT_DEFAULT,
                    action_type="default",
                    priority=6,
                    timeout_seconds=0,
                    default_value="Unnamed Character",
                ),
            ],
            AmbiguityType.DURATION_MISSING: [
                ResolutionAction(
                    strategy=ResolutionStrategy.USER_CLARIFICATION,
                    action_type="question",
                    priority=2,
                    timeout_seconds=30,
                    question="How long should the video be?",
                    options=["5 seconds", "15 seconds",
                             "30 seconds", "1 minute"],
                    default_answer="15 seconds",
                ),
                ResolutionAction(
                    strategy=ResolutionStrategy.CONTEXT_INFERENCE,
                    action_type="inference",
                    priority=4,
                    timeout_seconds=0,
                    inference_rules=[
                        "action scene -> 15 seconds",
                        "dialogue scene -> 30 seconds",
                        "character intro -> 10 seconds",
                    ],
                ),
                ResolutionAction(
                    strategy=ResolutionStrategy.INTELLIGENT_DEFAULT,
                    action_type="default",
                    priority=7,
                    timeout_seconds=0,
                    default_value=15,
                ),
            ],
            AmbiguityType.STYLE_CONFLICTING: [
                ResolutionAction(
                    strategy=ResolutionStrategy.USER_CLARIFICATION,
                    action_type="question",
                    priority=1,
                    timeout_seconds=30,
                    question="Which visual style would you prefer?",
                    options=[
                        "Photorealistic Anime",
                        "Traditional 2D Anime",
                        "Western Cartoon",
                        "Artistic/Experimental",
                    ],
                    default_answer="Traditional 2D Anime",
                )
            ],
            AmbiguityType.SCOPE_AMBIGUOUS: [
                ResolutionAction(
                    strategy=ResolutionStrategy.TEMPLATE_SUGGESTION,
                    action_type="suggestion",
                    priority=2,
                    timeout_seconds=60,
                    suggested_templates=[
                        {"name": "Character Profile", "scope": "character_profile"},
                        {"name": "Character in Scene", "scope": "character_scene"},
                        {"name": "Environment Only", "scope": "environment"},
                    ],
                ),
                ResolutionAction(
                    strategy=ResolutionStrategy.USER_CLARIFICATION,
                    action_type="question",
                    priority=3,
                    timeout_seconds=45,
                    question="What's the main focus of your request?",
                    options=[
                        "Character design/profile",
                        "Character in a scene",
                        "Background/environment",
                        "Action sequence",
                    ],
                    default_answer="Character in a scene",
                ),
            ],
            AmbiguityType.QUALITY_VAGUE: [
                ResolutionAction(
                    strategy=ResolutionStrategy.INTELLIGENT_DEFAULT,
                    action_type="default",
                    priority=5,
                    timeout_seconds=0,
                    default_value="high",
                    confidence_threshold=0.8,
                )
            ],
            AmbiguityType.INSUFFICIENT_DETAIL: [
                ResolutionAction(
                    strategy=ResolutionStrategy.PROGRESSIVE_REFINEMENT,
                    action_type="question",
                    priority=3,
                    timeout_seconds=120,
                    question="Could you provide more details about what you'd like to create?",
                    metadata={
                        "follow_up_questions": [
                            "What should the main character look like?",
                            "What style are you aiming for?",
                            "Any specific mood or atmosphere?",
                        ]
                    },
                )
            ],
        }

    async def resolve_ambiguities(
        self, ambiguities: List[AmbiguityDetection], context: Dict[str, Any] = None
    ) -> List[ResolutionResult]:
        """Resolve multiple ambiguities using appropriate strategies"""
        results = []

        # Sort ambiguities by priority (blocking first, then by severity)
        sorted_ambiguities = sorted(
            ambiguities, key=lambda x: (
                not x.blocking, x.severity, -x.confidence)
        )

        for ambiguity in sorted_ambiguities:
            try:
                result = await self._resolve_single_ambiguity(ambiguity, context)
                results.append(result)

                # Update context with resolved value for subsequent resolutions
                if result.resolved_value is not None and context:
                    field_name = (
                        ambiguity.affected_fields[0]
                        if ambiguity.affected_fields
                        else "general"
                    )
                    context[field_name] = result.resolved_value

            except Exception as e:
                logger.error(
                    f"Failed to resolve ambiguity {ambiguity.ambiguity_type}: {e}"
                )
                # Create failed resolution result
                results.append(
                    ResolutionResult(
                        ambiguity_type=ambiguity.ambiguity_type,
                        resolution_strategy=ResolutionStrategy.FALLBACK_WORKFLOW,
                        resolved_value=None,
                        confidence=0.0,
                        user_interaction_required=False,
                        resolution_time_seconds=0.0,
                        metadata={"error": str(e)},
                    )
                )

        return results

    async def _resolve_single_ambiguity(
        self, ambiguity: AmbiguityDetection, context: Dict[str, Any]
    ) -> ResolutionResult:
        """Resolve a single ambiguity"""
        start_time = time.time()

        # Get resolution strategies for this ambiguity type
        strategies = self.resolution_strategies.get(
            ambiguity.ambiguity_type, [])

        if not strategies:
            # No specific strategies, use fallback
            return self._create_fallback_resolution(ambiguity, start_time)

        # Try strategies in priority order
        for strategy in sorted(strategies, key=lambda x: x.priority):
            try:
                result = await self._execute_resolution_strategy(
                    strategy, ambiguity, context
                )
                if result:
                    result.resolution_time_seconds = time.time() - start_time
                    return result
            except Exception as e:
                logger.warning(
                    f"Resolution strategy {strategy.strategy} failed: {e}")
                continue

        # All strategies failed, create fallback
        return self._create_fallback_resolution(ambiguity, start_time)

    async def _execute_resolution_strategy(
        self,
        strategy: ResolutionAction,
        ambiguity: AmbiguityDetection,
        context: Dict[str, Any],
    ) -> Optional[ResolutionResult]:
        """Execute a specific resolution strategy"""

        if strategy.strategy == ResolutionStrategy.USER_CLARIFICATION:
            return await self._resolve_via_user_clarification(
                strategy, ambiguity, context
            )

        elif strategy.strategy == ResolutionStrategy.INTELLIGENT_DEFAULT:
            return await self._resolve_via_intelligent_default(
                strategy, ambiguity, context
            )

        elif strategy.strategy == ResolutionStrategy.CONTEXT_INFERENCE:
            return await self._resolve_via_context_inference(
                strategy, ambiguity, context
            )

        elif strategy.strategy == ResolutionStrategy.TEMPLATE_SUGGESTION:
            return await self._resolve_via_template_suggestion(
                strategy, ambiguity, context
            )

        elif strategy.strategy == ResolutionStrategy.PROGRESSIVE_REFINEMENT:
            return await self._resolve_via_progressive_refinement(
                strategy, ambiguity, context
            )

        else:
            return None

    async def _resolve_via_user_clarification(
        self,
        strategy: ResolutionAction,
        ambiguity: AmbiguityDetection,
        context: Dict[str, Any],
    ) -> ResolutionResult:
        """Resolve via user clarification (returns structure for frontend handling)"""
        # This creates a structure that the frontend can use to prompt the user
        clarification_data = {
            "question": strategy.question,
            "options": strategy.options,
            "default_answer": strategy.default_answer,
            "validation_pattern": strategy.validation_pattern,
            "timeout_seconds": strategy.timeout_seconds,
            "priority": "high" if ambiguity.blocking else "medium",
            "explanation": f"This helps resolve: {ambiguity.description}",
        }

        return ResolutionResult(
            ambiguity_type=ambiguity.ambiguity_type,
            resolution_strategy=ResolutionStrategy.USER_CLARIFICATION,
            resolved_value=clarification_data,
            confidence=0.9,
            user_interaction_required=True,
            resolution_time_seconds=0.0,
            metadata={
                "clarification_data": clarification_data,
                "requires_user_input": True,
            },
        )

    async def _resolve_via_intelligent_default(
        self,
        strategy: ResolutionAction,
        ambiguity: AmbiguityDetection,
        context: Dict[str, Any],
    ) -> ResolutionResult:
        """Resolve using intelligent defaults"""
        # Use context and user history to determine smart default
        smart_default = await self._calculate_smart_default(
            ambiguity, strategy.default_value, context
        )

        confidence = self._calculate_default_confidence(ambiguity, context)

        if confidence >= strategy.confidence_threshold:
            return ResolutionResult(
                ambiguity_type=ambiguity.ambiguity_type,
                resolution_strategy=ResolutionStrategy.INTELLIGENT_DEFAULT,
                resolved_value=smart_default,
                confidence=confidence,
                user_interaction_required=False,
                resolution_time_seconds=0.0,
                metadata={
                    "default_reason": "Based on user history and context patterns",
                    "confidence_threshold": strategy.confidence_threshold,
                },
            )

        return None  # Confidence too low for default

    async def _resolve_via_context_inference(
        self,
        strategy: ResolutionAction,
        ambiguity: AmbiguityDetection,
        context: Dict[str, Any],
    ) -> ResolutionResult:
        """Resolve via context inference using rules"""
        if not strategy.inference_rules:
            return None

        # Apply inference rules
        for rule in strategy.inference_rules:
            if " -> " in rule:
                condition, outcome = rule.split(" -> ")
                if self._check_inference_condition(condition, context):
                    return ResolutionResult(
                        ambiguity_type=ambiguity.ambiguity_type,
                        resolution_strategy=ResolutionStrategy.CONTEXT_INFERENCE,
                        resolved_value=outcome.strip(),
                        confidence=0.75,
                        user_interaction_required=False,
                        resolution_time_seconds=0.0,
                        metadata={
                            "inference_rule": rule,
                            "matched_condition": condition,
                        },
                    )

        return None

    async def _resolve_via_template_suggestion(
        self,
        strategy: ResolutionAction,
        ambiguity: AmbiguityDetection,
        context: Dict[str, Any],
    ) -> ResolutionResult:
        """Resolve by suggesting relevant templates"""
        if not strategy.suggested_templates:
            return None

        # Find best matching template based on context
        best_template = self._find_best_template(
            strategy.suggested_templates, context)

        if best_template:
            return ResolutionResult(
                ambiguity_type=ambiguity.ambiguity_type,
                resolution_strategy=ResolutionStrategy.TEMPLATE_SUGGESTION,
                resolved_value=best_template,
                confidence=0.8,
                user_interaction_required=True,  # User needs to confirm template
                resolution_time_seconds=0.0,
                metadata={
                    "suggested_templates": strategy.suggested_templates,
                    "best_match": best_template,
                },
            )

        return None

    async def _resolve_via_progressive_refinement(
        self,
        strategy: ResolutionAction,
        ambiguity: AmbiguityDetection,
        context: Dict[str, Any],
    ) -> ResolutionResult:
        """Resolve via progressive refinement (multi-step clarification)"""
        # Create a progressive refinement plan
        refinement_plan = {
            "initial_question": strategy.question,
            "follow_up_questions": strategy.metadata.get("follow_up_questions", []),
            "expected_iterations": len(strategy.metadata.get("follow_up_questions", []))
            + 1,
        }

        return ResolutionResult(
            ambiguity_type=ambiguity.ambiguity_type,
            resolution_strategy=ResolutionStrategy.PROGRESSIVE_REFINEMENT,
            resolved_value=refinement_plan,
            confidence=0.85,
            user_interaction_required=True,
            resolution_time_seconds=0.0,
            metadata={"refinement_plan": refinement_plan,
                      "progressive_approach": True},
        )

    async def _calculate_smart_default(
        self, ambiguity: AmbiguityDetection, base_default: Any, context: Dict[str, Any]
    ) -> Any:
        """Calculate smart default based on context and user history"""
        # TODO: Implement user preference learning
        # For now, use simple context-based logic

        if ambiguity.ambiguity_type == AmbiguityType.CONTENT_TYPE_UNCLEAR:
            # If video keywords present but no duration, lean towards image
            user_prompt = context.get("user_prompt", "")
            if re.search(r"\b(video|animation)\b", user_prompt, re.IGNORECASE):
                if not re.search(r"\d+\s*(second|minute)", user_prompt, re.IGNORECASE):
                    return "image"  # No duration specified, probably meant image
                return "video"
            return "image"  # Default to image for ambiguous cases

        elif ambiguity.ambiguity_type == AmbiguityType.DURATION_MISSING:
            # Infer duration from scope
            scope = context.get("generation_scope", "")
            if "action" in scope:
                return 15  # Action sequences are typically short
            elif "dialogue" in scope:
                return 30  # Dialogue needs more time
            else:
                return 10  # Generic default

        return base_default

    def _calculate_default_confidence(
        self, ambiguity: AmbiguityDetection, context: Dict[str, Any]
    ) -> float:
        """Calculate confidence in using default resolution"""
        base_confidence = 0.6

        # Adjust based on context richness
        context_indicators = len([v for v in context.values() if v])
        confidence_boost = min(0.3, context_indicators * 0.05)

        # Adjust based on ambiguity severity
        severity_penalty = {"low": 0.0, "medium": -0.1, "high": -0.2}.get(
            ambiguity.severity, 0.0
        )

        # Adjust based on user preference history (placeholder)
        # TODO: Implement actual user preference lookup
        preference_boost = 0.1  # Assume we have some user history

        return min(
            0.95,
            base_confidence + confidence_boost + severity_penalty + preference_boost,
        )

    def _check_inference_condition(
        self, condition: str, context: Dict[str, Any]
    ) -> bool:
        """Check if inference condition is met"""
        condition_lower = condition.lower()

        # Simple pattern matching for common conditions
        if "action" in condition_lower:
            return any("action" in str(v).lower() for v in context.values())
        elif "dialogue" in condition_lower:
            return any("dialogue" in str(v).lower() for v in context.values())
        elif "character" in condition_lower:
            return any("character" in str(v).lower() for v in context.values())

        return False

    def _find_best_template(
        self, templates: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find best matching template based on context"""
        if not templates:
            return None

        # Simple scoring based on context keywords
        best_template = None
        best_score = 0.0

        for template in templates:
            score = 0.0
            template_name = template.get("name", "").lower()

            # Score based on context matches
            for key, value in context.items():
                if value and str(value).lower() in template_name:
                    score += 1.0

            if score > best_score:
                best_score = score
                best_template = template

        return best_template or templates[0]  # Return first if no clear winner

    def _create_fallback_resolution(
        self, ambiguity: AmbiguityDetection, start_time: float
    ) -> ResolutionResult:
        """Create fallback resolution when all strategies fail"""
        fallback_defaults = {
            AmbiguityType.CONTENT_TYPE_UNCLEAR: "image",
            AmbiguityType.CHARACTER_UNDEFINED: "Unnamed Character",
            AmbiguityType.DURATION_MISSING: 15,
            AmbiguityType.STYLE_CONFLICTING: "traditional_anime",
            AmbiguityType.QUALITY_VAGUE: "standard",
            AmbiguityType.SCOPE_AMBIGUOUS: "character_scene",
        }

        fallback_value = fallback_defaults.get(
            ambiguity.ambiguity_type, "default")

        return ResolutionResult(
            ambiguity_type=ambiguity.ambiguity_type,
            resolution_strategy=ResolutionStrategy.FALLBACK_WORKFLOW,
            resolved_value=fallback_value,
            confidence=0.3,
            user_interaction_required=False,
            resolution_time_seconds=time.time() - start_time,
            metadata={
                "fallback_reason": "All resolution strategies failed",
                "fallback_value": fallback_value,
            },
        )


class AmbiguityResolutionOrchestrator:
    """Orchestrates the complete ambiguity detection and resolution process"""

    def __init__(self, db_manager, echo_integration=None):
        self.detector = AmbiguityDetector()
        self.resolver = AmbiguityResolver(db_manager, echo_integration)

    async def process_request(
        self,
        user_prompt: str,
        classification_result: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Process request for ambiguities and generate resolution plan"""

        # Detect ambiguities
        ambiguities = self.detector.detect_ambiguities(
            user_prompt, classification_result
        )

        if not ambiguities:
            return {
                "has_ambiguities": False,
                "ambiguities": [],
                "resolutions": [],
                "requires_user_interaction": False,
                "confidence": classification_result.get("confidence_score", 1.0),
            }

        # Resolve ambiguities
        context = context or {"user_prompt": user_prompt}
        resolutions = await self.resolver.resolve_ambiguities(ambiguities, context)

        # Determine if user interaction is required
        requires_interaction = any(
            r.user_interaction_required for r in resolutions)

        # Calculate overall confidence after resolution
        resolved_confidence = self._calculate_overall_confidence(resolutions)

        return {
            "has_ambiguities": True,
            "ambiguities": [
                {
                    "type": amb.ambiguity_type.value,
                    "description": amb.description,
                    "severity": amb.severity,
                    "blocking": amb.blocking,
                    "confidence": amb.confidence,
                    "affected_fields": amb.affected_fields,
                }
                for amb in ambiguities
            ],
            "resolutions": [
                {
                    "ambiguity_type": res.ambiguity_type.value,
                    "strategy": res.resolution_strategy.value,
                    "resolved_value": res.resolved_value,
                    "confidence": res.confidence,
                    "requires_user_input": res.user_interaction_required,
                    "metadata": res.metadata,
                }
                for res in resolutions
            ],
            "requires_user_interaction": requires_interaction,
            "confidence": resolved_confidence,
            "blocking_issues": [amb for amb in ambiguities if amb.blocking],
        }

    def _calculate_overall_confidence(
        self, resolutions: List[ResolutionResult]
    ) -> float:
        """Calculate overall confidence after resolution"""
        if not resolutions:
            return 1.0

        # Weight resolutions by their confidence and whether they require user input
        total_weight = 0.0
        weighted_sum = 0.0

        for resolution in resolutions:
            weight = 1.0
            if resolution.user_interaction_required:
                weight *= 0.8  # Lower weight for unresolved ambiguities

            weighted_sum += resolution.confidence * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.5


# Factory function
def create_ambiguity_resolution_system(db_manager, echo_integration=None):
    """Create configured ambiguity resolution system"""
    return AmbiguityResolutionOrchestrator(db_manager, echo_integration)


# Testing function
async def test_ambiguity_system():
    """Test the ambiguity resolution system"""

    # Mock database manager
    class MockDBManager:
        async def execute_query_robust(self, *args, **kwargs):
            return []

    system = create_ambiguity_resolution_system(MockDBManager())

    test_cases = [
        {
            "prompt": "Create a video",  # Missing duration, scope unclear
            "classification": {"content_type": "video", "confidence_score": 0.4},
        },
        {
            "prompt": "Make a realistic anime cartoon character",  # Style conflict
            "classification": {"content_type": "image", "confidence_score": 0.6},
        },
        {
            "prompt": "Character with blue hair",  # Character name missing
            "classification": {"content_type": "image", "confidence_score": 0.7},
        },
    ]

    for i, test in enumerate(test_cases):
        print(f"\n--- Test Case {i+1}: {test['prompt']} ---")

        result = await system.process_request(test["prompt"], test["classification"])

        print(f"Has ambiguities: {result['has_ambiguities']}")
        print(f"Requires interaction: {result['requires_user_interaction']}")
        print(f"Overall confidence: {result['confidence']:.2f}")

        for ambiguity in result.get("ambiguities", []):
            print(
                f"  - {ambiguity['type']}: {ambiguity['description']} ({ambiguity['severity']})"
            )

        for resolution in result.get("resolutions", []):
            print(
                f"  → {resolution['strategy']}: {resolution['resolved_value']} (conf: {resolution['confidence']:.2f})"
            )


if __name__ == "__main__":
    asyncio.run(test_ambiguity_system())
