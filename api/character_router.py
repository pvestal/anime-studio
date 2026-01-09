#!/usr/bin/env python3
"""
Character Studio Router for Tower Anime Production
Provides CRUD operations for characters from Echo Brain database
"""

import sys
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Import character models and schemas
sys.path.append("/tmp")
from character_studio_patch import (CharacterGenerationRequest, CharacterProfile,
                                    CharacterProfileCreate, CharacterProfileResponse,
                                    CharacterProfileUpdate, build_character_prompt)

# Database setup for Echo Brain
ECHO_BRAIN_DATABASE_URL = (
    "postgresql://patrick:tower_echo_brain_secret_key_2025@192.168.50.135/echo_brain"
)
echo_brain_engine = create_engine(ECHO_BRAIN_DATABASE_URL)
EchoBrainSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=echo_brain_engine
)

# Create router
character_router = APIRouter(prefix="/api/anime", tags=["characters"])


# Dependency for Echo Brain database
def get_echo_brain_db():
    db = EchoBrainSessionLocal()
    try:
        yield db
    finally:
        db.close()


@character_router.get("/characters", response_model=List[CharacterProfileResponse])
async def list_characters(echo_db: Session = Depends(get_echo_brain_db)):
    """List all active characters from Echo Brain database"""
    characters = (
        echo_db.query(CharacterProfile).filter(CharacterProfile.is_active).all()
    )
    return characters


@character_router.get(
    "/characters/{character_id}", response_model=CharacterProfileResponse
)
async def get_character(
    character_id: int, echo_db: Session = Depends(get_echo_brain_db)
):
    """Get specific character by ID"""
    character = (
        echo_db.query(CharacterProfile)
        .filter(CharacterProfile.id == character_id, CharacterProfile.is_active)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@character_router.post("/characters", response_model=CharacterProfileResponse)
async def create_character(
    character: CharacterProfileCreate, echo_db: Session = Depends(get_echo_brain_db)
):
    """Create new character in Echo Brain database"""
    # Check if character name already exists
    existing = (
        echo_db.query(CharacterProfile)
        .filter(CharacterProfile.character_name == character.character_name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Character name already exists")

    # Create character
    db_character = CharacterProfile(**character.dict())
    echo_db.add(db_character)
    echo_db.commit()
    echo_db.refresh(db_character)
    return db_character


@character_router.put(
    "/characters/{character_id}", response_model=CharacterProfileResponse
)
async def update_character(
    character_id: int,
    character_update: CharacterProfileUpdate,
    echo_db: Session = Depends(get_echo_brain_db),
):
    """Update existing character"""
    character = (
        echo_db.query(CharacterProfile)
        .filter(CharacterProfile.id == character_id, CharacterProfile.is_active)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    # Update fields
    update_data = character_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(character, field, value)

    from datetime import datetime

    character.updated_at = datetime.utcnow()
    echo_db.commit()
    echo_db.refresh(character)
    return character


@character_router.delete("/characters/{character_id}")
async def delete_character(
    character_id: int, echo_db: Session = Depends(get_echo_brain_db)
):
    """Soft delete character (set is_active = False)"""
    character = (
        echo_db.query(CharacterProfile)
        .filter(CharacterProfile.id == character_id, CharacterProfile.is_active)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    character.is_active = False
    from datetime import datetime

    character.updated_at = datetime.utcnow()
    echo_db.commit()
    return {"message": "Character deleted successfully"}


@character_router.post("/characters/{character_id}/generate")
async def generate_character_image(
    character_id: int,
    generation_request: CharacterGenerationRequest,
    echo_db: Session = Depends(get_echo_brain_db),
):
    """Generate image for specific character with enhanced prompts"""
    # Get character
    character = (
        echo_db.query(CharacterProfile)
        .filter(CharacterProfile.id == character_id, CharacterProfile.is_active)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    # Build comprehensive character prompt
    character_prompt = build_character_prompt(character, generation_request.prompt)

    # Update character generation stats
    character.generation_count += 1
    from datetime import datetime

    character.last_generated = datetime.utcnow()
    echo_db.commit()

    # Return generation details (actual ComfyUI integration would be handled by main service)
    return {
        "status": "generation_prepared",
        "character_id": character_id,
        "character_name": character.character_name,
        "enhanced_prompt": character_prompt,
        "generation_count": character.generation_count,
        "message": f"Enhanced prompt prepared for {character.character_name}",
        "comfyui_params": {
            "prompt": character_prompt,
            "scene_type": generation_request.scene_type,
            "duration": generation_request.duration,
            "style": generation_request.style,
            "quality": generation_request.quality,
        },
    }


@character_router.get("/characters/{character_id}/prompt-preview")
async def preview_character_prompt(
    character_id: int,
    additional_prompt: str = "",
    echo_db: Session = Depends(get_echo_brain_db),
):
    """Preview the enhanced prompt that would be generated for a character"""
    character = (
        echo_db.query(CharacterProfile)
        .filter(CharacterProfile.id == character_id, CharacterProfile.is_active)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    enhanced_prompt = build_character_prompt(character, additional_prompt)

    return {
        "character_name": character.character_name,
        "enhanced_prompt": enhanced_prompt,
        "prompt_parts": {
            "character_name": character.character_name,
            "age": character.age,
            "gender": character.gender,
            "physical_description": character.physical_description,
            "hair": (
                f"{character.hair_color} {character.hair_style}"
                if character.hair_color and character.hair_style
                else None
            ),
            "eyes": character.eye_color,
            "distinctive_features": character.distinctive_features,
            "art_style": character.art_style or character.visual_style,
            "occupation": character.occupation,
            "custom_prompts": character.generation_prompts,
            "additional": additional_prompt,
        },
    }


if __name__ == "__main__":
    print("Character Studio Router - Use by including in main FastAPI app")
