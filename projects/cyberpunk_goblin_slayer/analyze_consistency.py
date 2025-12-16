#!/usr/bin/env python3
"""Analyze Ghost Ryker character consistency across all references"""

import os
import sys
import json
import torch
import clip
from PIL import Image
import numpy as np
from pathlib import Path

def calculate_clip_similarity(img1_path, img2_path, model, preprocess, device):
    """Calculate CLIP similarity between two images"""
    try:
        image1 = preprocess(Image.open(img1_path)).unsqueeze(0).to(device)
        image2 = preprocess(Image.open(img2_path)).unsqueeze(0).to(device)

        with torch.no_grad():
            features1 = model.encode_image(image1)
            features2 = model.encode_image(image2)

            # Normalize features
            features1 = features1 / features1.norm(dim=-1, keepdim=True)
            features2 = features2 / features2.norm(dim=-1, keepdim=True)

            # Calculate cosine similarity
            similarity = torch.cosine_similarity(features1, features2).item()

        return similarity
    except Exception as e:
        print(f"Error comparing {img1_path} and {img2_path}: {e}")
        return 0.0

def analyze_ghost_ryker():
    """Analyze Ghost Ryker character consistency"""

    # Load CLIP model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, preprocess = clip.load("ViT-B/32", device=device)

    # Get all reference images
    assets_dir = Path("/opt/tower-anime-production/projects/cyberpunk_goblin_slayer/assets/characters")

    casual_refs = sorted(assets_dir.glob("ghost_ryker_casual_ref_*.png"))
    action_refs = sorted(assets_dir.glob("ghost_ryker_action_ref_*.png"))
    portrait_refs = sorted(assets_dir.glob("ghost_ryker_portrait_ref_*.png"))

    all_refs = casual_refs + action_refs + portrait_refs

    print("=== GHOST RYKER CONSISTENCY ANALYSIS ===")
    print(f"Total references: {len(all_refs)}")
    print(f"  Casual: {len(casual_refs)}")
    print(f"  Action: {len(action_refs)}")
    print(f"  Portrait: {len(portrait_refs)}")

    # Calculate all pairwise similarities
    similarities = []
    category_similarities = {
        "casual-casual": [],
        "action-action": [],
        "portrait-portrait": [],
        "casual-action": [],
        "casual-portrait": [],
        "action-portrait": []
    }

    for i, img1 in enumerate(all_refs):
        for j, img2 in enumerate(all_refs):
            if i < j:  # Only calculate upper triangle
                similarity = calculate_clip_similarity(img1, img2, model, preprocess, device)
                similarities.append(similarity)

                # Categorize the comparison
                cat1 = "casual" if "casual" in str(img1) else ("action" if "action" in str(img1) else "portrait")
                cat2 = "casual" if "casual" in str(img2) else ("action" if "action" in str(img2) else "portrait")

                if cat1 == cat2:
                    category_similarities[f"{cat1}-{cat1}"].append(similarity)
                else:
                    # Sort categories alphabetically for consistent key
                    cats = sorted([cat1, cat2])
                    key = f"{cats[0]}-{cats[1]}"
                    if key not in category_similarities:
                        category_similarities[key] = []
                    category_similarities[key].append(similarity)

    # Calculate statistics
    avg_similarity = np.mean(similarities)
    min_similarity = np.min(similarities)
    max_similarity = np.max(similarities)
    std_similarity = np.std(similarities)

    print(f"\n=== OVERALL METRICS ===")
    print(f"Average Similarity: {avg_similarity:.2%}")
    print(f"Min Similarity: {min_similarity:.2%}")
    print(f"Max Similarity: {max_similarity:.2%}")
    print(f"Std Deviation: {std_similarity:.2%}")

    # Check against thresholds
    hero_threshold = 0.75
    print(f"\n=== QUALITY GATE CHECK ===")
    print(f"Hero Character Threshold: {hero_threshold:.0%}")
    print(f"Status: {'✅ PASSED' if avg_similarity >= hero_threshold else '❌ FAILED'}")

    print(f"\n=== POSE CATEGORY ANALYSIS ===")
    for category, scores in category_similarities.items():
        if scores:
            avg = np.mean(scores)
            print(f"{category}: {avg:.2%} (n={len(scores)})")

    # Identify outliers
    print(f"\n=== OUTLIER ANALYSIS ===")
    threshold_low = avg_similarity - 2 * std_similarity
    outliers = [s for s in similarities if s < threshold_low]
    if outliers:
        print(f"Found {len(outliers)} outlier pairs below {threshold_low:.2%}")
    else:
        print("No significant outliers detected")

    # Save results
    results = {
        "character": "ghost_ryker",
        "total_references": len(all_refs),
        "average_similarity": float(avg_similarity),
        "min_similarity": float(min_similarity),
        "max_similarity": float(max_similarity),
        "std_deviation": float(std_similarity),
        "hero_threshold": hero_threshold,
        "passed": avg_similarity >= hero_threshold,
        "category_analysis": {k: float(np.mean(v)) if v else 0 for k, v in category_similarities.items()},
        "pose_counts": {
            "casual": len(casual_refs),
            "action": len(action_refs),
            "portrait": len(portrait_refs)
        }
    }

    with open(assets_dir / "consistency_analysis.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Analysis saved to consistency_analysis.json")

    return results

if __name__ == "__main__":
    analyze_ghost_ryker()