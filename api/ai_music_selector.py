#!/usr/bin/env python3
"""
AI-Powered Music Selection Engine
Integrates with Echo Brain to provide intelligent music recommendations for anime scenes.
Uses content analysis, mood detection, and contextual understanding for optimal music selection.

Author: Claude Code
Created: 2025-12-15
Service: Anime Production AI Music Selection
"""

import asyncio
import json
import logging
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import redis
import sqlite3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SceneContext(BaseModel):
    """Rich context about an anime scene for music selection"""
    scene_id: str
    duration: float
    emotional_arc: List[Dict[str, float]]  # Timeline of emotional progression
    visual_elements: Dict[str, Any]
    dialogue_density: float = Field(ge=0.0, le=1.0)
    action_sequences: List[Dict[str, float]]  # Action peaks with timestamps
    character_focus: List[str]  # Main characters in scene
    setting: str  # Location/environment
    time_of_day: str
    weather: Optional[str] = None
    narrative_importance: float = Field(ge=0.0, le=1.0)  # Story significance


class MusicCriteria(BaseModel):
    """Criteria for AI music selection"""
    primary_emotion: str
    energy_level: float = Field(ge=0.0, le=1.0)
    tension_arc: List[float]  # How tension should evolve
    genre_preferences: List[str] = []
    cultural_context: str = "japanese"
    instrumentation_hints: List[str] = []
    avoid_lyrics: bool = False
    target_bpm_range: Optional[Tuple[int, int]] = None


class MusicRecommendation(BaseModel):
    """AI-generated music recommendation"""
    track_id: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    emotional_match: float = Field(ge=0.0, le=1.0)
    timing_compatibility: float = Field(ge=0.0, le=1.0)
    cultural_appropriateness: float = Field(ge=0.0, le=1.0)
    suggested_sync_points: List[Dict[str, Any]]
    fallback_options: List[str] = []


class AIMatchingResult(BaseModel):
    """Complete AI matching result with multiple options"""
    scene_id: str
    primary_recommendation: MusicRecommendation
    alternative_options: List[MusicRecommendation]
    echo_brain_analysis: Dict[str, Any]
    selection_metadata: Dict[str, Any]


class AIMusicSelector:
    """AI-powered music selection engine"""

    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.db_path = "/opt/tower-anime-production/database/anime_production.db"
        self.echo_brain_base = "http://localhost:8309"
        self.apple_music_base = "http://localhost:8315"

        # Emotion-to-music mappings refined by AI learning
        self.emotion_mappings = {
            "peaceful": {"bpm_range": (60, 90), "energy": 0.2, "genres": ["ambient", "piano", "acoustic"]},
            "romantic": {"bmp_range": (70, 100), "energy": 0.4, "genres": ["ballad", "soft rock", "piano"]},
            "nostalgic": {"bpm_range": (80, 110), "energy": 0.3, "genres": ["indie", "folk", "acoustic"]},
            "dramatic": {"bpm_range": (90, 130), "energy": 0.7, "genres": ["orchestral", "cinematic", "epic"]},
            "tense": {"bmp_range": (100, 140), "energy": 0.8, "genres": ["thriller", "dark ambient", "electronic"]},
            "action": {"bpm_range": (130, 180), "energy": 0.9, "genres": ["rock", "electronic", "metal"]},
            "comedic": {"bpm_range": (110, 150), "energy": 0.6, "genres": ["upbeat", "quirky", "jazz"]},
            "melancholic": {"bpm_range": (60, 90), "energy": 0.3, "genres": ["sad piano", "strings", "ambient"]}
        }

    async def analyze_scene_for_music(self, scene_context: SceneContext) -> MusicCriteria:
        """Analyze scene context to determine optimal music criteria"""

        try:
            # Extract primary emotion from emotional arc
            if scene_context.emotional_arc:
                emotions = [point.get("emotion", "neutral") for point in scene_context.emotional_arc]
                emotion_weights = [point.get("intensity", 0.5) for point in scene_context.emotional_arc]

                # Weighted average of emotions
                primary_emotion = self._determine_primary_emotion(emotions, emotion_weights)
            else:
                primary_emotion = "neutral"

            # Calculate energy level from action sequences and emotional intensity
            energy_level = await self._calculate_scene_energy(scene_context)

            # Generate tension arc based on scene progression
            tension_arc = self._generate_tension_arc(scene_context)

            # Determine genre preferences based on context
            genre_preferences = await self._determine_genre_preferences(scene_context)

            # Calculate target BPM range
            bpm_range = self._calculate_target_bpm_range(scene_context, primary_emotion)

            # Determine instrumentation hints
            instrumentation_hints = self._suggest_instrumentation(scene_context, primary_emotion)

            # Check if lyrics should be avoided (high dialogue density)
            avoid_lyrics = scene_context.dialogue_density > 0.7

            return MusicCriteria(
                primary_emotion=primary_emotion,
                energy_level=energy_level,
                tension_arc=tension_arc,
                genre_preferences=genre_preferences,
                cultural_context="japanese",  # Default for anime
                instrumentation_hints=instrumentation_hints,
                avoid_lyrics=avoid_lyrics,
                target_bpm_range=bpm_range
            )

        except Exception as e:
            logger.error(f"Scene analysis failed: {e}")
            # Return safe defaults
            return MusicCriteria(
                primary_emotion="neutral",
                energy_level=0.5,
                tension_arc=[0.5] * 5,
                genre_preferences=["ambient", "orchestral"]
            )

    def _determine_primary_emotion(self, emotions: List[str], weights: List[float]) -> str:
        """Determine primary emotion from weighted list"""

        emotion_scores = {}
        for emotion, weight in zip(emotions, weights):
            emotion_scores[emotion] = emotion_scores.get(emotion, 0) + weight

        return max(emotion_scores, key=emotion_scores.get, default="neutral")

    async def _calculate_scene_energy(self, scene_context: SceneContext) -> float:
        """Calculate overall energy level of the scene"""

        energy_factors = []

        # Base energy from emotional arc
        if scene_context.emotional_arc:
            avg_intensity = sum(point.get("intensity", 0.5) for point in scene_context.emotional_arc) / len(scene_context.emotional_arc)
            energy_factors.append(avg_intensity * 0.4)

        # Action sequence contribution
        if scene_context.action_sequences:
            action_intensity = sum(seq.get("intensity", 0.5) for seq in scene_context.action_sequences) / len(scene_context.action_sequences)
            energy_factors.append(action_intensity * 0.3)

        # Dialogue density (inverse contribution - high dialogue = lower music energy)
        dialogue_factor = (1.0 - scene_context.dialogue_density) * 0.2
        energy_factors.append(dialogue_factor)

        # Narrative importance (important scenes tend to be more energetic)
        energy_factors.append(scene_context.narrative_importance * 0.1)

        return min(1.0, sum(energy_factors))

    def _generate_tension_arc(self, scene_context: SceneContext) -> List[float]:
        """Generate tension progression throughout the scene"""

        if not scene_context.emotional_arc:
            # Default tension arc: build to middle, release at end
            return [0.3, 0.5, 0.7, 0.6, 0.4]

        # Sample tension from emotional arc
        duration = scene_context.duration
        sample_points = 5
        tension_arc = []

        for i in range(sample_points):
            time_point = (i / (sample_points - 1)) * duration

            # Find closest emotional data point
            closest_point = min(
                scene_context.emotional_arc,
                key=lambda x: abs(x.get("timestamp", 0) - time_point)
            )

            # Convert emotion to tension value
            emotion = closest_point.get("emotion", "neutral")
            intensity = closest_point.get("intensity", 0.5)

            tension_value = self._emotion_to_tension(emotion, intensity)
            tension_arc.append(tension_value)

        return tension_arc

    def _emotion_to_tension(self, emotion: str, intensity: float) -> float:
        """Convert emotion and intensity to tension value"""

        tension_map = {
            "peaceful": 0.1,
            "romantic": 0.3,
            "nostalgic": 0.4,
            "dramatic": 0.8,
            "tense": 0.9,
            "action": 0.95,
            "comedic": 0.5,
            "melancholic": 0.6
        }

        base_tension = tension_map.get(emotion, 0.5)
        return min(1.0, base_tension * intensity)

    async def _determine_genre_preferences(self, scene_context: SceneContext) -> List[str]:
        """Determine appropriate music genres for the scene"""

        genres = []

        # Setting-based genres
        setting = scene_context.setting.lower()
        if "school" in setting:
            genres.extend(["j-pop", "indie", "acoustic"])
        elif "battle" in setting or "fight" in setting:
            genres.extend(["rock", "electronic", "epic"])
        elif "home" in setting or "room" in setting:
            genres.extend(["piano", "soft", "ambient"])
        elif "nature" in setting or "outdoor" in setting:
            genres.extend(["orchestral", "ambient", "folk"])

        # Time of day influences
        time_of_day = scene_context.time_of_day.lower()
        if "night" in time_of_day or "evening" in time_of_day:
            genres.extend(["ambient", "slow", "mysterious"])
        elif "morning" in time_of_day:
            genres.extend(["upbeat", "bright", "piano"])

        # Character focus influences
        if len(scene_context.character_focus) == 1:
            # Single character focus - more intimate music
            genres.extend(["solo piano", "acoustic", "intimate"])
        elif len(scene_context.character_focus) > 3:
            # Group scene - more energetic music
            genres.extend(["ensemble", "full orchestra", "dynamic"])

        # Remove duplicates and return top genres
        unique_genres = list(set(genres))
        return unique_genres[:5]

    def _calculate_target_bpm_range(self, scene_context: SceneContext, primary_emotion: str) -> Tuple[int, int]:
        """Calculate target BPM range based on scene characteristics"""

        # Start with emotion-based range
        emotion_mapping = self.emotion_mappings.get(primary_emotion, {"bpm_range": (90, 130)})
        base_min, base_max = emotion_mapping.get("bpm_range", (90, 130))

        # Adjust based on action sequences
        if scene_context.action_sequences:
            action_boost = len(scene_context.action_sequences) * 10
            base_min += action_boost
            base_max += action_boost

        # Adjust based on dialogue density
        if scene_context.dialogue_density > 0.6:
            # Lower BPM for dialogue-heavy scenes
            base_min = max(60, base_min - 20)
            base_max = max(100, base_max - 20)

        # Ensure reasonable range
        final_min = max(50, min(200, base_min))
        final_max = max(final_min + 20, min(220, base_max))

        return (final_min, final_max)

    def _suggest_instrumentation(self, scene_context: SceneContext, primary_emotion: str) -> List[str]:
        """Suggest instrumentation based on scene context"""

        instruments = []

        # Emotion-based instrumentation
        if primary_emotion in ["peaceful", "melancholic", "romantic"]:
            instruments.extend(["piano", "strings", "acoustic guitar"])
        elif primary_emotion in ["dramatic", "tense"]:
            instruments.extend(["orchestra", "brass", "percussion"])
        elif primary_emotion in ["action", "energetic"]:
            instruments.extend(["electric guitar", "drums", "synthesizer"])

        # Setting-based additions
        setting = scene_context.setting.lower()
        if "traditional" in setting or "temple" in setting:
            instruments.extend(["shamisen", "taiko", "flute"])
        elif "modern" in setting or "city" in setting:
            instruments.extend(["electronic", "synthesizer", "electric"])
        elif "nature" in setting:
            instruments.extend(["acoustic", "wind instruments", "natural sounds"])

        return list(set(instruments))[:4]

    async def find_matching_tracks(self, criteria: MusicCriteria, limit: int = 10) -> List[Dict[str, Any]]:
        """Find tracks that match the given criteria using Echo Brain and Apple Music"""

        try:
            # First, get AI-powered recommendations from Echo Brain
            echo_recommendations = await self._get_echo_brain_recommendations(criteria)

            # Search Apple Music catalog based on criteria
            apple_music_tracks = await self._search_apple_music_tracks(criteria)

            # Combine and score all candidates
            all_candidates = echo_recommendations + apple_music_tracks

            # Score and rank tracks
            scored_tracks = []
            for track in all_candidates:
                score = await self._score_track_compatibility(track, criteria)
                if score > 0.4:  # Minimum compatibility threshold
                    track["compatibility_score"] = score
                    scored_tracks.append(track)

            # Sort by compatibility score and return top matches
            scored_tracks.sort(key=lambda x: x["compatibility_score"], reverse=True)
            return scored_tracks[:limit]

        except Exception as e:
            logger.error(f"Track matching failed: {e}")
            return []

    async def _get_echo_brain_recommendations(self, criteria: MusicCriteria) -> List[Dict[str, Any]]:
        """Get music recommendations from Echo Brain AI"""

        try:
            # Construct detailed query for Echo Brain
            query = f"""
            Recommend anime background music for:
            - Primary emotion: {criteria.primary_emotion}
            - Energy level: {criteria.energy_level}
            - Cultural context: {criteria.cultural_context}
            - Preferred genres: {', '.join(criteria.genre_preferences)}
            - Instrumentation: {', '.join(criteria.instrumentation_hints)}
            - Avoid lyrics: {criteria.avoid_lyrics}
            - Target BPM: {criteria.target_bpm_range}

            Provide specific track suggestions with reasoning for each recommendation.
            Focus on tracks that would enhance the emotional impact of the scene.
            """

            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{self.echo_brain_base}/api/echo/query",
                    json={
                        "query": query,
                        "conversation_id": "anime_music_selection",
                        "context_type": "music_recommendation",
                        "response_format": "structured"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    return self._parse_echo_recommendations(result.get("response", ""))
                else:
                    logger.warning(f"Echo Brain request failed: {response.status_code}")
                    return []

        except Exception as e:
            logger.warning(f"Echo Brain recommendation failed: {e}")
            return []

    def _parse_echo_recommendations(self, echo_response: str) -> List[Dict[str, Any]]:
        """Parse Echo Brain response into structured track recommendations"""

        tracks = []

        try:
            # Simple parsing of Echo Brain response
            # Look for track suggestions in the response
            lines = echo_response.split('\n')
            current_track = {}

            for line in lines:
                line = line.strip()
                if not line:
                    if current_track:
                        tracks.append(current_track)
                        current_track = {}
                    continue

                # Look for track title patterns
                if line.startswith("Track:") or line.startswith("Song:") or line.startswith("-"):
                    title_match = re.search(r'["\'](.*?)["\']|Track:\s*(.+)|Song:\s*(.+)|-\s*(.+)', line)
                    if title_match:
                        title = title_match.group(1) or title_match.group(2) or title_match.group(3) or title_match.group(4)
                        current_track["title"] = title.strip()

                # Look for artist information
                elif "by" in line.lower() and "artist" in line.lower():
                    artist_match = re.search(r'by\s+([^,\n]+)', line, re.IGNORECASE)
                    if artist_match:
                        current_track["artist"] = artist_match.group(1).strip()

                # Look for reasoning
                elif "because" in line.lower() or "reason" in line.lower():
                    current_track["echo_reasoning"] = line

                # Look for genre information
                elif "genre" in line.lower():
                    genre_match = re.search(r'genre[:\s]+([^,\n]+)', line, re.IGNORECASE)
                    if genre_match:
                        current_track["genre"] = genre_match.group(1).strip()

            # Add final track if exists
            if current_track:
                tracks.append(current_track)

            # Add metadata to tracks
            for track in tracks:
                if "title" in track:
                    track["source"] = "echo_brain"
                    track["recommendation_type"] = "ai_generated"
                    track["track_id"] = f"echo_{hash(track['title'])}_{int(time.time())}"

        except Exception as e:
            logger.error(f"Failed to parse Echo Brain recommendations: {e}")

        return tracks

    async def _search_apple_music_tracks(self, criteria: MusicCriteria) -> List[Dict[str, Any]]:
        """Search Apple Music catalog based on criteria"""

        tracks = []

        try:
            # Build search queries based on criteria
            search_queries = []

            # Genre-based searches
            for genre in criteria.genre_preferences[:3]:  # Limit to top 3 genres
                search_queries.append(f"{genre} japanese anime")
                search_queries.append(f"{genre} instrumental")

            # Emotion-based searches
            emotion_terms = {
                "peaceful": ["peaceful", "calm", "serene"],
                "dramatic": ["dramatic", "epic", "powerful"],
                "action": ["energetic", "intense", "fast"],
                "romantic": ["romantic", "love", "gentle"],
                "melancholic": ["sad", "melancholy", "emotional"]
            }

            emotion_keywords = emotion_terms.get(criteria.primary_emotion, [criteria.primary_emotion])
            for keyword in emotion_keywords:
                search_queries.append(f"{keyword} anime soundtrack")

            # Execute searches
            async with httpx.AsyncClient(timeout=15) as client:
                for query in search_queries[:5]:  # Limit API calls
                    try:
                        response = await client.get(
                            f"{self.apple_music_base}/api/apple-music/search",
                            params={
                                "q": query,
                                "types": "songs",
                                "limit": 10
                            }
                        )

                        if response.status_code == 200:
                            results = response.json()
                            song_data = results.get("results", {}).get("songs", {}).get("data", [])

                            for song in song_data:
                                track_info = self._extract_apple_music_track_info(song)
                                if track_info:
                                    tracks.append(track_info)

                    except Exception as e:
                        logger.warning(f"Apple Music search failed for '{query}': {e}")

        except Exception as e:
            logger.error(f"Apple Music search failed: {e}")

        return tracks

    def _extract_apple_music_track_info(self, song_data: Dict) -> Optional[Dict[str, Any]]:
        """Extract relevant track information from Apple Music API response"""

        try:
            attributes = song_data.get("attributes", {})

            track_info = {
                "track_id": song_data.get("id", ""),
                "title": attributes.get("name", ""),
                "artist": attributes.get("artistName", ""),
                "album": attributes.get("albumName", ""),
                "duration": attributes.get("durationInMillis", 0) / 1000.0,  # Convert to seconds
                "apple_music_id": song_data.get("id"),
                "source": "apple_music",
                "preview_url": attributes.get("previews", [{}])[0].get("url"),
                "artwork_url": attributes.get("artwork", {}).get("url"),
                "genre": attributes.get("genreNames", [""])[0] if attributes.get("genreNames") else "",
                "release_date": attributes.get("releaseDate", "")
            }

            # Only return if we have essential information
            if track_info["title"] and track_info["artist"]:
                return track_info

        except Exception as e:
            logger.warning(f"Failed to extract track info: {e}")

        return None

    async def _score_track_compatibility(self, track: Dict[str, Any], criteria: MusicCriteria) -> float:
        """Score how well a track matches the criteria"""

        score_components = []

        # Genre compatibility
        track_genre = track.get("genre", "").lower()
        genre_score = 0.0
        for pref_genre in criteria.genre_preferences:
            if pref_genre.lower() in track_genre or track_genre in pref_genre.lower():
                genre_score = 1.0
                break
            # Partial matches
            elif any(word in track_genre for word in pref_genre.lower().split()):
                genre_score = max(genre_score, 0.6)

        score_components.append(("genre", genre_score, 0.3))

        # Duration compatibility (prefer tracks close to scene length)
        track_duration = track.get("duration", 180)
        if "scene_duration" in criteria.__dict__:  # If scene duration is available
            scene_duration = criteria.scene_duration
            duration_ratio = min(track_duration, scene_duration) / max(track_duration, scene_duration)
            duration_score = duration_ratio * 0.8 + 0.2  # Minimum 0.2 score
        else:
            duration_score = 0.7  # Default score when scene duration unknown

        score_components.append(("duration", duration_score, 0.1))

        # Title/artist analysis for relevance
        title_lower = track.get("title", "").lower()
        artist_lower = track.get("artist", "").lower()

        relevance_score = 0.5  # Default
        anime_keywords = ["anime", "soundtrack", "opening", "ending", "ost", "theme"]
        emotion_keywords = [criteria.primary_emotion.lower()]

        for keyword in anime_keywords + emotion_keywords:
            if keyword in title_lower or keyword in artist_lower:
                relevance_score = min(1.0, relevance_score + 0.2)

        score_components.append(("relevance", relevance_score, 0.2))

        # Source bonus (prefer Echo Brain recommendations for creativity)
        source_bonus = 0.8 if track.get("source") == "echo_brain" else 0.6
        score_components.append(("source", source_bonus, 0.1))

        # Lyrics penalty if avoid_lyrics is True
        lyrics_score = 1.0
        if criteria.avoid_lyrics:
            # Simple heuristic: check for "instrumental" in title/genre
            if "instrumental" not in title_lower and "instrumental" not in track_genre:
                lyrics_score = 0.5  # Penalty for likely vocal tracks

        score_components.append(("lyrics", lyrics_score, 0.15))

        # Cultural appropriateness (bonus for Japanese content)
        cultural_score = 0.7  # Default
        if "japanese" in artist_lower or "japan" in track_genre or "j-" in track_genre:
            cultural_score = 1.0

        score_components.append(("cultural", cultural_score, 0.15))

        # Calculate weighted score
        total_weight = sum(weight for _, _, weight in score_components)
        final_score = sum(score * weight for _, score, weight in score_components) / total_weight

        return min(1.0, max(0.0, final_score))

    async def generate_recommendations(self, scene_context: SceneContext) -> AIMatchingResult:
        """Generate complete AI-powered music recommendations for a scene"""

        try:
            # Analyze scene to determine music criteria
            criteria = await self.analyze_scene_for_music(scene_context)

            # Find matching tracks
            candidate_tracks = await self.find_matching_tracks(criteria, limit=15)

            if not candidate_tracks:
                raise ValueError("No suitable tracks found for the given criteria")

            # Create detailed recommendations
            recommendations = []
            for i, track in enumerate(candidate_tracks[:5]):  # Top 5 recommendations
                recommendation = await self._create_detailed_recommendation(
                    track, scene_context, criteria
                )
                recommendations.append(recommendation)

            # Get comprehensive Echo Brain analysis
            echo_analysis = await self._get_comprehensive_echo_analysis(
                scene_context, criteria, recommendations
            )

            # Generate selection metadata
            selection_metadata = {
                "criteria_used": criteria.dict(),
                "total_candidates_evaluated": len(candidate_tracks),
                "selection_timestamp": datetime.now().isoformat(),
                "confidence_levels": [rec.confidence_score for rec in recommendations],
                "average_confidence": sum(rec.confidence_score for rec in recommendations) / len(recommendations)
            }

            return AIMatchingResult(
                scene_id=scene_context.scene_id,
                primary_recommendation=recommendations[0],
                alternative_options=recommendations[1:],
                echo_brain_analysis=echo_analysis,
                selection_metadata=selection_metadata
            )

        except Exception as e:
            logger.error(f"AI recommendation generation failed: {e}")
            raise

    async def _create_detailed_recommendation(self,
                                           track: Dict[str, Any],
                                           scene_context: SceneContext,
                                           criteria: MusicCriteria) -> MusicRecommendation:
        """Create detailed recommendation with analysis"""

        # Calculate component scores
        emotional_match = await self._calculate_emotional_match(track, criteria)
        timing_compatibility = await self._calculate_timing_compatibility(track, scene_context)
        cultural_appropriateness = await self._calculate_cultural_appropriateness(track, criteria)

        # Generate reasoning
        reasoning = await self._generate_recommendation_reasoning(
            track, scene_context, criteria, emotional_match, timing_compatibility
        )

        # Suggest sync points
        sync_points = await self._suggest_sync_points(track, scene_context)

        # Find fallback options
        fallback_options = await self._find_fallback_tracks(track, criteria)

        # Calculate overall confidence
        confidence_score = (
            emotional_match * 0.4 +
            timing_compatibility * 0.3 +
            cultural_appropriateness * 0.2 +
            track.get("compatibility_score", 0.7) * 0.1
        )

        return MusicRecommendation(
            track_id=track.get("track_id", ""),
            confidence_score=confidence_score,
            reasoning=reasoning,
            emotional_match=emotional_match,
            timing_compatibility=timing_compatibility,
            cultural_appropriateness=cultural_appropriateness,
            suggested_sync_points=sync_points,
            fallback_options=fallback_options
        )

    async def _calculate_emotional_match(self, track: Dict[str, Any], criteria: MusicCriteria) -> float:
        """Calculate how well track emotion matches criteria"""

        # Simple heuristic based on title and genre analysis
        track_title = track.get("title", "").lower()
        track_genre = track.get("genre", "").lower()

        emotion = criteria.primary_emotion.lower()

        # Direct emotion keyword matching
        if emotion in track_title or emotion in track_genre:
            return 1.0

        # Emotion synonym matching
        emotion_synonyms = {
            "peaceful": ["calm", "serene", "tranquil", "gentle"],
            "dramatic": ["epic", "powerful", "intense", "cinematic"],
            "action": ["energetic", "fast", "dynamic", "exciting"],
            "romantic": ["love", "tender", "soft", "sweet"],
            "melancholic": ["sad", "emotional", "melancholy", "somber"]
        }

        synonyms = emotion_synonyms.get(emotion, [])
        for synonym in synonyms:
            if synonym in track_title or synonym in track_genre:
                return 0.8

        # Default moderate match
        return 0.6

    async def _calculate_timing_compatibility(self, track: Dict[str, Any], scene_context: SceneContext) -> float:
        """Calculate timing compatibility between track and scene"""

        track_duration = track.get("duration", 180)
        scene_duration = scene_context.duration

        # Duration matching
        duration_ratio = min(track_duration, scene_duration) / max(track_duration, scene_duration)

        # Bonus for tracks slightly longer than scenes (allows for fade-out)
        if track_duration > scene_duration and track_duration <= scene_duration * 1.2:
            duration_ratio = min(1.0, duration_ratio + 0.1)

        return duration_ratio

    async def _calculate_cultural_appropriateness(self, track: Dict[str, Any], criteria: MusicCriteria) -> float:
        """Calculate cultural appropriateness of track"""

        if criteria.cultural_context != "japanese":
            return 0.8  # Default for non-Japanese contexts

        # Check for Japanese/anime indicators
        track_artist = track.get("artist", "").lower()
        track_title = track.get("title", "").lower()
        track_genre = track.get("genre", "").lower()

        japanese_indicators = ["japanese", "japan", "anime", "j-pop", "j-rock", "ost", "soundtrack"]

        for indicator in japanese_indicators:
            if indicator in track_artist or indicator in track_title or indicator in track_genre:
                return 1.0

        # Check for non-Japanese indicators that might be inappropriate
        western_indicators = ["american", "british", "western", "country", "folk", "blues"]

        for indicator in western_indicators:
            if indicator in track_genre:
                return 0.3

        return 0.7  # Default neutral score

    async def _generate_recommendation_reasoning(self,
                                               track: Dict[str, Any],
                                               scene_context: SceneContext,
                                               criteria: MusicCriteria,
                                               emotional_match: float,
                                               timing_compatibility: float) -> str:
        """Generate human-readable reasoning for the recommendation"""

        reasoning_parts = []

        # Track basics
        track_title = track.get("title", "Unknown")
        track_artist = track.get("artist", "Unknown")
        reasoning_parts.append(f'"{track_title}" by {track_artist}')

        # Emotional matching
        if emotional_match > 0.8:
            reasoning_parts.append(f"perfectly matches the {criteria.primary_emotion} emotional tone")
        elif emotional_match > 0.6:
            reasoning_parts.append(f"complements the {criteria.primary_emotion} mood")
        else:
            reasoning_parts.append("provides suitable background ambiance")

        # Genre appropriateness
        if criteria.genre_preferences and track.get("genre"):
            track_genre = track.get("genre", "")
            matching_genres = [g for g in criteria.genre_preferences if g.lower() in track_genre.lower()]
            if matching_genres:
                reasoning_parts.append(f"fits the {matching_genres[0]} genre preference")

        # Timing compatibility
        if timing_compatibility > 0.9:
            reasoning_parts.append("has ideal duration for the scene")
        elif timing_compatibility > 0.7:
            reasoning_parts.append("duration works well with scene pacing")

        # Energy level matching
        if criteria.energy_level > 0.7:
            reasoning_parts.append("provides the high energy needed for this scene")
        elif criteria.energy_level < 0.3:
            reasoning_parts.append("offers the subdued energy appropriate for this scene")

        # Source-specific reasoning
        if track.get("source") == "echo_brain":
            reasoning_parts.append("was specifically recommended by AI analysis for creative enhancement")
        elif track.get("source") == "apple_music":
            reasoning_parts.append("is professionally produced and readily available")

        return ". ".join(reasoning_parts).capitalize() + "."

    async def _suggest_sync_points(self, track: Dict[str, Any], scene_context: SceneContext) -> List[Dict[str, Any]]:
        """Suggest specific synchronization points for the track"""

        sync_points = []

        # Scene change sync points
        scene_duration = scene_context.duration
        num_scenes = scene_context.scene_count

        for i in range(num_scenes):
            scene_start_time = (i / num_scenes) * scene_duration
            sync_points.append({
                "timestamp": scene_start_time,
                "sync_type": "scene_transition",
                "description": f"Scene {i + 1} begins",
                "importance": 0.8
            })

        # Action sequence sync points
        for action in scene_context.action_sequences:
            action_start = action.get("start_time", 0)
            action_intensity = action.get("intensity", 0.5)

            sync_points.append({
                "timestamp": action_start,
                "sync_type": "action_peak",
                "description": f"Action sequence (intensity: {action_intensity:.1f})",
                "importance": action_intensity
            })

        # Emotional arc sync points
        for emotion_point in scene_context.emotional_arc[:3]:  # Limit to top 3
            timestamp = emotion_point.get("timestamp", 0)
            emotion = emotion_point.get("emotion", "neutral")

            sync_points.append({
                "timestamp": timestamp,
                "sync_type": "emotional_shift",
                "description": f"Emotional shift to {emotion}",
                "importance": 0.6
            })

        return sorted(sync_points, key=lambda x: x["timestamp"])[:8]  # Limit to 8 points

    async def _find_fallback_tracks(self, primary_track: Dict[str, Any], criteria: MusicCriteria) -> List[str]:
        """Find fallback track options similar to primary recommendation"""

        fallbacks = []

        try:
            # Search for similar tracks by same artist
            artist = primary_track.get("artist", "")
            if artist:
                artist_tracks = await self._search_apple_music_tracks_by_artist(artist)
                fallbacks.extend([t.get("track_id", "") for t in artist_tracks[:2]])

            # Search for tracks in same genre
            genre = primary_track.get("genre", "")
            if genre and len(fallbacks) < 3:
                genre_tracks = await self._search_tracks_by_genre(genre, criteria)
                fallbacks.extend([t.get("track_id", "") for t in genre_tracks[:2]])

            return fallbacks[:3]  # Maximum 3 fallbacks

        except Exception as e:
            logger.warning(f"Fallback track search failed: {e}")
            return []

    async def _search_apple_music_tracks_by_artist(self, artist: str) -> List[Dict[str, Any]]:
        """Search Apple Music for tracks by specific artist"""

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.apple_music_base}/api/apple-music/search",
                    params={
                        "q": f"artist:{artist}",
                        "types": "songs",
                        "limit": 5
                    }
                )

                if response.status_code == 200:
                    results = response.json()
                    songs = results.get("results", {}).get("songs", {}).get("data", [])
                    return [self._extract_apple_music_track_info(song) for song in songs]

        except Exception as e:
            logger.warning(f"Artist search failed: {e}")

        return []

    async def _search_tracks_by_genre(self, genre: str, criteria: MusicCriteria) -> List[Dict[str, Any]]:
        """Search for tracks by genre with criteria filtering"""

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.apple_music_base}/api/apple-music/search",
                    params={
                        "q": f"genre:{genre} anime",
                        "types": "songs",
                        "limit": 5
                    }
                )

                if response.status_code == 200:
                    results = response.json()
                    songs = results.get("results", {}).get("songs", {}).get("data", [])
                    return [self._extract_apple_music_track_info(song) for song in songs if song]

        except Exception as e:
            logger.warning(f"Genre search failed: {e}")

        return []

    async def _get_comprehensive_echo_analysis(self,
                                             scene_context: SceneContext,
                                             criteria: MusicCriteria,
                                             recommendations: List[MusicRecommendation]) -> Dict[str, Any]:
        """Get comprehensive analysis from Echo Brain about the recommendations"""

        try:
            # Prepare detailed context for Echo Brain
            context_summary = f"""
            Scene Analysis:
            - Duration: {scene_context.duration}s
            - Emotion: {criteria.primary_emotion}
            - Energy: {criteria.energy_level}
            - Setting: {scene_context.setting}
            - Characters: {', '.join(scene_context.character_focus)}

            Top Recommendation: "{recommendations[0].track_id}"
            - Confidence: {recommendations[0].confidence_score:.2f}
            - Emotional Match: {recommendations[0].emotional_match:.2f}

            Analyze this music selection and provide insights on:
            1. How well the music enhances the emotional impact
            2. Potential timing and synchronization strategies
            3. Creative opportunities for dynamic music adaptation
            4. Alternative approaches to consider
            """

            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(
                    f"{self.echo_brain_base}/api/echo/query",
                    json={
                        "query": context_summary,
                        "conversation_id": "anime_music_analysis",
                        "context_type": "music_scene_analysis",
                        "depth": "comprehensive"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    return {
                        "analysis": result.get("response", ""),
                        "confidence": result.get("confidence", 0.8),
                        "insights": result.get("insights", []),
                        "suggestions": result.get("suggestions", []),
                        "creative_opportunities": result.get("creative_opportunities", []),
                        "timestamp": datetime.now().isoformat()
                    }

        except Exception as e:
            logger.warning(f"Echo Brain comprehensive analysis failed: {e}")

        # Return minimal analysis on failure
        return {
            "analysis": "Comprehensive analysis unavailable",
            "confidence": 0.5,
            "insights": [],
            "suggestions": [],
            "creative_opportunities": [],
            "timestamp": datetime.now().isoformat()
        }


# FastAPI Application
app = FastAPI(
    title="AI Music Selection Engine",
    description="AI-powered music selection for anime scenes using Echo Brain",
    version="1.0.0"
)

# Global selector instance
ai_music_selector = AIMusicSelector()


@app.post("/api/ai-music/analyze-scene")
async def analyze_scene(scene_context: SceneContext) -> MusicCriteria:
    """Analyze scene context to determine optimal music criteria"""

    try:
        return await ai_music_selector.analyze_scene_for_music(scene_context)
    except Exception as e:
        logger.error(f"Scene analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai-music/find-tracks")
async def find_matching_tracks(criteria: MusicCriteria, limit: int = 10) -> List[Dict[str, Any]]:
    """Find tracks matching the given criteria"""

    try:
        return await ai_music_selector.find_matching_tracks(criteria, limit)
    except Exception as e:
        logger.error(f"Track matching failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai-music/recommend")
async def generate_recommendations(scene_context: SceneContext) -> AIMatchingResult:
    """Generate complete AI-powered music recommendations"""

    try:
        return await ai_music_selector.generate_recommendations(scene_context)
    except Exception as e:
        logger.error(f"Recommendation generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai-music/health")
async def health_check() -> Dict[str, Any]:
    """Service health check"""

    # Check Redis connection
    redis_status = "connected"
    try:
        ai_music_selector.redis_client.ping()
    except:
        redis_status = "disconnected"

    # Check Echo Brain connection
    echo_brain_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{ai_music_selector.echo_brain_base}/api/echo/health")
            echo_brain_status = "connected" if response.status_code == 200 else "error"
    except:
        echo_brain_status = "disconnected"

    # Check Apple Music connection
    apple_music_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{ai_music_selector.apple_music_base}/api/apple-music/health")
            apple_music_status = "connected" if response.status_code == 200 else "error"
    except:
        apple_music_status = "disconnected"

    return {
        "status": "healthy",
        "service": "ai-music-selector",
        "dependencies": {
            "redis": redis_status,
            "echo_brain": echo_brain_status,
            "apple_music": apple_music_status
        },
        "features": [
            "Scene emotion analysis",
            "AI-powered track recommendations",
            "Echo Brain integration",
            "Apple Music catalog search",
            "Compatibility scoring",
            "Sync point suggestions"
        ],
        "emotion_mappings": len(ai_music_selector.emotion_mappings),
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    logger.info("🤖 Starting AI Music Selection Engine")
    uvicorn.run(app, host="127.0.0.1", port=8317, log_level="info")