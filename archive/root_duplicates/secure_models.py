#!/usr/bin/env python3
"""
Secure Pydantic models with enhanced validation for Anime Production API
"""

import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, validator, Field
from datetime import datetime
from enum import Enum

class ProjectStatus(str, Enum):
    """Valid project statuses"""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class VideoQuality(str, Enum):
    """Valid video quality options"""
    LOW = "480p"
    MEDIUM = "720p"
    HIGH = "1080p"
    ULTRA = "4k"

class AnimationStyle(str, Enum):
    """Valid animation styles"""
    PHOTOREALISTIC = "photorealistic"
    ANIME = "anime"
    CARTOON = "cartoon"
    CINEMATIC = "cinematic"

class SecureAnimeProjectCreate(BaseModel):
    """Secure model for creating anime projects with validation"""
    name: str = Field(..., min_length=1, max_length=200, description="Project name")
    description: Optional[str] = Field(None, max_length=2000, description="Project description")
    status: ProjectStatus = Field(default=ProjectStatus.DRAFT, description="Project status")

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Project name cannot be empty')

        # Only allow alphanumeric, spaces, hyphens, underscores, and periods
        if not re.match(r'^[a-zA-Z0-9\s\-_\.]+$', v):
            raise ValueError('Project name contains invalid characters')

        return v.strip()

    @validator('description')
    def validate_description(cls, v):
        if v is None:
            return v

        # Check for malicious content
        dangerous_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'onload\s*=',
            r'onerror\s*=',
            r'eval\s*\(',
            r'exec\s*\(',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError('Description contains potentially malicious content')

        return v.strip() if v else None

class SecureAnimeGenerationRequest(BaseModel):
    """Secure model for anime generation requests with comprehensive validation"""
    prompt: str = Field(..., min_length=1, max_length=5000, description="Generation prompt")
    character: Optional[str] = Field(None, max_length=100, description="Character name")
    style: AnimationStyle = Field(default=AnimationStyle.PHOTOREALISTIC, description="Animation style")
    duration: float = Field(default=3.0, ge=1.0, le=30.0, description="Video duration in seconds")
    quality: VideoQuality = Field(default=VideoQuality.MEDIUM, description="Video quality")
    fps: int = Field(default=24, ge=12, le=60, description="Frames per second")
    width: int = Field(default=1024, ge=512, le=2048, description="Video width")
    height: int = Field(default=1024, ge=512, le=2048, description="Video height")
    seed: Optional[int] = Field(None, ge=0, le=2147483647, description="Random seed")
    negative_prompt: Optional[str] = Field(None, max_length=2000, description="Negative prompt")

    @validator('prompt')
    def validate_prompt(cls, v):
        if not v or not v.strip():
            raise ValueError('Prompt cannot be empty')

        # Check for malicious content
        dangerous_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'onload\s*=',
            r'onerror\s*=',
            r'eval\s*\(',
            r'exec\s*\(',
            r'import\s+os',
            r'subprocess\.',
            r'__import__',
            r'\.\.\/.*\.\./',  # Path traversal
            r'\/etc\/passwd',
            r'cmd\.exe',
            r'powershell',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError('Prompt contains potentially malicious content')

        return v.strip()

    @validator('character')
    def validate_character(cls, v):
        if v is None:
            return v

        # Only allow alphanumeric, spaces, hyphens, and periods
        if not re.match(r'^[a-zA-Z0-9\s\-\.]+$', v):
            raise ValueError('Character name contains invalid characters')

        return v.strip()

    @validator('negative_prompt')
    def validate_negative_prompt(cls, v):
        if v is None:
            return v

        # Same validation as prompt
        dangerous_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'onload\s*=',
            r'onerror\s*=',
            r'eval\s*\(',
            r'exec\s*\(',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError('Negative prompt contains potentially malicious content')

        return v.strip()

    @validator('width', 'height')
    def validate_dimensions(cls, v):
        # Ensure dimensions are multiples of 8 for video encoding compatibility
        if v % 8 != 0:
            raise ValueError('Width and height must be multiples of 8')
        return v

class SecureProjectUpdate(BaseModel):
    """Secure model for project updates"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[ProjectStatus] = None

    @validator('name')
    def validate_name(cls, v):
        if v is None:
            return v

        if not v.strip():
            raise ValueError('Project name cannot be empty')

        # Only allow alphanumeric, spaces, hyphens, underscores, and periods
        if not re.match(r'^[a-zA-Z0-9\s\-_\.]+$', v):
            raise ValueError('Project name contains invalid characters')

        return v.strip()

    @validator('description')
    def validate_description(cls, v):
        if v is None:
            return v

        # Check for malicious content
        dangerous_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'onload\s*=',
            r'onerror\s*=',
            r'eval\s*\(',
            r'exec\s*\(',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError('Description contains potentially malicious content')

        return v.strip()

class SecureFileUpload(BaseModel):
    """Secure model for file uploads"""
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=100)

    @validator('filename')
    def validate_filename(cls, v):
        if not v or not v.strip():
            raise ValueError('Filename cannot be empty')

        # Remove path separators and dangerous characters
        sanitized = re.sub(r'[/\\:*?"<>|]', '', v)
        sanitized = re.sub(r'\.\.', '', sanitized)  # Remove ..

        if not sanitized:
            raise ValueError('Filename became empty after sanitization')

        # Check for dangerous extensions
        dangerous_extensions = [
            '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js',
            '.jar', '.sh', '.py', '.php', '.asp', '.jsp', '.pl'
        ]

        for ext in dangerous_extensions:
            if sanitized.lower().endswith(ext):
                raise ValueError(f'File type {ext} is not allowed')

        # Only allow specific image/video extensions
        allowed_extensions = [
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp',
            '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm'
        ]

        if not any(sanitized.lower().endswith(ext) for ext in allowed_extensions):
            raise ValueError('File type not allowed')

        return sanitized

    @validator('content_type')
    def validate_content_type(cls, v):
        allowed_types = [
            'image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/webp',
            'video/mp4', 'video/avi', 'video/quicktime', 'video/x-msvideo', 'video/webm'
        ]

        if v not in allowed_types:
            raise ValueError('Content type not allowed')

        return v

class AnimeProjectResponse(BaseModel):
    """Response model for anime projects"""
    id: int
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class GenerationResponse(BaseModel):
    """Response model for generation requests"""
    generation_id: str
    status: str
    project_id: Optional[int]
    message: str
    estimated_completion: Optional[datetime]

class HealthResponse(BaseModel):
    """Response model for health checks"""
    status: str
    timestamp: datetime
    services: Dict[str, str]
    version: str