"""
ComfyUI Connector Module
Handles all communication with ComfyUI server
"""
import aiohttp
import asyncio
import json
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ComfyUIConnector:
    """Manages all ComfyUI interactions"""

    def __init__(self, base_url: str = "http://***REMOVED***:8188"):
        self.base_url = base_url
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def submit_workflow(self, workflow: Dict[str, Any], client_id: str = None) -> Optional[str]:
        """Submit workflow to ComfyUI and return prompt_id"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            payload = {
                "prompt": workflow,
                "client_id": client_id or f"anime_{id(self)}"
            }

            async with self.session.post(
                f"{self.base_url}/prompt",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("prompt_id")
                    logger.info(f"Submitted workflow to ComfyUI: {prompt_id}")
                    return prompt_id
                else:
                    logger.error(f"ComfyUI returned status {response.status}")
                    return None

        except Exception as e:
            logger.error(f"Failed to submit to ComfyUI: {e}")
            return None

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{self.base_url}/queue") as response:
                data = await response.json()
                return {
                    "running": len(data.get("queue_running", [])),
                    "pending": len(data.get("queue_pending", [])),
                    "details": data
                }
        except Exception as e:
            logger.error(f"Failed to get queue status: {e}")
            return {"running": 0, "pending": 0, "error": str(e)}

    async def get_history(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get generation history for a specific prompt"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{self.base_url}/history/{prompt_id}") as response:
                if response.status == 200:
                    history = await response.json()
                    return history.get(prompt_id)
                return None
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return None

    async def interrupt_generation(self) -> bool:
        """Interrupt current generation"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.post(f"{self.base_url}/interrupt") as response:
                return response.status == 200
        except:
            return False

    async def check_health(self) -> bool:
        """Check if ComfyUI is responding"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(
                f"{self.base_url}/system_stats",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
        except:
            return False