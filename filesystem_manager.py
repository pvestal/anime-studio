#!/usr/bin/env python3
"""
Enhanced File System Manager with Error Handling and Disk Space Monitoring
Provides robust file operations with automatic recovery, disk space management,
and comprehensive error handling for the anime production system.
"""

import asyncio
import aiofiles
import shutil
import os
import stat
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, Optional, Any, List, Union, Callable, AsyncGenerator
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import logging
import psutil
import json
import zipfile
import tarfile

# Import our error handling framework
from shared.error_handling import (
    AnimeGenerationError, ResourceExhaustionError, ErrorSeverity, ErrorCategory,
    RetryManager, MetricsCollector, OperationMetrics
)

logger = logging.getLogger(__name__)

class StorageStatus(Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    FULL = "full"

class FileOperationType(Enum):
    READ = "read"
    WRITE = "write"
    COPY = "copy"
    MOVE = "move"
    DELETE = "delete"
    COMPRESS = "compress"
    EXTRACT = "extract"

@dataclass
class FileSystemConfig:
    """Configuration for file system management"""
    # Primary directories
    output_dir: str = "/mnt/1TB-storage/ComfyUI/output"
    cache_dir: str = "/opt/tower-anime-production/cache"
    temp_dir: str = "/tmp/anime-production"
    backup_dir: str = "/opt/tower-anime-production/backup"
    archive_dir: str = "/mnt/1TB-storage/archive"

    # Disk space thresholds (in GB)
    warning_threshold_gb: float = 50.0
    critical_threshold_gb: float = 20.0
    minimum_free_gb: float = 10.0

    # File operation settings
    max_file_size_gb: float = 10.0  # 10GB max per file
    chunk_size_mb: int = 64  # 64MB chunks for large operations
    max_retries: int = 3
    retry_delay: float = 1.0

    # Cleanup settings
    auto_cleanup_enabled: bool = True
    temp_file_ttl_hours: int = 24
    cache_ttl_days: int = 7
    archive_after_days: int = 30

    # Monitoring settings
    monitor_interval_seconds: int = 300  # 5 minutes
    alert_threshold_percent: float = 85.0

@dataclass
class DiskUsageInfo:
    """Disk usage information"""
    path: str
    total_gb: float
    used_gb: float
    free_gb: float
    usage_percent: float
    status: StorageStatus
    last_checked: datetime

@dataclass
class FileOperationResult:
    """Result of file operation"""
    operation_id: str
    operation_type: FileOperationType
    source_path: Optional[str]
    destination_path: Optional[str]
    success: bool
    bytes_processed: int
    processing_time_seconds: float
    error_message: Optional[str] = None
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = None

class FileSystemError(AnimeGenerationError):
    """File system specific errors"""

    def __init__(self, message: str, operation_type: FileOperationType = None,
                 file_path: str = None, **kwargs):
        super().__init__(message, ErrorCategory.SYSTEM, ErrorSeverity.HIGH, **kwargs)
        self.operation_type = operation_type
        self.file_path = file_path
        self.context.update({
            "operation_type": operation_type.value if operation_type else None,
            "file_path": file_path,
            "service": "filesystem"
        })

class DiskSpaceMonitor:
    """Monitors disk space and triggers cleanup when needed"""

    def __init__(self, config: FileSystemConfig):
        self.config = config
        self.disk_usage_history = {}
        self.alert_sent = {}
        self.last_cleanup = None

    async def check_disk_usage(self, path: str) -> DiskUsageInfo:
        """Check disk usage for a specific path"""
        try:
            usage = shutil.disk_usage(path)
            total_gb = usage.total / (1024**3)
            used_gb = usage.used / (1024**3)
            free_gb = usage.free / (1024**3)
            usage_percent = (used_gb / total_gb) * 100

            # Determine status
            if free_gb < self.config.critical_threshold_gb:
                status = StorageStatus.CRITICAL
            elif free_gb < self.config.warning_threshold_gb:
                status = StorageStatus.WARNING
            elif usage_percent > self.config.alert_threshold_percent:
                status = StorageStatus.WARNING
            else:
                status = StorageStatus.HEALTHY

            disk_info = DiskUsageInfo(
                path=path,
                total_gb=total_gb,
                used_gb=used_gb,
                free_gb=free_gb,
                usage_percent=usage_percent,
                status=status,
                last_checked=datetime.utcnow()
            )

            # Store in history
            self.disk_usage_history[path] = disk_info

            return disk_info

        except Exception as e:
            logger.error(f"Failed to check disk usage for {path}: {e}")
            return DiskUsageInfo(
                path=path,
                total_gb=0,
                used_gb=0,
                free_gb=0,
                usage_percent=100,
                status=StorageStatus.CRITICAL,
                last_checked=datetime.utcnow()
            )

    async def check_all_paths(self) -> Dict[str, DiskUsageInfo]:
        """Check disk usage for all configured paths"""
        paths = [
            self.config.output_dir,
            self.config.cache_dir,
            self.config.temp_dir,
            self.config.backup_dir,
            self.config.archive_dir
        ]

        results = {}
        for path in paths:
            if os.path.exists(path):
                results[path] = await self.check_disk_usage(path)

        return results

    async def check_space_available(self, path: str, required_gb: float) -> bool:
        """Check if sufficient space is available for operation"""
        disk_info = await self.check_disk_usage(path)
        return disk_info.free_gb >= (required_gb + self.config.minimum_free_gb)

    def get_usage_trend(self, path: str, hours: int = 24) -> Dict[str, Any]:
        """Get disk usage trend for path"""
        # This would be enhanced with persistent storage
        # For now, return current status
        current_info = self.disk_usage_history.get(path)
        if current_info:
            return {
                "path": path,
                "current_usage_percent": current_info.usage_percent,
                "current_free_gb": current_info.free_gb,
                "status": current_info.status.value,
                "trend": "stable"  # Would calculate from history
            }
        return {"path": path, "status": "unknown"}

class FileOperationManager:
    """Manages file operations with error handling and recovery"""

    def __init__(self, config: FileSystemConfig, disk_monitor: DiskSpaceMonitor):
        self.config = config
        self.disk_monitor = disk_monitor
        self.retry_manager = RetryManager()
        self.active_operations = {}

        # Ensure directories exist
        for dir_path in [config.temp_dir, config.backup_dir, config.cache_dir]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

    def _generate_operation_id(self) -> str:
        """Generate unique operation ID"""
        return f"fs_op_{int(datetime.utcnow().timestamp())}_{os.getpid()}"

    async def _calculate_checksum(self, file_path: str) -> str:
        """Calculate MD5 checksum of file"""
        try:
            hash_md5 = hashlib.md5()
            async with aiofiles.open(file_path, 'rb') as f:
                async for chunk in self._read_chunks(f, self.config.chunk_size_mb * 1024 * 1024):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.warning(f"Failed to calculate checksum for {file_path}: {e}")
            return ""

    async def _read_chunks(self, file_obj, chunk_size: int) -> AsyncGenerator[bytes, None]:
        """Read file in chunks"""
        while True:
            chunk = await file_obj.read(chunk_size)
            if not chunk:
                break
            yield chunk

    async def copy_file_robust(self, source: str, destination: str,
                             verify_checksum: bool = True) -> FileOperationResult:
        """Copy file with comprehensive error handling"""
        operation_id = self._generate_operation_id()
        self.active_operations[operation_id] = {
            "type": FileOperationType.COPY,
            "source": source,
            "destination": destination,
            "started_at": datetime.utcnow()
        }

        start_time = datetime.utcnow()

        try:
            source_path = Path(source)
            dest_path = Path(destination)

            # Validate source file
            if not source_path.exists():
                raise FileSystemError(
                    f"Source file does not exist: {source}",
                    FileOperationType.COPY,
                    source
                )

            # Check file size
            file_size_gb = source_path.stat().st_size / (1024**3)
            if file_size_gb > self.config.max_file_size_gb:
                raise FileSystemError(
                    f"File too large: {file_size_gb:.2f}GB > {self.config.max_file_size_gb}GB",
                    FileOperationType.COPY,
                    source
                )

            # Check destination space
            dest_dir = dest_path.parent
            dest_dir.mkdir(parents=True, exist_ok=True)

            if not await self.disk_monitor.check_space_available(str(dest_dir), file_size_gb):
                raise ResourceExhaustionError(
                    f"Insufficient disk space for copy operation: {file_size_gb:.2f}GB required",
                    resource_type="disk",
                    current_usage=file_size_gb
                )

            # Perform copy with retry
            async def _copy_operation():
                # Copy with progress tracking for large files
                if file_size_gb > 1.0:  # Large file
                    await self._copy_large_file(source_path, dest_path)
                else:
                    # Use shutil for smaller files
                    await asyncio.get_event_loop().run_in_executor(
                        None, shutil.copy2, str(source_path), str(dest_path)
                    )

            await self.retry_manager.retry_with_backoff(
                _copy_operation,
                max_retries=self.config.max_retries,
                base_delay=self.config.retry_delay,
                exceptions=(OSError, IOError, FileSystemError)
            )

            # Verify copy if requested
            checksum = None
            if verify_checksum:
                source_checksum = await self._calculate_checksum(source)
                dest_checksum = await self._calculate_checksum(destination)

                if source_checksum != dest_checksum:
                    # Clean up failed copy
                    if dest_path.exists():
                        dest_path.unlink()
                    raise FileSystemError(
                        f"Checksum verification failed: {source} -> {destination}",
                        FileOperationType.COPY,
                        destination
                    )
                checksum = source_checksum

            processing_time = (datetime.utcnow() - start_time).total_seconds()
            bytes_processed = dest_path.stat().st_size

            return FileOperationResult(
                operation_id=operation_id,
                operation_type=FileOperationType.COPY,
                source_path=source,
                destination_path=destination,
                success=True,
                bytes_processed=bytes_processed,
                processing_time_seconds=processing_time,
                checksum=checksum,
                metadata={"file_size_gb": file_size_gb}
            )

        except Exception as e:
            processing_time = (datetime.utcnow() - start_time).total_seconds()

            if isinstance(e, (FileSystemError, ResourceExhaustionError)):
                error = e
            else:
                error = FileSystemError(
                    f"Copy operation failed: {str(e)}",
                    FileOperationType.COPY,
                    source
                )

            return FileOperationResult(
                operation_id=operation_id,
                operation_type=FileOperationType.COPY,
                source_path=source,
                destination_path=destination,
                success=False,
                bytes_processed=0,
                processing_time_seconds=processing_time,
                error_message=str(error)
            )

        finally:
            if operation_id in self.active_operations:
                del self.active_operations[operation_id]

    async def _copy_large_file(self, source_path: Path, dest_path: Path):
        """Copy large file with progress tracking"""
        chunk_size = self.config.chunk_size_mb * 1024 * 1024

        async with aiofiles.open(source_path, 'rb') as src:
            async with aiofiles.open(dest_path, 'wb') as dst:
                bytes_copied = 0
                async for chunk in self._read_chunks(src, chunk_size):
                    await dst.write(chunk)
                    bytes_copied += len(chunk)

                    # Update progress (could emit events here)
                    if bytes_copied % (chunk_size * 10) == 0:  # Log every 640MB
                        mb_copied = bytes_copied / (1024 * 1024)
                        logger.debug(f"Copied {mb_copied:.1f}MB of {source_path.name}")

    async def move_file_robust(self, source: str, destination: str) -> FileOperationResult:
        """Move file with error handling"""
        # First copy, then delete source if successful
        copy_result = await self.copy_file_robust(source, destination, verify_checksum=True)

        if copy_result.success:
            try:
                Path(source).unlink()
                copy_result.operation_type = FileOperationType.MOVE
                return copy_result
            except Exception as e:
                # Copy succeeded but delete failed - log warning but don't fail
                logger.warning(f"Move operation: copy succeeded but source delete failed: {e}")
                copy_result.metadata = copy_result.metadata or {}
                copy_result.metadata["delete_failed"] = str(e)
                return copy_result
        else:
            copy_result.operation_type = FileOperationType.MOVE
            return copy_result

    async def delete_file_robust(self, file_path: str, backup_before_delete: bool = True) -> FileOperationResult:
        """Delete file with optional backup"""
        operation_id = self._generate_operation_id()
        start_time = datetime.utcnow()

        try:
            path = Path(file_path)
            if not path.exists():
                return FileOperationResult(
                    operation_id=operation_id,
                    operation_type=FileOperationType.DELETE,
                    source_path=file_path,
                    destination_path=None,
                    success=True,
                    bytes_processed=0,
                    processing_time_seconds=0,
                    metadata={"already_deleted": True}
                )

            file_size = path.stat().st_size
            backup_path = None

            # Create backup if requested
            if backup_before_delete:
                backup_dir = Path(self.config.backup_dir) / "deleted_files" / datetime.utcnow().strftime("%Y-%m-%d")
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"{path.name}_{int(datetime.utcnow().timestamp())}"

                backup_result = await self.copy_file_robust(str(path), str(backup_path), verify_checksum=False)
                if not backup_result.success:
                    logger.warning(f"Failed to backup file before deletion: {backup_result.error_message}")

            # Delete the file
            path.unlink()

            processing_time = (datetime.utcnow() - start_time).total_seconds()

            return FileOperationResult(
                operation_id=operation_id,
                operation_type=FileOperationType.DELETE,
                source_path=file_path,
                destination_path=str(backup_path) if backup_path else None,
                success=True,
                bytes_processed=file_size,
                processing_time_seconds=processing_time,
                metadata={"backup_created": backup_path is not None}
            )

        except Exception as e:
            processing_time = (datetime.utcnow() - start_time).total_seconds()

            error = FileSystemError(
                f"Delete operation failed: {str(e)}",
                FileOperationType.DELETE,
                file_path
            )

            return FileOperationResult(
                operation_id=operation_id,
                operation_type=FileOperationType.DELETE,
                source_path=file_path,
                destination_path=None,
                success=False,
                bytes_processed=0,
                processing_time_seconds=processing_time,
                error_message=str(error)
            )

    async def compress_files_robust(self, file_paths: List[str], output_path: str,
                                  compression_type: str = "zip") -> FileOperationResult:
        """Compress files with error handling"""
        operation_id = self._generate_operation_id()
        start_time = datetime.utcnow()

        try:
            # Calculate total size
            total_size = 0
            valid_paths = []
            for file_path in file_paths:
                path = Path(file_path)
                if path.exists():
                    total_size += path.stat().st_size
                    valid_paths.append(path)
                else:
                    logger.warning(f"File not found for compression: {file_path}")

            if not valid_paths:
                raise FileSystemError(
                    "No valid files found for compression",
                    FileOperationType.COMPRESS
                )

            # Check space for compressed output (estimate 50% compression)
            estimated_compressed_size = total_size * 0.5
            output_dir = Path(output_path).parent
            if not await self.disk_monitor.check_space_available(str(output_dir), estimated_compressed_size / (1024**3)):
                raise ResourceExhaustionError(
                    f"Insufficient disk space for compression: {estimated_compressed_size / (1024**3):.2f}GB estimated",
                    resource_type="disk",
                    current_usage=estimated_compressed_size
                )

            # Perform compression
            if compression_type.lower() == "zip":
                await self._create_zip_archive(valid_paths, output_path)
            elif compression_type.lower() in ["tar", "tar.gz"]:
                await self._create_tar_archive(valid_paths, output_path, compression_type == "tar.gz")
            else:
                raise FileSystemError(
                    f"Unsupported compression type: {compression_type}",
                    FileOperationType.COMPRESS
                )

            processing_time = (datetime.utcnow() - start_time).total_seconds()
            compressed_size = Path(output_path).stat().st_size

            return FileOperationResult(
                operation_id=operation_id,
                operation_type=FileOperationType.COMPRESS,
                source_path=f"{len(valid_paths)} files",
                destination_path=output_path,
                success=True,
                bytes_processed=compressed_size,
                processing_time_seconds=processing_time,
                metadata={
                    "original_size_bytes": total_size,
                    "compressed_size_bytes": compressed_size,
                    "compression_ratio": compressed_size / total_size if total_size > 0 else 0,
                    "files_compressed": len(valid_paths)
                }
            )

        except Exception as e:
            processing_time = (datetime.utcnow() - start_time).total_seconds()

            error = FileSystemError(
                f"Compression failed: {str(e)}",
                FileOperationType.COMPRESS
            )

            return FileOperationResult(
                operation_id=operation_id,
                operation_type=FileOperationType.COMPRESS,
                source_path=f"{len(file_paths)} files",
                destination_path=output_path,
                success=False,
                bytes_processed=0,
                processing_time_seconds=processing_time,
                error_message=str(error)
            )

    async def _create_zip_archive(self, file_paths: List[Path], output_path: str):
        """Create ZIP archive"""
        def _zip_files():
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in file_paths:
                    zipf.write(file_path, file_path.name)

        await asyncio.get_event_loop().run_in_executor(None, _zip_files)

    async def _create_tar_archive(self, file_paths: List[Path], output_path: str, use_compression: bool = False):
        """Create TAR archive"""
        def _tar_files():
            mode = 'w:gz' if use_compression else 'w'
            with tarfile.open(output_path, mode) as tarf:
                for file_path in file_paths:
                    tarf.add(file_path, file_path.name)

        await asyncio.get_event_loop().run_in_executor(None, _tar_files)

class CleanupManager:
    """Manages automatic cleanup of old files and directories"""

    def __init__(self, config: FileSystemConfig, disk_monitor: DiskSpaceMonitor):
        self.config = config
        self.disk_monitor = disk_monitor

    async def cleanup_temp_files(self) -> Dict[str, Any]:
        """Clean up old temporary files"""
        cleanup_results = {
            "files_deleted": 0,
            "bytes_freed": 0,
            "errors": []
        }

        try:
            temp_dir = Path(self.config.temp_dir)
            if not temp_dir.exists():
                return cleanup_results

            cutoff_time = datetime.utcnow() - timedelta(hours=self.config.temp_file_ttl_hours)

            for file_path in temp_dir.rglob("*"):
                if file_path.is_file():
                    try:
                        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if file_mtime < cutoff_time:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            cleanup_results["files_deleted"] += 1
                            cleanup_results["bytes_freed"] += file_size
                    except Exception as e:
                        cleanup_results["errors"].append(f"Failed to delete {file_path}: {e}")

        except Exception as e:
            cleanup_results["errors"].append(f"Temp cleanup failed: {e}")

        return cleanup_results

    async def cleanup_cache_files(self) -> Dict[str, Any]:
        """Clean up old cache files"""
        cleanup_results = {
            "files_deleted": 0,
            "bytes_freed": 0,
            "errors": []
        }

        try:
            cache_dir = Path(self.config.cache_dir)
            if not cache_dir.exists():
                return cleanup_results

            cutoff_time = datetime.utcnow() - timedelta(days=self.config.cache_ttl_days)

            for file_path in cache_dir.rglob("*.cache*"):
                try:
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        cleanup_results["files_deleted"] += 1
                        cleanup_results["bytes_freed"] += file_size
                except Exception as e:
                    cleanup_results["errors"].append(f"Failed to delete {file_path}: {e}")

        except Exception as e:
            cleanup_results["errors"].append(f"Cache cleanup failed: {e}")

        return cleanup_results

    async def archive_old_outputs(self) -> Dict[str, Any]:
        """Archive old output files"""
        archive_results = {
            "files_archived": 0,
            "bytes_archived": 0,
            "errors": []
        }

        try:
            output_dir = Path(self.config.output_dir)
            archive_dir = Path(self.config.archive_dir)
            archive_dir.mkdir(parents=True, exist_ok=True)

            cutoff_time = datetime.utcnow() - timedelta(days=self.config.archive_after_days)

            # Group files by date for efficient archiving
            files_by_date = {}
            for file_path in output_dir.glob("*"):
                if file_path.is_file():
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        date_key = file_mtime.strftime("%Y-%m-%d")
                        if date_key not in files_by_date:
                            files_by_date[date_key] = []
                        files_by_date[date_key].append(file_path)

            # Create archives by date
            for date_key, file_paths in files_by_date.items():
                try:
                    archive_path = archive_dir / f"output_{date_key}.tar.gz"

                    def _create_archive():
                        with tarfile.open(archive_path, 'w:gz') as tarf:
                            for file_path in file_paths:
                                tarf.add(file_path, file_path.name)

                    await asyncio.get_event_loop().run_in_executor(None, _create_archive)

                    # Delete original files after successful archiving
                    for file_path in file_paths:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        archive_results["files_archived"] += 1
                        archive_results["bytes_archived"] += file_size

                except Exception as e:
                    archive_results["errors"].append(f"Failed to archive {date_key}: {e}")

        except Exception as e:
            archive_results["errors"].append(f"Archive operation failed: {e}")

        return archive_results

class EnhancedFileSystemManager:
    """Enhanced file system manager with comprehensive error handling"""

    def __init__(self, config: FileSystemConfig = None, metrics_collector: MetricsCollector = None):
        self.config = config or FileSystemConfig()
        self.metrics_collector = metrics_collector
        self.disk_monitor = DiskSpaceMonitor(self.config)
        self.file_ops = FileOperationManager(self.config, self.disk_monitor)
        self.cleanup_manager = CleanupManager(self.config, self.disk_monitor)

        # Start monitoring task
        self.monitoring_task = None
        self.start_monitoring()

    def start_monitoring(self):
        """Start background monitoring"""
        if self.monitoring_task is None or self.monitoring_task.done():
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())

    async def _monitoring_loop(self):
        """Background monitoring loop"""
        while True:
            try:
                await asyncio.sleep(self.config.monitor_interval_seconds)

                # Check disk usage
                disk_usage = await self.disk_monitor.check_all_paths()

                # Trigger cleanup if needed
                for path, usage_info in disk_usage.items():
                    if usage_info.status in [StorageStatus.CRITICAL, StorageStatus.WARNING]:
                        if self.config.auto_cleanup_enabled:
                            logger.warning(f"Disk space {usage_info.status.value} for {path}, triggering cleanup")
                            await self.perform_emergency_cleanup()

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")

    async def perform_emergency_cleanup(self) -> Dict[str, Any]:
        """Perform emergency cleanup when disk space is critical"""
        logger.info("Performing emergency cleanup...")

        cleanup_results = {
            "temp_cleanup": await self.cleanup_manager.cleanup_temp_files(),
            "cache_cleanup": await self.cleanup_manager.cleanup_cache_files(),
            "archive_operation": await self.cleanup_manager.archive_old_outputs(),
            "total_bytes_freed": 0,
            "cleanup_timestamp": datetime.utcnow().isoformat()
        }

        # Calculate total bytes freed
        cleanup_results["total_bytes_freed"] = (
            cleanup_results["temp_cleanup"]["bytes_freed"] +
            cleanup_results["cache_cleanup"]["bytes_freed"] +
            cleanup_results["archive_operation"]["bytes_archived"]
        )

        total_mb_freed = cleanup_results["total_bytes_freed"] / (1024 * 1024)
        logger.info(f"Emergency cleanup completed: {total_mb_freed:.1f}MB freed")

        return cleanup_results

    async def ensure_space_available(self, path: str, required_gb: float) -> bool:
        """Ensure sufficient space is available, trigger cleanup if needed"""
        # Check current space
        if await self.disk_monitor.check_space_available(path, required_gb):
            return True

        # Space insufficient, try cleanup
        if self.config.auto_cleanup_enabled:
            logger.info(f"Insufficient space for {required_gb:.2f}GB operation, attempting cleanup")
            await self.perform_emergency_cleanup()

            # Check again after cleanup
            return await self.disk_monitor.check_space_available(path, required_gb)

        return False

    async def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive file system health"""
        disk_usage = await self.disk_monitor.check_all_paths()

        # Calculate overall status
        overall_status = StorageStatus.HEALTHY
        for usage_info in disk_usage.values():
            if usage_info.status == StorageStatus.CRITICAL:
                overall_status = StorageStatus.CRITICAL
                break
            elif usage_info.status == StorageStatus.WARNING:
                overall_status = StorageStatus.WARNING

        # Get active operations
        active_ops = len(self.file_ops.active_operations)

        return {
            "overall_status": overall_status.value,
            "disk_usage": {path: asdict(info) for path, info in disk_usage.items()},
            "active_operations": active_ops,
            "config": {
                "warning_threshold_gb": self.config.warning_threshold_gb,
                "critical_threshold_gb": self.config.critical_threshold_gb,
                "auto_cleanup_enabled": self.config.auto_cleanup_enabled,
                "monitor_interval_seconds": self.config.monitor_interval_seconds
            },
            "monitoring_status": "running" if self.monitoring_task and not self.monitoring_task.done() else "stopped",
            "last_check": datetime.utcnow().isoformat()
        }

    def close(self):
        """Close file system manager and stop monitoring"""
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()

# Factory function
def create_filesystem_manager(config: FileSystemConfig = None, metrics_collector: MetricsCollector = None) -> EnhancedFileSystemManager:
    """Create configured file system manager instance"""
    return EnhancedFileSystemManager(config, metrics_collector)

# Example usage and testing
async def test_filesystem_manager():
    """Test the enhanced file system manager"""
    fs_manager = create_filesystem_manager()

    try:
        # Test system health
        print("Getting file system health...")
        health = await fs_manager.get_system_health()
        print("System Health:", json.dumps(health, indent=2, default=str))

        # Test space checking
        print("\nTesting space availability...")
        has_space = await fs_manager.ensure_space_available("/tmp", 1.0)  # 1GB
        print(f"Space available for 1GB: {has_space}")

        # Test file operations
        print("\nTesting file operations...")
        test_file = "/tmp/test_file.txt"
        with open(test_file, 'w') as f:
            f.write("Test content for file operations")

        copy_result = await fs_manager.file_ops.copy_file_robust(
            test_file, "/tmp/test_file_copy.txt"
        )
        print(f"Copy operation successful: {copy_result.success}")

        # Test cleanup
        print("\nTesting cleanup...")
        cleanup_results = await fs_manager.perform_emergency_cleanup()
        total_freed_mb = cleanup_results["total_bytes_freed"] / (1024 * 1024)
        print(f"Cleanup freed: {total_freed_mb:.2f}MB")

    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        fs_manager.close()

if __name__ == "__main__":
    asyncio.run(test_filesystem_manager())