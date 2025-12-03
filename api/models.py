"""
Database models for anime production system.
Extracted from the 4286-line main.py for modularity.
"""

from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class AnimeProject(Base):
    __tablename__ = 'projects'
    __table_args__ = {'schema': 'anime_api'}

    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(Text)
    status = Column(String)
    metadata_ = Column('metadata', JSON)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    retry_count = Column(Integer)
    generation_start_time = Column(DateTime)
    output_path = Column(Text)
    quality_score = Column(String)  # Using String to match double precision
    completion_metadata = Column(Text)
    failure_reason = Column(Text)
    directory_path = Column(Text)
    style_guide = Column(JSON)

    # Relationships
    jobs = relationship("ProductionJob", back_populates="project")
    bible = relationship("ProjectBible", back_populates="project", uselist=False)


class ProductionJob(Base):
    __tablename__ = 'production_jobs'
    __table_args__ = {'schema': 'anime_api'}

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('anime_api.projects.id'))
    job_type = Column(String, nullable=False)
    status = Column(String, default='pending')
    prompt = Column(Text)
    comfyui_job_id = Column(String)
    output_path = Column(String)
    error = Column(Text)
    extra_metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    project = relationship("AnimeProject", back_populates="jobs")


class ProjectBible(Base):
    __tablename__ = 'project_bibles'
    __table_args__ = {'schema': 'anime_api'}

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('anime_api.projects.id'), unique=True)
    story_premise = Column(Text)
    world_setting = Column(JSON)
    visual_style = Column(JSON)
    extra_metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("AnimeProject", back_populates="bible")
    characters = relationship("BibleCharacter", back_populates="bible")


class BibleCharacter(Base):
    __tablename__ = 'bible_characters'
    __table_args__ = {'schema': 'anime_api'}

    id = Column(Integer, primary_key=True)
    bible_id = Column(Integer, ForeignKey('anime_api.project_bibles.id'))
    name = Column(String, nullable=False)
    description = Column(Text)
    visual_traits = Column(JSON)
    personality_traits = Column(JSON)
    relationships = Column(JSON)
    evolution_arc = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    bible = relationship("ProjectBible", back_populates="characters")