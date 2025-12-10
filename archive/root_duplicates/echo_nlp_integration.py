#!/usr/bin/env python3
"""
Enhanced Natural Language Processing Integration with Echo Brain
Provides advanced intent analysis, contextual understanding, and prompt optimization
specifically designed for anime production workflows.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ContextualAnalysis:
    """Contextual analysis result from Echo Brain"""
    intent_confidence: float
    semantic_categories: List[str]
    character_entities: List[Dict[str, Any]]
    scene_elements: List[str]
    artistic_style_indicators: List[str]
    temporal_indicators: List[str]
    quality_indicators: List[str]
    complexity_markers: List[str]
    ambiguity_points: List[str]
    suggested_clarifications: List[str]


@dataclass
class PromptOptimization:
    """Prompt optimization result"""
    optimized_prompt: str
    optimization_type: str  # "enhancement", "clarification", "style_injection"
    confidence_improvement: float
    added_elements: List[str]
    removed_elements: List[str]
    style_adjustments: List[str]
    technical_improvements: List[str]


class EchoNLPProcessor:
    """Advanced NLP processor using Echo Brain for anime production"""

    def __init__(self, echo_base_url: str = "http://localhost:8309"):
        self.echo_base_url = echo_base_url
        self.session = None

        # Cache for frequent analyses
        self.analysis_cache = {}
        self.cache_ttl = 300  # 5 minutes

        # Model selection for different analysis types
        self.model_mapping = {
            "intent_analysis": "qwen2.5-coder:32b",
            "contextual_analysis": "llama3.1:70b",
            "prompt_optimization": "mixtral:8x7b",
            "character_extraction": "qwen2.5-coder:32b",
            "style_analysis": "llama3.1:8b",
            "quick_classification": "llama3.2:latest"
        }

    async def _ensure_session(self):
        """Ensure aiohttp session is available"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def _query_echo(self, prompt: str, analysis_type: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Query Echo Brain with specific model selection"""
        await self._ensure_session()

        # Check cache first
        cache_key = f"{analysis_type}:{hash(prompt)}"
        if cache_key in self.analysis_cache:
            cached_result, timestamp = self.analysis_cache[cache_key]
            if datetime.utcnow() - timestamp < timedelta(seconds=self.cache_ttl):
                return cached_result

        try:
            model = self.model_mapping.get(analysis_type, "qwen2.5-coder:32b")

            payload = {
                "query": prompt,
                "context": f"anime_nlp_{analysis_type}",
                "intelligence_level": "expert",
                "model": model,
                "metadata": {
                    "analysis_type": analysis_type,
                    "context": context or {}
                }
            }

            async with self.session.post(
                f"{self.echo_base_url}/api/echo/query",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    response_text = result.get("response", "")

                    # Parse response based on analysis type
                    parsed_result = self._parse_echo_response(response_text, analysis_type)

                    # Cache the result
                    self.analysis_cache[cache_key] = (parsed_result, datetime.utcnow())

                    return parsed_result
                else:
                    logger.error(f"Echo query failed: {response.status}")
                    return {"error": "echo_query_failed", "status": response.status}

        except Exception as e:
            logger.error(f"Echo NLP integration error: {e}")
            return {"error": "echo_integration_failed", "details": str(e)}

    def _parse_echo_response(self, response_text: str, analysis_type: str) -> Dict[str, Any]:
        """Parse Echo Brain response based on analysis type"""
        try:
            # Try to parse as JSON first
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Fallback to text parsing
            return self._parse_text_response(response_text, analysis_type)

    def _parse_text_response(self, text: str, analysis_type: str) -> Dict[str, Any]:
        """Parse text response when JSON parsing fails"""
        result = {"raw_response": text}

        if analysis_type == "intent_analysis":
            result.update(self._extract_intent_from_text(text))
        elif analysis_type == "contextual_analysis":
            result.update(self._extract_context_from_text(text))
        elif analysis_type == "prompt_optimization":
            result.update(self._extract_optimization_from_text(text))
        elif analysis_type == "character_extraction":
            result.update(self._extract_characters_from_text(text))
        elif analysis_type == "style_analysis":
            result.update(self._extract_style_from_text(text))

        return result

    def _extract_intent_from_text(self, text: str) -> Dict[str, Any]:
        """Extract intent information from text response"""
        intent_data = {
            "content_type": "image",
            "generation_scope": "character_profile",
            "confidence_score": 0.5
        }

        # Look for content type indicators
        if any(word in text.lower() for word in ["video", "animation", "sequence", "movement"]):
            intent_data["content_type"] = "video"
        elif any(word in text.lower() for word in ["audio", "voice", "sound", "music"]):
            intent_data["content_type"] = "audio"

        # Look for scope indicators
        if any(word in text.lower() for word in ["character", "profile", "design"]):
            intent_data["generation_scope"] = "character_profile"
        elif any(word in text.lower() for word in ["scene", "environment", "location"]):
            intent_data["generation_scope"] = "character_scene"
        elif any(word in text.lower() for word in ["action", "fight", "battle"]):
            intent_data["generation_scope"] = "action_sequence"
        elif any(word in text.lower() for word in ["episode", "full", "complete"]):
            intent_data["generation_scope"] = "full_episode"

        return intent_data

    def _extract_context_from_text(self, text: str) -> Dict[str, Any]:
        """Extract contextual information from text response"""
        return {
            "semantic_categories": self._extract_categories(text),
            "character_entities": self._extract_character_entities(text),
            "scene_elements": self._extract_scene_elements(text),
            "artistic_style_indicators": self._extract_style_indicators(text),
            "temporal_indicators": self._extract_temporal_indicators(text),
            "ambiguity_points": self._identify_ambiguities(text)
        }

    def _extract_optimization_from_text(self, text: str) -> Dict[str, Any]:
        """Extract optimization suggestions from text response"""
        lines = text.split('\n')
        optimized_prompt = ""
        added_elements = []

        for line in lines:
            if "optimized" in line.lower() or "improved" in line.lower():
                optimized_prompt = line.strip()
            elif "add" in line.lower() or "include" in line.lower():
                added_elements.append(line.strip())

        return {
            "optimized_prompt": optimized_prompt or text[:200],
            "added_elements": added_elements,
            "confidence_improvement": 0.2
        }

    def _extract_categories(self, text: str) -> List[str]:
        """Extract semantic categories from text"""
        categories = []
        category_patterns = {
            "character_description": r"\b(appearance|looks|description|design)\b",
            "action": r"\b(action|movement|fighting|running|jumping)\b",
            "emotion": r"\b(happy|sad|angry|excited|calm|serious)\b",
            "setting": r"\b(background|environment|location|setting)\b",
            "style": r"\b(anime|realistic|cartoon|artistic|detailed)\b"
        }

        for category, pattern in category_patterns.items():
            if re.search(pattern, text.lower()):
                categories.append(category)

        return categories

    def _extract_character_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract character entities and their properties"""
        entities = []

        # Look for character name patterns
        name_patterns = [
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:with|has|is)\b",
            r"\bcharacter\s+named\s+([A-Z][a-z]+)\b",
            r"\b([A-Z][a-z]+)\s+(?:standing|sitting|fighting|running)\b"
        ]

        for pattern in name_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    name = match[0]
                else:
                    name = match

                if len(name) > 2 and name not in [e.get("name", "") for e in entities]:
                    entities.append({
                        "name": name,
                        "type": "character",
                        "confidence": 0.8,
                        "context": self._extract_character_context(text, name)
                    })

        return entities

    def _extract_character_context(self, text: str, character_name: str) -> Dict[str, Any]:
        """Extract context around a character name"""
        context = {}

        # Look for appearance descriptions near the character name
        name_pos = text.lower().find(character_name.lower())
        if name_pos != -1:
            # Get text around the name (50 chars before and after)
            start = max(0, name_pos - 50)
            end = min(len(text), name_pos + len(character_name) + 50)
            surrounding_text = text[start:end]

            # Extract appearance indicators
            appearance_patterns = {
                "hair_color": r"\b(blue|red|black|white|silver|gold|green|purple|pink|brown|blonde)\s+hair\b",
                "eye_color": r"\b(blue|red|black|white|silver|gold|green|purple|pink|brown|hazel)\s+eyes?\b",
                "clothing": r"\b(wearing|dressed in|outfit|uniform|costume)\s+([^.]+)",
                "age": r"\b(young|old|teenage|adult|child|elderly)\b"
            }

            for attr, pattern in appearance_patterns.items():
                match = re.search(pattern, surrounding_text.lower())
                if match:
                    context[attr] = match.group(1) if len(match.groups()) == 1 else match.group(2)

        return context

    def _extract_scene_elements(self, text: str) -> List[str]:
        """Extract scene elements from text"""
        elements = []

        scene_patterns = [
            r"\b(in|at|on|near|by)\s+(?:a|an|the)?\s*([^,.\n]+)",
            r"\b(background|environment|setting|location):\s*([^,.\n]+)",
            r"\b(cyberpunk|fantasy|modern|medieval|futuristic|urban|rural)\s+(city|world|setting|environment)"
        ]

        for pattern in scene_patterns:
            matches = re.findall(pattern, text.lower())
            for match in matches:
                if isinstance(match, tuple) and len(match) > 1:
                    element = match[1].strip()
                    if len(element) > 3 and element not in elements:
                        elements.append(element)

        return elements

    def _extract_style_indicators(self, text: str) -> List[str]:
        """Extract artistic style indicators"""
        indicators = []

        style_patterns = {
            "photorealistic": r"\b(photorealistic|realistic|detailed|3d|rendered)\b",
            "traditional_anime": r"\b(anime|manga|japanese|2d|cel.?shaded)\b",
            "cartoon": r"\b(cartoon|western|disney|pixar)\b",
            "artistic": r"\b(artistic|experimental|abstract|creative)\b",
            "cinematic": r"\b(cinematic|movie|film|dramatic)\b",
            "high_quality": r"\b(high.?quality|detailed|professional|masterpiece)\b"
        }

        for style, pattern in style_patterns.items():
            if re.search(pattern, text.lower()):
                indicators.append(style)

        return indicators

    def _extract_temporal_indicators(self, text: str) -> List[str]:
        """Extract temporal/timing indicators"""
        indicators = []

        temporal_patterns = [
            r"\b(\d+)\s*(second|minute|hour)s?\b",
            r"\b(now|immediately|asap|urgent|soon|later|tomorrow)\b",
            r"\b(quick|fast|slow|gradual)\b"
        ]

        for pattern in temporal_patterns:
            matches = re.findall(pattern, text.lower())
            for match in matches:
                if isinstance(match, tuple):
                    indicators.append(" ".join(match))
                else:
                    indicators.append(match)

        return indicators

    def _identify_ambiguities(self, text: str) -> List[str]:
        """Identify potential ambiguities in the request"""
        ambiguities = []

        # Check for multiple conflicting indicators
        if "image" in text.lower() and "video" in text.lower():
            ambiguities.append("content_type_conflict")

        # Check for missing essential information
        if any(word in text.lower() for word in ["character", "person"]) and not re.search(r"\b[A-Z][a-z]+\b", text):
            ambiguities.append("character_name_missing")

        if "video" in text.lower() and not re.search(r"\d+\s*(second|minute)", text.lower()):
            ambiguities.append("duration_not_specified")

        # Check for vague style descriptions
        if not any(style in text.lower() for style in ["anime", "realistic", "cartoon", "artistic"]):
            ambiguities.append("style_not_specified")

        return ambiguities

    async def perform_intent_analysis(self, user_prompt: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Perform comprehensive intent analysis"""
        analysis_prompt = f"""
Analyze this anime production request for intent classification. Respond with JSON only.

Request: "{user_prompt}"

Analyze and classify:
1. content_type: "image", "video", "audio", or "mixed_media"
2. generation_scope: "character_profile", "character_scene", "environment", "action_sequence", "dialogue_scene", "full_episode", or "batch_generation"
3. style_preference: "photorealistic_anime", "traditional_anime", "cartoon", "artistic", "chibi", "cinematic", or "sketch"
4. urgency_level: "immediate", "urgent", "standard", "scheduled", or "batch_processing"
5. complexity_level: "simple", "moderate", "complex", or "expert"
6. character_names: array of character names found
7. duration_seconds: estimated duration for video content (null for images)
8. quality_level: "draft", "standard", "high", or "maximum"
9. confidence_score: 0.0-1.0 confidence in classification
10. ambiguity_flags: array of unclear aspects needing clarification
11. processed_prompt: optimized version of the original prompt
12. target_workflow: recommended generation workflow

Context: {json.dumps(context or {}, default=str)}
"""

        return await self._query_echo(analysis_prompt, "intent_analysis", context)

    async def perform_contextual_analysis(self, user_prompt: str) -> ContextualAnalysis:
        """Perform deep contextual analysis"""
        analysis_prompt = f"""
Perform deep contextual analysis of this anime production request:

"{user_prompt}"

Extract and analyze:
1. Semantic categories (character_description, action, emotion, setting, style)
2. Character entities with properties (name, appearance, role)
3. Scene elements (background, objects, atmosphere)
4. Artistic style indicators (visual style cues)
5. Temporal indicators (timing, urgency, duration)
6. Quality indicators (detail level, quality expectations)
7. Complexity markers (technical complexity indicators)
8. Ambiguity points (unclear or conflicting elements)
9. Suggested clarifications (questions to resolve ambiguities)

Respond with detailed JSON analysis.
"""

        result = await self._query_echo(analysis_prompt, "contextual_analysis")

        # Convert to ContextualAnalysis object
        return ContextualAnalysis(
            intent_confidence=result.get("intent_confidence", 0.5),
            semantic_categories=result.get("semantic_categories", []),
            character_entities=result.get("character_entities", []),
            scene_elements=result.get("scene_elements", []),
            artistic_style_indicators=result.get("artistic_style_indicators", []),
            temporal_indicators=result.get("temporal_indicators", []),
            quality_indicators=result.get("quality_indicators", []),
            complexity_markers=result.get("complexity_markers", []),
            ambiguity_points=result.get("ambiguity_points", []),
            suggested_clarifications=result.get("suggested_clarifications", [])
        )

    async def optimize_prompt(self, original_prompt: str, target_style: str = "anime",
                            target_quality: str = "high") -> PromptOptimization:
        """Optimize prompt for better generation results"""
        optimization_prompt = f"""
Optimize this anime generation prompt for better results:

Original prompt: "{original_prompt}"
Target style: {target_style}
Target quality: {target_quality}

Optimization goals:
1. Enhance clarity and specificity
2. Add appropriate anime/artistic terminology
3. Include quality modifiers
4. Improve technical specifications
5. Remove ambiguous or conflicting elements

Provide:
1. optimized_prompt: The improved version
2. optimization_type: "enhancement", "clarification", or "style_injection"
3. confidence_improvement: Estimated improvement (0.0-1.0)
4. added_elements: List of elements added
5. removed_elements: List of elements removed
6. style_adjustments: Style-specific improvements
7. technical_improvements: Technical specification improvements

Respond with JSON.
"""

        result = await self._query_echo(optimization_prompt, "prompt_optimization")

        return PromptOptimization(
            optimized_prompt=result.get("optimized_prompt", original_prompt),
            optimization_type=result.get("optimization_type", "enhancement"),
            confidence_improvement=result.get("confidence_improvement", 0.1),
            added_elements=result.get("added_elements", []),
            removed_elements=result.get("removed_elements", []),
            style_adjustments=result.get("style_adjustments", []),
            technical_improvements=result.get("technical_improvements", [])
        )

    async def extract_character_details(self, user_prompt: str) -> List[Dict[str, Any]]:
        """Extract detailed character information"""
        extraction_prompt = f"""
Extract character details from this anime request:

"{user_prompt}"

For each character mentioned, provide:
1. name: Character name
2. physical_description: Appearance details
3. personality_traits: Personality indicators
4. role: Role in the scene/story
5. relationships: Relationships to other characters
6. appearance_confidence: Confidence in appearance details (0.0-1.0)
7. context_clues: Additional context about the character

Respond with JSON array of character objects.
"""

        result = await self._query_echo(extraction_prompt, "character_extraction")

        if isinstance(result, dict) and "characters" in result:
            return result["characters"]
        elif isinstance(result, list):
            return result
        else:
            return []

    async def analyze_style_requirements(self, user_prompt: str) -> Dict[str, Any]:
        """Analyze style and quality requirements"""
        style_prompt = f"""
Analyze style and quality requirements from this request:

"{user_prompt}"

Determine:
1. visual_style: Primary visual style (anime, realistic, cartoon, artistic, etc.)
2. quality_level: Required quality level (draft, standard, high, maximum)
3. art_direction: Specific art direction notes
4. technical_requirements: Technical specifications needed
5. post_processing: Recommended post-processing steps
6. reference_styles: Similar styles or artists to reference
7. color_palette: Preferred color schemes
8. lighting_style: Lighting preferences
9. composition_notes: Composition suggestions

Respond with detailed JSON analysis.
"""

        return await self._query_echo(style_prompt, "style_analysis")

    async def generate_clarification_questions(self, ambiguities: List[str],
                                             context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Generate clarification questions for ambiguous requests"""
        question_prompt = f"""
Generate clarification questions for these ambiguities:

Ambiguities: {json.dumps(ambiguities)}
Context: {json.dumps(context or {}, default=str)}

For each ambiguity, provide:
1. question: Clear question to resolve the ambiguity
2. options: Array of possible answer options (if applicable)
3. priority: "high", "medium", or "low" priority
4. default_answer: Suggested default if user doesn't respond
5. explanation: Brief explanation of why this matters

Respond with JSON array of clarification objects.
"""

        result = await self._query_echo(question_prompt, "intent_analysis")

        if isinstance(result, dict) and "clarifications" in result:
            return result["clarifications"]
        elif isinstance(result, list):
            return result
        else:
            return []

    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()


# Example usage and testing
async def test_nlp_integration():
    """Test the NLP integration with example scenarios"""
    nlp = EchoNLPProcessor()

    test_prompts = [
        "Create a character named Kai with silver hair and blue eyes",
        "Generate a 30-second action scene with Kai fighting robots",
        "Make a photorealistic anime portrait of a girl with pink hair",
        "Create background art for a cyberpunk city at night",
        "I want a video of someone running"  # Ambiguous example
    ]

    try:
        for prompt in test_prompts:
            print(f"\n--- Analyzing: {prompt} ---")

            # Intent analysis
            intent = await nlp.perform_intent_analysis(prompt)
            print(f"Intent: {intent.get('content_type', 'unknown')} - {intent.get('generation_scope', 'unknown')}")
            print(f"Confidence: {intent.get('confidence_score', 0)}")

            # Contextual analysis
            context = await nlp.perform_contextual_analysis(prompt)
            print(f"Characters: {[c.get('name', 'unknown') for c in context.character_entities]}")
            print(f"Style indicators: {context.artistic_style_indicators}")

            # Prompt optimization
            optimization = await nlp.optimize_prompt(prompt)
            print(f"Optimized: {optimization.optimized_prompt}")

            if context.ambiguity_points:
                print(f"Ambiguities: {context.ambiguity_points}")

    except Exception as e:
        print(f"Test failed: {e}")
    finally:
        await nlp.close()


if __name__ == "__main__":
    asyncio.run(test_nlp_integration())