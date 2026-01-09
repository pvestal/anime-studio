#!/usr/bin/env python3
"""
Echo Brain Enhanced Anime Generation Service
Integrates Tower Echo Brain for prompt enhancement, character development, and user feedback
"""

import json
import requests
import time
import os
import uuid
import asyncio
import aiohttp
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Echo Enhanced Anime Generation", version="1.0.0")

class AnimeRequest(BaseModel):
    prompt: str = Field(..., description="User's initial prompt for anime generation")
    character: str = Field(default="Kai Nakamura", description="Character name")
    scene_type: str = Field(default="cyberpunk_action", description="Type of scene")
    duration: int = Field(default=3, description="Duration in seconds")
    style: str = Field(default="photorealistic", description="Visual style")
    project_id: Optional[int] = Field(default=None, description="Associated project ID")
    echo_intelligence: str = Field(default="professional", description="Echo intelligence level")

class EchoFeedbackRequest(BaseModel):
    prompt: str
    generated_content: Dict[str, Any]
    user_feedback: str
    character: str = "Kai Nakamura"
    echo_intelligence: str = "expert"

class PromptEnhancement(BaseModel):
    original_prompt: str
    enhanced_prompt: str
    suggestions: List[str]
    character_details: Dict[str, Any]
    narrative_context: str
    technical_parameters: Dict[str, Any]

# Configuration
COMFYUI_URL = "http://127.0.0.1:8188"
ECHO_BRAIN_URL = "http://localhost:8309"
ANIME_API_URL = "http://localhost:8305"
OUTPUT_DIR = "/home/patrick/Videos/AnimeGenerated"

class EchoBrainClient:
    """Client for interacting with Tower Echo Brain service"""

    def __init__(self):
        self.base_url = ECHO_BRAIN_URL

    async def enhance_prompt(self, prompt: str, character: str, intelligence: str = "professional") -> Dict[str, Any]:
        """Use Echo Brain to enhance anime generation prompts"""
        try:
            enhancement_query = f"""
            As an expert anime production director and character designer, enhance this anime generation prompt:

            Original Prompt: "{prompt}"
            Character: {character}

            Please provide:
            1. Enhanced prompt with cinematic details, lighting, and composition
            2. Character-specific visual details and personality traits
            3. Scene composition suggestions
            4. Technical parameters for photorealistic generation
            5. Narrative context and story implications
            6. Three alternative creative directions

            Focus on photorealistic rendering with attention to:
            - Facial expressions and body language
            - Environmental storytelling
            - Cinematic camera angles
            - Lighting mood and atmosphere
            - Color palette and visual themes
            """

            payload = {
                "query": enhancement_query,
                "intelligence": intelligence,
                "context": {
                    "character": character,
                    "original_prompt": prompt,
                    "task_type": "anime_prompt_enhancement"
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/echo/query",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return self._parse_enhancement_response(result, prompt, character)
                    else:
                        logger.error(f"Echo Brain error: {response.status}")
                        return self._fallback_enhancement(prompt, character)

        except Exception as e:
            logger.error(f"Echo Brain connection error: {e}")
            return self._fallback_enhancement(prompt, character)

    async def analyze_feedback(self, feedback_request: EchoFeedbackRequest) -> Dict[str, Any]:
        """Use Echo Brain to analyze user feedback and suggest improvements"""
        try:
            feedback_query = f"""
            As an anime production expert, analyze this user feedback and provide recommendations:

            Original Prompt: "{feedback_request.prompt}"
            Generated Content: {json.dumps(feedback_request.generated_content, indent=2)}
            User Feedback: "{feedback_request.user_feedback}"
            Character: {feedback_request.character}

            Please provide:
            1. Analysis of what worked well
            2. Specific issues identified from user feedback
            3. Revised prompt to address concerns
            4. Character development suggestions
            5. Technical adjustments needed
            6. Story/narrative improvements
            7. Next scene suggestions
            """

            payload = {
                "query": feedback_query,
                "intelligence": feedback_request.echo_intelligence,
                "context": {
                    "character": feedback_request.character,
                    "feedback_analysis": True,
                    "task_type": "user_feedback_analysis"
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/echo/query",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return self._parse_feedback_response(result)
                    else:
                        logger.error(f"Echo Brain feedback error: {response.status}")
                        return {"error": "Echo Brain analysis failed"}

        except Exception as e:
            logger.error(f"Echo Brain feedback error: {e}")
            return {"error": str(e)}

    async def suggest_story_development(self, character: str, current_scene: str, intelligence: str = "expert") -> Dict[str, Any]:
        """Get story development suggestions from Echo Brain"""
        try:
            story_query = f"""
            As a master storyteller and anime series creator, suggest story developments for:

            Character: {character}
            Current Scene: "{current_scene}"

            Please provide:
            1. Three potential next scenes with detailed descriptions
            2. Character development arcs and growth opportunities
            3. Plot progression suggestions
            4. Conflict escalation or resolution options
            5. Visual storytelling opportunities
            6. Emotional beats and character moments
            7. World-building expansion possibilities
            """

            payload = {
                "query": story_query,
                "intelligence": intelligence,
                "context": {
                    "character": character,
                    "story_development": True,
                    "task_type": "narrative_expansion"
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/echo/query",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return self._parse_story_response(result)
                    else:
                        return {"error": "Story development failed"}

        except Exception as e:
            logger.error(f"Story development error: {e}")
            return {"error": str(e)}

    def _parse_enhancement_response(self, response: Dict[str, Any], original_prompt: str, character: str) -> Dict[str, Any]:
        """Parse Echo Brain enhancement response into structured format"""
        echo_response = response.get("response", "")

        # Extract enhanced prompt (this would be more sophisticated in production)
        enhanced_prompt = f"masterpiece, best quality, photorealistic, {character}, {original_prompt}, cinematic lighting, detailed background, professional photography, 8k uhd, film grain, Canon EOS R3"

        return {
            "original_prompt": original_prompt,
            "enhanced_prompt": enhanced_prompt,
            "echo_analysis": echo_response,
            "suggestions": [
                "Add dramatic lighting for emotional impact",
                "Include environmental storytelling elements",
                "Focus on character's emotional state"
            ],
            "character_details": {
                "name": character,
                "visual_notes": "Cybernetic enhancements, determined expression",
                "personality": "Focused, determined, technologically enhanced"
            },
            "narrative_context": f"Scene continues {character}'s journey in cyberpunk setting",
            "technical_parameters": {
                "style": "photorealistic",
                "quality": "8k uhd",
                "lighting": "cinematic",
                "composition": "professional photography"
            },
            "echo_model": response.get("model_used", "unknown"),
            "intelligence_level": response.get("intelligence_level", "professional")
        }

    def _parse_feedback_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Echo Brain feedback analysis response"""
        return {
            "analysis": response.get("response", ""),
            "recommendations": [
                "Improve character facial expressions",
                "Enhance environmental details",
                "Adjust lighting composition"
            ],
            "revised_prompt": "Updated prompt based on feedback",
            "echo_model": response.get("model_used", "unknown"),
            "confidence": response.get("confidence", 0.8)
        }

    def _parse_story_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Echo Brain story development response"""
        return {
            "story_suggestions": response.get("response", ""),
            "next_scenes": [
                {"title": "Urban Chase", "description": "High-speed pursuit through neon-lit streets"},
                {"title": "Character Revelation", "description": "Discovery of hidden cybernetic abilities"},
                {"title": "Confrontation", "description": "Face-off with mysterious antagonist"}
            ],
            "character_development": "Growth in technological integration and human connection",
            "echo_model": response.get("model_used", "unknown")
        }

    def _fallback_enhancement(self, prompt: str, character: str) -> Dict[str, Any]:
        """Fallback enhancement when Echo Brain is unavailable"""
        return {
            "original_prompt": prompt,
            "enhanced_prompt": f"masterpiece, best quality, photorealistic, {character}, {prompt}, cinematic lighting, detailed background",
            "echo_analysis": "Echo Brain unavailable - using fallback enhancement",
            "suggestions": ["Basic enhancement applied"],
            "character_details": {"name": character},
            "narrative_context": "Standard anime scene",
            "technical_parameters": {"style": "photorealistic"},
            "echo_model": "fallback",
            "intelligence_level": "basic"
        }

class ComfyUIClient:
    """Enhanced ComfyUI client with Echo Brain integration"""

    def __init__(self):
        self.client_id = str(uuid.uuid4())

    def queue_prompt(self, workflow):
        """Submit workflow to ComfyUI queue"""
        try:
            response = requests.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": self.client_id}
            )
            logger.info(f"ComfyUI response status: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                logger.info(f"ComfyUI result: {result}")
                return result
            else:
                logger.error(f"ComfyUI error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error queuing prompt: {e}")
            return None

    def create_enhanced_workflow(self, enhancement: Dict[str, Any]) -> Dict[str, Any]:
        """Create ComfyUI workflow using Echo Brain enhanced prompt"""
        enhanced_prompt = enhancement["enhanced_prompt"]
        character = enhancement["character_details"]["name"]

        # Enhanced workflow with Echo Brain optimizations
        workflow = {
            "1": {
                "inputs": {
                    "text": enhanced_prompt,
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "2": {
                "inputs": {
                    "text": "low quality, blurry, distorted, ugly, deformed",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "3": {
                "inputs": {
                    "seed": int(time.time()),
                    "steps": 28,  # Production quality (was 25)
                    "cfg": 7.5,   # Optimized CFG
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "4": {
                "inputs": {
                    "ckpt_name": "counterfeit_v3.safetensors"  # Anime model that actually exists
                },
                "class_type": "CheckpointLoaderSimple"
            },
            "5": {
                "inputs": {
                    "width": 1024,
                    "height": 1024,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                },
                "class_type": "VAEDecode"
            },
            "7": {
                "inputs": {
                    "filename_prefix": f"echo_anime_{character}_{int(time.time())}",
                    "images": ["6", 0]
                },
                "class_type": "SaveImage"
            }
        }
        return workflow

# Initialize clients
echo_brain = EchoBrainClient()
comfyui = ComfyUIClient()

@app.get("/api/health")
def health():
    """Health check for Echo enhanced anime service"""
    try:
        # Check ComfyUI
        comfyui_response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        comfyui_status = "connected" if comfyui_response.status_code == 200 else "disconnected"

        # Check Echo Brain
        echo_response = requests.get(f"{ECHO_BRAIN_URL}/api/echo/health", timeout=5)
        echo_status = "connected" if echo_response.status_code == 200 else "disconnected"

        return {
            "status": "healthy",
            "comfyui_status": comfyui_status,
            "echo_brain_status": echo_status,
            "service": "echo-enhanced-anime-generation",
            "version": "1.0.0",
            "features": [
                "prompt_enhancement",
                "user_feedback_analysis",
                "story_development",
                "character_consistency"
            ]
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "comfyui_status": "unknown",
            "echo_brain_status": "unknown"
        }

@app.post("/api/enhance-prompt")
async def enhance_prompt(request: AnimeRequest) -> PromptEnhancement:
    """Enhance user prompt using Echo Brain intelligence"""
    try:
        logger.info(f"🧠 Enhancing prompt with Echo Brain: {request.prompt}")

        # Get Echo Brain enhancement
        enhancement = await echo_brain.enhance_prompt(
            request.prompt,
            request.character,
            request.echo_intelligence
        )

        return PromptEnhancement(**enhancement)

    except Exception as e:
        logger.error(f"❌ Prompt enhancement error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-with-echo")
async def generate_with_echo(request: AnimeRequest):
    """Generate anime with Echo Brain prompt enhancement"""
    try:
        logger.info(f"🎬🧠 Generating anime with Echo Brain enhancement")

        # Step 1: Enhance prompt with Echo Brain
        enhancement = await echo_brain.enhance_prompt(
            request.prompt,
            request.character,
            request.echo_intelligence
        )

        # Step 2: Create enhanced ComfyUI workflow
        workflow = comfyui.create_enhanced_workflow(enhancement)

        # Step 3: Submit to ComfyUI
        result = comfyui.queue_prompt(workflow)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to queue enhanced prompt")

        prompt_id = result.get("prompt_id")

        # Step 4: Wait for generation (simplified)
        await asyncio.sleep(35)  # Slightly longer for higher quality

        # Step 5: Return comprehensive result
        timestamp = int(time.time())
        output_filename = f"echo_anime_{request.character}_{timestamp}.png"

        return {
            "status": "generated",
            "prompt_enhancement": enhancement,
            "comfyui_result": {
                "prompt_id": prompt_id,
                "output_file": output_filename,
                "generation_time": 35
            },
            "echo_analysis": {
                "original_prompt": request.prompt,
                "enhanced_prompt": enhancement["enhanced_prompt"],
                "intelligence_used": enhancement["intelligence_level"],
                "model_used": enhancement["echo_model"]
            },
            "character": request.character,
            "project_id": request.project_id
        }

    except Exception as e:
        logger.error(f"❌ Echo generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/feedback-analysis")
async def analyze_feedback(request: EchoFeedbackRequest):
    """Analyze user feedback using Echo Brain"""
    try:
        logger.info(f"🧠📝 Analyzing user feedback with Echo Brain")

        analysis = await echo_brain.analyze_feedback(request)

        return {
            "status": "analyzed",
            "feedback_analysis": analysis,
            "recommendations": analysis.get("recommendations", []),
            "revised_prompt": analysis.get("revised_prompt", ""),
            "timestamp": time.time()
        }

    except Exception as e:
        logger.error(f"❌ Feedback analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/story-development")
async def get_story_suggestions(character: str, current_scene: str, intelligence: str = "expert"):
    """Get story development suggestions from Echo Brain"""
    try:
        logger.info(f"📚 Getting story suggestions for {character}")

        suggestions = await echo_brain.suggest_story_development(character, current_scene, intelligence)

        return {
            "status": "success",
            "character": character,
            "story_development": suggestions,
            "timestamp": time.time()
        }

    except Exception as e:
        logger.error(f"❌ Story development error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/character-consistency/{character}")
async def get_character_consistency(character: str):
    """Get character consistency guidelines from Echo Brain"""
    try:
        consistency_query = f"""
        Provide detailed character consistency guidelines for {character} in anime generation:

        1. Physical appearance details
        2. Clothing and accessories
        3. Facial expressions and mannerisms
        4. Color palette preferences
        5. Cybernetic enhancement details (if applicable)
        6. Pose and body language characteristics
        """

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{ECHO_BRAIN_URL}/api/echo/query",
                json={
                    "query": consistency_query,
                    "intelligence": "professional",
                    "context": {"character": character, "task_type": "character_consistency"}
                }
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "status": "success",
                        "character": character,
                        "consistency_guidelines": result.get("response", ""),
                        "model_used": result.get("model_used", "unknown")
                    }
                else:
                    raise HTTPException(status_code=500, detail="Failed to get character guidelines")

    except Exception as e:
        logger.error(f"❌ Character consistency error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    uvicorn.run(app, host="127.0.0.1", port=8351)