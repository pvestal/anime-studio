#!/usr/bin/env python3
"""
Echo Brain Quality Review Service - Learning Loop for Generation Quality
========================================================================
This service:
1. Runs contract tests on generated content
2. Records results to database with full parameter tracking
3. Asks Echo Brain (via Ollama) to analyze patterns in successes/failures
4. Learns which prompt elements and parameters correlate with quality
5. Provides recommendations for future generations

This creates a feedback loop where every generation makes the system smarter.
"""

import os
import json
import logging
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import requests

from video_contract import VideoQualityContract, ContractResult

logger = logging.getLogger("echo_brain_reviewer")
logging.basicConfig(level=logging.INFO)


class EchoBrainQualityReviewer:
    """Reviews generation quality and learns patterns over time."""

    def __init__(self):
        self.contract = VideoQualityContract()
        self.db_config = {
            'host': os.getenv('PG_HOST', 'localhost'),
            'port': int(os.getenv('PG_PORT', '5432')),
            'user': os.getenv('PG_USER', 'patrick'),
            'password': os.getenv('PG_PASSWORD', 'RP78eIrW7cI2jYvL5akt1yurE'),
            'database': os.getenv('PG_DATABASE', 'anime_production')
        }
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.echo_brain_url = os.getenv('ECHO_BRAIN_URL', 'http://localhost:8309')

        # Ensure database schema exists
        self._ensure_schema()

    def _ensure_schema(self):
        """Create the quality feedback table if it doesn't exist."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS generation_quality_feedback (
            id                  SERIAL PRIMARY KEY,
            generation_id       INTEGER,
            prompt_id           TEXT UNIQUE,
            project             TEXT NOT NULL,
            character_id        TEXT,

            -- Generation parameters
            checkpoint          TEXT,
            lora_name           TEXT,
            lora_strength       FLOAT,
            prompt_positive     TEXT,
            prompt_negative     TEXT,
            sampler             TEXT,
            steps               INTEGER,
            cfg                 FLOAT,
            batch_size          INTEGER,
            seed                BIGINT,
            width               INTEGER,
            height              INTEGER,
            workflow_name       TEXT,

            -- Contract results
            contract_passed     BOOLEAN NOT NULL,
            quality_score       FLOAT NOT NULL,
            structural_results  JSONB,
            motion_results      JSONB,
            quality_results     JSONB,
            frame_samples       TEXT[],
            recommendations     TEXT[],

            -- Learned patterns (populated by Echo Brain analysis)
            successful_elements TEXT[],
            failed_elements     TEXT[],
            analysis_notes      TEXT,

            -- File info
            output_path         TEXT,
            file_size_kb        FLOAT,
            duration_seconds    FLOAT,
            frame_count         INTEGER,

            -- Human override (optional)
            human_score         FLOAT,
            human_notes         TEXT,

            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_quality_project ON generation_quality_feedback(project);
        CREATE INDEX IF NOT EXISTS idx_quality_score ON generation_quality_feedback(quality_score DESC);
        CREATE INDEX IF NOT EXISTS idx_quality_checkpoint ON generation_quality_feedback(checkpoint);
        CREATE INDEX IF NOT EXISTS idx_quality_prompt_id ON generation_quality_feedback(prompt_id);
        CREATE INDEX IF NOT EXISTS idx_quality_passed ON generation_quality_feedback(contract_passed);
        """

        with psycopg2.connect(**self.db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(create_table_sql)
                conn.commit()
                logger.info("Database schema verified")

    def review_generation(self,
                          prompt_id: str,
                          output_path: str,
                          generation_params: Dict[str, Any],
                          project: str = "unknown") -> Dict[str, Any]:
        """
        Review a generated output using quality contract and record results.

        Args:
            prompt_id: ComfyUI prompt ID
            output_path: Path to generated file
            generation_params: All parameters used for generation
            project: Project name (tokyo, cyberpunk, etc.)

        Returns:
            Dict with review results and recommendations
        """
        logger.info(f"Reviewing generation {prompt_id}: {output_path}")

        # Run contract validation
        contract_result = self.contract.validate(output_path, generation_params)

        # Extract key metrics
        file_stats = self._get_file_stats(output_path)

        # Prepare database record
        record = {
            'prompt_id': prompt_id,
            'project': project,
            'character_id': generation_params.get('character_id'),
            'checkpoint': generation_params.get('checkpoint', generation_params.get('model')),
            'lora_name': generation_params.get('lora_name'),
            'lora_strength': generation_params.get('lora_strength'),
            'prompt_positive': generation_params.get('positive_prompt', generation_params.get('prompt')),
            'prompt_negative': generation_params.get('negative_prompt'),
            'sampler': generation_params.get('sampler', 'euler'),
            'steps': generation_params.get('steps', 20),
            'cfg': generation_params.get('cfg', 7.0),
            'batch_size': generation_params.get('batch_size', 1),
            'seed': generation_params.get('seed'),
            'width': generation_params.get('width', 512),
            'height': generation_params.get('height', 512),
            'workflow_name': generation_params.get('workflow'),
            'contract_passed': contract_result.passed,
            'quality_score': contract_result.quality_score,
            'structural_results': Json({k: {
                'passed': bool(v.passed),
                'value': float(v.value) if isinstance(v.value, (int, float, np.number)) else str(v.value),
                'threshold': str(v.threshold),
                'details': str(v.details)
            } for k, v in contract_result.structural_gates.items()}),
            'motion_results': Json({k: {
                'passed': bool(v.passed),
                'value': float(v.value) if isinstance(v.value, (int, float, np.number)) else str(v.value),
                'threshold': str(v.threshold),
                'details': str(v.details)
            } for k, v in contract_result.motion_gates.items()}),
            'quality_results': Json({k: {
                'passed': bool(v.passed),
                'value': float(v.value) if isinstance(v.value, (int, float, np.number)) else str(v.value),
                'threshold': str(v.threshold),
                'details': str(v.details)
            } for k, v in contract_result.quality_gates.items()}),
            'frame_samples': contract_result.frame_samples,
            'recommendations': contract_result.recommendations,
            'output_path': output_path,
            'file_size_kb': file_stats['size_kb'],
            'duration_seconds': file_stats.get('duration'),
            'frame_count': file_stats.get('frames')
        }

        # Store in database
        record_id = self._store_feedback(record)

        # Analyze patterns with Echo Brain
        learned_patterns = self._analyze_patterns(project, prompt_id)

        # Update record with learned patterns
        if learned_patterns:
            self._update_learned_patterns(record_id, learned_patterns)
            record.update(learned_patterns)

        # Return comprehensive review
        return {
            'prompt_id': prompt_id,
            'passed': contract_result.passed,
            'quality_score': contract_result.quality_score,
            'structural_gates': {k: v.passed for k, v in contract_result.structural_gates.items()},
            'motion_gates': {k: v.passed for k, v in contract_result.motion_gates.items()},
            'quality_gates': {k: v.passed for k, v in contract_result.quality_gates.items()},
            'recommendations': contract_result.recommendations,
            'learned_patterns': learned_patterns,
            'frame_samples': contract_result.frame_samples
        }

    def _get_file_stats(self, file_path: str) -> Dict[str, Any]:
        """Extract file statistics."""
        stats = {
            'size_kb': os.path.getsize(file_path) / 1024 if os.path.exists(file_path) else 0
        }

        # Try to get video stats
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {'.mp4', '.webm', '.avi', '.mov'}:
            import subprocess
            try:
                result = subprocess.run([
                    'ffprobe', '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=nb_frames,duration',
                    '-of', 'json', file_path
                ], capture_output=True, text=True, timeout=5)

                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    stream = data.get('streams', [{}])[0]
                    stats['frames'] = int(stream.get('nb_frames', 0))
                    stats['duration'] = float(stream.get('duration', 0))
            except:
                pass

        return stats

    def _store_feedback(self, record: Dict) -> int:
        """Store feedback record in database."""
        columns = list(record.keys())
        values = list(record.values())
        placeholders = ', '.join(['%s'] * len(columns))
        column_str = ', '.join(columns)

        insert_sql = f"""
        INSERT INTO generation_quality_feedback ({column_str})
        VALUES ({placeholders})
        ON CONFLICT (prompt_id) DO UPDATE SET
            quality_score = EXCLUDED.quality_score,
            structural_results = EXCLUDED.structural_results,
            motion_results = EXCLUDED.motion_results,
            quality_results = EXCLUDED.quality_results,
            updated_at = NOW()
        RETURNING id
        """

        with psycopg2.connect(**self.db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(insert_sql, values)
                record_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Stored quality feedback record {record_id}")
                return record_id

    def _analyze_patterns(self, project: str, current_prompt_id: str) -> Dict[str, Any]:
        """
        Use Echo Brain + Ollama to analyze patterns in generation quality.
        """
        logger.info(f"Analyzing quality patterns for project {project}")

        # Get recent generations for this project
        with psycopg2.connect(**self.db_config) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get top 5 best and worst recent generations
                cur.execute("""
                    (SELECT * FROM generation_quality_feedback
                     WHERE project = %s AND prompt_id != %s
                     ORDER BY quality_score DESC, created_at DESC
                     LIMIT 5)
                    UNION ALL
                    (SELECT * FROM generation_quality_feedback
                     WHERE project = %s AND prompt_id != %s AND quality_score < 0.5
                     ORDER BY quality_score ASC, created_at DESC
                     LIMIT 5)
                    ORDER BY quality_score DESC
                """, (project, current_prompt_id, project, current_prompt_id))

                history = cur.fetchall()

        if len(history) < 3:
            logger.info("Not enough history for pattern analysis")
            return {}

        # Prepare analysis prompt for Ollama
        analysis_prompt = self._build_analysis_prompt(history)

        try:
            # Call Ollama for analysis
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    'model': 'qwen2.5:14b',
                    'prompt': analysis_prompt,
                    'stream': False,
                    'temperature': 0.3
                },
                timeout=30
            )

            if response.status_code == 200:
                analysis = response.json().get('response', '')
                return self._parse_analysis(analysis)
            else:
                logger.error(f"Ollama analysis failed: {response.status_code}")
                return {}

        except Exception as e:
            logger.error(f"Pattern analysis failed: {e}")
            return {}

    def _build_analysis_prompt(self, history: List[Dict]) -> str:
        """Build prompt for Ollama to analyze generation patterns."""

        good_examples = []
        bad_examples = []

        for gen in history:
            summary = {
                'score': gen['quality_score'],
                'passed': gen['contract_passed'],
                'prompt': (gen.get('prompt_positive') or '')[:200],
                'checkpoint': gen.get('checkpoint'),
                'steps': gen.get('steps'),
                'cfg': gen.get('cfg'),
                'batch_size': gen.get('batch_size'),
                'issues': gen.get('recommendations', [])
            }

            if gen['quality_score'] >= 0.7:
                good_examples.append(summary)
            elif gen['quality_score'] < 0.5:
                bad_examples.append(summary)

        prompt = f"""Analyze these anime generation results to identify patterns.

SUCCESSFUL GENERATIONS (score >= 0.7):
{json.dumps(good_examples, indent=2)}

FAILED GENERATIONS (score < 0.5):
{json.dumps(bad_examples, indent=2)}

Based on these results, identify:
1. Which prompt elements appear in successful but not failed generations
2. Which parameters (steps, cfg, batch_size) correlate with success
3. Common issues in failed generations

Respond in JSON format:
{{
  "successful_elements": ["list", "of", "positive", "patterns"],
  "failed_elements": ["list", "of", "negative", "patterns"],
  "recommended_params": {{"steps": N, "cfg": N, "batch_size": N}},
  "analysis_notes": "Brief explanation of patterns found"
}}
"""
        return prompt

    def _parse_analysis(self, analysis_text: str) -> Dict[str, Any]:
        """Parse Ollama's analysis response."""
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', analysis_text)
            if json_match:
                return json.loads(json_match.group())
            else:
                # Fallback: extract key phrases
                return {
                    'successful_elements': [],
                    'failed_elements': [],
                    'analysis_notes': analysis_text[:500]
                }
        except Exception as e:
            logger.error(f"Failed to parse analysis: {e}")
            return {
                'successful_elements': [],
                'failed_elements': [],
                'analysis_notes': f"Analysis available but unparseable: {analysis_text[:200]}"
            }

    def _update_learned_patterns(self, record_id: int, patterns: Dict):
        """Update database record with learned patterns."""
        update_sql = """
        UPDATE generation_quality_feedback
        SET successful_elements = %s,
            failed_elements = %s,
            analysis_notes = %s,
            updated_at = NOW()
        WHERE id = %s
        """

        with psycopg2.connect(**self.db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(update_sql, (
                    patterns.get('successful_elements', []),
                    patterns.get('failed_elements', []),
                    patterns.get('analysis_notes', ''),
                    record_id
                ))
                conn.commit()

    def get_learned_elements(self, project: str) -> Dict[str, List[str]]:
        """
        Get learned successful and failed elements for a project.
        This is used to improve future generations.
        """
        with psycopg2.connect(**self.db_config) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        ARRAY_AGG(DISTINCT elem) FILTER (WHERE elem IS NOT NULL) as elements
                    FROM (
                        SELECT unnest(successful_elements) as elem
                        FROM generation_quality_feedback
                        WHERE project = %s AND quality_score > 0.7
                        ORDER BY created_at DESC
                        LIMIT 20
                    ) t
                """, (project,))

                successful = cur.fetchone()['elements'] or []

                cur.execute("""
                    SELECT
                        ARRAY_AGG(DISTINCT elem) FILTER (WHERE elem IS NOT NULL) as elements
                    FROM (
                        SELECT unnest(failed_elements) as elem
                        FROM generation_quality_feedback
                        WHERE project = %s AND quality_score < 0.5
                        ORDER BY created_at DESC
                        LIMIT 20
                    ) t
                """, (project,))

                failed = cur.fetchone()['elements'] or []

        return {
            'successful_elements': successful,
            'failed_elements': failed
        }

    def get_project_stats(self, project: str) -> Dict[str, Any]:
        """Get quality statistics for a project."""
        with psycopg2.connect(**self.db_config) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total_generations,
                        AVG(quality_score) as avg_quality,
                        SUM(CASE WHEN contract_passed THEN 1 ELSE 0 END) as passed_count,
                        MAX(quality_score) as best_score,
                        MIN(quality_score) as worst_score,
                        AVG(CASE WHEN duration_seconds > 0 THEN duration_seconds END) as avg_duration,
                        AVG(frame_count) as avg_frames
                    FROM generation_quality_feedback
                    WHERE project = %s
                """, (project,))

                stats = cur.fetchone()

                # Get most successful parameters
                cur.execute("""
                    SELECT
                        checkpoint,
                        AVG(quality_score) as avg_score,
                        COUNT(*) as usage_count
                    FROM generation_quality_feedback
                    WHERE project = %s AND quality_score > 0.5
                    GROUP BY checkpoint
                    ORDER BY avg_score DESC
                    LIMIT 3
                """, (project,))

                best_checkpoints = cur.fetchall()

        return {
            'stats': dict(stats) if stats else {},
            'best_checkpoints': [dict(c) for c in best_checkpoints]
        }


# API endpoints for Echo Brain integration
class QualityReviewAPI:
    """REST API for quality review service."""

    def __init__(self, reviewer: EchoBrainQualityReviewer):
        self.reviewer = reviewer

    def review_endpoint(self, request_data: Dict) -> Dict:
        """POST /api/quality/review"""
        prompt_id = request_data.get('prompt_id')
        output_path = request_data.get('output_path')
        generation_params = request_data.get('params', {})
        project = request_data.get('project', 'unknown')

        if not prompt_id or not output_path:
            return {'error': 'prompt_id and output_path required'}, 400

        result = self.reviewer.review_generation(
            prompt_id, output_path, generation_params, project
        )
        return result

    def learned_elements_endpoint(self, project: str) -> Dict:
        """GET /api/quality/learned/{project}"""
        return self.reviewer.get_learned_elements(project)

    def stats_endpoint(self, project: str) -> Dict:
        """GET /api/quality/stats/{project}"""
        return self.reviewer.get_project_stats(project)


if __name__ == "__main__":
    import sys

    reviewer = EchoBrainQualityReviewer()

    if len(sys.argv) < 3:
        print("Usage: python echo_brain_reviewer.py <prompt_id> <output_path> [project]")
        sys.exit(1)

    prompt_id = sys.argv[1]
    output_path = sys.argv[2]
    project = sys.argv[3] if len(sys.argv) > 3 else "test"

    # Mock generation params for testing
    params = {
        'checkpoint': 'realistic_vision_v51.safetensors',
        'positive_prompt': '1girl, portrait, high quality',
        'steps': 20,
        'cfg': 7.0,
        'batch_size': 16,
        'width': 512,
        'height': 512
    }

    result = reviewer.review_generation(prompt_id, output_path, params, project)

    print(f"\n{'='*60}")
    print(f"QUALITY REVIEW RESULT")
    print(f"{'='*60}")
    print(f"Passed: {'✅' if result['passed'] else '❌'}")
    print(f"Quality Score: {result['quality_score']:.2f}")
    print(f"\nRecommendations:")
    for rec in result.get('recommendations', []):
        print(f"  • {rec}")

    if result.get('learned_patterns'):
        print(f"\nLearned Patterns:")
        print(f"  Successful: {result['learned_patterns'].get('successful_elements', [])}")
        print(f"  Failed: {result['learned_patterns'].get('failed_elements', [])}")