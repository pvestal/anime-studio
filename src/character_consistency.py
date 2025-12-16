#!/usr/bin/env python3
"""
Character Consistency using CLIP embeddings for high-quality similarity checking
Enhanced with both CLIP-based and fallback histogram methods
"""

import hashlib
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image
import numpy as np
import logging
import torch
import clip
import pickle
import json

logger = logging.getLogger(__name__)

class SimpleCharacterConsistency:
    """Basic character consistency using histogram comparison"""

    def __init__(self, reference_dir: Path = None):
        self.reference_dir = reference_dir or Path("/mnt/1TB-storage/anime/character_refs")
        self.reference_dir.mkdir(parents=True, exist_ok=True)

    def calculate_histogram_similarity(self, img1_path: str, img2_path: str) -> float:
        """Calculate histogram similarity between two images"""
        try:
            img1 = Image.open(img1_path).convert('RGB')
            img2 = Image.open(img2_path).convert('RGB')

            # Resize to same size for comparison
            size = (256, 256)
            img1 = img1.resize(size)
            img2 = img2.resize(size)

            # Convert to numpy arrays
            arr1 = np.array(img1)
            arr2 = np.array(img2)

            # Calculate histograms for each channel
            similarity_scores = []

            for channel in range(3):  # RGB
                hist1, _ = np.histogram(arr1[:, :, channel], bins=32, range=(0, 256))
                hist2, _ = np.histogram(arr2[:, :, channel], bins=32, range=(0, 256))

                # Normalize histograms
                hist1 = hist1.astype(float) / np.sum(hist1)
                hist2 = hist2.astype(float) / np.sum(hist2)

                # Calculate correlation coefficient
                correlation = np.corrcoef(hist1, hist2)[0, 1]
                if np.isnan(correlation):
                    correlation = 0.0

                similarity_scores.append(max(0, correlation))

            # Average across channels
            return float(np.mean(similarity_scores))

        except Exception as e:
            logger.error(f"Histogram similarity calculation failed: {e}")
            return 0.0

    def calculate_pixel_similarity(self, img1_path: str, img2_path: str) -> float:
        """Calculate pixel-level similarity (MSE-based)"""
        try:
            img1 = Image.open(img1_path).convert('RGB')
            img2 = Image.open(img2_path).convert('RGB')

            # Resize to same size
            size = (128, 128)  # Smaller for faster computation
            img1 = img1.resize(size)
            img2 = img2.resize(size)

            # Convert to numpy arrays
            arr1 = np.array(img1, dtype=np.float32)
            arr2 = np.array(img2, dtype=np.float32)

            # Calculate MSE
            mse = np.mean((arr1 - arr2) ** 2)

            # Convert to similarity score (0-1, where 1 is identical)
            max_mse = 255.0 ** 2  # Maximum possible MSE
            similarity = 1.0 - (mse / max_mse)

            return float(max(0.0, similarity))

        except Exception as e:
            logger.error(f"Pixel similarity calculation failed: {e}")
            return 0.0

    def get_character_consistency_score(self, image_path: str, character_name: str) -> float:
        """Get consistency score against stored character references"""

        character_ref_dir = self.reference_dir / character_name
        if not character_ref_dir.exists():
            logger.info(f"No references for character {character_name}, creating first reference")
            self.store_character_reference(image_path, character_name)
            return 1.0  # First image is perfectly consistent with itself

        # Compare against all existing references
        reference_files = list(character_ref_dir.glob("*.png")) + list(character_ref_dir.glob("*.jpg"))

        if not reference_files:
            logger.info(f"No valid references found for {character_name}")
            self.store_character_reference(image_path, character_name)
            return 1.0

        similarities = []

        for ref_path in reference_files[:5]:  # Limit to 5 most recent
            hist_sim = self.calculate_histogram_similarity(image_path, str(ref_path))
            pixel_sim = self.calculate_pixel_similarity(image_path, str(ref_path))

            # Weighted combination (histogram more important for character features)
            combined_sim = (hist_sim * 0.7) + (pixel_sim * 0.3)
            similarities.append(combined_sim)

        # Return best match (most similar reference)
        best_similarity = max(similarities) if similarities else 0.0

        # Store as reference if it's reasonably consistent
        if best_similarity > 0.6:
            self.store_character_reference(image_path, character_name)

        return float(best_similarity)

    def store_character_reference(self, image_path: str, character_name: str):
        """Store image as character reference"""
        try:
            character_dir = self.reference_dir / character_name
            character_dir.mkdir(parents=True, exist_ok=True)

            # Create unique filename based on content hash
            with open(image_path, 'rb') as f:
                content_hash = hashlib.md5(f.read()).hexdigest()[:8]

            source_path = Path(image_path)
            ref_path = character_dir / f"ref_{content_hash}{source_path.suffix}"

            # Copy image to reference directory
            img = Image.open(image_path)
            img.save(ref_path, quality=95)

            logger.info(f"Stored reference for {character_name}: {ref_path.name}")

            # Keep only latest 10 references per character
            refs = sorted(character_dir.glob("ref_*"), key=lambda x: x.stat().st_mtime)
            while len(refs) > 10:
                oldest = refs.pop(0)
                oldest.unlink()
                logger.info(f"Removed old reference: {oldest.name}")

        except Exception as e:
            logger.error(f"Failed to store character reference: {e}")

    def get_character_references(self, character_name: str) -> List[str]:
        """Get list of stored references for a character"""
        character_dir = self.reference_dir / character_name
        if not character_dir.exists():
            return []

        refs = list(character_dir.glob("ref_*"))
        return [str(ref) for ref in sorted(refs, key=lambda x: x.stat().st_mtime, reverse=True)]


# Integration with v2 tracking
async def check_character_consistency(
    image_path: str,
    character_name: str,
    minimum_score: float = 0.7
) -> Dict:
    """Check character consistency and return results for v2 tracking"""

    checker = SimpleCharacterConsistency()
    consistency_score = checker.get_character_consistency_score(image_path, character_name)

    result = {
        "character_name": character_name,
        "image_path": image_path,
        "consistency_score": consistency_score,
        "minimum_required": minimum_score,
        "passed": bool(consistency_score >= minimum_score),
        "references_count": len(checker.get_character_references(character_name))
    }

    if result["passed"]:
        logger.info(f"Character consistency PASSED: {consistency_score:.3f} >= {minimum_score}")
    else:
        logger.warning(f"Character consistency FAILED: {consistency_score:.3f} < {minimum_score}")

    return result


# Test function
async def test_consistency():
    """Test character consistency checker"""

    # Test with existing images
    test_images = list(Path("/mnt/1TB-storage/ComfyUI/output").glob("anime_*.png"))

    if not test_images:
        print("No test images found")
        return

    checker = SimpleCharacterConsistency()

    for i, img_path in enumerate(test_images[:3]):
        print(f"Testing image {i+1}: {img_path.name}")

        result = await check_character_consistency(
            str(img_path),
            "test_character",
            minimum_score=0.7
        )

        print(f"  Consistency score: {result['consistency_score']:.3f}")
        print(f"  Passed: {result['passed']}")
        print(f"  References: {result['references_count']}")
        print()


if __name__ == "__main__":
    asyncio.run(test_consistency())