#!/usr/bin/env python3
"""Expression progression training images for Tokyo Debt Desire.

Generates 5 arousal/expression progression images per character,
capturing each character's UNIQUE emotional arc during intimate scenes.
These teach the LoRA how each character specifically expresses arousal/climax.

Usage:
    cd /opt/tower-anime-production
    source venv/bin/activate
    python3 scripts/batch_expression_progression.py [--dry-run] [--character SLUG]
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
logger = logging.getLogger("batch_expression")

PONY_Q = "score_9, score_8_up, score_7_up, source_anime, masterpiece, best quality"
NSFW = "detailed skin, correct anatomy, detailed genitalia, detailed nipples, detailed facial expression"

# ──────────────────────────────────────────────────────────────────
# Expression progression: 5 stages per character
# Stage 1: Initial state (character's baseline personality)
# Stage 2: Early arousal (blushing, breathing changes)
# Stage 3: Building intensity (losing composure)
# Stage 4: Climax (character-specific orgasm expression)
# Stage 5: Afterglow (post-orgasm, character-specific recovery)
# ──────────────────────────────────────────────────────────────────

CHAR_PROMPTS = {
    # ── Mei Kobayashi — shy, gentle, vulnerable ──
    # Her arc: timid nervousness → reluctant arousal → overwhelmed trembling → gentle crying orgasm → peaceful soft afterglow
    "mei_kobayashi": [
        # Stage 1: Shy baseline
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"sitting on bed, knees together, hands covering chest shyly, looking away with blush, "
        f"nervous expression, bare skin, underwear only, soft bedroom lighting, {NSFW}, solo",

        # Stage 2: Reluctant arousal
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair, large breasts, curvy body, "
        f"lying on bed, face flushed red, eyes half-closed, lips slightly parted, heavy breathing, "
        f"one hand gripping sheets, body trembling slightly, nude, sweat, blush, {NSFW}, solo",

        # Stage 3: Building intensity — losing her shyness
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair spread on pillow, large breasts, curvy body, "
        f"back arching off bed, head tilted back, mouth open panting, eyes squeezed shut, "
        f"hands gripping sheets tightly, body glistening with sweat, nude, intense blush, {NSFW}, solo",

        # Stage 4: Climax — Mei's signature: gentle tears, trembling, overwhelmed
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair disheveled, large breasts, curvy body, "
        f"orgasm, back fully arched, eyes squeezed shut with tears, mouth wide open crying out, "
        f"trembling body, hands clutching pillow, tears streaming, overwhelmed expression, nude, {NSFW}, solo",

        # Stage 5: Afterglow — peaceful, soft, vulnerable
        f"{PONY_Q}, 1girl, beautiful japanese woman, long dark hair messy on pillow, large breasts, curvy body, "
        f"lying still, eyes half-open dreamy expression, gentle satisfied smile, tear tracks on cheeks, "
        f"body relaxed, soft breathing, nude, warm soft lighting, peaceful, {NSFW}, solo",
    ],

    # ── Rina Suzuki — aggressive, dominant, confident ──
    # Her arc: predatory confidence → controlled arousal → aggressive intensity → triumphant climax → smug satisfaction
    "rina_suzuki": [
        # Stage 1: Predatory confidence
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"sitting confidently, legs apart, one hand on thigh, predatory smirk, "
        f"direct eye contact with viewer, lingerie, dominant pose, dim lighting, {NSFW}, solo",

        # Stage 2: Controlled arousal — she stays in control
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair, large breasts, curvy body, "
        f"leaning back, one eyebrow raised, knowing smirk, slight flush on cheeks, "
        f"tongue touching upper lip, confident even while aroused, nude, {NSFW}, solo",

        # Stage 3: Aggressive intensity — channeling arousal into dominance
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair disheveled, large breasts, curvy body, "
        f"riding position, aggressive expression, teeth bared in grin, heavy breathing, "
        f"sweat on skin, hands gripping hard, dominant aggressive pose, nude, intense, {NSFW}, solo",

        # Stage 4: Climax — Rina's signature: triumphant, back arched, aggressive moan
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair wild, large breasts, curvy body, "
        f"orgasm, head thrown back, triumphant expression, mouth open in aggressive moan, "
        f"back arched powerfully, muscles tensed, sweat, flushed skin, nude, {NSFW}, solo",

        # Stage 5: Afterglow — smug satisfaction, still in control
        f"{PONY_Q}, 1girl, attractive japanese woman, short brown hair messy, large breasts, curvy body, "
        f"lying back with smug satisfied smirk, one arm behind head, "
        f"relaxed confident pose, slightly flushed, knowing expression, nude, {NSFW}, solo",
    ],

    # ── Takeshi Sato — powerful, menacing, intense ──
    # His arc: dangerous composure → controlled tension → raw power → primal release → cold satisfaction
    "takeshi_sato": [
        # Stage 1: Dangerous composure
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"sitting in chair, shirt open showing chest tattoos, cold intense stare, "
        f"controlled dangerous energy, dimly lit room, scar, {NSFW}, solo",

        # Stage 2: Controlled tension
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, dark hair slightly loose, "
        f"jaw clenched, veins visible on neck and arms, intense focused gaze, "
        f"shirtless, tattoos visible, controlled breathing, sweat on brow, {NSFW}, solo",

        # Stage 3: Raw power unleashed
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, dark hair falling forward, "
        f"aggressive stance, muscles fully tensed, teeth bared, heavy breathing, "
        f"shirtless, tattoos glistening with sweat, raw intensity, {NSFW}, solo",

        # Stage 4: Primal release — Takeshi's signature: controlled even in climax, deep growl
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, dark hair disheveled, "
        f"orgasm, head tilted back slightly, jaw clenched tight, low growl expression, "
        f"muscles locked, veins prominent, shirtless, sweat, intense, {NSFW}, solo",

        # Stage 5: Cold satisfaction
        f"{PONY_Q}, 1boy, intimidating japanese man, muscular build, slicked back dark hair, "
        f"cold satisfied expression, barely any change from baseline, wiping sweat, "
        f"shirtless, tattoos visible, composed dangerous, slight smirk, {NSFW}, solo",
    ],

    # ── Yuki Tanaka — desperate, anxious, vulnerable ──
    # His arc: nervous anxiety → overwhelmed sensation → desperate clinging → release with relief → exhausted guilt
    "yuki_tanaka": [
        # Stage 1: Nervous anxiety
        f"{PONY_Q}, 1boy, young japanese man, average build, messy black hair, "
        f"sitting on edge of bed, hunched shoulders, nervous fidgeting, "
        f"worried expression, shirtless showing thin frame, dim lighting, {NSFW}, solo",

        # Stage 2: Overwhelmed by sensation
        f"{PONY_Q}, 1boy, young japanese man, average build, messy black hair, "
        f"eyes wide, mouth slightly open in surprise, face flushed bright red, "
        f"overwhelmed expression, gripping sheets, shirtless, nervous sweat, {NSFW}, solo",

        # Stage 3: Desperate clinging
        f"{PONY_Q}, 1boy, young japanese man, average build, messy black hair falling over eyes, "
        f"desperate expression, eyes squeezed shut, biting lip hard, "
        f"body trembling, hands clutching at anything, nude, sweat, tense, {NSFW}, solo",

        # Stage 4: Release with relief — Yuki's signature: relief mixed with pleasure, almost crying
        f"{PONY_Q}, 1boy, young japanese man, average build, messy black hair disheveled, "
        f"orgasm, face contorted in relief and pleasure, eyes watering, mouth open gasping, "
        f"body shaking, thin frame trembling, tears of relief, nude, {NSFW}, solo",

        # Stage 5: Exhausted guilt
        f"{PONY_Q}, 1boy, young japanese man, average build, messy black hair, "
        f"lying still, staring at ceiling, mixed guilt and relief expression, "
        f"exhausted, one arm over forehead, thin body, nude, dim lonely lighting, {NSFW}, solo",
    ],
}


async def run_batch(character_slug: str | None = None, dry_run: bool = False):
    slugs = [character_slug] if character_slug else list(CHAR_PROMPTS.keys())
    total = sum(len(CHAR_PROMPTS[s]) for s in slugs)
    completed = 0
    failed = 0

    logger.info(f"=== EXPRESSION PROGRESSION BATCH ===")
    logger.info(f"Characters: {', '.join(slugs)}")
    logger.info(f"Total images: {total} (5 stages × {len(slugs)} chars)")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"====================================")

    for slug in slugs:
        prompts = CHAR_PROMPTS[slug]
        stages = ["baseline", "early_arousal", "building", "climax", "afterglow"]
        logger.info(f"\n--- {slug}: expression progression ---")

        for i, (prompt, stage) in enumerate(zip(prompts, stages)):
            logger.info(f"  [{slug}] Stage {i+1}/5: {stage}")
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
                        logger.info(f"  [{slug}] {stage} DONE — seed={r['seed']}")
                    else:
                        failed += 1
                        logger.warning(f"  [{slug}] {stage} FAILED — {r['status']}")
            except Exception as e:
                failed += 1
                logger.error(f"  [{slug}] {stage} ERROR: {e}")

    logger.info(f"\n=== EXPRESSION BATCH COMPLETE ===")
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
