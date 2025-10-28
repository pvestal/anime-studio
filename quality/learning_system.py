#!/usr/bin/env python3
"""
Learning System for Anime Production Quality Improvement
Machine learning-based system that learns from successful and failed generations
Automatically improves prompts and parameters over time based on quality feedback
"""

import asyncio
import json
import logging
import numpy as np
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
import hashlib
import re
from collections import defaultdict, Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
import pickle

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnimeLearningSystem:
    def __init__(self):
        self.echo_brain_url = "http://127.0.0.1:8309"

        # Database connection
        self.db_params = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': '***REMOVED***'
        }

        # Learning models and data
        self.prompt_vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
        self.quality_patterns = {}
        self.successful_prompt_features = []
        self.failed_prompt_features = []

        # Learning parameters
        self.min_samples_for_learning = 10
        self.quality_threshold = 0.7
        self.similarity_threshold = 0.8

        # Cache for learned patterns
        self.learned_improvements = {}
        self.parameter_patterns = defaultdict(list)
        self.style_preferences = defaultdict(dict)

        # Initialize learning data
        asyncio.create_task(self.load_learning_data())

    async def load_learning_data(self):
        """Load historical data for learning"""
        try:
            logger.info("Loading historical data for learning...")

            # Load successful generations
            successful_data = await self.load_successful_generations()
            failed_data = await self.load_failed_generations()

            # Analyze patterns
            await self.analyze_quality_patterns(successful_data, failed_data)
            await self.analyze_parameter_patterns(successful_data)
            await self.analyze_prompt_patterns(successful_data, failed_data)

            logger.info(f"Learning system initialized with {len(successful_data)} successful and {len(failed_data)} failed examples")

        except Exception as e:
            logger.error(f"Error loading learning data: {e}")

    async def load_successful_generations(self) -> List[Dict]:
        """Load successful generation data from database"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT
                    qa.prompt_id,
                    qa.quality_score,
                    qa.metrics,
                    gm.event_data,
                    sw.workflow_params
                FROM quality_assessments qa
                JOIN generation_metrics gm ON gm.prompt_id = qa.prompt_id
                LEFT JOIN successful_workflows sw ON sw.prompt_hash = MD5(gm.event_data->>'prompt')
                WHERE qa.passes_standards = true
                    AND qa.quality_score >= %s
                    AND qa.created_at > NOW() - INTERVAL '30 days'
                    AND gm.event_type = 'started'
                ORDER BY qa.quality_score DESC
            """, (self.quality_threshold,))

            results = cur.fetchall()
            cur.close()
            conn.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Error loading successful generations: {e}")
            return []

    async def load_failed_generations(self) -> List[Dict]:
        """Load failed generation data from database"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT
                    qa.prompt_id,
                    qa.quality_score,
                    qa.rejection_reasons,
                    qa.metrics,
                    gm.event_data
                FROM quality_assessments qa
                JOIN generation_metrics gm ON gm.prompt_id = qa.prompt_id
                WHERE qa.passes_standards = false
                    AND qa.created_at > NOW() - INTERVAL '14 days'
                    AND gm.event_type = 'started'
                ORDER BY qa.created_at DESC
            """, )

            results = cur.fetchall()
            cur.close()
            conn.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Error loading failed generations: {e}")
            return []

    async def analyze_quality_patterns(self, successful_data: List[Dict], failed_data: List[Dict]):
        """Analyze patterns in quality metrics"""
        try:
            # Analyze successful patterns
            successful_metrics = []
            for item in successful_data:
                if item.get('metrics'):
                    metrics = json.loads(item['metrics']) if isinstance(item['metrics'], str) else item['metrics']
                    successful_metrics.append(metrics)

            # Analyze failed patterns
            failed_metrics = []
            for item in failed_data:
                if item.get('metrics'):
                    metrics = json.loads(item['metrics']) if isinstance(item['metrics'], str) else item['metrics']
                    failed_metrics.append(metrics)

            # Find quality patterns
            if successful_metrics:
                self.quality_patterns['successful'] = {
                    'avg_resolution': self.analyze_resolution_patterns(successful_metrics),
                    'avg_quality_score': np.mean([m.get('quality_score', 0) for m in successful_metrics]),
                    'common_attributes': self.find_common_attributes(successful_metrics)
                }

            if failed_metrics:
                self.quality_patterns['failed'] = {
                    'avg_resolution': self.analyze_resolution_patterns(failed_metrics),
                    'avg_quality_score': np.mean([m.get('quality_score', 0) for m in failed_metrics]),
                    'common_failure_reasons': self.analyze_failure_reasons(failed_data)
                }

            logger.info("Quality patterns analyzed")

        except Exception as e:
            logger.error(f"Error analyzing quality patterns: {e}")

    def analyze_resolution_patterns(self, metrics_list: List[Dict]) -> Tuple[float, float]:
        """Analyze common resolution patterns"""
        resolutions = []
        for metrics in metrics_list:
            resolution = metrics.get('resolution', (0, 0))
            if isinstance(resolution, list) and len(resolution) >= 2:
                resolutions.append((resolution[0], resolution[1]))

        if resolutions:
            avg_width = np.mean([r[0] for r in resolutions])
            avg_height = np.mean([r[1] for r in resolutions])
            return (avg_width, avg_height)

        return (1024, 1024)  # Default

    def find_common_attributes(self, metrics_list: List[Dict]) -> Dict:
        """Find common attributes in successful generations"""
        attributes = defaultdict(list)

        for metrics in metrics_list:
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    attributes[key].append(value)

        common_attrs = {}
        for key, values in attributes.items():
            if len(values) >= 3:  # Need at least 3 samples
                common_attrs[key] = {
                    'mean': np.mean(values),
                    'median': np.median(values),
                    'std': np.std(values),
                    'min': np.min(values),
                    'max': np.max(values)
                }

        return common_attrs

    def analyze_failure_reasons(self, failed_data: List[Dict]) -> Dict:
        """Analyze common failure reasons"""
        reason_counts = Counter()

        for item in failed_data:
            if item.get('rejection_reasons'):
                reasons = json.loads(item['rejection_reasons']) if isinstance(item['rejection_reasons'], str) else item['rejection_reasons']
                for reason in reasons:
                    # Categorize reasons
                    if 'resolution' in reason.lower():
                        reason_counts['low_resolution'] += 1
                    elif 'quality' in reason.lower():
                        reason_counts['low_quality'] += 1
                    elif 'duration' in reason.lower():
                        reason_counts['short_duration'] += 1
                    elif 'blur' in reason.lower():
                        reason_counts['blur'] += 1
                    elif 'contrast' in reason.lower():
                        reason_counts['low_contrast'] += 1
                    else:
                        reason_counts['other'] += 1

        return dict(reason_counts)

    async def analyze_parameter_patterns(self, successful_data: List[Dict]):
        """Analyze successful parameter patterns"""
        try:
            for item in successful_data:
                if item.get('workflow_params'):
                    params = json.loads(item['workflow_params']) if isinstance(item['workflow_params'], str) else item['workflow_params']
                    quality_score = item.get('quality_score', 0)

                    # Extract key parameters
                    self.extract_parameter_patterns(params, quality_score)

            # Find optimal parameter ranges
            self.find_optimal_parameter_ranges()

            logger.info("Parameter patterns analyzed")

        except Exception as e:
            logger.error(f"Error analyzing parameter patterns: {e}")

    def extract_parameter_patterns(self, workflow_params: Dict, quality_score: float):
        """Extract parameter patterns from workflow"""
        try:
            if 'prompt' in workflow_params:
                for node_id, node_data in workflow_params['prompt'].items():
                    class_type = node_data.get('class_type', '')
                    inputs = node_data.get('inputs', {})

                    if class_type == 'KSampler':
                        self.parameter_patterns['steps'].append((inputs.get('steps', 20), quality_score))
                        self.parameter_patterns['cfg'].append((inputs.get('cfg', 7.0), quality_score))
                        self.parameter_patterns['sampler'].append((inputs.get('sampler_name', 'euler'), quality_score))

                    elif class_type == 'EmptyLatentImage':
                        width = inputs.get('width', 512)
                        height = inputs.get('height', 512)
                        self.parameter_patterns['resolution'].append(((width, height), quality_score))

        except Exception as e:
            logger.error(f"Error extracting parameter patterns: {e}")

    def find_optimal_parameter_ranges(self):
        """Find optimal parameter ranges based on quality scores"""
        try:
            self.optimal_params = {}

            # Analyze steps
            if self.parameter_patterns['steps']:
                steps_data = self.parameter_patterns['steps']
                high_quality_steps = [steps for steps, score in steps_data if score > 0.8]
                if high_quality_steps:
                    self.optimal_params['steps'] = {
                        'min': int(np.percentile(high_quality_steps, 25)),
                        'max': int(np.percentile(high_quality_steps, 75)),
                        'optimal': int(np.median(high_quality_steps))
                    }

            # Analyze CFG
            if self.parameter_patterns['cfg']:
                cfg_data = self.parameter_patterns['cfg']
                high_quality_cfg = [cfg for cfg, score in cfg_data if score > 0.8]
                if high_quality_cfg:
                    self.optimal_params['cfg'] = {
                        'min': np.percentile(high_quality_cfg, 25),
                        'max': np.percentile(high_quality_cfg, 75),
                        'optimal': np.median(high_quality_cfg)
                    }

            # Analyze samplers
            if self.parameter_patterns['sampler']:
                sampler_scores = defaultdict(list)
                for sampler, score in self.parameter_patterns['sampler']:
                    sampler_scores[sampler].append(score)

                best_sampler = max(sampler_scores.items(), key=lambda x: np.mean(x[1]))
                self.optimal_params['sampler'] = best_sampler[0]

            logger.info(f"Optimal parameters found: {self.optimal_params}")

        except Exception as e:
            logger.error(f"Error finding optimal parameter ranges: {e}")

    async def analyze_prompt_patterns(self, successful_data: List[Dict], failed_data: List[Dict]):
        """Analyze prompt patterns for improvement suggestions"""
        try:
            # Extract prompts
            successful_prompts = []
            failed_prompts = []

            for item in successful_data:
                if item.get('event_data'):
                    event_data = json.loads(item['event_data']) if isinstance(item['event_data'], str) else item['event_data']
                    prompt = event_data.get('prompt', '')
                    if prompt:
                        successful_prompts.append(prompt)

            for item in failed_data:
                if item.get('event_data'):
                    event_data = json.loads(item['event_data']) if isinstance(item['event_data'], str) else item['event_data']
                    prompt = event_data.get('prompt', '')
                    if prompt:
                        failed_prompts.append(prompt)

            # Analyze keyword patterns
            await self.analyze_keyword_patterns(successful_prompts, failed_prompts)
            await self.analyze_style_patterns(successful_prompts)

            logger.info("Prompt patterns analyzed")

        except Exception as e:
            logger.error(f"Error analyzing prompt patterns: {e}")

    async def analyze_keyword_patterns(self, successful_prompts: List[str], failed_prompts: List[str]):
        """Analyze keyword patterns in successful vs failed prompts"""
        try:
            # Extract keywords from successful prompts
            successful_keywords = Counter()
            for prompt in successful_prompts:
                keywords = self.extract_keywords(prompt)
                successful_keywords.update(keywords)

            # Extract keywords from failed prompts
            failed_keywords = Counter()
            for prompt in failed_prompts:
                keywords = self.extract_keywords(prompt)
                failed_keywords.update(keywords)

            # Find keywords that correlate with success
            self.success_keywords = {}
            for keyword, success_count in successful_keywords.items():
                if success_count >= 3:  # Minimum occurrences
                    failed_count = failed_keywords.get(keyword, 0)
                    total_count = success_count + failed_count
                    success_rate = success_count / total_count if total_count > 0 else 0

                    if success_rate > 0.7:  # High success rate
                        self.success_keywords[keyword] = {
                            'success_rate': success_rate,
                            'occurrences': success_count,
                            'category': self.categorize_keyword(keyword)
                        }

            logger.info(f"Found {len(self.success_keywords)} high-success keywords")

        except Exception as e:
            logger.error(f"Error analyzing keyword patterns: {e}")

    def extract_keywords(self, prompt: str) -> List[str]:
        """Extract keywords from prompt text"""
        # Remove common words and punctuation
        prompt = re.sub(r'[^\w\s]', ' ', prompt.lower())
        words = prompt.split()

        # Filter out common words
        stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did'}
        keywords = [word for word in words if word not in stop_words and len(word) > 2]

        return keywords

    def categorize_keyword(self, keyword: str) -> str:
        """Categorize keyword by type"""
        style_words = {'anime', 'manga', 'detailed', 'cinematic', 'masterpiece', 'high quality', 'photorealistic', '4k', '8k'}
        character_words = {'girl', 'boy', 'woman', 'man', 'warrior', 'mage', 'ninja', 'princess'}
        action_words = {'fighting', 'battle', 'running', 'jumping', 'flying', 'magic', 'sword', 'spell'}
        environment_words = {'forest', 'city', 'mountain', 'ocean', 'sky', 'temple', 'castle', 'street'}

        if keyword in style_words:
            return 'style'
        elif keyword in character_words:
            return 'character'
        elif keyword in action_words:
            return 'action'
        elif keyword in environment_words:
            return 'environment'
        else:
            return 'other'

    async def analyze_style_patterns(self, successful_prompts: List[str]):
        """Analyze style patterns in successful prompts"""
        try:
            style_patterns = defaultdict(int)

            for prompt in successful_prompts:
                # Look for style indicators
                if 'cinematic' in prompt.lower():
                    style_patterns['cinematic'] += 1
                if 'detailed' in prompt.lower():
                    style_patterns['detailed'] += 1
                if 'masterpiece' in prompt.lower():
                    style_patterns['masterpiece'] += 1
                if 'high quality' in prompt.lower():
                    style_patterns['high_quality'] += 1
                if 'photorealistic' in prompt.lower():
                    style_patterns['photorealistic'] += 1

            # Store successful style patterns
            self.successful_styles = dict(style_patterns)

            logger.info(f"Style patterns analyzed: {self.successful_styles}")

        except Exception as e:
            logger.error(f"Error analyzing style patterns: {e}")

    async def improve_prompt(self, original_prompt: str, quality_issues: List[str] = None) -> str:
        """Improve a prompt based on learned patterns"""
        try:
            improved_prompt = original_prompt

            # Add successful keywords if missing
            improved_prompt = await self.add_successful_keywords(improved_prompt)

            # Fix specific quality issues
            if quality_issues:
                improved_prompt = await self.fix_quality_issues_in_prompt(improved_prompt, quality_issues)

            # Add style improvements
            improved_prompt = await self.add_style_improvements(improved_prompt)

            # Use Echo Brain for final enhancement
            improved_prompt = await self.enhance_with_echo_brain(improved_prompt, quality_issues)

            return improved_prompt

        except Exception as e:
            logger.error(f"Error improving prompt: {e}")
            return original_prompt

    async def add_successful_keywords(self, prompt: str) -> str:
        """Add successful keywords to prompt"""
        try:
            if not hasattr(self, 'success_keywords'):
                return prompt

            current_keywords = set(self.extract_keywords(prompt))

            # Find high-value keywords not in prompt
            missing_keywords = []
            for keyword, data in self.success_keywords.items():
                if keyword not in current_keywords and data['success_rate'] > 0.8:
                    missing_keywords.append((keyword, data['success_rate']))

            # Add top missing keywords
            missing_keywords.sort(key=lambda x: x[1], reverse=True)
            top_missing = missing_keywords[:3]  # Add top 3

            for keyword, _ in top_missing:
                if keyword not in prompt.lower():
                    prompt = f"{prompt}, {keyword}"

            return prompt

        except Exception as e:
            logger.error(f"Error adding successful keywords: {e}")
            return prompt

    async def fix_quality_issues_in_prompt(self, prompt: str, quality_issues: List[str]) -> str:
        """Fix specific quality issues in prompt"""
        try:
            for issue in quality_issues:
                issue_lower = issue.lower()

                if 'resolution' in issue_lower or 'quality' in issue_lower:
                    if 'high quality' not in prompt.lower():
                        prompt = f"{prompt}, high quality, detailed"

                if 'blur' in issue_lower:
                    if 'sharp' not in prompt.lower():
                        prompt = f"{prompt}, sharp focus, crisp details"

                if 'contrast' in issue_lower:
                    if 'contrast' not in prompt.lower():
                        prompt = f"{prompt}, high contrast, vivid colors"

                if 'brightness' in issue_lower:
                    if 'lighting' not in prompt.lower():
                        prompt = f"{prompt}, well-lit, proper lighting"

            return prompt

        except Exception as e:
            logger.error(f"Error fixing quality issues in prompt: {e}")
            return prompt

    async def add_style_improvements(self, prompt: str) -> str:
        """Add style improvements based on successful patterns"""
        try:
            if not hasattr(self, 'successful_styles'):
                return prompt

            # Add most successful style elements
            for style, count in self.successful_styles.items():
                if count >= 5 and style.replace('_', ' ') not in prompt.lower():
                    style_text = style.replace('_', ' ')
                    prompt = f"{prompt}, {style_text}"

            return prompt

        except Exception as e:
            logger.error(f"Error adding style improvements: {e}")
            return prompt

    async def enhance_with_echo_brain(self, prompt: str, quality_issues: List[str] = None) -> str:
        """Use Echo Brain for final prompt enhancement"""
        try:
            enhancement_query = f"Enhance this anime prompt for better quality: {prompt}"

            if quality_issues:
                enhancement_query += f". Fix these quality issues: {', '.join(quality_issues)}"

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.echo_brain_url}/api/query", json={
                    "query": enhancement_query,
                    "context": "anime_prompt_enhancement"
                }) as response:

                    if response.status == 200:
                        result = await response.json()
                        enhanced_prompt = result.get('response', prompt)

                        # Validate enhanced prompt isn't too different
                        if len(enhanced_prompt) < len(prompt) * 2:  # Reasonable length
                            return enhanced_prompt

        except Exception as e:
            logger.error(f"Error enhancing with Echo Brain: {e}")

        return prompt

    async def suggest_optimal_parameters(self, prompt: str) -> Dict:
        """Suggest optimal parameters based on learned patterns"""
        try:
            suggestions = {}

            if hasattr(self, 'optimal_params'):
                # Use learned optimal parameters
                suggestions.update(self.optimal_params)

            # Adjust based on prompt content
            prompt_lower = prompt.lower()

            if 'detailed' in prompt_lower or 'high quality' in prompt_lower:
                suggestions['steps'] = max(suggestions.get('steps', {}).get('optimal', 30), 40)
                suggestions['cfg'] = max(suggestions.get('cfg', {}).get('optimal', 7.5), 8.5)

            if 'cinematic' in prompt_lower:
                suggestions['resolution'] = (1024, 1024)
                suggestions['sampler'] = 'dpmpp_2m'

            return suggestions

        except Exception as e:
            logger.error(f"Error suggesting optimal parameters: {e}")
            return {}

    async def learn_from_quality_feedback(self, prompt_id: str, prompt: str, workflow_params: Dict, quality_result: Dict):
        """Learn from new quality feedback"""
        try:
            quality_score = quality_result.get('quality_score', 0)
            passes_standards = quality_result.get('passes_standards', False)

            prompt_hash = hashlib.md5(prompt.encode()).hexdigest()

            if passes_standards and quality_score > 0.8:
                # Store successful pattern
                await self.store_successful_pattern(prompt_hash, prompt, workflow_params, quality_score)

                # Update learned patterns
                self.extract_parameter_patterns(workflow_params, quality_score)

            elif not passes_standards:
                # Store failed pattern
                rejection_reasons = quality_result.get('rejection_reasons', [])
                await self.store_failed_pattern(prompt_hash, prompt, workflow_params, rejection_reasons)

            # Periodically retrain models
            if len(self.parameter_patterns.get('steps', [])) % 10 == 0:
                await self.retrain_models()

            logger.info(f"Learned from quality feedback: {prompt_id} (score: {quality_score})")

        except Exception as e:
            logger.error(f"Error learning from quality feedback: {e}")

    async def store_successful_pattern(self, prompt_hash: str, prompt: str, workflow_params: Dict, quality_score: float):
        """Store successful pattern for learning"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO learning_successful_patterns (prompt_hash, prompt_text, workflow_params, quality_score, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (prompt_hash) DO UPDATE SET
                    quality_score = EXCLUDED.quality_score,
                    workflow_params = EXCLUDED.workflow_params,
                    updated_at = NOW()
                WHERE learning_successful_patterns.quality_score < EXCLUDED.quality_score
            """, (
                prompt_hash,
                prompt,
                json.dumps(workflow_params),
                quality_score,
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error storing successful pattern: {e}")

    async def store_failed_pattern(self, prompt_hash: str, prompt: str, workflow_params: Dict, rejection_reasons: List[str]):
        """Store failed pattern for learning"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO learning_failed_patterns (prompt_hash, prompt_text, workflow_params, rejection_reasons, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                prompt_hash,
                prompt,
                json.dumps(workflow_params),
                json.dumps(rejection_reasons),
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error storing failed pattern: {e}")

    async def retrain_models(self):
        """Retrain learning models with new data"""
        try:
            logger.info("Retraining learning models...")

            # Reload data
            successful_data = await self.load_successful_generations()
            failed_data = await self.load_failed_generations()

            # Reanalyze patterns
            await self.analyze_quality_patterns(successful_data, failed_data)
            await self.analyze_parameter_patterns(successful_data)
            await self.analyze_prompt_patterns(successful_data, failed_data)

            logger.info("Learning models retrained successfully")

        except Exception as e:
            logger.error(f"Error retraining models: {e}")

    async def get_learning_statistics(self) -> Dict:
        """Get learning system statistics"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Get successful patterns count
            cur.execute("SELECT COUNT(*) as count FROM learning_successful_patterns")
            successful_count = cur.fetchone()['count']

            # Get failed patterns count
            cur.execute("SELECT COUNT(*) as count FROM learning_failed_patterns")
            failed_count = cur.fetchone()['count']

            # Get average quality improvement
            cur.execute("""
                SELECT AVG(quality_score) as avg_quality
                FROM learning_successful_patterns
                WHERE created_at > NOW() - INTERVAL '7 days'
            """)
            recent_quality = cur.fetchone()['avg_quality'] or 0

            cur.close()
            conn.close()

            return {
                'successful_patterns': successful_count,
                'failed_patterns': failed_count,
                'recent_average_quality': float(recent_quality),
                'learned_keywords': len(getattr(self, 'success_keywords', {})),
                'optimal_parameters': len(getattr(self, 'optimal_params', {})),
                'learning_enabled': True
            }

        except Exception as e:
            logger.error(f"Error getting learning statistics: {e}")
            return {}

# Database table creation
async def create_learning_tables():
    """Create tables for learning system"""
    try:
        conn = psycopg2.connect(
            host='localhost',
            database='tower_consolidated',
            user='patrick',
            password=''
        )
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS learning_successful_patterns (
                id SERIAL PRIMARY KEY,
                prompt_hash VARCHAR(32) UNIQUE,
                prompt_text TEXT,
                workflow_params JSONB,
                quality_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS learning_failed_patterns (
                id SERIAL PRIMARY KEY,
                prompt_hash VARCHAR(32),
                prompt_text TEXT,
                workflow_params JSONB,
                rejection_reasons JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS learning_improvements (
                id SERIAL PRIMARY KEY,
                original_prompt TEXT,
                improved_prompt TEXT,
                improvement_type VARCHAR(50),
                quality_improvement FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_learning_successful_hash ON learning_successful_patterns(prompt_hash);
            CREATE INDEX IF NOT EXISTS idx_learning_failed_hash ON learning_failed_patterns(prompt_hash);
            CREATE INDEX IF NOT EXISTS idx_learning_improvements_type ON learning_improvements(improvement_type);
        """)

        conn.commit()
        cur.close()
        conn.close()
        logger.info("Learning system tables created/verified")

    except Exception as e:
        logger.error(f"Error creating learning tables: {e}")

async def main():
    """Main entry point for testing"""
    await create_learning_tables()

    # Test learning system
    learning_system = AnimeLearningSystem()

    # Test prompt improvement
    original_prompt = "anime girl"
    improved_prompt = await learning_system.improve_prompt(original_prompt, ["Resolution too low", "Overall quality too low"])
    print(f"Original: {original_prompt}")
    print(f"Improved: {improved_prompt}")

    # Test parameter suggestions
    suggestions = await learning_system.suggest_optimal_parameters(improved_prompt)
    print(f"Parameter suggestions: {suggestions}")

    # Get statistics
    stats = await learning_system.get_learning_statistics()
    print(f"Learning statistics: {stats}")

if __name__ == "__main__":
    asyncio.run(main())