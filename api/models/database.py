"""
Database models for Tower Anime Production API
"""
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime

# Database Setup
DATABASE_PASSWORD = os.getenv('DATABASE_PASSWORD')
if not DATABASE_PASSWORD:
    raise ValueError("DATABASE_PASSWORD environment variable is required")
DATABASE_URL = f"postgresql://patrick:{DATABASE_PASSWORD}@localhost/anime_production"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class AnimeProject(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    style = Column(String, default="anime")
    characters = Column(JSONB, default=list)  # Legacy field, use character_list relationship
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    character_list = relationship("Character", back_populates="project")

class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"))
    age = Column(Integer)
    personality = Column(Text)
    background = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("AnimeProject", back_populates="character_list")

class Scene(Base):
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    title = Column(String, nullable=False)
    description = Column(Text)
    visual_description = Column(Text)
    scene_number = Column(Integer, default=1)
    status = Column(String, default="draft")
    prompt = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("AnimeProject")

class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    title = Column(String, nullable=False)
    episode_number = Column(Integer)
    description = Column(Text)
    script = Column(Text)
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("AnimeProject")

class ProductionJob(Base):
    __tablename__ = "production_jobs"

    id = Column(String, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    job_type = Column(String)
    prompt = Column(Text)
    parameters = Column(JSONB)
    status = Column(String, default="pending")
    progress = Column(Float, default=0.0)
    result_path = Column(String)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    project = relationship("AnimeProject")

class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Database dependency
def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()