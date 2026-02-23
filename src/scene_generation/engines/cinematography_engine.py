"""
Cinematography Engine
Professional cinematography and camera work for anime production
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json

from .cinematography_data import (
    CAMERA_MOVEMENTS,
    SHOT_SEQUENCES,
    TRANSITION_TYPES,
    LENS_SPECIFICATIONS,
    SHOT_LENS_MAPPING,
)

logger = logging.getLogger(__name__)

class CinematographyEngine:
    """Engine for generating professional cinematography directions"""

    def __init__(self):
        self.camera_movements = CAMERA_MOVEMENTS
        self.shot_sequences = SHOT_SEQUENCES
        self.transition_types = TRANSITION_TYPES
        self.lens_specifications = LENS_SPECIFICATIONS

    async def generate_cinematography_plan(
        self,
        scene_data: Dict[str, Any],
        visual_composition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate comprehensive cinematography plan"""
        try:
            # Analyze scene requirements
            shot_sequence = await self._plan_shot_sequence(scene_data, visual_composition)
            camera_movements = await self._plan_camera_movements(scene_data, shot_sequence)
            lens_choices = await self._select_lenses(shot_sequence)
            transitions = await self._plan_transitions(scene_data, shot_sequence)

            # Generate timing
            timing_plan = await self._calculate_timing(shot_sequence, transitions)

            # Generate technical notes
            technical_notes = await self._generate_cinematography_notes(
                shot_sequence, camera_movements, lens_choices, transitions
            )

            return {
                "shot_sequence": shot_sequence,
                "camera_movements": camera_movements,
                "lens_choices": lens_choices,
                "transitions": transitions,
                "timing_plan": timing_plan,
                "technical_notes": technical_notes,
                "total_duration": timing_plan["total_duration"]
            }

        except Exception as e:
            logger.error(f"Cinematography planning failed: {e}")
            raise

    async def _plan_shot_sequence(
        self,
        scene_data: Dict[str, Any],
        visual_composition: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Plan the sequence of shots for the scene"""

        action_summary = scene_data.get("action_summary", "").lower()
        character_count = len(scene_data.get("characters", []))
        mood = scene_data.get("mood", "peaceful")

        # Select base sequence pattern
        if "dialogue" in action_summary or "conversation" in action_summary:
            base_sequence = self.shot_sequences["dialogue_standard"]
        elif "action" in action_summary or mood == "energetic":
            base_sequence = self.shot_sequences["action_buildup"]
        elif "reveal" in action_summary or "discover" in action_summary:
            base_sequence = self.shot_sequences["revelation_sequence"]
        elif "contemplat" in action_summary or mood == "contemplative":
            base_sequence = self.shot_sequences["contemplation_sequence"]
        else:
            # Default balanced sequence
            base_sequence = [
                {"shot": "establishing_shot", "duration": 3, "purpose": "scene_establishment"},
                {"shot": "medium_shot", "duration": 4, "purpose": "character_focus"},
                {"shot": "close_up", "duration": 3, "purpose": "emotional_detail"},
                {"shot": "wide_shot", "duration": 2, "purpose": "context_closure"}
            ]

        # Adapt sequence to scene specifics
        adapted_sequence = []
        for shot_spec in base_sequence:
            adapted_shot = shot_spec.copy()

            # Adjust duration based on mood
            if mood == "energetic":
                adapted_shot["duration"] *= 0.8  # Faster pacing
            elif mood == "contemplative":
                adapted_shot["duration"] *= 1.3  # Slower pacing

            # Add camera angle from visual composition
            if "camera_angle" in visual_composition:
                adapted_shot["camera_angle"] = visual_composition["camera_angle"]

            adapted_sequence.append(adapted_shot)

        return adapted_sequence

    async def _plan_camera_movements(
        self,
        scene_data: Dict[str, Any],
        shot_sequence: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Plan camera movements for each shot"""

        mood = scene_data.get("mood", "peaceful")
        action_level = "high" if "action" in scene_data.get("action_summary", "").lower() else "low"

        movement_plan = []

        for i, shot in enumerate(shot_sequence):
            shot_purpose = shot.get("purpose", "")

            # Select movement based on shot purpose and scene characteristics
            if shot_purpose == "establish_characters" or shot_purpose == "scene_establishment":
                movement = "static" if mood == "contemplative" else "pan"
            elif shot_purpose == "emotional_intensity" or shot_purpose == "emotional_impact":
                movement = "zoom_in" if action_level == "high" else "dolly_in"
            elif shot_purpose == "full_context" or shot_purpose == "environment_context":
                movement = "dolly_out"
            elif shot_purpose == "character_preparation" and action_level == "high":
                movement = "tracking"
            else:
                movement = "static"

            movement_spec = self.camera_movements[movement].copy()
            movement_spec["shot_index"] = i
            movement_spec["duration"] = shot["duration"]

            movement_plan.append(movement_spec)

        return movement_plan

    async def _select_lenses(
        self,
        shot_sequence: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """Select appropriate lenses for each shot"""

        lens_plan = []

        for shot in shot_sequence:
            shot_type = shot.get("shot", "medium_shot")

            lens_type = SHOT_LENS_MAPPING.get(shot_type, "standard")
            lens_spec = self.lens_specifications[lens_type].copy()
            lens_spec["shot_type"] = shot_type

            lens_plan.append(lens_spec)

        return lens_plan

    async def _plan_transitions(
        self,
        scene_data: Dict[str, Any],
        shot_sequence: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Plan transitions between shots"""

        mood = scene_data.get("mood", "peaceful")
        pacing = "fast" if mood in ["energetic", "action"] else "moderate"

        transition_plan = []

        for i in range(len(shot_sequence) - 1):
            current_shot = shot_sequence[i]
            next_shot = shot_sequence[i + 1]

            # Select transition type based on shot purposes and mood
            current_purpose = current_shot.get("purpose", "")
            next_purpose = next_shot.get("purpose", "")

            if pacing == "fast":
                transition_type = "cut"
            elif "emotional" in current_purpose or "emotional" in next_purpose:
                transition_type = "dissolve"
            elif "establish" in current_purpose:
                transition_type = "fade_in"
            elif "conclusion" in current_purpose or "closure" in current_purpose:
                transition_type = "fade_out"
            else:
                transition_type = "cut"

            transition_spec = self.transition_types[transition_type].copy()
            transition_spec["from_shot"] = i
            transition_spec["to_shot"] = i + 1

            transition_plan.append(transition_spec)

        return transition_plan

    async def _calculate_timing(
        self,
        shot_sequence: List[Dict[str, Any]],
        transitions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate precise timing for the entire sequence"""

        shot_timings = []
        current_time = 0.0

        for i, shot in enumerate(shot_sequence):
            shot_start = current_time
            shot_duration = shot["duration"]
            shot_end = shot_start + shot_duration

            shot_timings.append({
                "shot_index": i,
                "start_time": shot_start,
                "duration": shot_duration,
                "end_time": shot_end
            })

            current_time = shot_end

            # Add transition time
            if i < len(transitions):
                transition_duration = transitions[i]["duration"]
                current_time += transition_duration

        total_duration = current_time

        return {
            "shot_timings": shot_timings,
            "total_duration": total_duration,
            "average_shot_length": total_duration / len(shot_sequence),
            "pacing": "fast" if total_duration / len(shot_sequence) < 3 else "moderate"
        }

    async def _generate_cinematography_notes(
        self,
        shot_sequence: List[Dict[str, Any]],
        camera_movements: List[Dict[str, Any]],
        lens_choices: List[Dict[str, str]],
        transitions: List[Dict[str, Any]]
    ) -> str:
        """Generate comprehensive cinematography notes"""

        notes_sections = []

        # Shot sequence overview
        sequence_note = f"Shot sequence: {len(shot_sequence)} shots with varied pacing and purpose"
        notes_sections.append(sequence_note)

        # Camera movement summary
        movements = [mov.get("description", "static") for mov in camera_movements]
        movement_note = f"Camera movements: {', '.join(set(movements))}"
        notes_sections.append(movement_note)

        # Lens usage summary
        lenses = [lens.get("focal_length", "standard") for lens in lens_choices]
        lens_note = f"Lens requirements: {', '.join(set(lenses))}"
        notes_sections.append(lens_note)

        # Transition summary
        transition_types = [trans.get("description", "cut") for trans in transitions]
        transition_note = f"Transitions: {', '.join(set(transition_types))}"
        notes_sections.append(transition_note)

        # Technical requirements
        technical_requirements = []
        for movement in camera_movements:
            if "technical_notes" in movement:
                technical_requirements.append(movement["technical_notes"])

        if technical_requirements:
            tech_note = f"Technical requirements: {' | '.join(set(technical_requirements))}"
            notes_sections.append(tech_note)

        return " • ".join(notes_sections)

    async def generate_frame_by_frame_breakdown(
        self,
        cinematography_plan: Dict[str, Any],
        frame_rate: int = 24
    ) -> List[Dict[str, Any]]:
        """Generate frame-by-frame breakdown for animation"""

        frame_breakdown = []
        shot_timings = cinematography_plan["timing_plan"]["shot_timings"]

        for shot_timing in shot_timings:
            shot_index = shot_timing["shot_index"]
            start_time = shot_timing["start_time"]
            duration = shot_timing["duration"]

            frame_count = int(duration * frame_rate)

            for frame_num in range(frame_count):
                frame_time = start_time + (frame_num / frame_rate)

                frame_data = {
                    "frame_number": frame_num,
                    "absolute_time": frame_time,
                    "shot_index": shot_index,
                    "shot_progress": frame_num / frame_count,
                    "camera_position": await self._calculate_camera_position(
                        cinematography_plan, shot_index, frame_num / frame_count
                    ),
                    "lens_settings": cinematography_plan["lens_choices"][shot_index],
                    "movement_state": await self._calculate_movement_state(
                        cinematography_plan, shot_index, frame_num / frame_count
                    )
                }

                frame_breakdown.append(frame_data)

        return frame_breakdown

    async def _calculate_camera_position(
        self,
        cinematography_plan: Dict[str, Any],
        shot_index: int,
        progress: float
    ) -> Dict[str, Any]:
        """Calculate camera position for specific frame"""

        movement = cinematography_plan["camera_movements"][shot_index]
        movement_type = movement.get("description", "static")

        if "zoom" in movement_type:
            zoom_factor = 1.0 + (progress * 0.5)  # Example zoom calculation
            return {"zoom_factor": zoom_factor, "position": "static"}
        elif "dolly" in movement_type:
            dolly_distance = progress * 2.0  # Example dolly calculation
            return {"dolly_distance": dolly_distance, "position": "moving"}
        else:
            return {"position": "static", "stability": "locked"}

    async def _calculate_movement_state(
        self,
        cinematography_plan: Dict[str, Any],
        shot_index: int,
        progress: float
    ) -> Dict[str, Any]:
        """Calculate movement state for specific frame"""

        movement = cinematography_plan["camera_movements"][shot_index]

        return {
            "movement_type": movement.get("description", "static"),
            "progress": progress,
            "velocity": await self._calculate_velocity(movement, progress),
            "acceleration": await self._calculate_acceleration(movement, progress)
        }

    async def _calculate_velocity(self, movement: Dict[str, Any], progress: float) -> float:
        """Calculate camera velocity for smooth movement"""
        # Smooth acceleration/deceleration curve
        if progress < 0.2:
            return progress * 5  # Accelerate
        elif progress > 0.8:
            return (1 - progress) * 5  # Decelerate
        else:
            return 1.0  # Constant velocity

    async def _calculate_acceleration(self, movement: Dict[str, Any], progress: float) -> float:
        """Calculate camera acceleration for natural movement"""
        # Simple acceleration curve
        if progress < 0.2:
            return 5.0  # Positive acceleration
        elif progress > 0.8:
            return -5.0  # Negative acceleration (deceleration)
        else:
            return 0.0  # No acceleration
