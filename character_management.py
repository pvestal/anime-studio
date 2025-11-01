#!/usr/bin/env python3
"""
Enhanced Character System with Validation, Fallbacks, and Error Recovery
Provides robust character management with automatic validation, fallback generation,
and comprehensive error handling for the anime production system.
"""

import json
import os
import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Dict, Optional, List, Any, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import logging
import aiofiles
import aiohttp
from PIL import Image
import requests

# Import our error handling framework
from shared.error_handling import (
    AnimeGenerationError, ErrorSeverity, ErrorCategory,
    RetryManager, MetricsCollector, OperationMetrics
)

logger = logging.getLogger(__name__)

class CharacterValidationStatus(Enum):
    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"
    MISSING = "missing"

class CharacterImageStatus(Enum):
    AVAILABLE = "available"
    PROCESSING = "processing"
    MISSING = "missing"
    CORRUPTED = "corrupted"

@dataclass
class CharacterValidationResult:
    """Result of character validation"""
    status: CharacterValidationStatus
    character_name: str
    errors: List[str]
    warnings: List[str]
    suggestions: List[str]
    confidence_score: float  # 0.0 - 1.0
    last_validated: datetime
    character_data: Optional[Dict[str, Any]] = None

@dataclass
class CharacterConfig:
    """Configuration for character system"""
    characters_dir: str = "/opt/tower-anime-production/characters"
    cache_dir: str = "/opt/tower-anime-production/cache/characters"
    reference_images_dir: str = "/opt/tower-anime-production/characters/reference_images"
    fallback_characters_dir: str = "/opt/tower-anime-production/characters/fallback"
    backup_dir: str = "/opt/tower-anime-production/backup/characters"

    # Validation settings
    max_prompt_length: int = 2000
    min_prompt_length: int = 20
    required_fields: List[str] = None
    cache_ttl_hours: int = 24

    # Fallback settings
    enable_auto_generation: bool = True
    enable_echo_integration: bool = True
    fallback_style: str = "anime"

    def __post_init__(self):
        if self.required_fields is None:
            self.required_fields = ['name', 'gender', 'generation_prompts']

class CharacterError(AnimeGenerationError):
    """Character system specific errors"""

    def __init__(self, message: str, character_name: str = None,
                 validation_errors: List[str] = None, **kwargs):
        super().__init__(message, ErrorCategory.VALIDATION, ErrorSeverity.MEDIUM, **kwargs)
        self.character_name = character_name
        self.validation_errors = validation_errors or []
        self.context.update({
            "character_name": character_name,
            "validation_errors": validation_errors,
            "service": "character_system"
        })

class CharacterCache:
    """Character data cache with TTL and validation"""

    def __init__(self, cache_dir: str, ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_hours = ttl_hours
        self.memory_cache = {}
        self.cache_stats = {"hits": 0, "misses": 0, "expires": 0}

    def _get_cache_path(self, character_name: str) -> Path:
        """Get cache file path for character"""
        safe_name = "".join(c for c in character_name if c.isalnum() or c in '-_').lower()
        return self.cache_dir / f"{safe_name}.cache.json"

    def _is_cache_valid(self, cache_file: Path) -> bool:
        """Check if cache file is still valid"""
        if not cache_file.exists():
            return False

        try:
            stat = cache_file.stat()
            cache_age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
            return cache_age < timedelta(hours=self.ttl_hours)
        except Exception:
            return False

    async def get(self, character_name: str) -> Optional[Dict[str, Any]]:
        """Get character from cache"""
        # Check memory cache first
        if character_name in self.memory_cache:
            cache_entry = self.memory_cache[character_name]
            if datetime.now() - cache_entry["cached_at"] < timedelta(hours=self.ttl_hours):
                self.cache_stats["hits"] += 1
                return cache_entry["data"]
            else:
                del self.memory_cache[character_name]
                self.cache_stats["expires"] += 1

        # Check file cache
        cache_file = self._get_cache_path(character_name)
        if self._is_cache_valid(cache_file):
            try:
                async with aiofiles.open(cache_file, 'r') as f:
                    content = await f.read()
                    cache_data = json.loads(content)

                # Store in memory cache
                self.memory_cache[character_name] = {
                    "data": cache_data,
                    "cached_at": datetime.now()
                }

                self.cache_stats["hits"] += 1
                return cache_data
            except Exception as e:
                logger.warning(f"Failed to read cache for {character_name}: {e}")

        self.cache_stats["misses"] += 1
        return None

    async def set(self, character_name: str, character_data: Dict[str, Any]):
        """Set character in cache"""
        # Store in memory cache
        self.memory_cache[character_name] = {
            "data": character_data,
            "cached_at": datetime.now()
        }

        # Store in file cache
        cache_file = self._get_cache_path(character_name)
        try:
            async with aiofiles.open(cache_file, 'w') as f:
                await f.write(json.dumps(character_data, indent=2, default=str))
        except Exception as e:
            logger.error(f"Failed to write cache for {character_name}: {e}")

    def invalidate(self, character_name: str):
        """Invalidate character cache"""
        if character_name in self.memory_cache:
            del self.memory_cache[character_name]

        cache_file = self._get_cache_path(character_name)
        if cache_file.exists():
            cache_file.unlink()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = sum(self.cache_stats.values())
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            **self.cache_stats,
            "hit_rate_percent": round(hit_rate, 2),
            "memory_cache_size": len(self.memory_cache),
            "cache_dir": str(self.cache_dir)
        }

class CharacterValidator:
    """Validates character definitions and suggests improvements"""

    def __init__(self, config: CharacterConfig):
        self.config = config

    async def validate_character(self, character_name: str, character_data: Dict[str, Any]) -> CharacterValidationResult:
        """Comprehensive character validation"""
        errors = []
        warnings = []
        suggestions = []
        confidence_score = 1.0

        # Check required fields
        for field in self.config.required_fields:
            if field not in character_data:
                errors.append(f"Missing required field: {field}")
                confidence_score -= 0.3

        # Validate name consistency
        data_name = character_data.get('name', '').lower()
        if data_name and data_name != character_name.lower():
            warnings.append(f"Name mismatch: file '{character_name}' vs data '{data_name}'")
            confidence_score -= 0.1

        # Validate generation prompts
        if 'generation_prompts' in character_data:
            gen_prompts = character_data['generation_prompts']

            # Check visual description
            visual_desc = gen_prompts.get('visual_description', '')
            if not visual_desc:
                errors.append("Missing visual_description in generation_prompts")
                confidence_score -= 0.4
            elif len(visual_desc) < self.config.min_prompt_length:
                warnings.append(f"Visual description too short ({len(visual_desc)} chars)")
                confidence_score -= 0.1
            elif len(visual_desc) > self.config.max_prompt_length:
                errors.append(f"Visual description too long ({len(visual_desc)} chars)")
                confidence_score -= 0.2

            # Check negative prompts
            if 'negative_prompts' not in gen_prompts:
                warnings.append("Missing negative_prompts - may generate incorrect features")
                suggestions.append("Add negative prompts to prevent wrong gender/age/style")
                confidence_score -= 0.05

            # Check style tags
            style_tags = gen_prompts.get('style_tags', [])
            if not style_tags:
                warnings.append("No style tags defined - generation may be inconsistent")
                suggestions.append("Add style tags like 'anime', 'manga', 'photorealistic'")
                confidence_score -= 0.05

        # Validate character consistency fields
        self._validate_character_attributes(character_data, errors, warnings, suggestions)

        # Update confidence score based on completeness
        confidence_score = max(0.0, min(1.0, confidence_score))

        # Determine overall status
        if errors:
            status = CharacterValidationStatus.INVALID
        elif warnings:
            status = CharacterValidationStatus.WARNING
        else:
            status = CharacterValidationStatus.VALID

        return CharacterValidationResult(
            status=status,
            character_name=character_name,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
            confidence_score=confidence_score,
            last_validated=datetime.utcnow(),
            character_data=character_data
        )

    def _validate_character_attributes(self, character_data: Dict[str, Any],
                                     errors: List[str], warnings: List[str], suggestions: List[str]):
        """Validate character-specific attributes"""
        # Gender validation
        gender = character_data.get('gender', '').lower()
        if gender not in ['male', 'female', 'non-binary', 'other']:
            if gender:
                warnings.append(f"Unusual gender value: '{gender}'")
            else:
                warnings.append("Gender not specified")

        # Age validation
        age = character_data.get('age')
        if age:
            try:
                age_num = int(age)
                if age_num < 0 or age_num > 200:
                    warnings.append(f"Unusual age: {age_num}")
            except (ValueError, TypeError):
                warnings.append(f"Invalid age format: {age}")

        # Check for reference images
        reference_images = character_data.get('reference_images', [])
        if not reference_images:
            suggestions.append("Add reference images for more consistent generation")

        # Check for personality traits
        if 'personality' not in character_data:
            suggestions.append("Add personality traits for richer character generation")

class ReferenceImageManager:
    """Manages character reference images with validation and processing"""

    def __init__(self, config: CharacterConfig):
        self.config = config
        self.images_dir = Path(config.reference_images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    async def get_character_images(self, character_name: str) -> Dict[str, Any]:
        """Get all reference images for a character"""
        char_dir = self.images_dir / character_name.lower()
        images_info = {
            "character_name": character_name,
            "images": [],
            "status": CharacterImageStatus.MISSING,
            "total_images": 0,
            "total_size_mb": 0
        }

        if not char_dir.exists():
            return images_info

        try:
            image_files = list(char_dir.glob("*.{jpg,jpeg,png,webp}"))
            total_size = 0

            for img_file in image_files:
                try:
                    stat = img_file.stat()
                    total_size += stat.st_size

                    # Validate image
                    img_info = await self._validate_image(img_file)
                    images_info["images"].append(img_info)

                except Exception as e:
                    logger.warning(f"Error processing image {img_file}: {e}")
                    images_info["images"].append({
                        "path": str(img_file),
                        "status": "error",
                        "error": str(e)
                    })

            images_info["total_images"] = len(images_info["images"])
            images_info["total_size_mb"] = round(total_size / (1024 * 1024), 2)

            # Determine overall status
            if images_info["total_images"] > 0:
                valid_images = sum(1 for img in images_info["images"] if img.get("valid", False))
                if valid_images > 0:
                    images_info["status"] = CharacterImageStatus.AVAILABLE
                else:
                    images_info["status"] = CharacterImageStatus.CORRUPTED
            else:
                images_info["status"] = CharacterImageStatus.MISSING

        except Exception as e:
            logger.error(f"Error scanning images for {character_name}: {e}")
            images_info["status"] = CharacterImageStatus.CORRUPTED

        return images_info

    async def _validate_image(self, image_path: Path) -> Dict[str, Any]:
        """Validate a single reference image"""
        try:
            with Image.open(image_path) as img:
                return {
                    "path": str(image_path),
                    "filename": image_path.name,
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "size_bytes": image_path.stat().st_size,
                    "valid": True,
                    "aspect_ratio": round(img.width / img.height, 2)
                }
        except Exception as e:
            return {
                "path": str(image_path),
                "filename": image_path.name,
                "valid": False,
                "error": str(e)
            }

class FallbackCharacterGenerator:
    """Generates fallback character data when original is missing or invalid"""

    def __init__(self, config: CharacterConfig):
        self.config = config
        self.echo_url = "http://localhost:8309"

    async def generate_fallback_character(self, character_name: str,
                                        context: str = "") -> Dict[str, Any]:
        """Generate fallback character data"""
        logger.info(f"Generating fallback character for: {character_name}")

        # Try Echo Brain integration first
        if self.config.enable_echo_integration:
            try:
                echo_result = await self._generate_via_echo(character_name, context)
                if echo_result:
                    return echo_result
            except Exception as e:
                logger.warning(f"Echo generation failed for {character_name}: {e}")

        # Fall back to template-based generation
        return self._generate_template_character(character_name, context)

    async def _generate_via_echo(self, character_name: str, context: str) -> Optional[Dict[str, Any]]:
        """Generate character using Echo Brain"""
        try:
            prompt = f"""
            Generate a detailed anime character profile for "{character_name}".
            Context: {context}

            Create a JSON structure with:
            - name: character name
            - gender: male/female/non-binary
            - age: age in years
            - generation_prompts:
              - visual_description: detailed physical description for image generation
              - style_tags: list of style tags (anime, manga, etc.)
              - negative_prompts: list of things to avoid
            - personality: list of personality traits
            - background: character background story
            - reference_type: "echo_generated"

            Make the visual_description detailed and specific for consistent generation.
            Include clothing, hair color/style, eye color, expression, and pose suggestions.
            """

            async with aiohttp.ClientSession() as session:
                payload = {
                    "query": prompt,
                    "context": "character_generation",
                    "model": "qwen2.5-coder:32b"  # Use a capable model
                }

                async with session.post(
                    f"{self.echo_url}/api/echo/query",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        response_text = result.get('response', '')

                        # Try to extract JSON from response
                        character_data = self._extract_json_from_response(response_text)
                        if character_data:
                            character_data['generated_by'] = 'echo_brain'
                            character_data['generated_at'] = datetime.utcnow().isoformat()
                            return character_data

        except Exception as e:
            logger.error(f"Echo character generation failed: {e}")

        return None

    def _extract_json_from_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON character data from Echo response"""
        try:
            # Look for JSON blocks in the response
            import re
            json_pattern = r'```json\s*(.*?)\s*```'
            json_match = re.search(json_pattern, response_text, re.DOTALL)

            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)

            # Try to parse the entire response as JSON
            return json.loads(response_text)

        except Exception as e:
            logger.warning(f"Failed to extract JSON from Echo response: {e}")
            return None

    def _generate_template_character(self, character_name: str, context: str) -> Dict[str, Any]:
        """Generate character using template system"""
        # Analyze character name for clues
        name_lower = character_name.lower()

        # Determine likely gender from name patterns
        gender = "female"
        if any(indicator in name_lower for indicator in ["kun", "san", "mr", "master", "lord", "king"]):
            gender = "male"
        elif any(indicator in name_lower for indicator in ["chan", "sama", "lady", "princess", "queen"]):
            gender = "female"

        # Generate basic description
        style_base = f"1{gender[0]}, anime style, detailed character design"

        # Add context-based descriptors
        if "cyberpunk" in context.lower():
            style_descriptors = "cyberpunk clothing, neon highlights, futuristic accessories"
        elif "fantasy" in context.lower():
            style_descriptors = "fantasy clothing, magical accessories, ethereal appearance"
        elif "school" in context.lower():
            style_descriptors = "school uniform, student appearance, youthful"
        else:
            style_descriptors = "casual anime clothing, modern appearance"

        return {
            "name": character_name,
            "gender": gender,
            "age": 18,  # Safe default
            "generation_prompts": {
                "visual_description": f"{style_base}, {style_descriptors}, high quality, detailed, masterpiece",
                "style_tags": ["anime", "detailed", "high quality", self.config.fallback_style],
                "negative_prompts": [
                    "low quality", "blurry", "distorted", "ugly", "bad anatomy",
                    "wrong gender", "inconsistent", "malformed"
                ]
            },
            "personality": ["friendly", "determined", "curious"],
            "background": f"Generated character based on name '{character_name}' and context '{context}'",
            "reference_type": "template_generated",
            "generated_by": "fallback_template",
            "generated_at": datetime.utcnow().isoformat(),
            "confidence_score": 0.6
        }

class EnhancedCharacterSystem:
    """Enhanced character system with comprehensive error handling and recovery"""

    def __init__(self, config: CharacterConfig = None, metrics_collector: MetricsCollector = None):
        self.config = config or CharacterConfig()
        self.metrics_collector = metrics_collector
        self.cache = CharacterCache(self.config.cache_dir, self.config.cache_ttl_hours)
        self.validator = CharacterValidator(self.config)
        self.image_manager = ReferenceImageManager(self.config)
        self.fallback_generator = FallbackCharacterGenerator(self.config)
        self.retry_manager = RetryManager()

        # Ensure directories exist
        for dir_path in [self.config.characters_dir, self.config.cache_dir,
                        self.config.reference_images_dir, self.config.fallback_characters_dir,
                        self.config.backup_dir]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

        # Load initial character data
        self.characters_loaded = 0
        asyncio.create_task(self._initial_load())

    async def _initial_load(self):
        """Load and validate all characters on startup"""
        try:
            characters_dir = Path(self.config.characters_dir)
            character_files = list(characters_dir.glob("*.json"))

            for char_file in character_files:
                try:
                    async with aiofiles.open(char_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        character_data = json.loads(content)

                    character_name = character_data.get('name', char_file.stem)
                    await self.cache.set(character_name.lower(), character_data)
                    self.characters_loaded += 1

                except Exception as e:
                    logger.error(f"Error loading character file {char_file}: {e}")

            logger.info(f"✅ Loaded {self.characters_loaded} characters into cache")

        except Exception as e:
            logger.error(f"Error during initial character load: {e}")

    async def get_character_robust(self, character_name: str,
                                 context: str = "",
                                 auto_generate: bool = None) -> Dict[str, Any]:
        """Get character with comprehensive error handling and fallback"""
        operation_id = f"get_character_{int(time.time())}"
        metrics = OperationMetrics(
            operation_id=operation_id,
            operation_type="character_retrieval",
            start_time=datetime.utcnow(),
            context={"character_name": character_name, "context": context}
        )

        try:
            # Try cache first
            cached_character = await self.cache.get(character_name.lower())
            if cached_character:
                logger.debug(f"Character '{character_name}' retrieved from cache")

                # Validate cached character
                validation = await self.validator.validate_character(character_name, cached_character)

                if validation.status != CharacterValidationStatus.INVALID:
                    metrics.complete(True, {"source": "cache", "validation_status": validation.status.value})
                    if self.metrics_collector:
                        await self.metrics_collector.log_operation(metrics)

                    return self._enrich_character_data(cached_character, validation)

            # Try loading from file
            character_data = await self._load_character_from_file(character_name)
            if character_data:
                validation = await self.validator.validate_character(character_name, character_data)

                if validation.status != CharacterValidationStatus.INVALID:
                    # Cache the loaded character
                    await self.cache.set(character_name.lower(), character_data)

                    metrics.complete(True, {"source": "file", "validation_status": validation.status.value})
                    if self.metrics_collector:
                        await self.metrics_collector.log_operation(metrics)

                    return self._enrich_character_data(character_data, validation)

            # Character not found or invalid - try fallback generation
            if auto_generate is None:
                auto_generate = self.config.enable_auto_generation

            if auto_generate:
                logger.info(f"Generating fallback character for: {character_name}")
                fallback_character = await self.fallback_generator.generate_fallback_character(character_name, context)

                # Save generated character for future use
                await self._save_character_to_fallback(character_name, fallback_character)
                await self.cache.set(character_name.lower(), fallback_character)

                metrics.complete(True, {"source": "generated", "validation_status": "fallback"})
                if self.metrics_collector:
                    await self.metrics_collector.log_operation(metrics)

                return self._enrich_character_data(fallback_character, None)

            # No character found and generation disabled
            raise CharacterError(
                f"Character '{character_name}' not found and auto-generation disabled",
                character_name=character_name
            )

        except Exception as e:
            if isinstance(e, CharacterError):
                error = e
            else:
                error = CharacterError(
                    f"Failed to retrieve character '{character_name}': {str(e)}",
                    character_name=character_name,
                    correlation_id=operation_id
                )

            metrics.complete(False, error.to_dict())
            if self.metrics_collector:
                await self.metrics_collector.log_operation(metrics)
                await self.metrics_collector.log_error(error)

            raise error

    async def _load_character_from_file(self, character_name: str) -> Optional[Dict[str, Any]]:
        """Load character from JSON file with error handling"""
        characters_dir = Path(self.config.characters_dir)

        # Try exact filename match
        exact_file = characters_dir / f"{character_name}.json"
        if exact_file.exists():
            try:
                async with aiofiles.open(exact_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            except Exception as e:
                logger.error(f"Error reading character file {exact_file}: {e}")

        # Try case-insensitive search
        for char_file in characters_dir.glob("*.json"):
            if char_file.stem.lower() == character_name.lower():
                try:
                    async with aiofiles.open(char_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        return json.loads(content)
                except Exception as e:
                    logger.error(f"Error reading character file {char_file}: {e}")

        return None

    def _enrich_character_data(self, character_data: Dict[str, Any],
                             validation: Optional[CharacterValidationResult]) -> Dict[str, Any]:
        """Enrich character data with additional metadata"""
        enriched = character_data.copy()

        enriched["system_metadata"] = {
            "retrieved_at": datetime.utcnow().isoformat(),
            "source": enriched.get("generated_by", "file"),
            "cache_stats": self.cache.get_stats()
        }

        if validation:
            enriched["validation"] = {
                "status": validation.status.value,
                "confidence_score": validation.confidence_score,
                "errors": validation.errors,
                "warnings": validation.warnings,
                "suggestions": validation.suggestions,
                "last_validated": validation.last_validated.isoformat()
            }

        return enriched

    async def _save_character_to_fallback(self, character_name: str, character_data: Dict[str, Any]):
        """Save generated character to fallback directory"""
        try:
            fallback_dir = Path(self.config.fallback_characters_dir)
            fallback_file = fallback_dir / f"{character_name.lower()}.json"

            async with aiofiles.open(fallback_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(character_data, indent=2, default=str))

            logger.info(f"Saved fallback character: {fallback_file}")

        except Exception as e:
            logger.error(f"Failed to save fallback character {character_name}: {e}")

    async def build_generation_prompt_robust(self, character_name: str,
                                           scene_context: str = "",
                                           style_override: str = None) -> Dict[str, Any]:
        """Build generation prompt with comprehensive error handling"""
        try:
            character_data = await self.get_character_robust(character_name, scene_context)

            # Extract generation prompts
            gen_prompts = character_data.get('generation_prompts', {})
            visual_desc = gen_prompts.get('visual_description', '')
            style_tags = gen_prompts.get('style_tags', [])
            negative_prompts = gen_prompts.get('negative_prompts', [])

            # Build main prompt
            if scene_context:
                main_prompt = f"{visual_desc}, {scene_context}"
            else:
                main_prompt = visual_desc

            # Add style tags
            if style_override:
                main_prompt = f"{main_prompt}, {style_override}"
            elif style_tags:
                style_text = ", ".join(style_tags)
                main_prompt = f"{main_prompt}, {style_text}"

            # Get reference images
            image_info = await self.image_manager.get_character_images(character_name)

            return {
                'prompt': main_prompt,
                'negative_prompt': ", ".join(negative_prompts),
                'style_tags': style_tags,
                'character_data': character_data,
                'character_found': True,
                'validation_status': character_data.get('validation', {}).get('status', 'unknown'),
                'confidence_score': character_data.get('validation', {}).get('confidence_score', 1.0),
                'reference_images': image_info,
                'source': character_data.get('system_metadata', {}).get('source', 'unknown'),
                'build_timestamp': datetime.utcnow().isoformat()
            }

        except CharacterError as e:
            # Return fallback prompt for missing characters
            return {
                'prompt': f"anime character {character_name}, {scene_context}",
                'negative_prompt': "low quality, blurry, distorted",
                'style_tags': [self.config.fallback_style],
                'character_data': None,
                'character_found': False,
                'error': str(e),
                'validation_status': 'missing',
                'confidence_score': 0.1,
                'reference_images': {"status": "missing"},
                'source': 'fallback',
                'build_timestamp': datetime.utcnow().isoformat()
            }

    async def validate_all_characters(self) -> Dict[str, CharacterValidationResult]:
        """Validate all characters in the system"""
        results = {}
        characters_dir = Path(self.config.characters_dir)

        for char_file in characters_dir.glob("*.json"):
            try:
                async with aiofiles.open(char_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    character_data = json.loads(content)

                character_name = character_data.get('name', char_file.stem)
                validation = await self.validator.validate_character(character_name, character_data)
                results[character_name] = validation

            except Exception as e:
                results[char_file.stem] = CharacterValidationResult(
                    status=CharacterValidationStatus.INVALID,
                    character_name=char_file.stem,
                    errors=[f"Failed to load: {str(e)}"],
                    warnings=[],
                    suggestions=[],
                    confidence_score=0.0,
                    last_validated=datetime.utcnow()
                )

        return results

    async def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive character system health"""
        validation_results = await self.validate_all_characters()

        status_counts = {}
        for result in validation_results.values():
            status = result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        avg_confidence = sum(r.confidence_score for r in validation_results.values()) / len(validation_results) if validation_results else 0

        return {
            "total_characters": len(validation_results),
            "characters_loaded": self.characters_loaded,
            "status_distribution": status_counts,
            "average_confidence_score": round(avg_confidence, 3),
            "cache_stats": self.cache.get_stats(),
            "directories": {
                "characters_dir": str(self.config.characters_dir),
                "cache_dir": str(self.config.cache_dir),
                "reference_images_dir": str(self.config.reference_images_dir),
                "fallback_characters_dir": str(self.config.fallback_characters_dir)
            },
            "config": {
                "auto_generation_enabled": self.config.enable_auto_generation,
                "echo_integration_enabled": self.config.enable_echo_integration,
                "cache_ttl_hours": self.config.cache_ttl_hours
            },
            "last_check": datetime.utcnow().isoformat()
        }

# Factory function
def create_character_system(config: CharacterConfig = None, metrics_collector: MetricsCollector = None) -> EnhancedCharacterSystem:
    """Create configured character system instance"""
    return EnhancedCharacterSystem(config, metrics_collector)

# Global instance for backward compatibility
character_system = None

def get_character_prompt(character_name: str, scene_context: str = "") -> Dict[str, Any]:
    """Main function for getting character generation prompts (backward compatible)"""
    global character_system
    if not character_system:
        character_system = create_character_system()

    # Convert async call to sync for backward compatibility
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            character_system.build_generation_prompt_robust(character_name, scene_context)
        )
    except RuntimeError:
        # Create new event loop if needed
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                character_system.build_generation_prompt_robust(character_name, scene_context)
            )
        finally:
            loop.close()

# Example usage and testing
async def test_enhanced_character_system():
    """Test the enhanced character system"""
    char_system = create_character_system()

    try:
        # Test system health
        print("Getting system health...")
        health = await char_system.get_system_health()
        print("System Health:", json.dumps(health, indent=2, default=str))

        # Test character retrieval with fallback
        print("\nTesting character retrieval...")
        char_result = await char_system.get_character_robust("Test Character", "cyberpunk scene")
        print("Character retrieved:", char_result.get('name', 'N/A'))

        # Test prompt building
        print("\nTesting prompt building...")
        prompt_result = await char_system.build_generation_prompt_robust(
            "Kai Nakamura", "standing confidently in neon-lit alley"
        )
        print("Prompt built successfully:", prompt_result.get('character_found', False))

        # Test validation
        print("\nTesting character validation...")
        validations = await char_system.validate_all_characters()
        print(f"Validated {len(validations)} characters")

    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_enhanced_character_system())