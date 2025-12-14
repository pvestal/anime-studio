#!/usr/bin/env python3
"""
Echo Brain Text-Based QC
Analyzes prompt intent and detected face counts for intelligent decisions
"""

import requests
import json
import cv2
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class EchoTextQC:
    """Lightweight Echo QC using text analysis"""

    def __init__(self, echo_url: str = "http://localhost:8309"):
        self.echo_url = echo_url
        self.conversation_id = "anime_qc_text"
        # Face detector for counts
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def check_with_echo(self, image_path: str, original_prompt: str) -> Dict:
        """Use Echo to analyze prompt intent vs detected results"""
        try:
            # Detect faces in image
            img = cv2.imread(image_path)
            if img is None:
                return {'error': f'Could not load image: {image_path}'}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3)
            detected_count = len(faces)

            # Ask Echo to analyze
            echo_query = f"""Analyze this anime generation for quality control:

ORIGINAL PROMPT: {original_prompt}

DETECTION RESULTS: Found {detected_count} faces in the generated image

TASK: Determine if this result matches the prompt intent.

Rules:
- If prompt contains "solo", "1girl", "1boy", "single person" → Should have exactly 1 face
- If prompt contains "2girls", "3girls", "group", "multiple" → Multiple faces expected
- Consider context and artistic intent
- Be practical - some reflection/mirror effects might trigger false positives

Respond with JSON:
{{
  "passes_qc": true/false,
  "expected_count": number,
  "detected_count": {detected_count},
  "intent_analysis": "What the prompt intended",
  "decision_reason": "Why this passes or fails",
  "should_regenerate": true/false,
  "confidence": 0.0-1.0
}}"""

            # Send to Echo
            payload = {
                "query": echo_query,
                "conversation_id": self.conversation_id
            }

            response = requests.post(
                f"{self.echo_url}/api/echo/query",
                json=payload,
                timeout=15
            )

            if response.status_code == 200:
                echo_result = response.json()
                return self._parse_echo_decision(echo_result, image_path, original_prompt, detected_count)
            else:
                logger.error(f"Echo error: {response.status_code}")
                return {'error': f"Echo API failed: {response.status_code}"}

        except Exception as e:
            logger.error(f"Echo QC error: {e}")
            return {'error': str(e)}

    def _parse_echo_decision(self, echo_result: Dict, image_path: str, prompt: str, detected: int) -> Dict:
        """Parse Echo's QC decision"""
        response_text = echo_result.get('response', '')

        # Try to extract JSON
        result = {
            'image_path': image_path,
            'original_prompt': prompt,
            'detected_faces': detected,
            'echo_response': response_text,
            'timestamp': echo_result.get('timestamp')
        }

        try:
            # Look for JSON in response
            if '{' in response_text and '}' in response_text:
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                json_str = response_text[start:end]
                echo_decision = json.loads(json_str)

                result.update({
                    'passes_qc': echo_decision.get('passes_qc', False),
                    'expected_count': echo_decision.get('expected_count', 1),
                    'intent_analysis': echo_decision.get('intent_analysis', ''),
                    'decision_reason': echo_decision.get('decision_reason', ''),
                    'should_regenerate': echo_decision.get('should_regenerate', True),
                    'confidence': echo_decision.get('confidence', 0.5),
                    'echo_parsed': True
                })
            else:
                # Fallback parsing
                result.update({
                    'passes_qc': 'pass' in response_text.lower(),
                    'should_regenerate': 'regenerate' in response_text.lower(),
                    'echo_parsed': False
                })

        except json.JSONDecodeError:
            logger.warning("Could not parse Echo JSON response")
            result.update({
                'passes_qc': False,
                'should_regenerate': True,
                'echo_parsed': False
            })

        return result

def test_echo_text_qc():
    """Test Echo text-based QC"""
    qc = EchoTextQC()

    test_cases = [
        ("/mnt/1TB-storage/ComfyUI/output/yuki_anatomy_corrected_00001_.png",
         "photo of Yuki Tanaka, solo, 1girl, beautiful Japanese woman, photorealistic"),
        ("/mnt/1TB-storage/ComfyUI/output/mei_anatomy_corrected_00001_.png",
         "photo of Mei Kobayashi, solo, 1girl, gentle beautiful Japanese woman")
    ]

    for image_path, prompt in test_cases:
        print(f"\n=== Testing: {image_path} ===")
        print(f"Prompt: {prompt}")

        result = qc.check_with_echo(image_path, prompt)

        if 'error' not in result:
            print(f"Detected faces: {result['detected_faces']}")
            print(f"Passes QC: {result.get('passes_qc', 'Unknown')}")
            print(f"Should regenerate: {result.get('should_regenerate', 'Unknown')}")
            if result.get('decision_reason'):
                print(f"Reason: {result['decision_reason']}")
        else:
            print(f"Error: {result['error']}")

if __name__ == "__main__":
    test_echo_text_qc()