"""
Characters router for Tower Anime Production API
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List
from api.models.database import get_db, Character, AnimeProject
from api.dependencies.auth import require_auth

router = APIRouter(prefix="/api/anime/characters", tags=["characters"])

@router.get("")
async def get_characters(current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):
    """Get all characters with their projects using SQLAlchemy ORM"""
    characters = db.query(Character).join(AnimeProject).all()
    return [
        {
            "id": char.id,
            "name": char.name,
            "description": char.description,
            "project_id": char.project_id,
            "project_name": char.project.name if char.project else None,
            "age": char.age,
            "personality": char.personality,
            "background": char.background
        }
        for char in characters
    ]

@router.post("")
async def create_character(data: dict, current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):
    """Create character using SQLAlchemy ORM"""
    character = Character(
        name=data["name"],
        description=data.get("description"),
        project_id=data.get("project_id"),
        age=data.get("age"),
        personality=data.get("personality"),
        background=data.get("background")
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return {"id": character.id, "name": character.name}

@router.delete("/{character_id}")
async def delete_character(character_id: int, current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):
    """Delete character using SQLAlchemy ORM"""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    db.delete(character)
    db.commit()
    return {"message": "Character deleted"}

@router.get("/list")
async def list_all_characters(current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):
    """List all characters with their projects using SQLAlchemy ORM"""
    characters = db.query(Character).join(AnimeProject).all()
    return [
        {
            "id": char.id,
            "name": char.name,
            "description": char.description,
            "project_id": char.project_id,
            "project_name": char.project.name if char.project else None
        }
        for char in characters
    ]