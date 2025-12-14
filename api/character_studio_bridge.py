#!/usr/bin/env python3
"""
Character Studio Bridge - Integrates Echo Brain character management with existing UI
Provides QC workflow and consistency tracking through the studio interface
"""

from fastapi import FastAPI, HTTPException, Form, Query, UploadFile, File
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
import httpx
import asyncio
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Echo Brain character management endpoints
ECHO_BRAIN_URL = "http://localhost:8309/api/echo/anime"

class CharacterStudioBridge:
    """Bridges Character Studio UI with Echo Brain's character consistency system"""

    def __init__(self):
        self.echo_client = httpx.AsyncClient(timeout=30.0)

    async def list_characters_for_studio(self) -> Dict:
        """Get characters formatted for studio UI"""
        try:
            # Get characters from Echo Brain
            response = await self.echo_client.get(f"{ECHO_BRAIN_URL}/characters")
            if response.status_code == 200:
                echo_chars = response.json()["characters"]

                # Transform to studio format
                studio_chars = []
                for char in echo_chars:
                    studio_chars.append({
                        "id": char["id"],
                        "character_name": char["name"],
                        "project_name": char["project"],
                        "age": None,  # Add if available
                        "gender": None,  # Add if available
                        "personality": None,
                        "appearance": f"Reference: {char['reference_image']}",
                        "reference_images": [{
                            "url": f"/api/anime/image/{char['id']}/reference",
                            "path": char["reference_image"]
                        }] if char.get("reference_image") else [],
                        "generation_count": char["stats"]["generations"],
                        "approved_count": char["stats"]["approved"],
                        "consistency_score": char["stats"]["avg_consistency"],
                        "created_at": datetime.now().isoformat()
                    })

                return {"characters": studio_chars}
            else:
                return {"characters": []}
        except Exception as e:
            logger.error(f"Error fetching characters: {e}")
            return {"characters": []}

    async def get_character_details(self, character_id: int) -> Dict:
        """Get detailed character info including generation history"""
        try:
            # Get character report from Echo Brain
            response = await self.echo_client.get(
                f"{ECHO_BRAIN_URL}/character/{character_id}/report"
            )

            if response.status_code == 200:
                report = response.json()

                # Add QC-specific fields
                return {
                    "character": report["character"],
                    "stats": report["stats"],
                    "recent_generations": report["recent_generations"],
                    "best_patterns": report["best_patterns"],
                    "qc_status": {
                        "approval_rate": report["stats"]["approval_rate"],
                        "consistency_trend": "improving" if report["stats"]["avg_consistency"] > 0.7 else "needs_work",
                        "ready_for_production": report["stats"]["approval_rate"] > 0.8
                    }
                }
            else:
                raise HTTPException(status_code=404, detail="Character not found")
        except Exception as e:
            logger.error(f"Error getting character details: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def generate_with_qc(self, character_id: int, prompt: str, settings: Dict) -> Dict:
        """Generate character variation with QC metadata"""
        try:
            # Generate via Echo Brain
            response = await self.echo_client.post(
                f"{ECHO_BRAIN_URL}/character/{character_id}/generate",
                data={
                    "prompt": prompt,
                    "denoise": settings.get("denoise", 0.5),
                    "seed": settings.get("seed")
                }
            )

            if response.status_code == 200:
                result = response.json()

                # Add QC tracking
                return {
                    **result,
                    "qc_metadata": {
                        "generation_id": result["generation_id"],
                        "needs_approval": True,
                        "auto_score_threshold": 0.75,
                        "review_deadline": "24_hours"
                    }
                }
            else:
                raise HTTPException(status_code=500, detail="Generation failed")
        except Exception as e:
            logger.error(f"Generation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_qc_queue(self, character_id: Optional[int] = None) -> List[Dict]:
        """Get generations pending QC approval"""
        try:
            # In production, would query database for unapproved generations
            # For now, return mock data showing the QC workflow
            queue = []

            if character_id:
                # Get recent generations for this character
                response = await self.echo_client.get(
                    f"{ECHO_BRAIN_URL}/character/{character_id}/report"
                )
                if response.status_code == 200:
                    report = response.json()
                    for gen in report.get("recent_generations", []):
                        if gen.get("approved") is None:
                            queue.append({
                                "generation_id": 1,  # Would be real ID
                                "character_name": report["character"]["name"],
                                "prompt": gen["prompt"],
                                "consistency": gen.get("consistency", 0),
                                "created_at": gen["date"],
                                "preview_url": f"/api/anime/preview/{character_id}/latest",
                                "actions": ["approve", "reject", "regenerate"]
                            })

            return queue
        except Exception as e:
            logger.error(f"Error getting QC queue: {e}")
            return []

    async def approve_generation(self, character_id: int, generation_id: int, feedback: str = None) -> Dict:
        """Approve a generation through studio QC"""
        try:
            response = await self.echo_client.post(
                f"{ECHO_BRAIN_URL}/character/{character_id}/approve",
                params={"generation_id": generation_id},
                data={"feedback": feedback or "Approved via Character Studio QC"}
            )

            if response.status_code == 200:
                return {
                    "status": "approved",
                    "message": "Generation approved and added to character library",
                    "learned_patterns": True
                }
            else:
                raise HTTPException(status_code=500, detail="Approval failed")
        except Exception as e:
            logger.error(f"Approval error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def reject_generation(self, character_id: int, generation_id: int, reason: str) -> Dict:
        """Reject a generation through studio QC"""
        try:
            response = await self.echo_client.post(
                f"{ECHO_BRAIN_URL}/character/{character_id}/reject",
                params={"generation_id": generation_id},
                data={"reason": reason}
            )

            if response.status_code == 200:
                return {
                    "status": "rejected",
                    "message": "Generation rejected, Echo will learn from this",
                    "will_retry": True
                }
            else:
                raise HTTPException(status_code=500, detail="Rejection failed")
        except Exception as e:
            logger.error(f"Rejection error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_consistency_metrics(self, character_id: int) -> Dict:
        """Get detailed consistency metrics for QC dashboard"""
        try:
            response = await self.echo_client.get(
                f"{ECHO_BRAIN_URL}/character/{character_id}/report"
            )

            if response.status_code == 200:
                report = response.json()

                # Calculate QC metrics
                total = report["stats"]["total_generations"]
                approved = report["stats"]["approved"]

                return {
                    "character_id": character_id,
                    "character_name": report["character"]["name"],
                    "metrics": {
                        "total_generations": total,
                        "approved": approved,
                        "rejected": total - approved if total > 0 else 0,
                        "approval_rate": report["stats"]["approval_rate"],
                        "average_consistency": report["stats"]["avg_consistency"],
                        "trend": "improving" if report["stats"]["avg_consistency"] > 0.7 else "needs_attention"
                    },
                    "recommendations": self._get_qc_recommendations(report["stats"])
                }
            else:
                raise HTTPException(status_code=404, detail="Character not found")
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _get_qc_recommendations(self, stats: Dict) -> List[str]:
        """Generate QC recommendations based on stats"""
        recommendations = []

        if stats["approval_rate"] < 0.5:
            recommendations.append("Consider adjusting generation parameters")

        if stats["avg_consistency"] < 0.7:
            recommendations.append("Reduce denoise strength for better consistency")

        if stats["total_generations"] < 10:
            recommendations.append("Generate more variations to establish patterns")

        if not recommendations:
            recommendations.append("Character is production-ready")

        return recommendations


# Integration with existing anime API
async def register_studio_bridge_endpoints(app: FastAPI):
    """Register character studio bridge endpoints with the anime production API"""

    bridge = CharacterStudioBridge()

    @app.get("/api/anime/studio/characters")
    async def get_studio_characters():
        """Get characters formatted for Character Studio UI"""
        return await bridge.list_characters_for_studio()

    @app.get("/api/anime/studio/character/{character_id}")
    async def get_studio_character(character_id: int):
        """Get detailed character info for studio"""
        return await bridge.get_character_details(character_id)

    @app.post("/api/anime/studio/character/{character_id}/generate")
    async def generate_with_studio_qc(
        character_id: int,
        prompt: str = Form(...),
        denoise: float = Form(0.5),
        seed: Optional[int] = Form(None)
    ):
        """Generate with QC metadata for studio"""
        settings = {"denoise": denoise, "seed": seed}
        return await bridge.generate_with_qc(character_id, prompt, settings)

    @app.get("/api/anime/studio/qc/queue")
    async def get_qc_queue(character_id: Optional[int] = Query(None)):
        """Get generations pending QC approval"""
        return {"queue": await bridge.get_qc_queue(character_id)}

    @app.post("/api/anime/studio/qc/{character_id}/approve")
    async def approve_in_studio(
        character_id: int,
        generation_id: int = Query(...),
        feedback: Optional[str] = Form(None)
    ):
        """Approve generation through studio QC"""
        return await bridge.approve_generation(character_id, generation_id, feedback)

    @app.post("/api/anime/studio/qc/{character_id}/reject")
    async def reject_in_studio(
        character_id: int,
        generation_id: int = Query(...),
        reason: str = Form(...)
    ):
        """Reject generation through studio QC"""
        return await bridge.reject_generation(character_id, generation_id, reason)

    @app.get("/api/anime/studio/qc/{character_id}/metrics")
    async def get_qc_metrics(character_id: int):
        """Get QC metrics for character"""
        return await bridge.get_consistency_metrics(character_id)

    logger.info("✅ Character Studio Bridge endpoints registered")


# Test scenarios for QC workflow
async def test_qc_workflow():
    """Test the complete QC workflow with existing structure"""

    bridge = CharacterStudioBridge()

    print("=" * 60)
    print("TESTING CHARACTER STUDIO QC WORKFLOW")
    print("=" * 60)

    # Test 1: List characters in studio format
    print("\n📋 Test 1: List characters for studio")
    characters = await bridge.list_characters_for_studio()
    print(f"Found {len(characters['characters'])} characters")
    for char in characters["characters"]:
        print(f"  - {char['character_name']}: {char['generation_count']} generations, "
              f"{char['approved_count']} approved")

    # Test 2: Get character details with QC status
    if characters["characters"]:
        char_id = characters["characters"][0]["id"]
        print(f"\n🔍 Test 2: Get character details for ID {char_id}")
        details = await bridge.get_character_details(char_id)
        print(f"  QC Status: {details['qc_status']}")
        print(f"  Recent generations: {len(details['recent_generations'])}")

    # Test 3: Generate with QC tracking
    print(f"\n🎨 Test 3: Generate with QC metadata")
    generation = await bridge.generate_with_qc(
        char_id,
        "character in action pose",
        {"denoise": 0.45}
    )
    print(f"  Generation ID: {generation['generation_id']}")
    print(f"  QC Required: {generation['qc_metadata']['needs_approval']}")

    # Test 4: Get QC queue
    print(f"\n📊 Test 4: Get QC queue")
    queue = await bridge.get_qc_queue(char_id)
    print(f"  Items pending QC: {len(queue)}")

    # Test 5: Approve generation
    if generation.get("generation_id"):
        print(f"\n✅ Test 5: Approve generation")
        approval = await bridge.approve_generation(
            char_id,
            generation["generation_id"],
            "Good consistency, approved"
        )
        print(f"  Status: {approval['status']}")

    # Test 6: Get consistency metrics
    print(f"\n📈 Test 6: Get consistency metrics")
    metrics = await bridge.get_consistency_metrics(char_id)
    print(f"  Approval rate: {metrics['metrics']['approval_rate']:.1%}")
    print(f"  Recommendations: {metrics['recommendations']}")

    print("\n" + "=" * 60)
    print("✅ QC WORKFLOW TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    # Run test workflow
    asyncio.run(test_qc_workflow())