#!/usr/bin/env python3
"""
Echo Brain Integration for Intelligent QC
Leverages Echo's intelligence for context-aware quality assessment
"""

import requests
import json
import base64
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class EchoQualityChecker:
    """Intelligent QC using Echo Brain's analysis capabilities"""

    def __init__(self, echo_base_url: str = "http://localhost:8309"):
        self.echo_url = echo_base_url
        self.conversation_id = "anime_qc_checker"

    def analyze_image_with_echo(self, image_path: str, original_prompt: str, generation_params: Dict = None) -> Dict:
        """Send image and prompt to Echo for intelligent quality analysis"""
        try:
            # Encode image as base64
            with open(image_path, "rb") as img_file:
                image_b64 = base64.b64encode(img_file.read()).decode('utf-8')

            # Construct analysis prompt for Echo
            analysis_request = self._build_echo_prompt(
                image_path, original_prompt, generation_params
            )

            # Send to Echo Brain
            echo_payload = {
                "query": analysis_request,
                "conversation_id": self.conversation_id,
                "context": {
                    "image_data": image_b64,
                    "image_format": "png",
                    "original_prompt": original_prompt,
                    "generation_params": generation_params or {}
                }
            }

            response = requests.post(
                f"{self.echo_url}/api/echo/query",
                json=echo_payload,
                timeout=30
            )

            if response.status_code == 200:
                echo_result = response.json()
                return self._parse_echo_response(echo_result, image_path, original_prompt)
            else:
                logger.error(f"Echo API error: {response.status_code} - {response.text}")
                return {'error': f"Echo API failed: {response.status_code}"}

        except Exception as e:
            logger.error(f"Error communicating with Echo Brain: {e}")
            return {'error': str(e)}

    def _build_echo_prompt(self, image_path: str, original_prompt: str, generation_params: Dict) -> str:
        """Build intelligent analysis prompt for Echo"""
        return f"""Analyze this anime character image for quality control:

ORIGINAL GENERATION PROMPT: {original_prompt}

GENERATION PARAMETERS: {json.dumps(generation_params, indent=2) if generation_params else 'Not provided'}

IMAGE FILE: {Path(image_path).name}

Please analyze:
1. **Intent Matching**: Does the generated image match what the prompt requested?
   - If prompt says "solo" or "1girl", there should be exactly one person
   - If prompt says "2girls" or "group", multiple people are expected
   - Check for character consistency with description

2. **Technical Quality**:
   - Image clarity and focus
   - Anatomy correctness (hands, face, proportions)
   - Lighting and composition
   - Artifacts or distortions

3. **Artistic Merit**:
   - Does it capture the intended mood/style?
   - Character expression and pose appropriateness
   - Background and setting match

4. **Specific Issues**:
   - Multiple people when solo was requested
   - Missing people when group was requested
   - Character inconsistencies
   - Technical artifacts

Provide your analysis in JSON format:
{{
  "passes_qc": true/false,
  "overall_score": 0.0-10.0,
  "intent_match": {{
    "matches_prompt": true/false,
    "expected_people": number,
    "detected_people": number,
    "explanation": "detailed explanation"
  }},
  "technical_quality": {{
    "score": 0.0-10.0,
    "issues": ["list of technical issues"],
    "strengths": ["list of strengths"]
  }},
  "recommendations": {{
    "should_regenerate": true/false,
    "prompt_improvements": "suggestions for better prompt",
    "parameter_adjustments": "suggested parameter changes"
  }},
  "summary": "Brief overall assessment"
}}

Be thorough but concise. Focus on actionable feedback for improving generation quality."""

    def _parse_echo_response(self, echo_result: Dict, image_path: str, original_prompt: str) -> Dict:
        """Parse and structure Echo's response"""
        try:
            # Extract the response text
            response_text = echo_result.get('response', '')

            # Try to extract JSON from response
            json_match = None
            if '{' in response_text and '}' in response_text:
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                json_str = response_text[start:end]
                try:
                    json_match = json.loads(json_str)
                except json.JSONDecodeError:
                    logger.warning("Could not parse JSON from Echo response")

            # Structure the result
            result = {
                'image_path': image_path,
                'original_prompt': original_prompt,
                'echo_raw_response': response_text,
                'echo_analysis': json_match,
                'timestamp': echo_result.get('timestamp'),
                'conversation_id': self.conversation_id
            }

            # Extract key decisions from Echo's analysis
            if json_match:
                result.update({
                    'passes_qc': json_match.get('passes_qc', False),
                    'overall_score': json_match.get('overall_score', 0.0),
                    'should_regenerate': json_match.get('recommendations', {}).get('should_regenerate', True),
                    'echo_summary': json_match.get('summary', 'No summary provided')
                })
            else:
                # Fallback analysis if JSON parsing failed
                result.update({
                    'passes_qc': 'passes' in response_text.lower() or 'accept' in response_text.lower(),
                    'overall_score': 5.0,  # Neutral score
                    'should_regenerate': 'regenerate' in response_text.lower() or 'retry' in response_text.lower(),
                    'echo_summary': 'Failed to parse structured response'
                })

            return result

        except Exception as e:
            logger.error(f"Error parsing Echo response: {e}")
            return {
                'image_path': image_path,
                'error': f"Failed to parse Echo response: {e}",
                'passes_qc': False,
                'should_regenerate': True
            }

def test_echo_qc():
    """Test Echo QC integration"""
    echo_qc = EchoQualityChecker()

    # Test with recent problematic image
    test_image = "/mnt/1TB-storage/ComfyUI/output/yuki_anatomy_corrected_00001_.png"
    test_prompt = "photo of Yuki Tanaka, solo, 1girl, beautiful Japanese woman, photorealistic"

    print("=== Testing Echo QC Integration ===")
    print(f"Testing: {test_image}")
    print(f"Prompt: {test_prompt}")

    result = echo_qc.analyze_image_with_echo(test_image, test_prompt)

    print("\n=== Echo QC Result ===")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_echo_qc()