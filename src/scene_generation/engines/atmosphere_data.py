"""
Atmosphere Data
Atmosphere presets, mood data, lighting configs, and constant mappings for the AtmosphereEngine.
"""

from typing import Dict, List, Any


# ── Atmosphere Templates ─────────────────────────────────────────────────────

ATMOSPHERE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "dramatic": {
        "visual_elements": ["stark_contrasts", "sharp_shadows", "dramatic_lighting"],
        "weather_tendency": ["stormy", "overcast", "windswept"],
        "color_influence": ["deep_reds", "harsh_blacks", "stark_whites"],
        "environmental_mood": "tense_anticipation",
        "audio_elements": ["distant_thunder", "wind_howling", "ominous_silence"]
    },
    "romantic": {
        "visual_elements": ["soft_lighting", "warm_colors", "gentle_shadows"],
        "weather_tendency": ["sunset_glow", "light_breeze", "clear_skies"],
        "color_influence": ["warm_pinks", "golden_yellows", "soft_purples"],
        "environmental_mood": "intimate_warmth",
        "audio_elements": ["gentle_breeze", "distant_music", "soft_rustling"]
    },
    "mysterious": {
        "visual_elements": ["obscured_details", "fog_effects", "hidden_areas"],
        "weather_tendency": ["foggy", "misty", "twilight"],
        "color_influence": ["deep_purples", "shadowy_blues", "mysterious_grays"],
        "environmental_mood": "enigmatic_uncertainty",
        "audio_elements": ["distant_sounds", "echoing_footsteps", "whispered_wind"]
    },
    "peaceful": {
        "visual_elements": ["natural_harmony", "soft_textures", "balanced_composition"],
        "weather_tendency": ["clear", "gentle_breeze", "perfect_temperature"],
        "color_influence": ["natural_greens", "sky_blues", "earth_tones"],
        "environmental_mood": "serene_tranquility",
        "audio_elements": ["nature_sounds", "gentle_water", "bird_songs"]
    },
    "energetic": {
        "visual_elements": ["dynamic_movement", "vibrant_colors", "active_elements"],
        "weather_tendency": ["bright_sunshine", "crisp_air", "clear_visibility"],
        "color_influence": ["bright_yellows", "energetic_oranges", "vibrant_reds"],
        "environmental_mood": "dynamic_excitement",
        "audio_elements": ["upbeat_ambient", "bustling_activity", "rhythmic_elements"]
    },
    "melancholic": {
        "visual_elements": ["muted_colors", "gentle_rain", "overcast_skies"],
        "weather_tendency": ["light_rain", "overcast", "cool_temperature"],
        "color_influence": ["muted_blues", "soft_grays", "faded_colors"],
        "environmental_mood": "reflective_sadness",
        "audio_elements": ["gentle_rain", "distant_sounds", "melancholic_silence"]
    },
    "suspenseful": {
        "visual_elements": ["sharp_contrasts", "unexpected_shadows", "tension_building"],
        "weather_tendency": ["approaching_storm", "still_air", "building_clouds"],
        "color_influence": ["warning_yellows", "danger_reds", "ominous_blacks"],
        "environmental_mood": "building_tension",
        "audio_elements": ["building_wind", "creaking_sounds", "tension_silence"]
    },
    "comedic": {
        "visual_elements": ["bright_colors", "exaggerated_proportions", "playful_details"],
        "weather_tendency": ["perfect_day", "gentle_breeze", "optimal_conditions"],
        "color_influence": ["cheerful_yellows", "playful_oranges", "happy_blues"],
        "environmental_mood": "lighthearted_fun",
        "audio_elements": ["cheerful_sounds", "playful_elements", "upbeat_ambient"]
    }
}


# ── Weather Patterns ─────────────────────────────────────────────────────────

WEATHER_PATTERNS: Dict[str, Dict[str, Any]] = {
    "clear_skies": {
        "visibility": "excellent",
        "lighting_quality": "bright_natural",
        "atmospheric_effects": ["crisp_air", "clear_shadows"],
        "mood_enhancement": "positive_energy"
    },
    "overcast": {
        "visibility": "diffused",
        "lighting_quality": "soft_even",
        "atmospheric_effects": ["even_lighting", "muted_shadows"],
        "mood_enhancement": "contemplative_calm"
    },
    "light_rain": {
        "visibility": "slightly_reduced",
        "lighting_quality": "soft_gray",
        "atmospheric_effects": ["rain_drops", "wet_surfaces", "fresh_air"],
        "mood_enhancement": "reflective_melancholy"
    },
    "heavy_rain": {
        "visibility": "significantly_reduced",
        "lighting_quality": "dramatic_contrast",
        "atmospheric_effects": ["rain_sheets", "water_streams", "storm_energy"],
        "mood_enhancement": "dramatic_intensity"
    },
    "fog": {
        "visibility": "limited",
        "lighting_quality": "diffused_mysterious",
        "atmospheric_effects": ["obscured_distances", "mysterious_shapes"],
        "mood_enhancement": "mysterious_atmosphere"
    },
    "snow": {
        "visibility": "crystal_clear_or_limited",
        "lighting_quality": "bright_reflected",
        "atmospheric_effects": ["falling_snow", "pristine_surfaces", "muffled_sound"],
        "mood_enhancement": "peaceful_purity"
    },
    "sunset": {
        "visibility": "warm_golden",
        "lighting_quality": "golden_hour",
        "atmospheric_effects": ["warm_glow", "long_shadows", "color_enhancement"],
        "mood_enhancement": "romantic_tranquility"
    },
    "stormy": {
        "visibility": "dramatic_variation",
        "lighting_quality": "harsh_contrasts",
        "atmospheric_effects": ["lightning_flashes", "dramatic_clouds", "intense_wind"],
        "mood_enhancement": "dramatic_tension"
    }
}


# ── Environmental Effects ────────────────────────────────────────────────────

ENVIRONMENTAL_EFFECTS: Dict[str, List[str]] = {
    "natural": [
        "sunlight_filtering", "wind_movement", "water_reflections",
        "natural_shadows", "organic_textures", "seasonal_elements"
    ],
    "urban": [
        "city_lighting", "traffic_movement", "architectural_shadows",
        "neon_reflections", "urban_textures", "metropolitan_energy"
    ],
    "rural": [
        "pastoral_calm", "agricultural_elements", "countryside_textures",
        "farm_life_details", "rustic_charm", "traditional_elements"
    ],
    "fantasy": [
        "magical_lighting", "otherworldly_elements", "mystical_atmosphere",
        "enchanted_details", "supernatural_effects", "magical_particles"
    ],
    "historical": [
        "period_appropriate_details", "historical_atmosphere", "vintage_textures",
        "traditional_craftsmanship", "aged_materials", "historical_authenticity"
    ],
    "futuristic": [
        "advanced_lighting", "technological_elements", "sleek_surfaces",
        "digital_effects", "futuristic_materials", "sci_fi_atmosphere"
    ]
}


# ── Sensory Elements ─────────────────────────────────────────────────────────

SENSORY_ELEMENTS: Dict[str, Dict[str, List[str]]] = {
    "visual": {
        "lighting": ["soft_glow", "harsh_brightness", "dim_ambiance", "dramatic_shadows"],
        "colors": ["vibrant_hues", "muted_tones", "warm_palette", "cool_spectrum"],
        "textures": ["smooth_surfaces", "rough_materials", "organic_patterns", "geometric_forms"],
        "movement": ["gentle_sway", "dynamic_motion", "static_stillness", "rhythmic_flow"]
    },
    "auditory": {
        "natural": ["wind_whispers", "water_flowing", "birds_singing", "leaves_rustling"],
        "urban": ["distant_traffic", "city_hum", "footsteps_echoing", "urban_rhythm"],
        "atmospheric": ["silence_profound", "ambient_drone", "mysterious_sounds", "tension_building"]
    },
    "tactile": {
        "temperature": ["warm_comfort", "cool_freshness", "humid_air", "crisp_coldness"],
        "texture_feel": ["smooth_touch", "rough_surface", "soft_material", "hard_edge"],
        "air_quality": ["fresh_breeze", "still_air", "heavy_atmosphere", "light_movement"]
    }
}


# ── Time-Weather Mapping ────────────────────────────────────────────────────

TIME_WEATHER_MAP: Dict[str, List[str]] = {
    "dawn": ["clear_skies", "light_fog", "morning_mist"],
    "morning": ["clear_skies", "light_clouds", "crisp_air"],
    "midday": ["clear_skies", "bright_sunshine", "optimal_visibility"],
    "afternoon": ["partly_cloudy", "warm_air", "good_visibility"],
    "evening": ["sunset", "golden_light", "calm_air"],
    "dusk": ["twilight", "soft_lighting", "evening_calm"],
    "night": ["clear_night", "moonlight", "cool_air"],
    "midnight": ["deep_night", "starlight", "still_air"]
}


# ── Environment Classification Keywords ──────────────────────────────────────

ENVIRONMENT_KEYWORDS: Dict[str, List[str]] = {
    "urban": ["city", "town", "street", "building"],
    "rural": ["village", "farm", "countryside", "rural"],
    "fantasy": ["magical", "enchanted", "mystical"],
    "historical": ["ancient", "traditional", "historic"],
    "futuristic": ["futuristic", "cyber", "space"],
}

INDOOR_KEYWORDS: List[str] = ["room", "house", "building", "indoor"]
HIGH_ELEVATION_KEYWORDS: List[str] = ["mountain", "tower", "peak", "high"]
LOW_ELEVATION_KEYWORDS: List[str] = ["valley", "basement", "underground"]
WATER_KEYWORDS: List[str] = ["ocean", "lake", "river", "water"]
