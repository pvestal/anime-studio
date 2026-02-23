"""
Timing Engine / Timing Orchestrator
Professional timing and pacing for anime scene production
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import json

from .timing_templates import (
    PACING_TEMPLATES,
    RHYTHM_PATTERNS,
    TEMPO_GUIDELINES,
    BEAT_STRUCTURES,
    SPEED_DURATION_MAP,
    BASE_INSTRUMENTS,
    calculate_scene_bpm,
    suggest_instrumentation,
    intensity_to_dynamics,
    calculate_tempo_variation,
    suggest_key_signature,
    suggest_harmony,
)

logger = logging.getLogger(__name__)

class TimingOrchestrator:
    """Engine for orchestrating professional timing and pacing"""

    def __init__(self):
        self.pacing_templates = PACING_TEMPLATES
        self.rhythm_patterns = RHYTHM_PATTERNS
        self.tempo_guidelines = TEMPO_GUIDELINES
        self.beat_structures = BEAT_STRUCTURES

    async def generate_timing_plan(
        self,
        scene_data: Dict[str, Any],
        cinematography_plan: Dict[str, Any],
        atmosphere_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate comprehensive timing and pacing plan"""
        try:
            # Analyze scene requirements
            pacing_type = await self._determine_pacing_type(scene_data)
            base_tempo = await self._calculate_base_tempo(scene_data, atmosphere_data)
            rhythm_pattern = await self._select_rhythm_pattern(scene_data, pacing_type)

            # Generate shot timing
            shot_timings = await self._calculate_shot_timings(
                cinematography_plan, pacing_type, rhythm_pattern
            )

            # Calculate beat structure
            beat_structure = await self._apply_beat_structure(scene_data, shot_timings)

            # Generate transition timings
            transition_timings = await self._calculate_transition_timings(
                cinematography_plan, pacing_type
            )

            # Create musical timing suggestions
            musical_timing = await self._generate_musical_timing(
                scene_data, shot_timings, beat_structure
            )

            # Generate comprehensive timing notes
            timing_notes = await self._generate_timing_notes(
                pacing_type, rhythm_pattern, shot_timings, beat_structure
            )

            return {
                "pacing_type": pacing_type,
                "base_tempo": base_tempo,
                "rhythm_pattern": rhythm_pattern,
                "shot_timings": shot_timings,
                "beat_structure": beat_structure,
                "transition_timings": transition_timings,
                "musical_timing": musical_timing,
                "timing_notes": timing_notes,
                "total_duration": sum(shot["duration"] for shot in shot_timings),
                "pacing_analysis": await self._analyze_pacing_effectiveness(shot_timings, beat_structure)
            }

        except Exception as e:
            logger.error(f"Timing plan generation failed: {e}")
            raise

    async def _determine_pacing_type(self, scene_data: Dict[str, Any]) -> str:
        """Determine the appropriate pacing type for the scene"""

        mood = scene_data.get("mood", "peaceful")
        action_summary = scene_data.get("action_summary", "").lower()
        character_count = len(scene_data.get("characters", []))

        # Direct mood mapping
        if mood in self.pacing_templates:
            return mood

        # Action-based analysis
        if any(action_word in action_summary for action_word in ["fight", "chase", "run", "battle"]):
            return "action"
        elif any(dialogue_word in action_summary for dialogue_word in ["talk", "speak", "discuss", "conversation"]):
            return "dialogue"
        elif any(contemplative_word in action_summary for contemplative_word in ["think", "remember", "reflect", "contemplate"]):
            return "contemplative"
        elif any(dramatic_word in action_summary for dramatic_word in ["reveal", "discover", "confront", "dramatic"]):
            return "dramatic"

        # Default based on character count
        if character_count <= 1:
            return "contemplative"
        elif character_count == 2:
            return "dialogue"
        else:
            return "dramatic"

    async def _calculate_base_tempo(
        self,
        scene_data: Dict[str, Any],
        atmosphere_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate base tempo considering all factors"""

        time_of_day = scene_data.get("time_of_day", "midday")
        mood = scene_data.get("mood", "peaceful")

        # Get time-based tempo modifier
        time_guidelines = self.tempo_guidelines.get(time_of_day, self.tempo_guidelines["afternoon"])
        base_modifier = time_guidelines["tempo_modifier"]

        # Get mood-based pacing
        pacing_type = await self._determine_pacing_type(scene_data)
        mood_pacing = self.pacing_templates.get(pacing_type, self.pacing_templates["dialogue"])

        # Combine factors
        final_tempo = {
            "base_pace": mood_pacing["base_tempo"],
            "time_modifier": base_modifier,
            "atmospheric_influence": atmosphere_data.get("mood_enhancement_factors", "neutral"),
            "calculated_bpm": calculate_scene_bpm(mood_pacing["base_tempo"], base_modifier),
            "pacing_descriptor": f"{mood_pacing['base_tempo']}_modified_by_{time_of_day}"
        }

        return final_tempo

    async def _select_rhythm_pattern(
        self,
        scene_data: Dict[str, Any],
        pacing_type: str
    ) -> Dict[str, Any]:
        """Select appropriate rhythm pattern"""

        pacing_template = self.pacing_templates[pacing_type]
        suggested_pattern = pacing_template["rhythm_pattern"]

        rhythm_data = self.rhythm_patterns.get(suggested_pattern, self.rhythm_patterns["conversational"])

        # Modify pattern based on scene specifics
        action_summary = scene_data.get("action_summary", "").lower()

        if "climax" in action_summary or "peak" in action_summary:
            rhythm_data = self.rhythm_patterns["building_tension"]
        elif "resolve" in action_summary or "end" in action_summary:
            rhythm_data = self.rhythm_patterns["decelerating"]

        return rhythm_data

    async def _calculate_shot_timings(
        self,
        cinematography_plan: Dict[str, Any],
        pacing_type: str,
        rhythm_pattern: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Calculate precise timing for each shot"""

        shot_sequence = cinematography_plan.get("shot_sequence", [])
        pacing_template = self.pacing_templates[pacing_type]
        pattern_multipliers = rhythm_pattern["pattern"]

        shot_timings = []

        for i, shot in enumerate(shot_sequence):
            # Get base duration from cinematography plan
            base_duration = shot.get("duration", 3.0)

            # Apply rhythm pattern
            pattern_index = i % len(pattern_multipliers)
            rhythm_multiplier = pattern_multipliers[pattern_index]

            # Apply pacing constraints
            min_duration, max_duration = pacing_template["shot_duration_range"]
            calculated_duration = base_duration * rhythm_multiplier

            # Clamp to acceptable range
            final_duration = max(min_duration, min(max_duration, calculated_duration))

            shot_timing = {
                "shot_index": i,
                "shot_type": shot.get("shot", "medium_shot"),
                "purpose": shot.get("purpose", "scene_development"),
                "base_duration": base_duration,
                "rhythm_multiplier": rhythm_multiplier,
                "calculated_duration": calculated_duration,
                "final_duration": final_duration,
                "start_time": sum(s["final_duration"] for s in shot_timings),
                "intensity_level": await self._calculate_shot_intensity(i, len(shot_sequence), pacing_template)
            }

            shot_timing["end_time"] = shot_timing["start_time"] + shot_timing["final_duration"]
            shot_timings.append(shot_timing)

        return shot_timings

    async def _calculate_shot_intensity(
        self,
        shot_index: int,
        total_shots: int,
        pacing_template: Dict[str, Any]
    ) -> float:
        """Calculate intensity level for each shot"""

        # Get peak timing from template
        peak_timing = pacing_template["peak_intensity_timing"]
        peak_shot_index = int(total_shots * peak_timing)

        # Calculate distance from peak
        distance_from_peak = abs(shot_index - peak_shot_index) / total_shots

        # Create intensity curve
        if shot_index <= peak_shot_index:
            # Building to peak
            intensity = 0.3 + (0.7 * (shot_index / peak_shot_index))
        else:
            # After peak
            remaining_shots = total_shots - peak_shot_index
            shots_after_peak = shot_index - peak_shot_index
            intensity = 1.0 - (0.6 * (shots_after_peak / remaining_shots))

        return max(0.1, min(1.0, intensity))

    async def _apply_beat_structure(
        self,
        scene_data: Dict[str, Any],
        shot_timings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Apply story beat structure to timing"""

        action_summary = scene_data.get("action_summary", "").lower()

        # Select appropriate beat structure
        if "reveal" in action_summary or "discover" in action_summary:
            structure_type = "revelation_structure"
        elif any(tension_word in action_summary for tension_word in ["tension", "suspense", "buildup"]):
            structure_type = "tension_release"
        elif len(shot_timings) <= 3:
            structure_type = "three_act_micro"
        else:
            structure_type = "five_beat_structure"

        beat_structure = self.beat_structures[structure_type]
        total_duration = sum(shot["final_duration"] for shot in shot_timings)

        # Apply beats to timing
        applied_beats = []
        current_time = 0.0

        for beat in beat_structure:
            beat_duration = total_duration * beat["timing_percent"]

            applied_beat = {
                "beat_name": beat["beat"],
                "start_time": current_time,
                "duration": beat_duration,
                "end_time": current_time + beat_duration,
                "intensity": beat["intensity"],
                "timing_percent": beat["timing_percent"]
            }

            applied_beats.append(applied_beat)
            current_time += beat_duration

        return {
            "structure_type": structure_type,
            "beats": applied_beats,
            "total_duration": total_duration,
            "beat_analysis": await self._analyze_beat_effectiveness(applied_beats, shot_timings)
        }

    async def _calculate_transition_timings(
        self,
        cinematography_plan: Dict[str, Any],
        pacing_type: str
    ) -> List[Dict[str, Any]]:
        """Calculate transition timings between shots"""

        transitions = cinematography_plan.get("transitions", [])
        pacing_template = self.pacing_templates[pacing_type]
        transition_speed = pacing_template["transition_speed"]

        base_duration = SPEED_DURATION_MAP.get(transition_speed, 0.5)

        transition_timings = []
        for i, transition in enumerate(transitions):
            timing = {
                "transition_index": i,
                "type": transition.get("description", "cut"),
                "base_duration": base_duration,
                "pacing_modifier": await self._get_transition_pacing_modifier(i, len(transitions)),
                "final_duration": base_duration * await self._get_transition_pacing_modifier(i, len(transitions))
            }
            transition_timings.append(timing)

        return transition_timings

    async def _get_transition_pacing_modifier(self, transition_index: int, total_transitions: int) -> float:
        """Get pacing modifier for specific transition"""

        # Faster transitions toward climax, slower at resolution
        progress = transition_index / max(1, total_transitions - 1)

        if progress < 0.7:  # Building section
            return 1.0 - (progress * 0.3)  # Get slightly faster
        else:  # Resolution section
            return 0.7 + ((progress - 0.7) * 1.0)  # Get slower again

    async def _generate_musical_timing(
        self,
        scene_data: Dict[str, Any],
        shot_timings: List[Dict[str, Any]],
        beat_structure: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate musical timing suggestions for the scene"""

        total_duration = sum(shot["final_duration"] for shot in shot_timings)
        scene_bpm = calculate_scene_bpm("moderate", 1.0)

        # Calculate musical measures
        beats_per_measure = 4
        seconds_per_beat = 60 / scene_bpm
        seconds_per_measure = seconds_per_beat * beats_per_measure
        total_measures = total_duration / seconds_per_measure

        # Generate musical cue points
        cue_points = []
        for beat in beat_structure["beats"]:
            cue_point = {
                "beat_name": beat["beat_name"],
                "time": beat["start_time"],
                "musical_marker": f"Measure {int(beat['start_time'] / seconds_per_measure) + 1}",
                "intensity": beat["intensity"],
                "suggested_instrumentation": suggest_instrumentation(beat["intensity"], scene_data.get("mood", "peaceful"))
            }
            cue_points.append(cue_point)

        return {
            "scene_bpm": scene_bpm,
            "total_measures": round(total_measures, 1),
            "seconds_per_measure": round(seconds_per_measure, 2),
            "cue_points": cue_points,
            "musical_structure": await self._generate_musical_structure(beat_structure, scene_data)
        }

    async def _generate_musical_structure(
        self,
        beat_structure: Dict[str, Any],
        scene_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate overall musical structure recommendations"""

        structure_type = beat_structure["structure_type"]
        total_duration = beat_structure["total_duration"]

        musical_sections = []
        for beat in beat_structure["beats"]:
            section = {
                "name": beat["beat_name"],
                "duration": beat["duration"],
                "dynamics": intensity_to_dynamics(beat["intensity"]),
                "tempo_variation": calculate_tempo_variation(beat["intensity"]),
                "harmonic_suggestion": suggest_harmony(beat["beat_name"], scene_data.get("mood", "peaceful"))
            }
            musical_sections.append(section)

        return {
            "overall_form": structure_type,
            "total_duration": total_duration,
            "sections": musical_sections,
            "key_signature": suggest_key_signature(scene_data.get("mood", "peaceful")),
            "time_signature": "4/4"  # Standard for most scenes
        }

    async def _generate_timing_notes(
        self,
        pacing_type: str,
        rhythm_pattern: Dict[str, Any],
        shot_timings: List[Dict[str, Any]],
        beat_structure: Dict[str, Any]
    ) -> str:
        """Generate comprehensive timing notes"""

        notes_sections = []

        # Pacing overview
        pacing_note = f"Scene pacing: {pacing_type} with {rhythm_pattern['description']}"
        notes_sections.append(pacing_note)

        # Shot timing summary
        total_duration = sum(shot["final_duration"] for shot in shot_timings)
        avg_shot_length = total_duration / len(shot_timings)
        timing_note = f"Total duration: {total_duration:.1f}s with {len(shot_timings)} shots (avg: {avg_shot_length:.1f}s each)"
        notes_sections.append(timing_note)

        # Beat structure note
        structure_note = f"Story beats: {beat_structure['structure_type']} with {len(beat_structure['beats'])} distinct beats"
        notes_sections.append(structure_note)

        # Intensity curve
        max_intensity = max(shot["intensity_level"] for shot in shot_timings)
        min_intensity = min(shot["intensity_level"] for shot in shot_timings)
        intensity_note = f"Intensity range: {min_intensity:.1f} to {max_intensity:.1f} with strategic pacing"
        notes_sections.append(intensity_note)

        return " | ".join(notes_sections)

    async def _analyze_pacing_effectiveness(
        self,
        shot_timings: List[Dict[str, Any]],
        beat_structure: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze the effectiveness of the pacing plan"""

        # Calculate pacing metrics
        duration_variance = await self._calculate_duration_variance(shot_timings)
        intensity_curve_smoothness = await self._calculate_curve_smoothness(shot_timings)
        beat_alignment = await self._calculate_beat_alignment(shot_timings, beat_structure)

        effectiveness_score = (
            (1.0 - min(duration_variance, 1.0)) * 0.3 +  # Lower variance is better
            intensity_curve_smoothness * 0.4 +
            beat_alignment * 0.3
        )

        return {
            "effectiveness_score": round(effectiveness_score, 2),
            "duration_variance": round(duration_variance, 2),
            "intensity_curve_smoothness": round(intensity_curve_smoothness, 2),
            "beat_alignment": round(beat_alignment, 2),
            "recommendations": await self._generate_pacing_recommendations(effectiveness_score, duration_variance, intensity_curve_smoothness)
        }

    async def _calculate_duration_variance(self, shot_timings: List[Dict[str, Any]]) -> float:
        """Calculate variance in shot durations"""
        durations = [shot["final_duration"] for shot in shot_timings]
        mean_duration = sum(durations) / len(durations)
        variance = sum((d - mean_duration) ** 2 for d in durations) / len(durations)
        return variance / mean_duration  # Normalized variance

    async def _calculate_curve_smoothness(self, shot_timings: List[Dict[str, Any]]) -> float:
        """Calculate smoothness of intensity curve"""
        intensities = [shot["intensity_level"] for shot in shot_timings]

        if len(intensities) < 2:
            return 1.0

        # Calculate smoothness as inverse of average intensity change
        intensity_changes = [abs(intensities[i+1] - intensities[i]) for i in range(len(intensities)-1)]
        avg_change = sum(intensity_changes) / len(intensity_changes)

        # Convert to smoothness score (0-1, where 1 is smoothest)
        return max(0.0, 1.0 - avg_change)

    async def _calculate_beat_alignment(
        self,
        shot_timings: List[Dict[str, Any]],
        beat_structure: Dict[str, Any]
    ) -> float:
        """Calculate alignment between shots and story beats"""

        total_shots = len(shot_timings)
        total_beats = len(beat_structure["beats"])

        # Good alignment typically has similar numbers of shots and beats
        ratio = min(total_shots, total_beats) / max(total_shots, total_beats)

        return ratio

    async def _analyze_beat_effectiveness(
        self,
        applied_beats: List[Dict[str, Any]],
        shot_timings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze effectiveness of beat structure application"""

        return {
            "beat_count": len(applied_beats),
            "average_beat_duration": sum(beat["duration"] for beat in applied_beats) / len(applied_beats),
            "intensity_progression": [beat["intensity"] for beat in applied_beats],
            "timing_efficiency": "optimal"  # Simplified for this implementation
        }

    async def _generate_pacing_recommendations(
        self,
        effectiveness_score: float,
        duration_variance: float,
        intensity_curve_smoothness: float
    ) -> List[str]:
        """Generate recommendations for improving pacing"""

        recommendations = []

        if effectiveness_score < 0.7:
            recommendations.append("Consider adjusting overall pacing strategy")

        if duration_variance > 0.5:
            recommendations.append("Shot durations show high variance - consider more consistent pacing")

        if intensity_curve_smoothness < 0.6:
            recommendations.append("Intensity curve could be smoother - adjust shot intensities")

        if not recommendations:
            recommendations.append("Pacing plan is well-optimized for the scene requirements")

        return recommendations
