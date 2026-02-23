#!/usr/bin/env python3
"""
Lightweight image quality scorer for LoRA Studio.

Uses OpenCV for blur, contrast, brightness, and edge analysis.
Extracted from /opt/anime-studio/quality/comfyui_quality_integration.py.

Usage:
    # As a library
    from quality_scorer import score_image
    result = score_image("/path/to/image.png")

    # As CLI
    python3 quality_scorer.py /path/to/image.png
    python3 quality_scorer.py --batch /path/to/datasets/  # score all dataset images
"""

import json
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def score_image(image_path: str) -> dict:
    """Score an image's quality. Returns dict with overall score and breakdown."""
    if not HAS_CV2:
        return {"quality_score": None, "error": "opencv not available"}

    path = Path(image_path)
    if not path.exists():
        return {"quality_score": None, "error": "file not found"}

    try:
        image = cv2.imread(str(path))
        if image is None:
            return {"quality_score": None, "error": "failed to read image"}

        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Blur detection (Laplacian variance)
        blur_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        blur_score = min(blur_var / 1000.0, 1.0)

        # Contrast (standard deviation of grayscale)
        contrast = gray.std() / 255.0

        # Brightness (penalize extremes)
        brightness = gray.mean() / 255.0
        brightness_score = 1.0 - abs(brightness - 0.5) * 2

        # Edge density (detail richness)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.count_nonzero(edges) / edges.size

        # Weighted combination
        quality_score = (
            blur_score * 0.3 +
            contrast * 0.3 +
            brightness_score * 0.2 +
            edge_density * 0.2
        )
        quality_score = min(quality_score, 1.0)

        return {
            "quality_score": round(quality_score, 4),
            "blur_score": round(blur_score, 4),
            "contrast": round(contrast, 4),
            "brightness": round(brightness, 4),
            "brightness_score": round(brightness_score, 4),
            "edge_density": round(edge_density, 4),
            "resolution": f"{width}x{height}",
        }
    except Exception as e:
        return {"quality_score": None, "error": str(e)}


def batch_score_datasets(datasets_dir: str, write_to_meta: bool = False):
    """Score all images in dataset directories and optionally update .meta.json files."""
    base = Path(datasets_dir)
    total = 0
    scored = 0

    for char_dir in sorted(base.iterdir()):
        if not char_dir.is_dir():
            continue
        images_dir = char_dir / "images"
        if not images_dir.exists():
            continue

        for png in sorted(images_dir.glob("*.png")):
            total += 1
            result = score_image(str(png))

            if result.get("quality_score") is not None:
                scored += 1

                if write_to_meta:
                    meta_path = png.with_suffix(".meta.json")
                    meta = {}
                    if meta_path.exists():
                        try:
                            meta = json.loads(meta_path.read_text())
                        except (json.JSONDecodeError, IOError):
                            pass
                    meta["quality_score"] = result["quality_score"]
                    meta["quality_breakdown"] = {
                        "blur": result["blur_score"],
                        "contrast": result["contrast"],
                        "brightness": result["brightness_score"],
                        "edge_density": result["edge_density"],
                    }
                    meta_path.write_text(json.dumps(meta, indent=2))

                print(f"  {char_dir.name}/{png.name}: {result['quality_score']:.3f}")

    print(f"\nScored {scored}/{total} images")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 quality_scorer.py <image_path>")
        print("       python3 quality_scorer.py --batch <datasets_dir> [--write]")
        sys.exit(1)

    if sys.argv[1] == "--batch":
        datasets_dir = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent.parent / "datasets")
        write = "--write" in sys.argv
        batch_score_datasets(datasets_dir, write_to_meta=write)
    else:
        result = score_image(sys.argv[1])
        print(json.dumps(result, indent=2))
