#!/usr/bin/env python3
"""Batch NSFW training image generation for Tokyo Debt Desire.

Generates 10 scene-based NSFW images per character using PonyXL V6,
with poses/actions derived from each character's defined scenes.

Usage:
    cd /opt/anime-studio
    source venv/bin/activate
    python scripts/batch_nsfw_tdd.py [--dry-run] [--character SLUG]
"""

import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.core.generation import generate_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("batch_nsfw_tdd")

# PonyXL quality prefix — MUST be included in prompt_override since
# translate_prompt() is skipped when prompt_override is used.
PONY_QUALITY = "score_9, score_8_up, score_7_up, source_anime, masterpiece, best quality"
PONY_NSFW_TAGS = "detailed skin, correct anatomy, detailed genitalia, detailed nipples, detailed facial expression"

# ──────────────────────────────────────────────────────────────────
# Character scene-based NSFW prompts — 10 per character
# Each combines: quality prefix + character identity + scene action + NSFW tags
# Format: PonyXL booru-style tags
# ──────────────────────────────────────────────────────────────────

CHAR_PROMPTS = {
    # ── Mei Kobayashi ──────────────────────────────────────────
    # Scenes: "Mei Private Session" (vulnerable intimate), "Mei Evening Bath" (peaceful sensual)
    "mei_kobayashi": [
        # Private Session scene
        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"sitting on bed edge, partially undressed, shy expression, soft warm lighting, "
        f"thin curtains, modest apartment bedroom, bare shoulders, blush, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair cascading on sheets, large breasts, curvy body, "
        f"lying back on bed, vulnerable yearning expression, partially nude, revealing lingerie, "
        f"warm lighting through curtains, intimate bedroom, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"standing in bedroom, removing clothing, gentle blush, shy expression, "
        f"soft lighting, bare skin, underwear, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"on bed wearing lace lingerie, shy pose, looking away with blush, "
        f"soft warm lighting, intimate atmosphere, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"kneeling on futon, hands clasped, looking up shyly, bare shoulders, "
        f"partially undressed, dim warm lighting, vulnerable, {PONY_NSFW_TAGS}, solo",

        # Evening Bath scene
        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair pinned up, large breasts, curvy body, "
        f"in traditional japanese bath, onsen, steam rising, eyes closed, relaxing, "
        f"wet skin, bare shoulders and neck, soft lighting, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"stepping into ofuro bath, nude back view, looking over shoulder, soft lighting, "
        f"steam, wet skin, traditional japanese bathroom, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair wet, large breasts, curvy body, "
        f"wrapped in towel, standing in front of foggy mirror, post-bath, "
        f"wet skin, steam, soft lighting, bare legs, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair wet and pinned up, large breasts, curvy body, "
        f"bathing in ofuro, side profile, steam rising around body, "
        f"serene expression, bare skin, water, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"close-up portrait, gentle yearning expression, bare skin, bare shoulders, "
        f"soft warm lighting, intimate, blush, {PONY_NSFW_TAGS}, solo",
    ],

    # ── Rina Suzuki ────────────────────────────────────────────
    # Scenes: "Rina Apartment Seduction" (seductive), "Rina Debt Collection Leverage" (dominant provocative), "Rent Due"
    "rina_suzuki": [
        # Apartment Seduction scene
        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"in upscale tokyo apartment, wearing lingerie, seductive pose on bed, "
        f"city lights through window, confident smirk, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"standing against window, city lights at night, revealing outfit, "
        f"confident aggressive pose, looking over shoulder, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"lying on bed, intimate close-up, smirk, lingerie, "
        f"upscale apartment bedroom, seductive expression, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"on bed, aggressive confident pose, hands behind head, lingerie, "
        f"city lights background, provocative, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"bending forward provocatively, revealing cleavage, seductive smile, "
        f"upscale apartment, city night skyline, {PONY_NSFW_TAGS}, solo",

        # Debt Collection Leverage scene
        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"in private room at high-end club, low cut top, short skirt, "
        f"standing assertively, dominant expression, dim lighting, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"leaning forward provocatively, low cut revealing top, dominant gaze, "
        f"high-end club room, dark moody lighting, power play, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"sitting with legs crossed confidently, provocative outfit, fishnet stockings, "
        f"smirk, club setting, dominant, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"standing over viewer, dominant stance, revealing outfit, "
        f"confident aggressive smirk, dim club lighting, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"close-up, biting lip, bedroom eyes, intimate framing, bare shoulders, "
        f"seductive expression, dark background, {PONY_NSFW_TAGS}, solo",
    ],

    # ── Takeshi Sato ───────────────────────────────────────────
    # Scene: "Takeshi Power Display" (threatening, powerful, menacing)
    "takeshi_sato": [
        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"in yakuza headquarters, shirt unbuttoned showing tattoos, "
        f"sitting in leather chair behind desk, menacing expression, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"standing menacingly by floor-to-ceiling windows, shirtless, "
        f"back tattoos visible, city lights, threatening presence, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"pouring expensive whiskey, muscular arms, open shirt, "
        f"yakuza headquarters, dim lighting, scar, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"shirtless from behind, elaborate back tattoo, irezumi, "
        f"muscular build, dramatic lighting, dark room, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"standing arms crossed, open shirt, chest tattoos visible, "
        f"menacing expression, dark business suit, yakuza, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"leaning on desk, shirt partially removed, scar visible, "
        f"dangerous expression, dimly lit room, whiskey glass, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"side profile, muscular silhouette against city window lights, "
        f"open shirt, contemplative threatening pose, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"full body standing, open dark suit, bare chest, yakuza tattoos, "
        f"intimidating stance, luxury office, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"sitting on leather sofa, legs spread confidently, open shirt, "
        f"cigar in hand, menacing gaze, dark atmosphere, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"close-up portrait, menacing expression, scar detail, "
        f"dark dramatic lighting, intense gaze, {PONY_NSFW_TAGS}, solo",
    ],

    # ── Yuki Tanaka ────────────────────────────────────────────
    # Scene: "Yuki Spiraling Desperation" (desperate, anxious, vulnerable)
    "yuki_tanaka": [
        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"sitting at cluttered desk, staring at debt notices, shirtless, "
        f"anxious expression, cramped apartment, dim lighting, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"lying on unmade futon, staring at ceiling, thin frame, "
        f"vulnerable expression, shirtless, messy room, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"standing in doorway, defeated expression, shirtless, "
        f"thin anxious frame, dim hallway lighting, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"sitting on floor, head in hands, scattered papers around, "
        f"partially undressed, desperate, dim apartment, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"leaning against wall, shirtless, looking down, "
        f"cramped apartment, dim lighting, vulnerable, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"on futon, tangled in blankets, sleepless, disheveled, "
        f"vulnerable expression, dark room, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"standing at window, looking out, silhouette, thin frame, "
        f"lonely atmosphere, night city lights, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"sitting hunched over, holding phone, worried expression, "
        f"dim apartment, debt notices on desk, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"lying on side, curled up on futon, vulnerable, "
        f"messy hair, anxious expression, dark room, {PONY_NSFW_TAGS}, solo",

        f"{PONY_QUALITY}, 1boy, young japanese man, average build, messy black hair, "
        f"close-up portrait, nervous worried expression, disheveled, "
        f"dark circles under eyes, dim lighting, {PONY_NSFW_TAGS}, solo",
    ],
}


async def run_batch(character_slug: str | None = None, dry_run: bool = False):
    """Generate NSFW training images for TDD characters."""
    slugs = [character_slug] if character_slug else list(CHAR_PROMPTS.keys())
    total = sum(len(CHAR_PROMPTS[s]) for s in slugs)
    completed = 0
    failed = 0

    logger.info(f"=== BATCH NSFW TDD GENERATION ===")
    logger.info(f"Characters: {', '.join(slugs)}")
    logger.info(f"Total images: {total}")
    logger.info(f"Checkpoint: ponyDiffusionV6XL.safetensors")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"================================")

    for slug in slugs:
        prompts = CHAR_PROMPTS[slug]
        logger.info(f"\n--- {slug}: {len(prompts)} images ---")

        for i, prompt in enumerate(prompts):
            logger.info(f"  [{slug}] Image {i+1}/{len(prompts)}")
            if dry_run:
                logger.info(f"  [DRY RUN] Prompt: {prompt[:120]}...")
                completed += 1
                continue

            try:
                results = await generate_batch(
                    character_slug=slug,
                    count=1,
                    prompt_override=prompt,
                    pose_variation=False,  # Pose is baked into prompt_override
                    include_feedback_negatives=True,
                    include_learned_negatives=True,
                    fire_events=True,
                    checkpoint_override="ponyDiffusionV6XL.safetensors",
                )

                for r in results:
                    if r["status"] == "completed":
                        completed += 1
                        logger.info(
                            f"  [{slug}] Image {i+1} DONE — "
                            f"seed={r['seed']}, images={r['images']}"
                        )
                    else:
                        failed += 1
                        logger.warning(
                            f"  [{slug}] Image {i+1} FAILED — status={r['status']}"
                        )

            except Exception as e:
                failed += 1
                logger.error(f"  [{slug}] Image {i+1} ERROR: {e}")

    logger.info(f"\n=== BATCH COMPLETE ===")
    logger.info(f"Completed: {completed}/{total}")
    logger.info(f"Failed: {failed}/{total}")
    logger.info(f"======================")


def main():
    parser = argparse.ArgumentParser(description="Batch NSFW TDD image generation")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without generating")
    parser.add_argument("--character", type=str, help="Generate for a single character slug")
    args = parser.parse_args()

    if args.character and args.character not in CHAR_PROMPTS:
        print(f"Unknown character: {args.character}")
        print(f"Available: {', '.join(CHAR_PROMPTS.keys())}")
        sys.exit(1)

    asyncio.run(run_batch(character_slug=args.character, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
