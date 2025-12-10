"""
Database models for anime production system.
Updated to match existing database schema in public schema.
"""

from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Text, Boolean, LargeBinary, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class Project(Base):
    """Projects table matching existing schema"""
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    type = Column(String(100), default='anime')
    status = Column(String(50), default='active')
    metadata_ = Column('metadata', JSON, default=lambda: {})
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    jobs = relationship("ProductionJob", back_populates="project", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="project", cascade="all, delete-orphan")
    story_bibles = relationship("StoryBible", back_populates="project", cascade="all, delete-orphan")
    episodes = relationship("Episode", back_populates="project", cascade="all, delete-orphan")


class Character(Base):
    """Characters table matching existing schema"""
    __tablename__ = 'characters'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    project_id = Column(Integer, ForeignKey('projects.id'))
    description = Column(Text)
    visual_traits = Column(JSON)
    canonical_hash = Column(String(64))
    status = Column(String(50), default='draft')
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())
    metadata_ = Column('metadata', JSON)
    reference_embedding = Column(LargeBinary)
    color_palette = Column(JSON, default=lambda: {})
    base_prompt = Column(Text)
    negative_tokens = Column(ARRAY(Text), default=lambda: [])
    lora_model_path = Column(String(500))

    # Relationships
    project = relationship("Project", back_populates="characters")
    jobs = relationship("ProductionJob", back_populates="character")
    character_anchors = relationship("CharacterAnchor", back_populates="character", cascade="all, delete-orphan")
    character_attributes = relationship("CharacterAttribute", back_populates="character", cascade="all, delete-orphan")
    character_variations = relationship("CharacterVariation", back_populates="character", cascade="all, delete-orphan")
    face_embeddings = relationship("FaceEmbedding", back_populates="character", cascade="all, delete-orphan")


class ProductionJob(Base):
    """Jobs table matching existing schema"""
    __tablename__ = 'jobs'

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'))
    character_id = Column(Integer, ForeignKey('characters.id'))
    job_type = Column(String(100), nullable=False)
    status = Column(String(50), default='pending')
    priority = Column(Integer, default=0)
    prompt = Column(Text)
    negative_prompt = Column(Text)
    output_path = Column(String(500))
    error_message = Column(Text)
    metadata_ = Column('metadata', JSON, default=lambda: {})
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)

    # Relationships
    project = relationship("Project", back_populates="jobs")
    character = relationship("Character", back_populates="jobs")
    generation_params = relationship("GenerationParam", back_populates="job", cascade="all, delete-orphan")
    quality_scores = relationship("QualityScore", back_populates="job", cascade="all, delete-orphan")


class GeneratedAsset(Base):
    """New model for tracking generated files"""
    __tablename__ = 'generated_assets'

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'))
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(50))  # 'image', 'video', 'gif'
    file_size = Column(Integer)
    metadata_ = Column('metadata', JSON, default=lambda: {})
    quality_metrics = Column(JSON, default=lambda: {})
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    job = relationship("ProductionJob", backref="assets")


class StoryBible(Base):
    """Story bibles table matching existing schema"""
    __tablename__ = 'story_bibles'

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'))
    title = Column(String(255))
    premise = Column(Text)
    world_building = Column(JSON)
    character_arcs = Column(JSON)
    themes = Column(JSON)
    metadata_ = Column('metadata', JSON, default=lambda: {})
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="story_bibles")


class Episode(Base):
    """Episodes table matching existing schema"""
    __tablename__ = 'episodes'

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'))
    episode_number = Column(Integer)
    title = Column(String(255))
    synopsis = Column(Text)
    script = Column(Text)
    storyboard = Column(JSON)
    status = Column(String(50), default='planning')
    metadata_ = Column('metadata', JSON, default=lambda: {})
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="episodes")


# Supporting models for character consistency
class CharacterAnchor(Base):
    """Character anchors for consistency"""
    __tablename__ = 'character_anchors'

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    anchor_type = Column(String(100))
    anchor_data = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())

    character = relationship("Character", back_populates="character_anchors")


class CharacterAttribute(Base):
    """Character attributes for tracking"""
    __tablename__ = 'character_attributes'

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    attribute_name = Column(String(100))
    attribute_value = Column(Text)
    confidence = Column(Integer, default=100)
    created_at = Column(DateTime, server_default=func.now())

    character = relationship("Character", back_populates="character_attributes")


class CharacterVariation(Base):
    """Character variations for different contexts"""
    __tablename__ = 'character_variations'

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    variation_type = Column(String(100))
    variation_data = Column(JSON)
    image_path = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())

    character = relationship("Character", back_populates="character_variations")


class FaceEmbedding(Base):
    """Face embeddings for character recognition"""
    __tablename__ = 'face_embeddings'

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    embedding_data = Column(LargeBinary)
    source_image_path = Column(String(500))
    confidence_score = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

    character = relationship("Character", back_populates="face_embeddings")


class GenerationParam(Base):
    """Generation parameters for jobs matching existing schema"""
    __tablename__ = 'generation_params'

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'))
    positive_prompt = Column(Text, nullable=False)
    negative_prompt = Column(Text)
    seed = Column(Integer, nullable=False)  # Changed from bigint for simplicity
    subseed = Column(Integer)
    model_name = Column(String(255), nullable=False)
    model_hash = Column(String(64))
    vae_name = Column(String(255))
    sampler_name = Column(String(100))
    scheduler = Column(String(100))
    steps = Column(Integer)
    cfg_scale = Column(Integer)  # Simplified from double precision
    width = Column(Integer)
    height = Column(Integer)
    batch_size = Column(Integer, default=1)
    n_iter = Column(Integer, default=1)
    lora_models = Column(JSON, default=lambda: [])
    controlnet_configs = Column(JSON, default=lambda: [])
    comfyui_workflow = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())

    job = relationship("ProductionJob", back_populates="generation_params")


class QualityScore(Base):
    """Quality scores for generated content matching existing schema"""
    __tablename__ = 'quality_scores'

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'))
    metric_name = Column(String(100), nullable=False)
    score_value = Column(Integer, nullable=False)  # Simplified from double precision
    threshold_min = Column(Integer)  # Simplified from double precision
    threshold_max = Column(Integer)  # Simplified from double precision
    passed = Column(Boolean)
    details = Column(JSON, default=lambda: {})
    created_at = Column(DateTime, server_default=func.now())

    job = relationship("ProductionJob", back_populates="quality_scores")