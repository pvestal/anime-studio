#!/usr/bin/env python3
"""
Generation caching system for Tower Anime Production.

Features:
- Model caching (keep models loaded in VRAM)
- LoRA model caching
- Embedding cache for repeated prompts
- Output caching for similar requests
- Smart cache eviction based on usage patterns
"""

import json
import time
import hashlib
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
import httpx

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Cache entry metadata"""
    key: str
    timestamp: float
    access_count: int
    last_accessed: float
    size_mb: int
    ttl_seconds: int = 3600  # 1 hour default TTL

    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        return time.time() - self.timestamp > self.ttl_seconds

    def is_stale(self, max_age_seconds: int = 1800) -> bool:
        """Check if cache entry is stale (not accessed recently)"""
        return time.time() - self.last_accessed > max_age_seconds

@dataclass
class ModelCacheEntry(CacheEntry):
    """Cache entry for loaded models"""
    model_name: str = ""
    model_type: str = "checkpoint"  # "checkpoint", "lora", "embedding"
    vram_usage_mb: int = 0
    load_time_seconds: float = 0.0

@dataclass
class OutputCacheEntry(CacheEntry):
    """Cache entry for generated outputs"""
    prompt_hash: str = ""
    output_path: str = ""
    generation_params: Dict[str, Any] = None
    quality_score: float = 0.0

    def __post_init__(self):
        super().__post_init__() if hasattr(super(), '__post_init__') else None
        if self.generation_params is None:
            self.generation_params = {}

class GenerationCache:
    """Generation caching system for optimized performance"""

    def __init__(self, cache_dir: str = "/tmp/tower_anime_cache"):
        """
        Initialize generation cache

        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache storage
        self.model_cache: Dict[str, ModelCacheEntry] = {}
        self.output_cache: Dict[str, OutputCacheEntry] = {}
        self.prompt_embeddings: Dict[str, Any] = {}

        # Cache limits
        self.max_model_cache_mb = 8000  # Keep 8GB of models in VRAM
        self.max_output_cache_entries = 100
        self.max_prompt_embeddings = 500

        # Cache files
        self.model_cache_file = self.cache_dir / "model_cache.json"
        self.output_cache_file = self.cache_dir / "output_cache.json"
        self.prompt_cache_file = self.cache_dir / "prompt_embeddings.json"

        # Load existing cache
        self._load_cache()

    def _load_cache(self):
        """Load cache from disk"""
        try:
            # Load model cache
            if self.model_cache_file.exists():
                with open(self.model_cache_file, 'r') as f:
                    data = json.load(f)
                    self.model_cache = {
                        k: ModelCacheEntry(**v) for k, v in data.items()
                    }

            # Load output cache
            if self.output_cache_file.exists():
                with open(self.output_cache_file, 'r') as f:
                    data = json.load(f)
                    self.output_cache = {
                        k: OutputCacheEntry(**v) for k, v in data.items()
                    }

            # Load prompt embeddings
            if self.prompt_cache_file.exists():
                with open(self.prompt_cache_file, 'r') as f:
                    self.prompt_embeddings = json.load(f)

            logger.info(
                f"Loaded cache: {len(self.model_cache)} models, "
                f"{len(self.output_cache)} outputs, "
                f"{len(self.prompt_embeddings)} prompts"
            )

        except Exception as e:
            logger.error(f"Failed to load cache: {e}")

    def _save_cache(self):
        """Save cache to disk"""
        try:
            # Save model cache
            with open(self.model_cache_file, 'w') as f:
                data = {k: asdict(v) for k, v in self.model_cache.items()}
                json.dump(data, f, indent=2)

            # Save output cache
            with open(self.output_cache_file, 'w') as f:
                data = {k: asdict(v) for k, v in self.output_cache.items()}
                json.dump(data, f, indent=2)

            # Save prompt embeddings
            with open(self.prompt_cache_file, 'w') as f:
                json.dump(self.prompt_embeddings, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _generate_prompt_hash(self, prompt: str, generation_params: Dict[str, Any]) -> str:
        """Generate hash for prompt and parameters combination"""
        # Normalize parameters for consistent hashing
        normalized_params = {
            "model": generation_params.get("model", ""),
            "steps": generation_params.get("steps", 20),
            "cfg": generation_params.get("cfg", 7.0),
            "sampler": generation_params.get("sampler", ""),
            "width": generation_params.get("width", 512),
            "height": generation_params.get("height", 512),
            "seed": generation_params.get("seed", -1)  # Include seed for exact reproduction
        }

        # Create hash from prompt + params
        content = f"{prompt}|{json.dumps(normalized_params, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _generate_similar_prompt_hash(self, prompt: str, generation_params: Dict[str, Any]) -> str:
        """Generate hash for similar prompts (ignoring seed)"""
        # Exclude seed for similarity matching
        normalized_params = {
            "model": generation_params.get("model", ""),
            "steps": generation_params.get("steps", 20),
            "cfg": generation_params.get("cfg", 7.0),
            "sampler": generation_params.get("sampler", ""),
            "width": generation_params.get("width", 512),
            "height": generation_params.get("height", 512)
        }

        content = f"{prompt}|{json.dumps(normalized_params, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def check_model_loaded(self, model_name: str) -> bool:
        """Check if model is already loaded in ComfyUI"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Check ComfyUI's current model status
                response = await client.get("http://localhost:8188/object_info")
                if response.status_code == 200:
                    # This is a simplified check - in practice, ComfyUI doesn't
                    # expose which models are currently loaded
                    # We'll rely on our cache tracking
                    return model_name in self.model_cache

        except Exception as e:
            logger.warning(f"Failed to check ComfyUI model status: {e}")

        return False

    def cache_model(self, model_name: str, model_type: str,
                   vram_usage_mb: int, load_time_seconds: float):
        """Cache model metadata"""

        cache_key = f"{model_type}:{model_name}"
        current_time = time.time()

        entry = ModelCacheEntry(
            key=cache_key,
            timestamp=current_time,
            access_count=1,
            last_accessed=current_time,
            size_mb=vram_usage_mb,
            model_name=model_name,
            model_type=model_type,
            vram_usage_mb=vram_usage_mb,
            load_time_seconds=load_time_seconds
        )

        self.model_cache[cache_key] = entry
        logger.info(f"Cached model: {model_name} ({vram_usage_mb}MB)")

        # Check if we need to evict models
        self._evict_models_if_needed()
        self._save_cache()

    def get_cached_model(self, model_name: str, model_type: str) -> Optional[ModelCacheEntry]:
        """Get cached model entry"""
        cache_key = f"{model_type}:{model_name}"
        entry = self.model_cache.get(cache_key)

        if entry and not entry.is_expired():
            # Update access statistics
            entry.access_count += 1
            entry.last_accessed = time.time()
            return entry

        # Remove expired entry
        if entry:
            del self.model_cache[cache_key]

        return None

    def _evict_models_if_needed(self):
        """Evict models if cache size exceeds limit"""
        total_vram = sum(entry.vram_usage_mb for entry in self.model_cache.values())

        if total_vram <= self.max_model_cache_mb:
            return

        # Sort by access patterns (LRU + access count)
        entries = list(self.model_cache.items())
        entries.sort(key=lambda x: (x[1].access_count, x[1].last_accessed))

        # Evict least used models
        while total_vram > self.max_model_cache_mb and entries:
            cache_key, entry = entries.pop(0)
            del self.model_cache[cache_key]
            total_vram -= entry.vram_usage_mb
            logger.info(f"Evicted model: {entry.model_name} ({entry.vram_usage_mb}MB)")

    def cache_output(self, prompt: str, generation_params: Dict[str, Any],
                    output_path: str, quality_score: float = 0.0):
        """Cache generation output"""

        prompt_hash = self._generate_prompt_hash(prompt, generation_params)
        current_time = time.time()

        # Calculate file size
        output_file = Path(output_path)
        size_mb = 0
        if output_file.exists():
            size_mb = output_file.stat().st_size / (1024 * 1024)

        entry = OutputCacheEntry(
            key=prompt_hash,
            timestamp=current_time,
            access_count=1,
            last_accessed=current_time,
            size_mb=int(size_mb),
            prompt_hash=prompt_hash,
            output_path=output_path,
            generation_params=generation_params.copy(),
            quality_score=quality_score
        )

        self.output_cache[prompt_hash] = entry
        logger.info(f"Cached output: {prompt[:50]}... -> {output_path}")

        # Evict old outputs if needed
        self._evict_outputs_if_needed()
        self._save_cache()

    def get_cached_output(self, prompt: str,
                         generation_params: Dict[str, Any]) -> Optional[OutputCacheEntry]:
        """Get cached output for exact prompt/params match"""

        prompt_hash = self._generate_prompt_hash(prompt, generation_params)
        entry = self.output_cache.get(prompt_hash)

        if entry and not entry.is_expired():
            # Check if output file still exists
            if Path(entry.output_path).exists():
                entry.access_count += 1
                entry.last_accessed = time.time()
                return entry
            else:
                # Remove entry if file is gone
                del self.output_cache[prompt_hash]

        return None

    def find_similar_output(self, prompt: str,
                           generation_params: Dict[str, Any],
                           similarity_threshold: float = 0.8) -> Optional[OutputCacheEntry]:
        """Find similar cached output (ignoring seed)"""

        similar_hash = self._generate_similar_prompt_hash(prompt, generation_params)

        # Find entries with similar parameters
        candidates = []
        for entry in self.output_cache.values():
            if entry.is_expired():
                continue

            entry_similar_hash = self._generate_similar_prompt_hash(
                prompt, entry.generation_params
            )

            if entry_similar_hash == similar_hash:
                candidates.append(entry)

        if not candidates:
            return None

        # Return highest quality candidate
        candidates.sort(key=lambda x: (x.quality_score, x.access_count), reverse=True)
        best_candidate = candidates[0]

        # Update access
        best_candidate.access_count += 1
        best_candidate.last_accessed = time.time()

        return best_candidate

    def _evict_outputs_if_needed(self):
        """Evict old outputs if cache is full"""
        if len(self.output_cache) <= self.max_output_cache_entries:
            return

        # Sort by access patterns and quality
        entries = list(self.output_cache.items())
        entries.sort(key=lambda x: (
            x[1].quality_score,
            x[1].access_count,
            x[1].last_accessed
        ))

        # Evict lowest quality, least accessed entries
        to_evict = len(entries) - self.max_output_cache_entries
        for i in range(to_evict):
            cache_key, entry = entries[i]
            del self.output_cache[cache_key]
            logger.info(f"Evicted output: {entry.output_path}")

    def cache_prompt_embedding(self, prompt: str, embedding: Any):
        """Cache prompt embedding for faster processing"""
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        self.prompt_embeddings[prompt_hash] = {
            "prompt": prompt,
            "embedding": embedding,
            "timestamp": time.time(),
            "access_count": 1
        }

        # Evict old embeddings if needed
        if len(self.prompt_embeddings) > self.max_prompt_embeddings:
            # Remove oldest embeddings
            sorted_embeddings = sorted(
                self.prompt_embeddings.items(),
                key=lambda x: x[1]["timestamp"]
            )

            to_remove = len(sorted_embeddings) - self.max_prompt_embeddings
            for i in range(to_remove):
                del self.prompt_embeddings[sorted_embeddings[i][0]]

    def get_cached_prompt_embedding(self, prompt: str) -> Optional[Any]:
        """Get cached prompt embedding"""
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        cached = self.prompt_embeddings.get(prompt_hash)

        if cached:
            cached["access_count"] += 1
            return cached["embedding"]

        return None

    @asynccontextmanager
    async def cached_generation(self, prompt: str, generation_params: Dict[str, Any]):
        """
        Context manager for cached generation

        Usage:
            async with cache.cached_generation(prompt, params) as cached:
                if cached:
                    return cached.output_path
                else:
                    # Perform generation
                    result = await generate(...)
                    cache.cache_output(prompt, params, result.output_path)
        """

        # Check for exact match first
        cached = self.get_cached_output(prompt, generation_params)
        if cached:
            logger.info(f"Cache hit (exact): {prompt[:50]}...")
            yield cached
            return

        # Check for similar output if seed is randomized
        if generation_params.get("seed", -1) == -1:
            similar = self.find_similar_output(prompt, generation_params)
            if similar:
                logger.info(f"Cache hit (similar): {prompt[:50]}...")
                yield similar
                return

        # No cache hit
        logger.info(f"Cache miss: {prompt[:50]}...")
        yield None

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_model_vram = sum(entry.vram_usage_mb for entry in self.model_cache.values())
        total_output_size = sum(entry.size_mb for entry in self.output_cache.values())

        return {
            "models": {
                "count": len(self.model_cache),
                "total_vram_mb": total_model_vram,
                "models": [
                    {
                        "name": entry.model_name,
                        "type": entry.model_type,
                        "vram_mb": entry.vram_usage_mb,
                        "access_count": entry.access_count,
                        "load_time": entry.load_time_seconds
                    }
                    for entry in sorted(
                        self.model_cache.values(),
                        key=lambda x: x.access_count,
                        reverse=True
                    )
                ]
            },
            "outputs": {
                "count": len(self.output_cache),
                "total_size_mb": int(total_output_size),
                "hit_rate": self._calculate_hit_rate()
            },
            "prompt_embeddings": {
                "count": len(self.prompt_embeddings)
            }
        }

    def _calculate_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        if not self.output_cache:
            return 0.0

        total_accesses = sum(entry.access_count for entry in self.output_cache.values())
        unique_entries = len(self.output_cache)

        if total_accesses == 0:
            return 0.0

        hit_rate = max(0.0, (total_accesses - unique_entries) / total_accesses)
        return round(hit_rate * 100, 1)

    def clear_expired_entries(self):
        """Clear all expired cache entries"""
        current_time = time.time()

        # Clear expired models
        expired_models = [
            key for key, entry in self.model_cache.items()
            if entry.is_expired()
        ]
        for key in expired_models:
            del self.model_cache[key]

        # Clear expired outputs
        expired_outputs = [
            key for key, entry in self.output_cache.items()
            if entry.is_expired()
        ]
        for key in expired_outputs:
            del self.output_cache[key]

        if expired_models or expired_outputs:
            logger.info(f"Cleared {len(expired_models)} expired models, "
                       f"{len(expired_outputs)} expired outputs")
            self._save_cache()


# Factory function
def get_generation_cache() -> GenerationCache:
    """Get configured generation cache instance"""
    return GenerationCache()


# Example usage
if __name__ == "__main__":
    async def test_cache():
        cache = get_generation_cache()

        # Test caching a model
        cache.cache_model(
            "counterfeit_v3.safetensors",
            "checkpoint",
            vram_usage_mb=2800,
            load_time_seconds=8.5
        )

        # Test caching output
        generation_params = {
            "model": "counterfeit_v3.safetensors",
            "steps": 15,
            "cfg": 6.5,
            "width": 768,
            "height": 768,
            "seed": 12345
        }

        cache.cache_output(
            "anime girl with blue hair",
            generation_params,
            "/mnt/1TB-storage/ComfyUI/output/test.png",
            quality_score=7.5
        )

        # Test cache retrieval
        async with cache.cached_generation("anime girl with blue hair", generation_params) as cached:
            if cached:
                print(f"Cache hit! Output: {cached.output_path}")
            else:
                print("Cache miss - need to generate")

        # Print cache stats
        stats = cache.get_cache_stats()
        print(f"Cache stats: {json.dumps(stats, indent=2)}")

    asyncio.run(test_cache())