"""
Atmosphere Engine
Professional atmosphere and mood creation for anime scenes
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json
import random

from .atmosphere_data import (
    ATMOSPHERE_TEMPLATES,
    WEATHER_PATTERNS,
    ENVIRONMENTAL_EFFECTS,
    SENSORY_ELEMENTS,
    TIME_WEATHER_MAP,
    ENVIRONMENT_KEYWORDS,
    INDOOR_KEYWORDS,
    HIGH_ELEVATION_KEYWORDS,
    LOW_ELEVATION_KEYWORDS,
    WATER_KEYWORDS,
)

logger = logging.getLogger(__name__)

class AtmosphereEngine:
    """Engine for generating professional atmospheric descriptions"""

    def __init__(self):
        self.atmosphere_templates = ATMOSPHERE_TEMPLATES
        self.weather_patterns = WEATHER_PATTERNS
        self.environmental_effects = ENVIRONMENTAL_EFFECTS
        self.sensory_elements = SENSORY_ELEMENTS

    async def generate_atmosphere_description(
        self,
        scene_data: Dict[str, Any],
        visual_composition: Dict[str, Any],
        cinematography: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate comprehensive atmosphere description"""
        try:
            # Get base atmosphere template
            mood = scene_data.get("mood", "peaceful")
            atmosphere_base = self.atmosphere_templates.get(mood, self.atmosphere_templates["peaceful"])

            # Determine weather and environmental conditions
            weather = await self._determine_weather(scene_data, atmosphere_base)
            environmental_context = await self._analyze_environmental_context(scene_data)

            # Generate sensory descriptions
            sensory_description = await self._create_sensory_description(
                scene_data, atmosphere_base, weather, environmental_context
            )

            # Create atmospheric effects
            atmospheric_effects = await self._generate_atmospheric_effects(
                atmosphere_base, weather, environmental_context
            )

            # Generate comprehensive description
            atmosphere_description = await self._compose_atmosphere_description(
                atmosphere_base, weather, sensory_description, atmospheric_effects, scene_data
            )

            return {
                "base_mood": mood,
                "weather_conditions": weather,
                "environmental_context": environmental_context,
                "sensory_elements": sensory_description,
                "atmospheric_effects": atmospheric_effects,
                "atmosphere_description": atmosphere_description,
                "mood_enhancement_factors": atmosphere_base.get("environmental_mood", "neutral"),
                "audio_landscape": atmosphere_base.get("audio_elements", [])
            }

        except Exception as e:
            logger.error(f"Atmosphere generation failed: {e}")
            raise

    async def _determine_weather(
        self,
        scene_data: Dict[str, Any],
        atmosphere_base: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Determine appropriate weather conditions"""

        time_of_day = scene_data.get("time_of_day", "midday")
        location = scene_data.get("location", "").lower()

        # Get weather tendencies from atmosphere template
        weather_tendencies = atmosphere_base.get("weather_tendency", ["clear"])

        # Time-based weather modifications
        time_appropriate = TIME_WEATHER_MAP.get(time_of_day, ["clear_skies"])

        # Combine tendencies with time appropriateness
        selected_weather = random.choice(weather_tendencies + time_appropriate)

        # Get weather pattern details
        weather_pattern = self.weather_patterns.get(selected_weather, self.weather_patterns["clear_skies"])

        # Location-specific modifications
        if "mountain" in location:
            weather_pattern["altitude_effects"] = ["thin_air", "clear_visibility", "dramatic_views"]
        elif "ocean" in location or "sea" in location:
            weather_pattern["maritime_effects"] = ["salt_air", "ocean_breeze", "marine_atmosphere"]
        elif "forest" in location:
            weather_pattern["forest_effects"] = ["dappled_light", "nature_sounds", "organic_atmosphere"]

        return weather_pattern

    async def _analyze_environmental_context(self, scene_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze environmental context for atmosphere generation"""

        location = scene_data.get("location", "").lower()

        # Categorize environment type
        environment_type = "natural"  # default
        for env_type, keywords in ENVIRONMENT_KEYWORDS.items():
            if any(kw in location for kw in keywords):
                environment_type = env_type
                break

        # Get environmental effects for this type
        available_effects = self.environmental_effects.get(environment_type, self.environmental_effects["natural"])

        return {
            "environment_type": environment_type,
            "location_description": location,
            "available_effects": available_effects,
            "primary_characteristics": available_effects[:3],  # Top 3 characteristics
            "atmosphere_modifiers": await self._get_location_atmosphere_modifiers(location)
        }

    async def _get_location_atmosphere_modifiers(self, location: str) -> List[str]:
        """Get atmosphere modifiers based on specific location"""

        modifiers = []

        location_lower = location.lower()

        # Indoor vs outdoor
        if any(indoor in location_lower for indoor in INDOOR_KEYWORDS):
            modifiers.extend(["enclosed_space", "interior_lighting", "controlled_environment"])
        else:
            modifiers.extend(["open_space", "natural_lighting", "environmental_exposure"])

        # Elevation
        if any(high in location_lower for high in HIGH_ELEVATION_KEYWORDS):
            modifiers.extend(["elevated_perspective", "dramatic_views", "thin_atmosphere"])
        elif any(low in location_lower for low in LOW_ELEVATION_KEYWORDS):
            modifiers.extend(["enclosed_feeling", "limited_views", "dense_atmosphere"])

        # Water proximity
        if any(water in location_lower for water in WATER_KEYWORDS):
            modifiers.extend(["aquatic_influence", "moisture_in_air", "water_reflections"])

        return modifiers

    async def _create_sensory_description(
        self,
        scene_data: Dict[str, Any],
        atmosphere_base: Dict[str, Any],
        weather: Dict[str, Any],
        environmental_context: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """Create comprehensive sensory descriptions"""

        mood = scene_data.get("mood", "peaceful")
        time_of_day = scene_data.get("time_of_day", "midday")

        sensory_elements = {
            "visual": [],
            "auditory": [],
            "tactile": []
        }

        # Visual elements
        visual_base = self.sensory_elements["visual"]

        # Lighting based on time and weather
        if time_of_day in ["dawn", "dusk"]:
            sensory_elements["visual"].extend(["golden_light", "long_shadows", "warm_glow"])
        elif "overcast" in weather.get("lighting_quality", ""):
            sensory_elements["visual"].extend(["soft_even_light", "muted_colors", "gentle_shadows"])
        else:
            sensory_elements["visual"].extend(["natural_lighting", "clear_visibility", "defined_shadows"])

        # Colors from atmosphere template
        color_influences = atmosphere_base.get("color_influence", ["natural_tones"])
        sensory_elements["visual"].extend(color_influences)

        # Auditory elements
        audio_base = atmosphere_base.get("audio_elements", ["ambient_silence"])
        sensory_elements["auditory"].extend(audio_base)

        # Environment-specific audio
        env_type = environmental_context["environment_type"]
        if env_type in self.sensory_elements["auditory"]:
            env_audio = self.sensory_elements["auditory"][env_type]
            sensory_elements["auditory"].extend(env_audio[:2])  # Add top 2

        # Tactile elements based on weather and environment
        if "temperature" in weather:
            if "warm" in weather.get("mood_enhancement", ""):
                sensory_elements["tactile"].extend(["warm_air", "comfortable_temperature"])
            elif "cool" in weather.get("mood_enhancement", ""):
                sensory_elements["tactile"].extend(["cool_breeze", "crisp_air"])

        # Remove duplicates while preserving order
        for category in sensory_elements:
            sensory_elements[category] = list(dict.fromkeys(sensory_elements[category]))

        return sensory_elements

    async def _generate_atmospheric_effects(
        self,
        atmosphere_base: Dict[str, Any],
        weather: Dict[str, Any],
        environmental_context: Dict[str, Any]
    ) -> List[str]:
        """Generate specific atmospheric effects"""

        effects = []

        # Base atmospheric effects from template
        visual_elements = atmosphere_base.get("visual_elements", [])
        effects.extend(visual_elements)

        # Weather-based effects
        atmospheric_effects = weather.get("atmospheric_effects", [])
        effects.extend(atmospheric_effects)

        # Environment-specific effects
        primary_characteristics = environmental_context.get("primary_characteristics", [])
        effects.extend(primary_characteristics)

        # Mood enhancement effects
        mood_enhancement = weather.get("mood_enhancement", "")
        if mood_enhancement:
            effects.append(f"mood_enhanced_{mood_enhancement}")

        # Remove duplicates
        return list(dict.fromkeys(effects))

    async def _compose_atmosphere_description(
        self,
        atmosphere_base: Dict[str, Any],
        weather: Dict[str, Any],
        sensory_description: Dict[str, List[str]],
        atmospheric_effects: List[str],
        scene_data: Dict[str, Any]
    ) -> str:
        """Compose the final atmospheric description"""

        description_parts = []

        # Opening with environmental mood
        environmental_mood = atmosphere_base.get("environmental_mood", "neutral atmosphere")
        description_parts.append(f"The scene radiates {environmental_mood}")

        # Weather and lighting
        lighting_quality = weather.get("lighting_quality", "natural lighting")
        visibility = weather.get("visibility", "clear")
        description_parts.append(f"enhanced by {lighting_quality} with {visibility} visibility")

        # Visual atmosphere
        visual_elements = sensory_description.get("visual", [])
        if visual_elements:
            visual_desc = f"Visual atmosphere features {', '.join(visual_elements[:3])}"
            description_parts.append(visual_desc)

        # Auditory landscape
        auditory_elements = sensory_description.get("auditory", [])
        if auditory_elements:
            audio_desc = f"accompanied by {', '.join(auditory_elements[:2])}"
            description_parts.append(audio_desc)

        # Tactile sensations
        tactile_elements = sensory_description.get("tactile", [])
        if tactile_elements:
            tactile_desc = f"with {', '.join(tactile_elements[:2])} creating physical atmosphere"
            description_parts.append(tactile_desc)

        # Atmospheric effects integration
        if atmospheric_effects:
            effects_desc = f"Atmospheric effects include {', '.join(atmospheric_effects[:3])}"
            description_parts.append(effects_desc)

        # Location-specific enhancement
        location = scene_data.get("location", "")
        if location:
            location_desc = f"perfectly suited to the {location} setting"
            description_parts.append(location_desc)

        return ". ".join(description_parts) + "."

    async def generate_mood_transition(
        self,
        from_mood: str,
        to_mood: str,
        transition_duration: float
    ) -> Dict[str, Any]:
        """Generate atmospheric transition between moods"""

        from_atmosphere = self.atmosphere_templates.get(from_mood, self.atmosphere_templates["peaceful"])
        to_atmosphere = self.atmosphere_templates.get(to_mood, self.atmosphere_templates["peaceful"])

        transition_steps = []
        step_count = max(3, int(transition_duration))

        for step in range(step_count):
            progress = step / (step_count - 1)

            # Interpolate between atmospheres
            step_atmosphere = await self._interpolate_atmosphere(
                from_atmosphere, to_atmosphere, progress
            )

            transition_steps.append({
                "step": step,
                "progress": progress,
                "duration": transition_duration / step_count,
                "atmosphere": step_atmosphere
            })

        return {
            "from_mood": from_mood,
            "to_mood": to_mood,
            "transition_duration": transition_duration,
            "steps": transition_steps,
            "description": await self._describe_mood_transition(from_mood, to_mood, transition_steps)
        }

    async def _interpolate_atmosphere(
        self,
        from_atmosphere: Dict[str, Any],
        to_atmosphere: Dict[str, Any],
        progress: float
    ) -> Dict[str, Any]:
        """Interpolate between two atmospheric states"""

        # Simple interpolation - in production, this would be more sophisticated
        if progress < 0.5:
            # Closer to from_atmosphere
            primary = from_atmosphere
            secondary = to_atmosphere
            blend_factor = progress * 2
        else:
            # Closer to to_atmosphere
            primary = to_atmosphere
            secondary = from_atmosphere
            blend_factor = (1 - progress) * 2

        interpolated = {
            "visual_elements": primary.get("visual_elements", []),
            "weather_tendency": primary.get("weather_tendency", []),
            "color_influence": primary.get("color_influence", []),
            "environmental_mood": f"transitioning_{primary.get('environmental_mood', 'neutral')}",
            "audio_elements": primary.get("audio_elements", [])
        }

        return interpolated

    async def _describe_mood_transition(
        self,
        from_mood: str,
        to_mood: str,
        transition_steps: List[Dict[str, Any]]
    ) -> str:
        """Describe the atmospheric mood transition"""

        return f"Atmospheric transition from {from_mood} to {to_mood} through {len(transition_steps)} gradual steps, " \
               f"creating a smooth evolution of environmental mood and sensory experience."
