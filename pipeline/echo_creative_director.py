#!/usr/bin/env python3
"""
Echo Brain Creative Director Integration
Coordinates anime production pipeline with Echo Brain as the Creative Director
Manages workflow orchestration, quality feedback, and creative decisions
"""

import asyncio
import json
import logging
import aiohttp
import websockets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
import uuid
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EchoCreativeDirector:
    def __init__(self):
        self.echo_brain_url = "http://127.0.0.1:8309"
        self.comfyui_url = "http://127.0.0.1:8188"
        self.anime_api_url = "http://127.0.0.1:8305"

        # Database connection
        self.db_params = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': 'tower_echo_brain_secret_key_2025'
        }

        # Creative direction state
        self.active_projects = {}
        self.creative_sessions = {}
        self.quality_feedback_history = []

        # Echo Brain models for different tasks
        self.models = {
            'creative_direction': 'qwen2.5-coder:32b',  # For complex creative decisions
            'prompt_enhancement': 'llama3.1:8b',        # For prompt improvements
            'quality_assessment': 'mixtral:8x7b',       # For quality evaluation
            'story_development': 'gemma2:9b'            # For narrative elements
        }

        # Creative direction templates
        self.direction_templates = {
            'character_development': {
                'prompt': "As a creative director, develop this character: {character}. Consider personality, visual design, backstory, and role in the story.",
                'context': "anime_character_development"
            },
            'scene_composition': {
                'prompt': "As a creative director, design this scene: {scene}. Focus on composition, lighting, mood, and visual storytelling.",
                'context': "anime_scene_direction"
            },
            'style_guidance': {
                'prompt': "As a creative director, define the visual style for: {concept}. Consider art style, color palette, and aesthetic choices.",
                'context': "anime_style_direction"
            },
            'quality_review': {
                'prompt': "As a creative director, review this generation quality: {quality_data}. Provide specific improvement recommendations.",
                'context': "anime_quality_direction"
            }
        }

    async def start_creative_session(self, project_id: int, project_name: str, creative_brief: Dict) -> str:
        """Start a new creative session with Echo Brain as Creative Director"""
        try:
            session_id = str(uuid.uuid4())

            # Initialize creative session
            session_data = {
                'session_id': session_id,
                'project_id': project_id,
                'project_name': project_name,
                'creative_brief': creative_brief,
                'start_time': datetime.now(),
                'status': 'active',
                'decisions': [],
                'quality_feedback': [],
                'generated_content': []
            }

            self.creative_sessions[session_id] = session_data

            # Get initial creative direction from Echo Brain
            initial_direction = await self.get_initial_creative_direction(creative_brief)
            session_data['initial_direction'] = initial_direction

            # Log session start
            await self.log_creative_event(session_id, 'session_started', {
                'project_id': project_id,
                'creative_brief': creative_brief,
                'initial_direction': initial_direction
            })

            logger.info(f"🎬 Creative session started: {session_id} for project {project_name}")

            return session_id

        except Exception as e:
            logger.error(f"Error starting creative session: {e}")
            return None

    async def get_initial_creative_direction(self, creative_brief: Dict) -> Dict:
        """Get initial creative direction from Echo Brain"""
        try:
            direction_query = f"""
            As the Creative Director for an anime production, analyze this brief and provide creative direction:

            Project Brief: {json.dumps(creative_brief, indent=2)}

            Provide direction on:
            1. Overall visual style and aesthetic
            2. Character design approach
            3. Scene composition guidelines
            4. Color palette and mood
            5. Technical quality standards
            6. Narrative focus points

            Be specific and actionable for the production team.
            """

            response = await self.query_echo_brain(
                query=direction_query,
                context="creative_direction_initial",
                model=self.models['creative_direction']
            )

            if response:
                return {
                    'direction': response.get('response', ''),
                    'model_used': self.models['creative_direction'],
                    'timestamp': datetime.now(),
                    'confidence': response.get('confidence', 0.8)
                }

        except Exception as e:
            logger.error(f"Error getting initial creative direction: {e}")

        return {
            'direction': 'Standard anime production approach with high quality standards',
            'model_used': 'fallback',
            'timestamp': datetime.now(),
            'confidence': 0.5
        }

    async def enhance_generation_request(self, session_id: str, original_request: Dict) -> Dict:
        """Enhance generation request with creative direction"""
        try:
            if session_id not in self.creative_sessions:
                logger.warning(f"Session not found: {session_id}")
                return original_request

            session = self.creative_sessions[session_id]
            creative_direction = session.get('initial_direction', {})

            # Enhance prompt with creative direction
            enhanced_prompt = await self.enhance_prompt_with_direction(
                original_request.get('prompt', ''),
                creative_direction,
                original_request
            )

            # Optimize parameters based on creative goals
            optimized_params = await self.optimize_parameters_for_creativity(
                original_request,
                creative_direction
            )

            enhanced_request = original_request.copy()
            enhanced_request.update({
                'prompt': enhanced_prompt,
                'creative_session_id': session_id,
                'creative_enhanced': True,
                **optimized_params
            })

            # Log creative enhancement
            await self.log_creative_event(session_id, 'request_enhanced', {
                'original_prompt': original_request.get('prompt', ''),
                'enhanced_prompt': enhanced_prompt,
                'optimizations': optimized_params
            })

            logger.info(f"🎨 Enhanced generation request for session {session_id}")

            return enhanced_request

        except Exception as e:
            logger.error(f"Error enhancing generation request: {e}")
            return original_request

    async def enhance_prompt_with_direction(self, original_prompt: str, creative_direction: Dict, request_data: Dict) -> str:
        """Enhance prompt with creative direction"""
        try:
            direction_text = creative_direction.get('direction', '')

            enhancement_query = f"""
            As the Creative Director, enhance this anime generation prompt:

            Original Prompt: {original_prompt}

            Creative Direction: {direction_text}

            Request Context: {json.dumps(request_data, indent=2)}

            Enhance the prompt to align with the creative direction while maintaining the original intent.
            Focus on visual quality, style consistency, and artistic vision.
            Return only the enhanced prompt.
            """

            response = await self.query_echo_brain(
                query=enhancement_query,
                context="prompt_enhancement",
                model=self.models['prompt_enhancement']
            )

            if response and response.get('response'):
                enhanced_prompt = response['response'].strip()

                # Validate enhanced prompt isn't too different
                if len(enhanced_prompt) > len(original_prompt) * 0.5 and len(enhanced_prompt) < len(original_prompt) * 3:
                    return enhanced_prompt

        except Exception as e:
            logger.error(f"Error enhancing prompt with direction: {e}")

        return original_prompt

    async def optimize_parameters_for_creativity(self, request_data: Dict, creative_direction: Dict) -> Dict:
        """Optimize generation parameters based on creative direction"""
        try:
            optimizations = {}

            direction_text = creative_direction.get('direction', '').lower()

            # Adjust parameters based on creative direction keywords
            if 'high quality' in direction_text or 'detailed' in direction_text:
                optimizations['steps'] = max(request_data.get('steps', 30), 40)
                optimizations['cfg'] = max(request_data.get('cfg', 7.5), 8.5)

            if 'cinematic' in direction_text:
                optimizations['width'] = 1024
                optimizations['height'] = 1024
                optimizations['sampler_name'] = 'dpmpp_2m'

            if 'artistic' in direction_text or 'stylized' in direction_text:
                optimizations['cfg'] = min(request_data.get('cfg', 7.5), 6.0)  # Lower CFG for artistic style

            if 'dramatic' in direction_text:
                optimizations['contrast_enhancement'] = True

            return optimizations

        except Exception as e:
            logger.error(f"Error optimizing parameters for creativity: {e}")
            return {}

    async def review_generation_quality(self, session_id: str, generation_result: Dict) -> Dict:
        """Review generation quality as Creative Director"""
        try:
            if session_id not in self.creative_sessions:
                return {'approved': True, 'feedback': 'No creative session found'}

            session = self.creative_sessions[session_id]

            # Prepare quality review data
            review_data = {
                'generation_result': generation_result,
                'quality_metrics': generation_result.get('quality_result', {}),
                'creative_direction': session.get('initial_direction', {}),
                'previous_feedback': session.get('quality_feedback', [])[-3:]  # Last 3 feedback items
            }

            # Get creative review from Echo Brain
            creative_review = await self.get_creative_quality_review(review_data)

            # Process review decision
            review_decision = await self.process_creative_review(session_id, creative_review, generation_result)

            # Log the review
            await self.log_creative_event(session_id, 'quality_reviewed', {
                'generation_id': generation_result.get('prompt_id', 'unknown'),
                'review_decision': review_decision,
                'creative_feedback': creative_review
            })

            logger.info(f"🎬 Creative quality review completed for session {session_id}: {'APPROVED' if review_decision['approved'] else 'REJECTED'}")

            return review_decision

        except Exception as e:
            logger.error(f"Error reviewing generation quality: {e}")
            return {'approved': True, 'feedback': 'Review error - defaulting to approval'}

    async def get_creative_quality_review(self, review_data: Dict) -> Dict:
        """Get creative quality review from Echo Brain"""
        try:
            quality_metrics = review_data.get('quality_metrics', {})
            creative_direction = review_data.get('creative_direction', {})

            review_query = f"""
            As the Creative Director, review this anime generation:

            Quality Metrics: {json.dumps(quality_metrics, indent=2)}

            Creative Direction: {json.dumps(creative_direction, indent=2)}

            Previous Feedback: {json.dumps(review_data.get('previous_feedback', []), indent=2)}

            Evaluate:
            1. Does it meet our creative vision?
            2. Is the quality acceptable for our standards?
            3. What specific improvements are needed?
            4. Should this be approved or require regeneration?

            Provide specific, actionable feedback as a Creative Director would.
            """

            response = await self.query_echo_brain(
                query=review_query,
                context="quality_review",
                model=self.models['quality_assessment']
            )

            if response:
                return {
                    'review': response.get('response', ''),
                    'model_used': self.models['quality_assessment'],
                    'timestamp': datetime.now()
                }

        except Exception as e:
            logger.error(f"Error getting creative quality review: {e}")

        return {
            'review': 'Standard quality review - proceed with generation',
            'model_used': 'fallback',
            'timestamp': datetime.now()
        }

    async def process_creative_review(self, session_id: str, creative_review: Dict, generation_result: Dict) -> Dict:
        """Process creative review and make approval decision"""
        try:
            review_text = creative_review.get('review', '').lower()
            quality_score = generation_result.get('quality_result', {}).get('quality_score', 0)

            # Extract decision indicators from review
            approval_indicators = ['approve', 'accept', 'good', 'excellent', 'meets standards', 'publish']
            rejection_indicators = ['reject', 'redo', 'regenerate', 'not acceptable', 'needs improvement', 'poor quality']

            approval_score = sum(1 for indicator in approval_indicators if indicator in review_text)
            rejection_score = sum(1 for indicator in rejection_indicators if indicator in review_text)

            # Make decision based on review and quality metrics
            if quality_score < 0.5:
                approved = False
                reason = "Quality score too low"
            elif rejection_score > approval_score:
                approved = False
                reason = "Creative Director feedback indicates rejection"
            elif quality_score > 0.7 and approval_score >= rejection_score:
                approved = True
                reason = "Meets creative and quality standards"
            else:
                # Default to requiring higher standards
                approved = quality_score > 0.6
                reason = f"Borderline quality (score: {quality_score})"

            # Generate improvement suggestions if rejected
            improvements = []
            if not approved:
                improvements = await self.generate_improvement_suggestions(creative_review, generation_result)

            decision = {
                'approved': approved,
                'reason': reason,
                'quality_score': quality_score,
                'creative_feedback': creative_review.get('review', ''),
                'improvements': improvements,
                'reviewer': 'Echo Creative Director',
                'timestamp': datetime.now()
            }

            # Update session with feedback
            session = self.creative_sessions[session_id]
            session['quality_feedback'].append(decision)

            return decision

        except Exception as e:
            logger.error(f"Error processing creative review: {e}")
            return {'approved': True, 'reason': 'Error in review process'}

    async def generate_improvement_suggestions(self, creative_review: Dict, generation_result: Dict) -> List[str]:
        """Generate specific improvement suggestions"""
        try:
            review_text = creative_review.get('review', '')

            suggestion_query = f"""
            Based on this Creative Director review, provide specific, actionable improvement suggestions:

            Review: {review_text}

            Quality Data: {json.dumps(generation_result.get('quality_result', {}), indent=2)}

            Provide 3-5 specific suggestions for improvement, focusing on:
            - Prompt modifications
            - Parameter adjustments
            - Style refinements
            - Quality enhancements

            Format as a simple list.
            """

            response = await self.query_echo_brain(
                query=suggestion_query,
                context="improvement_suggestions",
                model=self.models['creative_direction']
            )

            if response and response.get('response'):
                suggestions_text = response['response']
                # Extract list items (simple parsing)
                suggestions = [
                    line.strip().lstrip('- ').lstrip('* ').lstrip('1. ').lstrip('2. ').lstrip('3. ').lstrip('4. ').lstrip('5. ')
                    for line in suggestions_text.split('\n')
                    if line.strip() and not line.strip().startswith('Based on')
                ]
                return suggestions[:5]  # Max 5 suggestions

        except Exception as e:
            logger.error(f"Error generating improvement suggestions: {e}")

        return ["Increase generation steps for better quality", "Enhance prompt with more detail", "Adjust CFG scale for better results"]

    async def coordinate_regeneration(self, session_id: str, failed_generation: Dict, improvements: List[str]) -> Dict:
        """Coordinate regeneration with improvements"""
        try:
            if session_id not in self.creative_sessions:
                return None

            # Apply improvements to original request
            original_request = failed_generation.get('original_request', {})
            improved_request = await self.apply_improvements_to_request(original_request, improvements)

            # Enhance with creative direction again
            enhanced_request = await self.enhance_generation_request(session_id, improved_request)

            # Log regeneration coordination
            await self.log_creative_event(session_id, 'regeneration_coordinated', {
                'failed_generation_id': failed_generation.get('prompt_id', 'unknown'),
                'improvements_applied': improvements,
                'enhanced_request': enhanced_request
            })

            logger.info(f"🔄 Coordinated regeneration for session {session_id}")

            return enhanced_request

        except Exception as e:
            logger.error(f"Error coordinating regeneration: {e}")
            return None

    async def apply_improvements_to_request(self, original_request: Dict, improvements: List[str]) -> Dict:
        """Apply improvement suggestions to generation request"""
        try:
            improved_request = original_request.copy()

            for improvement in improvements:
                improvement_lower = improvement.lower()

                # Prompt improvements
                if 'prompt' in improvement_lower or 'detail' in improvement_lower:
                    current_prompt = improved_request.get('prompt', '')
                    if 'more detail' in improvement_lower and 'detailed' not in current_prompt:
                        improved_request['prompt'] = f"{current_prompt}, highly detailed"

                # Parameter improvements
                if 'steps' in improvement_lower:
                    current_steps = improved_request.get('steps', 30)
                    improved_request['steps'] = min(current_steps + 10, 50)

                if 'cfg' in improvement_lower:
                    if 'increase' in improvement_lower:
                        current_cfg = improved_request.get('cfg', 7.5)
                        improved_request['cfg'] = min(current_cfg + 1.0, 12.0)
                    elif 'decrease' in improvement_lower:
                        current_cfg = improved_request.get('cfg', 7.5)
                        improved_request['cfg'] = max(current_cfg - 1.0, 4.0)

                if 'resolution' in improvement_lower:
                    improved_request['width'] = 1024
                    improved_request['height'] = 1024

                if 'sampler' in improvement_lower:
                    improved_request['sampler_name'] = 'dpmpp_2m'

            return improved_request

        except Exception as e:
            logger.error(f"Error applying improvements to request: {e}")
            return original_request

    async def query_echo_brain(self, query: str, context: str, model: str = None) -> Optional[Dict]:
        """Query Echo Brain for creative decisions"""
        try:
            request_data = {
                'query': query,
                'context': context
            }

            if model:
                request_data['model'] = model

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.echo_brain_url}/api/query", json=request_data) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Echo Brain query failed: {response.status}")

        except Exception as e:
            logger.error(f"Error querying Echo Brain: {e}")

        return None

    async def log_creative_event(self, session_id: str, event_type: str, event_data: Dict):
        """Log creative direction event"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO creative_direction_events (session_id, event_type, event_data, created_at)
                VALUES (%s, %s, %s, %s)
            """, (
                session_id,
                event_type,
                json.dumps(event_data, default=str),
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error logging creative event: {e}")

    async def get_session_statistics(self, session_id: str) -> Dict:
        """Get statistics for a creative session"""
        try:
            if session_id not in self.creative_sessions:
                return {}

            session = self.creative_sessions[session_id]
            feedback_history = session.get('quality_feedback', [])

            # Calculate statistics
            total_reviews = len(feedback_history)
            approved_count = sum(1 for f in feedback_history if f.get('approved', False))
            approval_rate = approved_count / total_reviews if total_reviews > 0 else 0

            avg_quality_score = np.mean([f.get('quality_score', 0) for f in feedback_history]) if feedback_history else 0

            return {
                'session_id': session_id,
                'project_name': session['project_name'],
                'duration_hours': (datetime.now() - session['start_time']).total_seconds() / 3600,
                'total_reviews': total_reviews,
                'approval_rate': approval_rate,
                'average_quality_score': float(avg_quality_score),
                'creative_direction_model': session.get('initial_direction', {}).get('model_used', 'unknown'),
                'status': session['status']
            }

        except Exception as e:
            logger.error(f"Error getting session statistics: {e}")
            return {}

    async def end_creative_session(self, session_id: str) -> Dict:
        """End a creative session and generate summary"""
        try:
            if session_id not in self.creative_sessions:
                return {'error': 'Session not found'}

            session = self.creative_sessions[session_id]
            session['status'] = 'completed'
            session['end_time'] = datetime.now()

            # Generate session summary
            statistics = await self.get_session_statistics(session_id)

            # Log session end
            await self.log_creative_event(session_id, 'session_ended', {
                'statistics': statistics,
                'total_duration': (session['end_time'] - session['start_time']).total_seconds()
            })

            # Remove from active sessions
            del self.creative_sessions[session_id]

            logger.info(f"🎬 Creative session ended: {session_id}")

            return {
                'session_id': session_id,
                'statistics': statistics,
                'summary': f"Session completed with {statistics.get('approval_rate', 0)*100:.1f}% approval rate"
            }

        except Exception as e:
            logger.error(f"Error ending creative session: {e}")
            return {'error': str(e)}

# Database table creation
async def create_creative_director_tables():
    """Create tables for creative director system"""
    try:
        conn = psycopg2.connect(
            host='localhost',
            database='tower_consolidated',
            user='patrick',
            password=''
        )
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS creative_direction_events (
                id SERIAL PRIMARY KEY,
                session_id UUID,
                event_type VARCHAR(50),
                event_data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS creative_sessions (
                id SERIAL PRIMARY KEY,
                session_id UUID UNIQUE,
                project_id INTEGER,
                project_name VARCHAR(255),
                creative_brief JSONB,
                initial_direction JSONB,
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW(),
                ended_at TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_creative_events_session ON creative_direction_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_creative_events_type ON creative_direction_events(event_type);
            CREATE INDEX IF NOT EXISTS idx_creative_sessions_status ON creative_sessions(status);
        """)

        conn.commit()
        cur.close()
        conn.close()
        logger.info("Creative director tables created/verified")

    except Exception as e:
        logger.error(f"Error creating creative director tables: {e}")

async def main():
    """Main entry point for testing"""
    await create_creative_director_tables()

    # Test creative director
    director = EchoCreativeDirector()

    # Start a test session
    creative_brief = {
        'project_type': 'anime_video',
        'style': 'cyberpunk',
        'characters': ['Kai Nakamura'],
        'themes': ['technology', 'humanity'],
        'quality_requirements': 'high'
    }

    session_id = await director.start_creative_session(1, "Test Anime Project", creative_brief)
    print(f"Started session: {session_id}")

    # Test request enhancement
    original_request = {
        'prompt': 'anime girl fighting',
        'steps': 30,
        'cfg': 7.5
    }

    enhanced_request = await director.enhance_generation_request(session_id, original_request)
    print(f"Enhanced request: {enhanced_request}")

    # Test quality review
    generation_result = {
        'prompt_id': 'test_123',
        'quality_result': {
            'quality_score': 0.85,
            'passes_standards': True
        }
    }

    review = await director.review_generation_quality(session_id, generation_result)
    print(f"Quality review: {review}")

    # Get session statistics
    stats = await director.get_session_statistics(session_id)
    print(f"Session stats: {stats}")

if __name__ == "__main__":
    import numpy as np
    asyncio.run(main())