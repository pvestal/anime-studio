#!/usr/bin/env python3
"""
Character Studio Integration Patch for Tower Anime Production
Adds character management endpoints with Echo Brain integration
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base

# Character model for Echo Brain database (existing table)
EchoBrainBase = declarative_base()


class CharacterProfile(EchoBrainBase):
    __tablename__ = "character_profiles"

    id = Column(Integer, primary_key=True, index=True)
    character_name = Column(String(100), nullable=False, unique=True)
    creator = Column(String(100), nullable=False, default="Patrick Vestal")
    source_franchise = Column(String(200), nullable=False)
    character_type = Column(String(50), nullable=False, default="original")
    age = Column(Integer)
    gender = Column(String(20))
    physical_description = Column(Text)
    height = Column(String(20))
    build = Column(String(50))
    hair_color = Column(String(100))
    hair_style = Column(String(100))
    eye_color = Column(String(100))
    distinctive_features = Column(Text)
    personality_traits = Column(Text)
    background_story = Column(Text)
    occupation = Column(String(100))
    skills_abilities = Column(Text)
    relationships = Column(Text)
    visual_style = Column(String(100))
    art_style = Column(String(100))
    reference_images = Column(JSONB, default=[])
    style_elements = Column(JSONB, default=[])
    generation_prompts = Column(Text)
    generation_count = Column(Integer, default=0)
    consistency_score = Column(Numeric(3, 2), default=0.0)
    last_generated = Column(DateTime)
    conversation_mentions = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)
    is_active = Column(Boolean, default=True)


# Pydantic models for API


class CharacterProfileCreate(BaseModel):
    character_name: str
    source_franchise: str = "Tower Studio Original"
    character_type: str = "original"
    age: Optional[int] = None
    gender: Optional[str] = None
    physical_description: Optional[str] = None
    height: Optional[str] = None
    build: Optional[str] = None
    hair_color: Optional[str] = None
    hair_style: Optional[str] = None
    eye_color: Optional[str] = None
    distinctive_features: Optional[str] = None
    personality_traits: Optional[str] = None
    background_story: Optional[str] = None
    occupation: Optional[str] = None
    skills_abilities: Optional[str] = None
    relationships: Optional[str] = None
    visual_style: Optional[str] = None
    art_style: Optional[str] = None
    reference_images: Optional[List[dict]] = []
    style_elements: Optional[List[dict]] = []
    generation_prompts: Optional[str] = None
    notes: Optional[str] = None


class CharacterProfileUpdate(BaseModel):
    character_name: Optional[str] = None
    source_franchise: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    physical_description: Optional[str] = None
    height: Optional[str] = None
    build: Optional[str] = None
    hair_color: Optional[str] = None
    hair_style: Optional[str] = None
    eye_color: Optional[str] = None
    distinctive_features: Optional[str] = None
    personality_traits: Optional[str] = None
    background_story: Optional[str] = None
    occupation: Optional[str] = None
    skills_abilities: Optional[str] = None
    relationships: Optional[str] = None
    visual_style: Optional[str] = None
    art_style: Optional[str] = None
    reference_images: Optional[List[dict]] = None
    style_elements: Optional[List[dict]] = None
    generation_prompts: Optional[str] = None
    notes: Optional[str] = None


class CharacterProfileResponse(BaseModel):
    id: int
    character_name: str
    creator: str
    source_franchise: str
    character_type: str
    age: Optional[int]
    gender: Optional[str]
    physical_description: Optional[str]
    height: Optional[str]
    build: Optional[str]
    hair_color: Optional[str]
    hair_style: Optional[str]
    eye_color: Optional[str]
    distinctive_features: Optional[str]
    personality_traits: Optional[str]
    background_story: Optional[str]
    occupation: Optional[str]
    skills_abilities: Optional[str]
    relationships: Optional[str]
    visual_style: Optional[str]
    art_style: Optional[str]
    reference_images: List[dict]
    style_elements: List[dict]
    generation_prompts: Optional[str]
    generation_count: int
    consistency_score: float
    last_generated: Optional[datetime]
    conversation_mentions: int
    created_at: datetime
    updated_at: datetime
    notes: Optional[str]
    is_active: bool


    class Config:
        from_attributes = True


class CharacterGenerationRequest(BaseModel):
    prompt: Optional[str] = ""
    scene_type: str = "portrait"
    duration: int = 3
    style: str = "anime"
    quality: str = "high"


def build_character_prompt(character: CharacterProfile, additional_prompt: str = "") -> str:
    """Build comprehensive prompt from character data"""
    prompt_parts = []

    # Base character info
    if character.character_name:
        prompt_parts.append(f"character name: {character.character_name}")

    # Physical description
    physical_parts = []
    if character.age:
        physical_parts.append(f"{character.age} years old")
    if character.gender:
        physical_parts.append(character.gender.lower())
    if character.height:
        physical_parts.append(f"height: {character.height}")
    if character.build:
        physical_parts.append(f"build: {character.build}")

    if physical_parts:
        prompt_parts.append(", ".join(physical_parts))

    # Hair and eyes
    if character.hair_color and character.hair_style:
        prompt_parts.append(f"{character.hair_color} {character.hair_style} hair")
    elif character.hair_color:
        prompt_parts.append(f"{character.hair_color} hair")
    elif character.hair_style:
        prompt_parts.append(f"{character.hair_style} hair")

    if character.eye_color:
        prompt_parts.append(f"{character.eye_color} eyes")

    # Distinctive features
    if character.distinctive_features:
        prompt_parts.append(character.distinctive_features)

    # Occupation/role
    if character.occupation:
        prompt_parts.append(f"occupation: {character.occupation}")

    # Art style
    if character.art_style:
        prompt_parts.append(f"art style: {character.art_style}")
    elif character.visual_style:
        prompt_parts.append(f"style: {character.visual_style}")

    # Use generation prompts if available
    if character.generation_prompts:
        prompt_parts.append(character.generation_prompts)

    # Add additional prompt
    if additional_prompt:
        prompt_parts.append(additional_prompt)

    # Combine with anime quality enhancers
    base_prompt = ", ".join(prompt_parts)
    enhanced_prompt = f"masterpiece, best quality, {base_prompt}, anime style, detailed, high resolution, professional art"

    return enhanced_prompt
