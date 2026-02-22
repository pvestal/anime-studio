#!/usr/bin/env python3
"""Identity anchor training images for Tokyo Debt Desire.

Generates 5 clean neutral identity shots per character from multiple angles.
These lock in the LoRA's understanding of each character's core appearance
without distracting poses or expressions. Essential foundation images.

Usage:
    cd /opt/tower-anime-production
    source venv/bin/activate
    python3 scripts/batch_identity_anchors.py [--dry-run] [--character SLUG]
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from packages.core.generation import generate_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("batch_identity")

PONY_Q = "score_9, score_8_up, score_7_up, source_anime, masterpiece, best quality"
DETAIL = "detailed skin, detailed eyes, detailed hair, correct anatomy, detailed facial expression"

# ──────────────────────────────────────────────────────────────────
# Identity anchors: 5 clean shots per character
# These are the FOUNDATION — clear views of the character's defining features
# Shot 1: Front portrait (face + hair detail)
# Shot 2: Three-quarter view (face shape + body proportions)
# Shot 3: Side profile (nose, chin, hair silhouette)
# Shot 4: Full body front (proportions, build, outfit/skin)
# Shot 5: Full body back (hair length, back features, build from behind)
# ──────────────────────────────────────────────────────────────────

CHAR_PROMPTS = {
    "mei_kobayashi": [
        # Front portrait — face focus
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"front view portrait, close-up face and shoulders, neutral gentle expression, "
        f"clear lighting, {DETAIL}, simple background, solo",

        # Three-quarter view
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"three-quarter view, upper body, gentle shy expression, natural pose, "
        f"revealing clothing, bare shoulders, clear studio lighting, {DETAIL}, simple background, solo",

        # Side profile
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"side profile view, showing nose chin jawline, hair flowing down, "
        f"neutral expression, bare skin, clear lighting, {DETAIL}, simple background, solo",

        # Full body front
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair past shoulders, large breasts, curvy body, "
        f"full body shot, front view, standing relaxed, hands at sides, "
        f"nude, showing full proportions, clear even lighting, {DETAIL}, simple background, solo",

        # Full body back
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair down back, large breasts, curvy body, "
        f"full body shot, back view, looking slightly over shoulder, "
        f"nude, showing back and hair length, clear lighting, {DETAIL}, simple background, solo",
    ],

    "rina_suzuki": [
        # Front portrait
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"front view portrait, close-up face and shoulders, confident smirk, "
        f"clear lighting, {DETAIL}, simple background, solo",

        # Three-quarter view
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"three-quarter view, upper body, confident aggressive expression, "
        f"revealing outfit, clear studio lighting, {DETAIL}, simple background, solo",

        # Side profile
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"side profile view, showing facial structure, sharp confident expression, "
        f"bare skin, clear lighting, {DETAIL}, simple background, solo",

        # Full body front
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"full body shot, front view, standing confidently, hands on hips, "
        f"nude, showing full proportions, clear even lighting, {DETAIL}, simple background, solo",

        # Full body back
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"full body shot, back view, looking over shoulder with smirk, "
        f"nude, showing back, clear lighting, {DETAIL}, simple background, solo",
    ],

    "takeshi_sato": [
        # Front portrait
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, scar, "
        f"front view portrait, close-up face and shoulders, menacing expression, "
        f"clear lighting, {DETAIL}, simple background, solo",

        # Three-quarter view
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, scar, "
        f"three-quarter view, upper body, open shirt showing chest tattoos, "
        f"menacing expression, clear studio lighting, {DETAIL}, simple background, solo",

        # Side profile
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, scar, "
        f"side profile view, showing jawline and scar detail, "
        f"neutral expression, clear lighting, {DETAIL}, simple background, solo",

        # Full body front
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, scar, "
        f"full body shot, front view, standing arms at sides, shirtless, "
        f"yakuza tattoos visible on chest and arms, clear even lighting, {DETAIL}, simple background, solo",

        # Full body back — essential for back tattoo
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"full body shot, back view, shirtless, elaborate back tattoo irezumi, "
        f"muscular back, clear lighting, {DETAIL}, simple background, solo",
    ],

    "yuki_tanaka": [
        # Front portrait
        f"{PONY_Q}, 1boy, young japanese man, average build, messy black hair, "
        f"front view portrait, close-up face and shoulders, nervous expression, "
        f"clear lighting, {DETAIL}, simple background, solo",

        # Three-quarter view
        f"{PONY_Q}, 1boy, young japanese man, average build, messy black hair, "
        f"three-quarter view, upper body, worried expression, casual shirt, "
        f"thin frame visible, clear studio lighting, {DETAIL}, simple background, solo",

        # Side profile
        f"{PONY_Q}, 1boy, young japanese man, average build, messy black hair, "
        f"side profile view, showing facial structure, hair falling over eye, "
        f"neutral expression, clear lighting, {DETAIL}, simple background, solo",

        # Full body front
        f"{PONY_Q}, 1boy, young japanese man, average thin build, messy black hair, "
        f"full body shot, front view, standing slightly hunched, shirtless, "
        f"showing thin anxious frame, clear even lighting, {DETAIL}, simple background, solo",

        # Full body back
        f"{PONY_Q}, 1boy, young japanese man, average thin build, messy black hair, "
        f"full body shot, back view, slightly slouched posture, shirtless, "
        f"showing thin frame from behind, clear lighting, {DETAIL}, simple background, solo",
    ],
}


async def run_batch(character_slug: str | None = None, dry_run: bool = False):
    slugs = [character_slug] if character_slug else list(CHAR_PROMPTS.keys())
    total = sum(len(CHAR_PROMPTS[s]) for s in slugs)
    completed = 0
    failed = 0

    logger.info(f"=== IDENTITY ANCHOR BATCH ===")
    logger.info(f"Characters: {', '.join(slugs)}")
    logger.info(f"Total images: {total} (5 angles × {len(slugs)} chars)")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"=============================")

    for slug in slugs:
        prompts = CHAR_PROMPTS[slug]
        angles = ["front_portrait", "three_quarter", "side_profile", "full_body_front", "full_body_back"]
        logger.info(f"\n--- {slug}: identity anchors ---")

        for i, (prompt, angle) in enumerate(zip(prompts, angles)):
            logger.info(f"  [{slug}] Angle {i+1}/5: {angle}")
            if dry_run:
                logger.info(f"  [DRY RUN] {prompt[:100]}...")
                completed += 1
                continue

            try:
                results = await generate_batch(
                    character_slug=slug,
                    count=1,
                    prompt_override=prompt,
                    pose_variation=False,
                    include_feedback_negatives=True,
                    include_learned_negatives=True,
                    fire_events=True,
                    checkpoint_override="ponyDiffusionV6XL.safetensors",
                )
                for r in results:
                    if r["status"] == "completed":
                        completed += 1
                        logger.info(f"  [{slug}] {angle} DONE — seed={r['seed']}")
                    else:
                        failed += 1
                        logger.warning(f"  [{slug}] {angle} FAILED — {r['status']}")
            except Exception as e:
                failed += 1
                logger.error(f"  [{slug}] {angle} ERROR: {e}")

    logger.info(f"\n=== IDENTITY BATCH COMPLETE ===")
    logger.info(f"Completed: {completed}/{total}, Failed: {failed}/{total}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--character", type=str)
    args = parser.parse_args()
    if args.character and args.character not in CHAR_PROMPTS:
        print(f"Unknown: {args.character}. Available: {', '.join(CHAR_PROMPTS.keys())}")
        sys.exit(1)
    asyncio.run(run_batch(character_slug=args.character, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
