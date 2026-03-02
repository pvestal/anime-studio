"""Echo Brain integration — chat, prompt enhancement, narration assist."""

import json
import logging
import time as _time
import urllib.request as _ur

from fastapi import APIRouter, HTTPException

from packages.core.db import get_char_project_map
from packages.core.models import EchoChatRequest, EchoEnhanceRequest, NarrateRequest

logger = logging.getLogger(__name__)
router = APIRouter()

ECHO_BRAIN_URL = "http://localhost:8309"


@router.get("/echo/status")
async def echo_status():
    """Check Echo Brain availability."""
    try:
        req = _ur.Request(f"{ECHO_BRAIN_URL}/health")
        resp = _ur.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return {"status": "connected", "echo_brain": data}
    except Exception as e:
        return {"status": "offline", "error": str(e)}


@router.post("/echo/chat")
async def echo_chat(body: EchoChatRequest):
    """Send a message to Echo Brain and get a response."""
    context = ""
    if body.character_slug:
        char_map = await get_char_project_map()
        db_info = char_map.get(body.character_slug, {})
        if db_info:
            context = (
                f"Character: {db_info.get('name', body.character_slug)}, "
                f"Project: {db_info.get('project_name', '')}, "
                f"Design: {db_info.get('design_prompt', '')}"
            )

    try:
        search_payload = json.dumps({
            "method": "tools/call",
            "params": {
                "name": "search_memory",
                "arguments": {"query": body.message, "limit": 5},
            }
        }).encode()
        req = _ur.Request(
            f"{ECHO_BRAIN_URL}/mcp",
            data=search_payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _ur.urlopen(req, timeout=15)
        echo_result = json.loads(resp.read())

        response_text = ""
        if "result" in echo_result and "content" in echo_result["result"]:
            for item in echo_result["result"]["content"]:
                if item.get("type") == "text":
                    response_text += item["text"] + "\n"

        return {
            "response": response_text.strip() or "No relevant memories found.",
            "context_used": bool(context),
            "character_context": context if context else None,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Echo Brain unavailable: {e}")


@router.post("/echo/enhance-prompt")
async def echo_enhance_prompt(body: EchoEnhanceRequest):
    """Ask Echo Brain to suggest improvements to a design prompt."""
    char_context = ""
    if body.character_slug:
        char_map = await get_char_project_map()
        db_info = char_map.get(body.character_slug, {})
        if db_info:
            char_context = (
                f" for {db_info.get('name', body.character_slug)} "
                f"from {db_info.get('project_name', '')}"
            )

    try:
        query = f"Improve this anime character design prompt{char_context}: {body.prompt}"
        search_payload = json.dumps({
            "method": "tools/call",
            "params": {
                "name": "search_memory",
                "arguments": {"query": query, "limit": 5},
            }
        }).encode()
        req = _ur.Request(
            f"{ECHO_BRAIN_URL}/mcp",
            data=search_payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _ur.urlopen(req, timeout=15)
        echo_result = json.loads(resp.read())

        memories = []
        if "result" in echo_result and "content" in echo_result["result"]:
            for item in echo_result["result"]["content"]:
                if item.get("type") == "text":
                    memories.append(item["text"])

        return {
            "original_prompt": body.prompt,
            "echo_brain_context": memories,
            "suggestion": f"Based on Echo Brain memories, consider refining: {body.prompt}",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Echo Brain unavailable: {e}")


def _clean_llm_response(text: str, context_type: str) -> str:
    """Strip markdown code blocks, preambles, and explanatory text from LLM output.
    Return just the usable content."""
    import re

    # Strip markdown code blocks (```python ... ``` or ``` ... ```)
    text = re.sub(r'```\w*\n?', '', text)

    # Strip leading preamble lines like "Based on your query..." or "Here is..."
    lines = text.strip().split('\n')
    cleaned_lines = []
    skip_preamble = True
    for line in lines:
        stripped = line.strip()
        if skip_preamble:
            # Skip empty lines and preamble sentences
            if not stripped:
                continue
            lower = stripped.lower()
            if any(lower.startswith(p) for p in [
                'based on', 'here is', 'here\'s', 'this prompt',
                'the generated', 'this includes', 'prompt text:',
                'the prompt', 'i suggest', 'i recommend',
                'sure,', 'certainly,', 'of course,',
                'to improve', 'to create', 'let me', 'i\'ll',
                'we can', 'below is', 'the following',
            ]):
                continue
            skip_preamble = False
        cleaned_lines.append(stripped)

    text = '\n'.join(cleaned_lines).strip()

    # Strip trailing explanatory sentences (after the actual content)
    # For prompt types, remove trailing sentences that explain what the prompt does
    if context_type in ('prompt_override', 'design_prompt', 'positive_template', 'negative_template', 'scene_location', 'scene_mood', 'motion_prompt'):
        # Remove trailing lines that are explanations
        result_lines = text.split('\n')
        while result_lines:
            last = result_lines[-1].strip().lower()
            if any(last.startswith(p) for p in [
                'this prompt', 'the generated', 'this includes',
                'this should', 'note:', 'remember',
            ]) or not last:
                result_lines.pop()
            else:
                break
        text = '\n'.join(result_lines).strip()

    # For design_prompt: aggressive cleanup — strip markdown headers, multi-paragraph essays,
    # and reduce to a single line of comma-separated tags
    if context_type == 'design_prompt':
        # Remove markdown headers (### ..., ** ... **)
        text = re.sub(r'^#{1,4}\s+.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*\*[^*]+\*\*', '', text)
        text = re.sub(r'---+', '', text)
        # Remove lines that are clearly not SD tags (sentences with periods, narrative text)
        tag_lines = []
        for line in text.split('\n'):
            line = line.strip().rstrip('.')
            if not line:
                continue
            # Skip lines that look like prose sentences (long, with multiple periods or starting with articles)
            lower = line.lower()
            if any(lower.startswith(p) for p in [
                'to improve', 'to create', 'the world', 'the series',
                'roxy is', 'she is', 'he is', 'they are', 'this character',
                'this prompt', 'this design', 'by incorporating',
                'her past', 'his past', 'despite',
            ]):
                continue
            # Keep lines that look like comma-separated tags
            tag_lines.append(line)
        if tag_lines:
            # Join all remaining content into one line, collapse whitespace
            text = ', '.join(t.strip().rstrip(',') for t in tag_lines if t.strip())
            text = re.sub(r',\s*,', ',', text)  # remove empty commas
            text = re.sub(r'\s+', ' ', text).strip()

    # Strip surrounding quotes if the entire text is quoted
    if len(text) > 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()

    return text


def _build_narrate_prompt(body: NarrateRequest) -> str:
    """Build a targeted prompt for Echo Brain LLM synthesis based on context_type."""
    ct = body.context_type
    cv = body.current_value or ""

    if ct == "storyline":
        parts = [f"Project: '{body.project_name or 'unnamed'}'"]
        if body.project_genre:
            parts.append(f"Genre: {body.project_genre}")
        if body.project_premise:
            parts.append(f"Premise: {body.project_premise}")
        elif body.project_description:
            parts.append(f"Description: {body.project_description}")
        if body.storyline_theme:
            parts.append(f"Theme: {body.storyline_theme}")
        if body.storyline_title:
            parts.append(f"Title: {body.storyline_title}")
        context = ". ".join(parts)
        prompt = (
            f"{context}.\n\n"
            f"Based on the premise above, return a JSON object with these fields:\n"
            f"- \"summary\": 2-3 paragraph storyline summary capturing central conflict, key characters, narrative arc\n"
            f"- \"theme\": one-line theme (e.g. \"redemption through sacrifice\")\n"
            f"- \"tone\": 1-3 words for tone (e.g. \"dark, gritty\")\n"
            f"- \"target_audience\": target audience (e.g. \"young adults\")\n"
            f"- \"story_arcs\": array of {{\"arc_name\": \"...\", \"description\": \"...\"}} objects (2-4 arcs)\n\n"
            f"Be specific to this project — do not write generic filler. Return ONLY valid JSON, no extra text."
        )
        if cv:
            prompt += f"\n\nCurrent summary to improve: '{cv}'"
        return prompt
    elif ct == "description":
        parts = [f"Project: '{body.project_name or 'unnamed'}'"]
        if body.project_genre:
            parts.append(f"Genre: {body.project_genre}")
        if body.project_premise:
            parts.append(f"Premise: {body.project_premise}")
        context = ". ".join(parts)
        prompt = (
            f"{context}.\n\n"
            f"Suggest an improved 1-2 sentence project description that captures the essence of this project."
        )
        if cv:
            prompt += f"\n\nCurrent: '{cv}'"
        return prompt
    elif ct == "positive_template":
        parts = [f"Suggest positive quality tags for Stable Diffusion using {body.checkpoint_model or 'unknown model'}"]
        parts.append(f"Project: '{body.project_name or 'unnamed'}' ({body.project_genre or 'unspecified genre'})")
        if body.project_premise:
            parts.append(f"Premise: {body.project_premise}")
        prompt = ". ".join(parts) + "."
        if cv:
            prompt += f" Current: '{cv}'."
        prompt += " Return ONLY comma-separated tags, no character descriptions."
        return prompt
    elif ct == "negative_template":
        return (
            f"Suggest negative quality tags for Stable Diffusion using {body.checkpoint_model or 'unknown model'}."
            + (f" Current: '{cv}'" if cv else "")
            + " Return ONLY comma-separated tags."
        )
    elif ct == "design_prompt":
        parts = [
            f"Write a Stable Diffusion prompt for the character '{body.character_name or 'unnamed'}'",
            f"from the anime project '{body.project_name or 'unnamed'}' ({body.project_genre or 'unspecified genre'})",
        ]
        if body.checkpoint_model:
            parts.append(f"Model: {body.checkpoint_model}")
        if body.project_premise:
            parts.append(f"Project premise: {body.project_premise}")
        prompt = ". ".join(parts) + "."
        if cv:
            prompt += f" Current prompt: '{cv}'."
        prompt += (
            "\n\nRETURN ONLY a single line of comma-separated visual tags suitable for Stable Diffusion. "
            "Include: gender, hair color/style, eye color, body type, clothing, accessories, pose, expression. "
            "Do NOT include markdown, headers, explanations, personality, world-building, or backstory. "
            "Example format: 1girl, short pink hair, green eyes, black leather jacket, white crop top, "
            "black pants, knee-high boots, fierce expression, full body"
        )
        return prompt
    elif ct == "prompt_override":
        return (
            f"Create a generation prompt for '{body.character_name or 'unnamed'}' "
            f"from '{body.project_name or 'unnamed'}'. "
            f"Base design: '{body.design_prompt or 'none'}'. "
            f"Style template: '{body.positive_prompt_template or 'none'}'. "
            "Return ONLY the prompt text."
        )
    elif ct == "concept":
        return (
            f"Create an anime project from this concept: '{body.concept_description or 'no concept'}'. "
            "Return JSON with: name, genre, description, storyline_summary, theme, "
            "target_audience, recommended_steps (int), recommended_cfg (float)."
        )
    elif ct == "scene_location":
        return (
            f"Suggest a specific scene location for '{body.project_name or 'unnamed'}' ({body.project_genre or 'unspecified genre'}). "
            f"Storyline: {body.storyline_summary or 'none'}. "
            f"Scene description: {body.scene_description or 'none'}. "
            + (f"Current: '{cv}'. " if cv else "")
            + "Return ONLY a brief location name/description (e.g. 'abandoned rooftop overlooking neon district')."
        )
    elif ct == "scene_mood":
        return (
            f"Suggest a mood/atmosphere for a scene in '{body.project_name or 'unnamed'}' ({body.project_genre or 'unspecified genre'}). "
            f"Storyline tone: {body.storyline_theme or 'unspecified'}. "
            f"Scene description: {body.scene_description or 'none'}. "
            + (f"Current: '{cv}'. " if cv else "")
            + "Return ONLY 1-3 mood words (e.g. 'tense, foreboding')."
        )
    elif ct == "production_notes":
        parts = [f"Project: '{body.project_name or 'unnamed'}' ({body.project_genre or 'unspecified genre'})"]
        if body.project_premise:
            parts.append(f"Premise: {body.project_premise}")
        if body.storyline_summary:
            parts.append(f"Storyline: {body.storyline_summary}")
        if body.checkpoint_model:
            parts.append(f"Checkpoint: {body.checkpoint_model}")
        context = ". ".join(parts)
        prompt = (
            f"{context}.\n\n"
            f"Write concise production notes covering art direction, animation considerations, "
            f"and technical guidance for this project. Be specific to this project's style and content."
        )
        if cv:
            prompt += f"\n\nCurrent notes: '{cv}'"
        return prompt
    elif ct == "motion_prompt":
        return (
            f"Suggest a motion/animation prompt for a {body.shot_type or 'medium'} shot in '{body.project_name or 'unnamed'}'. "
            f"Scene: {body.scene_description or 'no description'}. "
            + (f"Current: '{cv}'. " if cv else "")
            + "Return ONLY a brief motion description for video generation (e.g. 'character slowly turns head, hair billowing in wind')."
        )
    elif ct == "character_profile":
        parts = [f"Character: '{body.character_name or 'unnamed'}'"]
        parts.append(f"Project: '{body.project_name or 'unnamed'}' ({body.project_genre or 'unspecified genre'})")
        if body.project_premise:
            parts.append(f"Premise: {body.project_premise}")
        if body.design_prompt:
            parts.append(f"Current design prompt: {body.design_prompt}")
        context = ". ".join(parts)
        return (
            f"{context}.\n\n"
            "Generate a comprehensive character bible as a JSON object with ALL of these fields:\n"
            '- "description": 2-3 sentence character summary\n'
            '- "personality": personality description in 2-3 sentences\n'
            '- "background": backstory in 2-3 sentences\n'
            '- "age": integer age\n'
            '- "character_role": one of protagonist/antagonist/supporting/mentor/comic_relief\n'
            '- "personality_tags": array of 3-6 personality trait words\n'
            '- "design_prompt": visual-only Stable Diffusion prompt with appearance tags (NO narrative text)\n'
            '- "species": what type of creature/being\n'
            '- "body_type": physical build description\n'
            '- "key_colors": object mapping body parts to colors (e.g. {"hair": "red", "eyes": "green"})\n'
            '- "key_features": array of 4-6 critical identifying visual features\n'
            '- "common_errors": array of known generation failure modes\n'
            '- "hair": {"color": "...", "style": "...", "length": "..."}\n'
            '- "eyes": {"color": "...", "shape": "...", "special": "..."}\n'
            '- "skin": {"tone": "...", "markings": "..."}\n'
            '- "face": {"shape": "...", "features": "..."}\n'
            '- "body": {"build": "...", "height": "...", "bust": "...", "waist": "...", "hips": "..."}\n'
            '- "clothing": {"default_outfit": "...", "style": "..."}\n'
            '- "weapons": array of {"name": "...", "type": "...", "description": "..."}\n'
            '- "accessories": array of accessory strings\n'
            '- "sexual": {"orientation": "...", "preferences": "...", "physical_traits": "..."}\n\n'
            "Be specific to this character and project. The design_prompt must be VISUAL ONLY — "
            "suitable for Stable Diffusion image generation. Do NOT put narrative backstory in design_prompt.\n"
            "Return ONLY valid JSON, no extra text."
        )
    else:
        return f"Provide a suggestion for: {cv or body.project_name or 'general content'}"


@router.post("/echo/narrate")
async def echo_narrate(body: NarrateRequest):
    """Use Echo Brain's LLM synthesis to generate contextual suggestions."""
    start = _time.time()
    prompt = _build_narrate_prompt(body)

    try:
        payload = json.dumps({"question": prompt}).encode()
        req = _ur.Request(
            f"{ECHO_BRAIN_URL}/api/echo/ask",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _ur.urlopen(req, timeout=60)
        data = json.loads(resp.read())

        raw_suggestion = data.get("answer", data.get("response", ""))
        suggestion = _clean_llm_response(raw_suggestion, body.context_type)
        sources = data.get("sources", [])
        confidence = data.get("confidence", 0.0)

        # Try to parse structured fields from JSON responses (e.g. storyline)
        fields = None
        if body.context_type in ("storyline", "concept", "character_profile"):
            try:
                # Strip markdown code fences if present
                cleaned = suggestion.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[-1]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    fields = parsed
                    # Use summary as the display suggestion if available
                    if "summary" in parsed:
                        suggestion = parsed["summary"]
            except (json.JSONDecodeError, ValueError):
                pass  # Not JSON — return raw text as suggestion

        elapsed_ms = int((_time.time() - start) * 1000)
        result = {
            "suggestion": suggestion,
            "confidence": confidence,
            "sources": sources,
            "execution_time_ms": elapsed_ms,
            "context_type": body.context_type,
        }
        if fields:
            result["fields"] = fields
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Echo Brain narration unavailable: {e}")
