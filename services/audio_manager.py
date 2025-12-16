#!/usr/bin/env python3
"""
Audio File Management and Optimization System
Handles audio file storage, caching, compression, and optimization
Provides efficient audio processing for anime voice production
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import asyncpg
import aiofiles
from fastapi import HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class AudioFile(BaseModel):
    """Audio file metadata"""
    file_id: str = Field(..., description="Unique file identifier")
    original_path: str = Field(..., description="Original file path")
    optimized_path: Optional[str] = Field(None, description="Optimized file path")
    file_size: int = Field(..., description="File size in bytes")
    duration: float = Field(..., description="Duration in seconds")
    format: str = Field(..., description="Audio format (mp3, wav, etc.)")
    sample_rate: int = Field(..., description="Sample rate in Hz")
    channels: int = Field(default=1, description="Number of audio channels")
    bitrate: Optional[int] = Field(None, description="Bitrate in kbps")

class AudioOptimizationSettings(BaseModel):
    """Settings for audio optimization"""
    target_format: str = Field(default="mp3", pattern="^(mp3|wav|ogg)$")
    target_bitrate: int = Field(default=128, ge=64, le=320)
    target_sample_rate: int = Field(default=22050, ge=8000, le=48000)
    normalize_volume: bool = Field(default=True)
    noise_reduction: bool = Field(default=False)
    compress: bool = Field(default=True)

class AudioCacheEntry(BaseModel):
    """Audio cache entry"""
    cache_key: str = Field(..., description="Cache key")
    file_path: str = Field(..., description="Cached file path")
    file_size: int = Field(..., description="File size in bytes")
    access_count: int = Field(default=1, description="Number of accesses")
    last_accessed: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = Field(None, description="Cache expiration")

class AudioManager:
    """Comprehensive audio file management system"""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.storage_root = Path("/mnt/1TB-storage/ComfyUI/output/voice")
        self.cache_root = Path("/mnt/1TB-storage/ComfyUI/output/voice/cache")
        self.temp_root = Path("/mnt/1TB-storage/ComfyUI/output/voice/temp")
        self.optimized_root = Path("/mnt/1TB-storage/ComfyUI/output/voice/optimized")

        # Create directories
        for path in [self.storage_root, self.cache_root, self.temp_root, self.optimized_root]:
            path.mkdir(parents=True, exist_ok=True)

        # Cache settings
        self.max_cache_size_gb = 5.0  # 5GB cache limit
        self.cache_cleanup_interval = 3600  # 1 hour
        self.default_cache_ttl = 7  # 7 days

        # Optimization settings
        self.optimization_queue = asyncio.Queue()
        self.optimization_workers = 2

    async def initialize(self):
        """Initialize audio manager"""
        try:
            # Start background tasks
            asyncio.create_task(self.cache_cleanup_worker())

            # Start optimization workers
            for i in range(self.optimization_workers):
                asyncio.create_task(self.optimization_worker(f"worker_{i}"))

            logger.info("Audio manager initialized successfully")

        except Exception as e:
            logger.error(f"Audio manager initialization error: {e}")
            raise

    async def store_audio_file(
        self,
        audio_data: bytes,
        metadata: Dict,
        character_name: Optional[str] = None,
        optimize: bool = True
    ) -> AudioFile:
        """Store audio file with metadata and optional optimization"""
        try:
            # Generate file ID
            file_hash = hashlib.sha256(audio_data).hexdigest()[:16]
            timestamp = int(time.time())
            file_id = f"{character_name or 'unknown'}_{timestamp}_{file_hash}"

            # Determine file format and extension
            audio_format = metadata.get("format", "mp3")
            extension = "." + audio_format.lower()

            # Create file path
            file_path = self.storage_root / f"{file_id}{extension}"

            # Write audio data
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(audio_data)

            # Create audio file record
            audio_file = AudioFile(
                file_id=file_id,
                original_path=str(file_path),
                file_size=len(audio_data),
                duration=metadata.get("duration", 0.0),
                format=audio_format,
                sample_rate=metadata.get("sample_rate", 22050),
                channels=metadata.get("channels", 1),
                bitrate=metadata.get("bitrate")
            )

            # Store in database
            await self.store_audio_metadata(audio_file, character_name)

            # Queue for optimization if requested
            if optimize:
                await self.optimization_queue.put({
                    "file_id": file_id,
                    "file_path": str(file_path),
                    "character_name": character_name
                })

            logger.info(f"Audio file stored: {file_id}")
            return audio_file

        except Exception as e:
            logger.error(f"Error storing audio file: {e}")
            raise

    async def store_audio_metadata(self, audio_file: AudioFile, character_name: Optional[str] = None):
        """Store audio metadata in database"""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO audio_files (
                        file_id, original_path, optimized_path, file_size, duration,
                        format, sample_rate, channels, bitrate, character_name, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (file_id) DO UPDATE SET
                        optimized_path = EXCLUDED.optimized_path,
                        updated_at = CURRENT_TIMESTAMP
                """,
                audio_file.file_id, audio_file.original_path, audio_file.optimized_path,
                audio_file.file_size, audio_file.duration, audio_file.format,
                audio_file.sample_rate, audio_file.channels, audio_file.bitrate,
                character_name, datetime.now()
                )

        except Exception as e:
            logger.error(f"Error storing audio metadata: {e}")
            raise

    async def get_audio_file(self, file_id: str) -> Optional[AudioFile]:
        """Retrieve audio file metadata"""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchrow(
                    "SELECT * FROM audio_files WHERE file_id = $1",
                    file_id
                )

                if result:
                    return AudioFile(
                        file_id=result["file_id"],
                        original_path=result["original_path"],
                        optimized_path=result["optimized_path"],
                        file_size=result["file_size"],
                        duration=result["duration"],
                        format=result["format"],
                        sample_rate=result["sample_rate"],
                        channels=result["channels"],
                        bitrate=result["bitrate"]
                    )

                return None

        except Exception as e:
            logger.error(f"Error getting audio file: {e}")
            return None

    async def optimize_audio_file(
        self,
        file_path: str,
        settings: AudioOptimizationSettings,
        file_id: str
    ) -> Optional[str]:
        """Optimize audio file for storage and streaming"""
        try:
            # Create optimized file path
            optimized_filename = f"{file_id}_opt.{settings.target_format}"
            optimized_path = self.optimized_root / optimized_filename

            # Build FFmpeg command for optimization
            ffmpeg_cmd = [
                "ffmpeg", "-y",  # Overwrite output
                "-i", file_path,  # Input file
            ]

            # Audio codec settings
            if settings.target_format == "mp3":
                ffmpeg_cmd.extend([
                    "-codec:a", "libmp3lame",
                    "-b:a", f"{settings.target_bitrate}k",
                ])
            elif settings.target_format == "ogg":
                ffmpeg_cmd.extend([
                    "-codec:a", "libvorbis",
                    "-b:a", f"{settings.target_bitrate}k",
                ])
            elif settings.target_format == "wav":
                ffmpeg_cmd.extend([
                    "-codec:a", "pcm_s16le",
                ])

            # Sample rate
            ffmpeg_cmd.extend(["-ar", str(settings.target_sample_rate)])

            # Normalize volume if requested
            if settings.normalize_volume:
                ffmpeg_cmd.extend([
                    "-filter:a", "loudnorm=I=-16:TP=-1.5:LRA=11",
                ])

            # Noise reduction if requested
            if settings.noise_reduction:
                ffmpeg_cmd.extend([
                    "-af", "afftdn",
                ])

            # Output file
            ffmpeg_cmd.append(str(optimized_path))

            # Execute FFmpeg
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0 and optimized_path.exists():
                # Update database with optimized path
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE audio_files
                        SET optimized_path = $1, updated_at = CURRENT_TIMESTAMP
                        WHERE file_id = $2
                    """, str(optimized_path), file_id)

                logger.info(f"Audio optimization completed: {file_id}")
                return str(optimized_path)
            else:
                logger.error(f"FFmpeg optimization failed: {stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"Audio optimization error: {e}")
            return None

    async def optimization_worker(self, worker_name: str):
        """Background worker for audio optimization"""
        logger.info(f"Audio optimization worker started: {worker_name}")

        while True:
            try:
                # Wait for optimization task
                task = await self.optimization_queue.get()

                file_id = task["file_id"]
                file_path = task["file_path"]
                character_name = task.get("character_name")

                logger.info(f"Optimizing audio: {file_id}")

                # Default optimization settings
                settings = AudioOptimizationSettings(
                    target_format="mp3",
                    target_bitrate=128,
                    target_sample_rate=22050,
                    normalize_volume=True,
                    noise_reduction=False
                )

                # Optimize the file
                optimized_path = await self.optimize_audio_file(file_path, settings, file_id)

                if optimized_path:
                    logger.info(f"Audio optimization successful: {file_id}")
                else:
                    logger.error(f"Audio optimization failed: {file_id}")

                # Mark task as done
                self.optimization_queue.task_done()

                # Brief pause between optimizations
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Optimization worker error ({worker_name}): {e}")
                await asyncio.sleep(5)

    async def cache_audio_file(
        self,
        source_path: str,
        cache_key: str,
        ttl_days: int = None
    ) -> AudioCacheEntry:
        """Cache audio file for quick access"""
        try:
            if ttl_days is None:
                ttl_days = self.default_cache_ttl

            # Create cache file path
            cache_filename = f"{cache_key}.cached"
            cache_path = self.cache_root / cache_filename

            # Copy file to cache
            shutil.copy2(source_path, cache_path)

            # Calculate expiration
            expires_at = datetime.now() + timedelta(days=ttl_days)

            # Create cache entry
            cache_entry = AudioCacheEntry(
                cache_key=cache_key,
                file_path=str(cache_path),
                file_size=cache_path.stat().st_size,
                expires_at=expires_at
            )

            # Store in database
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO audio_processing_cache (
                        cache_key, input_text_hash, cached_audio_path,
                        cache_size_bytes, expires_at, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (cache_key) DO UPDATE SET
                        access_count = audio_processing_cache.access_count + 1,
                        last_accessed = CURRENT_TIMESTAMP
                """,
                cache_key, cache_key[:64], str(cache_path),
                cache_entry.file_size, expires_at, datetime.now()
                )

            logger.info(f"Audio file cached: {cache_key}")
            return cache_entry

        except Exception as e:
            logger.error(f"Audio caching error: {e}")
            raise

    async def get_cached_audio(self, cache_key: str) -> Optional[str]:
        """Retrieve cached audio file"""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT cached_audio_path, expires_at FROM audio_processing_cache
                    WHERE cache_key = $1
                """, cache_key)

                if result:
                    cache_path = Path(result["cached_audio_path"])
                    expires_at = result["expires_at"]

                    # Check if cache is still valid
                    if expires_at and datetime.now() > expires_at:
                        await self.remove_cached_audio(cache_key)
                        return None

                    # Check if file exists
                    if cache_path.exists():
                        # Update access statistics
                        await conn.execute("""
                            UPDATE audio_processing_cache
                            SET access_count = access_count + 1, last_accessed = CURRENT_TIMESTAMP
                            WHERE cache_key = $1
                        """, cache_key)

                        return str(cache_path)

                return None

        except Exception as e:
            logger.error(f"Error getting cached audio: {e}")
            return None

    async def remove_cached_audio(self, cache_key: str):
        """Remove audio file from cache"""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchrow(
                    "SELECT cached_audio_path FROM audio_processing_cache WHERE cache_key = $1",
                    cache_key
                )

                if result:
                    cache_path = Path(result["cached_audio_path"])
                    if cache_path.exists():
                        cache_path.unlink()

                    await conn.execute(
                        "DELETE FROM audio_processing_cache WHERE cache_key = $1",
                        cache_key
                    )

        except Exception as e:
            logger.error(f"Error removing cached audio: {e}")

    async def cache_cleanup_worker(self):
        """Background worker for cache cleanup"""
        logger.info("Cache cleanup worker started")

        while True:
            try:
                await asyncio.sleep(self.cache_cleanup_interval)
                await self.cleanup_expired_cache()
                await self.cleanup_oversized_cache()

            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

    async def cleanup_expired_cache(self):
        """Clean up expired cache entries"""
        try:
            async with self.db_pool.acquire() as conn:
                # Get expired entries
                expired_entries = await conn.fetch("""
                    SELECT cache_key, cached_audio_path FROM audio_processing_cache
                    WHERE expires_at < CURRENT_TIMESTAMP
                """)

                for entry in expired_entries:
                    cache_path = Path(entry["cached_audio_path"])
                    if cache_path.exists():
                        cache_path.unlink()

                # Remove from database
                deleted_count = await conn.fetchval("""
                    DELETE FROM audio_processing_cache
                    WHERE expires_at < CURRENT_TIMESTAMP
                    RETURNING COUNT(*)
                """)

                if deleted_count:
                    logger.info(f"Cleaned up {deleted_count} expired cache entries")

        except Exception as e:
            logger.error(f"Expired cache cleanup error: {e}")

    async def cleanup_oversized_cache(self):
        """Clean up cache if it exceeds size limit"""
        try:
            # Calculate current cache size
            total_size = await self.get_cache_size()
            max_size_bytes = self.max_cache_size_gb * 1024 * 1024 * 1024

            if total_size > max_size_bytes:
                # Remove least recently used entries
                async with self.db_pool.acquire() as conn:
                    lru_entries = await conn.fetch("""
                        SELECT cache_key, cached_audio_path, cache_size_bytes
                        FROM audio_processing_cache
                        ORDER BY last_accessed ASC, access_count ASC
                    """)

                    size_freed = 0
                    removed_count = 0

                    for entry in lru_entries:
                        if total_size - size_freed <= max_size_bytes * 0.8:  # Keep 20% buffer
                            break

                        cache_path = Path(entry["cached_audio_path"])
                        if cache_path.exists():
                            cache_path.unlink()

                        await conn.execute(
                            "DELETE FROM audio_processing_cache WHERE cache_key = $1",
                            entry["cache_key"]
                        )

                        size_freed += entry["cache_size_bytes"]
                        removed_count += 1

                    if removed_count:
                        logger.info(f"Freed {size_freed / 1024 / 1024:.1f}MB by removing {removed_count} cache entries")

        except Exception as e:
            logger.error(f"Oversized cache cleanup error: {e}")

    async def get_cache_size(self) -> int:
        """Get current total cache size in bytes"""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT COALESCE(SUM(cache_size_bytes), 0) FROM audio_processing_cache"
                )
                return result or 0

        except Exception as e:
            logger.error(f"Error getting cache size: {e}")
            return 0

    async def get_storage_statistics(self) -> Dict:
        """Get comprehensive storage and performance statistics"""
        try:
            async with self.db_pool.acquire() as conn:
                # Audio files statistics
                audio_stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_files,
                        SUM(file_size) as total_size,
                        AVG(file_size) as avg_file_size,
                        AVG(duration) as avg_duration,
                        COUNT(CASE WHEN optimized_path IS NOT NULL THEN 1 END) as optimized_count
                    FROM audio_files
                """)

                # Cache statistics
                cache_stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_cache_entries,
                        SUM(cache_size_bytes) as total_cache_size,
                        AVG(access_count) as avg_access_count,
                        COUNT(CASE WHEN expires_at > CURRENT_TIMESTAMP THEN 1 END) as active_entries
                    FROM audio_processing_cache
                """)

                # Character usage statistics
                character_stats = await conn.fetch("""
                    SELECT character_name, COUNT(*) as file_count
                    FROM audio_files
                    WHERE character_name IS NOT NULL
                    GROUP BY character_name
                    ORDER BY file_count DESC
                    LIMIT 10
                """)

                return {
                    "audio_files": {
                        "total_files": audio_stats["total_files"] or 0,
                        "total_size_bytes": audio_stats["total_size"] or 0,
                        "total_size_mb": (audio_stats["total_size"] or 0) / 1024 / 1024,
                        "avg_file_size_kb": (audio_stats["avg_file_size"] or 0) / 1024,
                        "avg_duration_seconds": audio_stats["avg_duration"] or 0,
                        "optimization_rate": (audio_stats["optimized_count"] or 0) / max(1, audio_stats["total_files"] or 1)
                    },
                    "cache": {
                        "total_entries": cache_stats["total_cache_entries"] or 0,
                        "total_size_bytes": cache_stats["total_cache_size"] or 0,
                        "total_size_mb": (cache_stats["total_cache_size"] or 0) / 1024 / 1024,
                        "avg_access_count": cache_stats["avg_access_count"] or 0,
                        "active_entries": cache_stats["active_entries"] or 0,
                        "utilization_percent": min(100, ((cache_stats["total_cache_size"] or 0) / (self.max_cache_size_gb * 1024 * 1024 * 1024)) * 100)
                    },
                    "character_usage": [
                        {
                            "character_name": row["character_name"],
                            "file_count": row["file_count"]
                        }
                        for row in character_stats
                    ],
                    "storage_paths": {
                        "storage_root": str(self.storage_root),
                        "cache_root": str(self.cache_root),
                        "optimized_root": str(self.optimized_root),
                        "temp_root": str(self.temp_root)
                    },
                    "settings": {
                        "max_cache_size_gb": self.max_cache_size_gb,
                        "default_cache_ttl_days": self.default_cache_ttl,
                        "optimization_workers": self.optimization_workers
                    },
                    "timestamp": datetime.now().isoformat()
                }

        except Exception as e:
            logger.error(f"Error getting storage statistics: {e}")
            return {"error": str(e)}

    async def cleanup_orphaned_files(self) -> Dict:
        """Clean up orphaned files not referenced in database"""
        try:
            cleanup_stats = {
                "files_checked": 0,
                "orphaned_files": 0,
                "size_freed_bytes": 0,
                "errors": []
            }

            # Check all storage directories
            for storage_dir in [self.storage_root, self.optimized_root]:
                async for file_path in self.iterate_files(storage_dir):
                    cleanup_stats["files_checked"] += 1

                    # Check if file is referenced in database
                    async with self.db_pool.acquire() as conn:
                        referenced = await conn.fetchval("""
                            SELECT EXISTS(
                                SELECT 1 FROM audio_files
                                WHERE original_path = $1 OR optimized_path = $1
                            )
                        """, str(file_path))

                        if not referenced:
                            try:
                                file_size = file_path.stat().st_size
                                file_path.unlink()
                                cleanup_stats["orphaned_files"] += 1
                                cleanup_stats["size_freed_bytes"] += file_size
                            except Exception as e:
                                cleanup_stats["errors"].append(f"Failed to remove {file_path}: {e}")

            logger.info(f"Cleanup completed: {cleanup_stats['orphaned_files']} orphaned files removed")
            return cleanup_stats

        except Exception as e:
            logger.error(f"Orphaned files cleanup error: {e}")
            return {"error": str(e)}

    async def iterate_files(self, directory: Path):
        """Async generator for iterating files in directory"""
        try:
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    yield file_path
        except Exception as e:
            logger.error(f"Error iterating files in {directory}: {e}")

# Database table creation for audio manager
AUDIO_MANAGER_SCHEMA = """
-- Audio files metadata
CREATE TABLE IF NOT EXISTS audio_files (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) UNIQUE NOT NULL,
    original_path TEXT NOT NULL,
    optimized_path TEXT,
    file_size BIGINT NOT NULL,
    duration FLOAT DEFAULT 0.0,
    format VARCHAR(10) NOT NULL,
    sample_rate INTEGER DEFAULT 22050,
    channels INTEGER DEFAULT 1,
    bitrate INTEGER,
    character_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for audio files
CREATE INDEX IF NOT EXISTS idx_audio_files_character ON audio_files(character_name);
CREATE INDEX IF NOT EXISTS idx_audio_files_format ON audio_files(format);
CREATE INDEX IF NOT EXISTS idx_audio_files_created ON audio_files(created_at DESC);

-- Triggers for updated_at
CREATE TRIGGER update_audio_files_updated_at BEFORE UPDATE ON audio_files
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON audio_files TO patrick;
GRANT ALL PRIVILEGES ON SEQUENCE audio_files_id_seq TO patrick;
"""