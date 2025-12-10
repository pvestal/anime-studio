#!/usr/bin/env python3
"""
Secure file operations for Anime Production System
Prevents path traversal attacks and ensures safe file handling
"""

import os
import shutil
import tempfile
import hashlib
import magic
import logging
from pathlib import Path
from typing import Optional, List, Dict, Union, BinaryIO
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class SecureFileManager:
    """Secure file operations manager with path validation and access controls"""

    def __init__(self):
        # Define allowed base directories
        self.allowed_directories = {
            'frames': Path('/opt/tower-anime-production/frames').resolve(),
            'output': Path('/mnt/1TB-storage/ComfyUI/output').resolve(),
            'temp': Path('/tmp/claude').resolve(),
            'uploads': Path('/opt/tower-anime-production/uploads').resolve(),
            'references': Path('/opt/tower-anime-production/references').resolve(),
        }

        # Ensure allowed directories exist
        for name, path in self.allowed_directories.items():
            try:
                path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Ensured directory exists: {name} -> {path}")
            except Exception as e:
                logger.error(f"Failed to create directory {name} at {path}: {e}")

        # Define allowed file extensions and MIME types
        self.allowed_extensions = {
            'image': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'],
            'video': ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv'],
            'audio': ['.mp3', '.wav', '.ogg', '.m4a', '.flac'],
            'text': ['.txt', '.json', '.yaml', '.yml', '.md'],
            'archive': ['.zip', '.tar', '.gz']
        }

        self.allowed_mime_types = {
            'image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/webp',
            'video/mp4', 'video/avi', 'video/quicktime', 'video/x-msvideo', 'video/webm',
            'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp4',
            'text/plain', 'application/json', 'text/markdown'
        }

        # Maximum file sizes (in bytes)
        self.max_file_sizes = {
            'image': 50 * 1024 * 1024,  # 50 MB
            'video': 500 * 1024 * 1024,  # 500 MB
            'audio': 100 * 1024 * 1024,  # 100 MB
            'text': 1 * 1024 * 1024,     # 1 MB
            'archive': 100 * 1024 * 1024  # 100 MB
        }

    def validate_path(self, file_path: Union[str, Path], allowed_directory: str) -> Path:
        """
        Validate and resolve file path to prevent directory traversal attacks

        Args:
            file_path: The file path to validate
            allowed_directory: Key for allowed base directory

        Returns:
            Resolved safe path

        Raises:
            ValueError: If path is invalid or outside allowed directory
        """
        if allowed_directory not in self.allowed_directories:
            raise ValueError(f"Invalid directory key: {allowed_directory}")

        base_path = self.allowed_directories[allowed_directory]

        try:
            # Convert to Path object and resolve
            target_path = Path(file_path).resolve()

            # Check if the resolved path is within the allowed directory
            target_path.relative_to(base_path)

            return target_path

        except (ValueError, OSError) as e:
            logger.error(f"Path traversal attempt detected: {file_path} -> {base_path}")
            raise ValueError(f"Invalid file path: path is outside allowed directory") from e

    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to prevent security issues

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        if not filename or not isinstance(filename, str):
            raise ValueError("Invalid filename")

        # Remove any path separators and dangerous characters
        sanitized = re.sub(r'[/\\:*?"<>|]', '', filename)
        sanitized = re.sub(r'\.\.', '', sanitized)  # Remove .. sequences
        sanitized = sanitized.strip()

        if not sanitized:
            raise ValueError("Filename became empty after sanitization")

        # Limit length
        if len(sanitized) > 255:
            name, ext = os.path.splitext(sanitized)
            sanitized = name[:255-len(ext)] + ext

        return sanitized

    def get_file_type(self, file_path: Union[str, Path]) -> str:
        """
        Determine file type from extension

        Args:
            file_path: Path to file

        Returns:
            File type category
        """
        extension = Path(file_path).suffix.lower()

        for file_type, extensions in self.allowed_extensions.items():
            if extension in extensions:
                return file_type

        return 'unknown'

    def validate_file_content(self, file_path: Union[str, Path]) -> Dict[str, Union[str, bool]]:
        """
        Validate file content using magic numbers and MIME type detection

        Args:
            file_path: Path to file to validate

        Returns:
            Dictionary with validation results
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return {'valid': False, 'error': 'File does not exist'}

            # Get file size
            file_size = path.stat().st_size
            file_type = self.get_file_type(path)

            # Check file size limits
            max_size = self.max_file_sizes.get(file_type, 10 * 1024 * 1024)  # 10MB default
            if file_size > max_size:
                return {
                    'valid': False,
                    'error': f'File too large: {file_size} bytes > {max_size} bytes'
                }

            # Detect MIME type
            try:
                mime_type = magic.from_file(str(path), mime=True)
            except Exception as e:
                logger.warning(f"Could not detect MIME type for {path}: {e}")
                mime_type = 'application/octet-stream'

            # Validate MIME type
            if mime_type not in self.allowed_mime_types:
                return {
                    'valid': False,
                    'error': f'Invalid MIME type: {mime_type}'
                }

            return {
                'valid': True,
                'mime_type': mime_type,
                'file_type': file_type,
                'size': file_size
            }

        except Exception as e:
            logger.error(f"File validation error for {file_path}: {e}")
            return {'valid': False, 'error': str(e)}

    def safe_write_file(self, content: Union[str, bytes],
                       filename: str,
                       directory: str,
                       overwrite: bool = False) -> Path:
        """
        Safely write content to a file with validation

        Args:
            content: Content to write
            filename: Target filename
            directory: Directory key from allowed_directories
            overwrite: Whether to overwrite existing files

        Returns:
            Path to written file
        """
        # Sanitize filename
        safe_filename = self.sanitize_filename(filename)

        # Validate target path
        target_path = self.validate_path(safe_filename, directory)

        # Check if file exists and overwrite policy
        if target_path.exists() and not overwrite:
            # Generate unique filename
            name, ext = os.path.splitext(safe_filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{name}_{timestamp}{ext}"
            target_path = self.validate_path(safe_filename, directory)

        try:
            # Write to temporary file first
            with tempfile.NamedTemporaryFile(
                mode='wb' if isinstance(content, bytes) else 'w',
                delete=False,
                dir=self.allowed_directories['temp']
            ) as temp_file:
                temp_file.write(content)
                temp_file_path = Path(temp_file.name)

            # Validate written file
            validation = self.validate_file_content(temp_file_path)
            if not validation['valid']:
                temp_file_path.unlink()  # Delete temp file
                raise ValueError(f"File validation failed: {validation['error']}")

            # Move temp file to target location
            shutil.move(str(temp_file_path), str(target_path))

            logger.info(f"Successfully wrote file: {target_path}")
            return target_path

        except Exception as e:
            # Clean up temp file if it exists
            if 'temp_file_path' in locals() and temp_file_path.exists():
                temp_file_path.unlink()

            logger.error(f"Failed to write file {filename}: {e}")
            raise

    def safe_read_file(self, filename: str, directory: str, binary: bool = False) -> Union[str, bytes]:
        """
        Safely read file content with validation

        Args:
            filename: Filename to read
            directory: Directory key from allowed_directories
            binary: Whether to read in binary mode

        Returns:
            File content
        """
        # Validate path
        file_path = self.validate_path(filename, directory)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {filename}")

        # Validate file content
        validation = self.validate_file_content(file_path)
        if not validation['valid']:
            raise ValueError(f"File validation failed: {validation['error']}")

        try:
            mode = 'rb' if binary else 'r'
            encoding = None if binary else 'utf-8'

            with open(file_path, mode, encoding=encoding) as f:
                content = f.read()

            logger.info(f"Successfully read file: {file_path}")
            return content

        except Exception as e:
            logger.error(f"Failed to read file {filename}: {e}")
            raise

    def safe_copy_file(self, source_path: str, dest_filename: str,
                      source_directory: str, dest_directory: str) -> Path:
        """
        Safely copy file between allowed directories

        Args:
            source_path: Source filename
            dest_filename: Destination filename
            source_directory: Source directory key
            dest_directory: Destination directory key

        Returns:
            Path to copied file
        """
        # Validate source and destination paths
        src_path = self.validate_path(source_path, source_directory)
        dest_filename_safe = self.sanitize_filename(dest_filename)
        dest_path = self.validate_path(dest_filename_safe, dest_directory)

        if not src_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Validate source file
        validation = self.validate_file_content(src_path)
        if not validation['valid']:
            raise ValueError(f"Source file validation failed: {validation['error']}")

        try:
            # Copy file
            shutil.copy2(str(src_path), str(dest_path))

            logger.info(f"Successfully copied file: {src_path} -> {dest_path}")
            return dest_path

        except Exception as e:
            logger.error(f"Failed to copy file {source_path} to {dest_filename}: {e}")
            raise

    def safe_delete_file(self, filename: str, directory: str) -> bool:
        """
        Safely delete file with validation

        Args:
            filename: Filename to delete
            directory: Directory key from allowed_directories

        Returns:
            True if file was deleted successfully
        """
        # Validate path
        file_path = self.validate_path(filename, directory)

        if not file_path.exists():
            logger.warning(f"File not found for deletion: {filename}")
            return False

        try:
            file_path.unlink()
            logger.info(f"Successfully deleted file: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete file {filename}: {e}")
            raise

    def list_files(self, directory: str, pattern: str = "*") -> List[Dict[str, Union[str, int]]]:
        """
        Safely list files in directory with metadata

        Args:
            directory: Directory key from allowed_directories
            pattern: Glob pattern for filtering

        Returns:
            List of file information dictionaries
        """
        base_path = self.allowed_directories.get(directory)
        if not base_path:
            raise ValueError(f"Invalid directory key: {directory}")

        try:
            files = []
            for file_path in base_path.glob(pattern):
                if file_path.is_file():
                    try:
                        stat = file_path.stat()
                        validation = self.validate_file_content(file_path)

                        file_info = {
                            'name': file_path.name,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            'type': self.get_file_type(file_path),
                            'valid': validation['valid']
                        }

                        if validation['valid']:
                            file_info['mime_type'] = validation.get('mime_type', 'unknown')

                        files.append(file_info)

                    except Exception as e:
                        logger.warning(f"Could not get info for file {file_path}: {e}")

            return files

        except Exception as e:
            logger.error(f"Failed to list files in {directory}: {e}")
            raise

    def get_file_hash(self, filename: str, directory: str, algorithm: str = 'sha256') -> str:
        """
        Get cryptographic hash of file content

        Args:
            filename: Filename to hash
            directory: Directory key from allowed_directories
            algorithm: Hash algorithm ('md5', 'sha1', 'sha256', 'sha512')

        Returns:
            Hexadecimal hash string
        """
        file_path = self.validate_path(filename, directory)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {filename}")

        try:
            hash_func = hashlib.new(algorithm)

            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_func.update(chunk)

            return hash_func.hexdigest()

        except Exception as e:
            logger.error(f"Failed to hash file {filename}: {e}")
            raise


# Global instance for easy access
secure_file_manager = SecureFileManager()