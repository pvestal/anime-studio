#!/usr/bin/env python3
"""
Standalone WD14 auto-tagger for LoRA Studio.

Uses the same ONNX model as the ComfyUI WD14 Tagger node, but runs independently.
Downloads the model on first use to the local models/ directory.

Usage:
    # Tag a single image
    python3 wd14_tagger.py /path/to/image.png

    # Tag all images in datasets and write .txt captions
    python3 wd14_tagger.py --batch /path/to/datasets/ [--write-captions] [--write-meta]

    # Specify threshold
    python3 wd14_tagger.py --threshold 0.35 /path/to/image.png
"""

import json
import os
import sys
import csv
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
MODELS_DIR = _SCRIPT_DIR.parent / "models" / "wd14"
DEFAULT_MODEL = "wd-swinv2-tagger-v3"
MODEL_REPO = "https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/resolve/main/"


def ensure_model(model_name: str = DEFAULT_MODEL) -> tuple:
    """Download model if not present. Returns (onnx_path, csv_path)."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = MODELS_DIR / f"{model_name}.onnx"
    csv_path = MODELS_DIR / f"{model_name}.csv"

    if not onnx_path.exists() or not csv_path.exists():
        import urllib.request
        print(f"Downloading WD14 model '{model_name}'...")
        if not onnx_path.exists():
            print(f"  Downloading model.onnx...")
            urllib.request.urlretrieve(f"{MODEL_REPO}model.onnx", str(onnx_path))
        if not csv_path.exists():
            print(f"  Downloading selected_tags.csv...")
            urllib.request.urlretrieve(f"{MODEL_REPO}selected_tags.csv", str(csv_path))
        print("  Done.")

    return onnx_path, csv_path


def load_tags(csv_path: Path) -> list:
    """Load tag names from the CSV file."""
    tags = []
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) >= 2:
                tags.append(row[1])  # tag_name column
    return tags


def tag_image(image_path: str, threshold: float = 0.35,
              model_name: str = DEFAULT_MODEL) -> dict:
    """Tag a single image. Returns dict with tags and confidence scores."""
    try:
        import onnxruntime as ort
        from PIL import Image
        import numpy as np
    except ImportError as e:
        return {"tags": [], "error": f"Missing dependency: {e}. Install: pip install onnxruntime pillow numpy"}

    path = Path(image_path)
    if not path.exists():
        return {"tags": [], "error": "file not found"}

    try:
        onnx_path, csv_path = ensure_model(model_name)
        tags_list = load_tags(csv_path)

        # Load and preprocess image
        image = Image.open(path).convert("RGB")

        # Get model input size
        session = ort.InferenceSession(str(onnx_path))
        input_shape = session.get_inputs()[0].shape
        target_size = input_shape[1] if len(input_shape) >= 3 else 448

        # Resize with padding (same as ComfyUI node)
        image = image.resize((target_size, target_size), Image.LANCZOS)
        img_array = np.array(image, dtype=np.float32)

        # BGR conversion (model expects BGR)
        img_array = img_array[:, :, ::-1]

        # Add batch dimension
        img_array = np.expand_dims(img_array, axis=0)

        # Run inference
        input_name = session.get_inputs()[0].name
        output = session.run(None, {input_name: img_array})
        predictions = output[0][0]

        # Filter by threshold
        results = []
        for i, score in enumerate(predictions):
            if i < len(tags_list) and float(score) >= threshold:
                results.append({
                    "tag": tags_list[i],
                    "confidence": round(float(score), 4),
                })

        # Sort by confidence descending
        results.sort(key=lambda x: x["confidence"], reverse=True)

        return {
            "tags": results,
            "tag_string": ", ".join(r["tag"] for r in results),
            "count": len(results),
        }
    except Exception as e:
        return {"tags": [], "error": str(e)}


def batch_tag_datasets(datasets_dir: str, threshold: float = 0.35,
                       write_captions: bool = False, write_meta: bool = False):
    """Tag all images in dataset directories."""
    base = Path(datasets_dir)
    total = 0
    tagged = 0

    for char_dir in sorted(base.iterdir()):
        if not char_dir.is_dir():
            continue
        images_dir = char_dir / "images"
        if not images_dir.exists():
            continue

        print(f"\n  {char_dir.name}:")
        for png in sorted(images_dir.glob("*.png")):
            total += 1
            result = tag_image(str(png), threshold=threshold)

            if result.get("error"):
                print(f"    {png.name}: ERROR - {result['error']}")
                continue

            tagged += 1
            top_tags = [r["tag"] for r in result["tags"][:5]]
            print(f"    {png.name}: {', '.join(top_tags)} ({result['count']} total)")

            if write_captions:
                # Combine design_prompt with auto-tags for better captions
                meta_path = png.with_suffix(".meta.json")
                design_prompt = ""
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text())
                        design_prompt = meta.get("design_prompt", "")
                    except (json.JSONDecodeError, IOError):
                        pass

                # Write enhanced caption: design_prompt + top WD14 tags
                caption_parts = []
                if design_prompt:
                    caption_parts.append(design_prompt)
                caption_parts.append(result["tag_string"])
                png.with_suffix(".txt").write_text(", ".join(caption_parts))

            if write_meta:
                meta_path = png.with_suffix(".meta.json")
                meta = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text())
                    except (json.JSONDecodeError, IOError):
                        pass
                meta["wd14_tags"] = result["tags"][:30]  # top 30 tags
                meta["wd14_tag_string"] = result["tag_string"]
                meta_path.write_text(json.dumps(meta, indent=2))

    print(f"\nTagged {tagged}/{total} images")


if __name__ == "__main__":
    threshold = 0.35
    args = sys.argv[1:]

    # Parse --threshold
    for i, arg in enumerate(args):
        if arg == "--threshold" and i + 1 < len(args):
            threshold = float(args[i + 1])
            args = args[:i] + args[i+2:]
            break

    if not args:
        print("Usage: python3 wd14_tagger.py [--threshold 0.35] <image_path>")
        print("       python3 wd14_tagger.py --batch <datasets_dir> [--write-captions] [--write-meta]")
        sys.exit(1)

    if args[0] == "--batch":
        datasets_dir = args[1] if len(args) > 1 else str(Path(__file__).resolve().parent.parent / "datasets")
        write_captions = "--write-captions" in args
        write_meta = "--write-meta" in args
        batch_tag_datasets(datasets_dir, threshold, write_captions, write_meta)
    else:
        result = tag_image(args[0], threshold=threshold)
        print(json.dumps(result, indent=2))
