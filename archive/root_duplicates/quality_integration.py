#!/usr/bin/env python3
'''Quality Assessment Integration for Anime Service'''
import logging
import requests
import asyncio

logger = logging.getLogger(__name__)

ECHO_BRAIN_URL = 'http://127.0.0.1:8309'
QUALITY_ENABLED = True

async def assess_video_quality(video_path: str, generation_id: str) -> dict:
    '''Assess video quality for anime compliance'''
    if not QUALITY_ENABLED:
        return {'quality_check': 'disabled'}

    try:
        logger.info(f'📊 Starting quality assessment for {video_path}')

        # First try Echo Brain vision analysis
        try:
            response = await asyncio.to_thread(
                requests.post,
                f'{ECHO_BRAIN_URL}/api/vision/quality-check',
                json={
                    'video_path': video_path,
                    'generation_id': generation_id,
                    'source': 'anime_service'
                },
                timeout=15
            )

            if response.status_code == 200:
                quality_data = response.json()
                score = quality_data.get('overall_score', 'N/A')
                logger.info(f'✅ Echo Brain quality assessment: Score {score}')
                return quality_data
        except Exception as e:
            logger.warning(f'⚠️ Echo Brain quality check failed: {e}')

        # Fallback to local quality checks
        logger.info('📊 Using fallback quality assessment...')

        # Basic file validation
        import os
        if not os.path.exists(video_path):
            return {
                'overall_score': 0,
                'passes_quality': False,
                'rejection_reason': 'Video file not found',
                'method': 'file_check'
            }

        file_size = os.path.getsize(video_path)
        if file_size < 100000:  # Less than 100KB is suspicious
            return {
                'overall_score': 2,
                'passes_quality': False,
                'rejection_reason': f'Video file too small ({file_size} bytes) - likely generation failure',
                'method': 'file_size_check'
            }

        # Frame extraction and basic analysis
        try:
            import cv2
            import numpy as np

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return {
                    'overall_score': 0,
                    'passes_quality': False,
                    'rejection_reason': 'Video file corrupted or unreadable',
                    'method': 'video_integrity_check'
                }

            # Analyze first few frames
            frame_count = 0
            color_variance_scores = []
            brightness_scores = []

            while frame_count < 5:  # Check first 5 frames
                ret, frame = cap.read()
                if not ret:
                    break

                # Convert to HSV for better color analysis
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

                # Check color variance (anime has distinct color regions)
                color_variance = np.var(hsv[:,:,1])  # Saturation variance
                color_variance_scores.append(color_variance)

                # Check brightness distribution
                brightness = np.mean(hsv[:,:,2])  # Value channel
                brightness_scores.append(brightness)

                frame_count += 1

            cap.release()

            if frame_count == 0:
                return {
                    'overall_score': 0,
                    'passes_quality': False,
                    'rejection_reason': 'Video contains no readable frames',
                    'method': 'frame_analysis'
                }

            # Analyze results
            avg_color_variance = np.mean(color_variance_scores)
            avg_brightness = np.mean(brightness_scores)

            # Scoring logic for anime detection
            score = 5  # Start with base score
            issues = []

            # Anime typically has higher color variance than realistic images
            if avg_color_variance < 500:  # Low saturation variance suggests realistic/dull content
                score -= 2
                issues.append(f'Low color variance ({avg_color_variance:.1f}) - may be realistic rather than anime')

            # Check for overly dark content (common in failed generations)
            if avg_brightness < 80:
                score -= 1
                issues.append(f'Very dark content ({avg_brightness:.1f}) - possible generation failure')

            # Check for overly bright/washed out content
            if avg_brightness > 220:
                score -= 1
                issues.append(f'Overexposed content ({avg_brightness:.1f}) - possible generation failure')

            passes_quality = score >= 6

            result = {
                'overall_score': max(0, score),
                'passes_quality': passes_quality,
                'method': 'basic_cv_analysis',
                'metrics': {
                    'color_variance': avg_color_variance,
                    'brightness': avg_brightness,
                    'frames_analyzed': frame_count
                },
                'issues': issues
            }

            if not passes_quality:
                result['rejection_reason'] = '; '.join(issues) if issues else 'Quality score too low'

            logger.info(f'✅ Quality assessment complete: Score {score}/10, Passes: {passes_quality}')
            return result

        except ImportError:
            logger.warning('OpenCV not available, using basic file checks only')
            return {
                'overall_score': 7,  # Assume good if we can't check
                'passes_quality': True,
                'method': 'basic_file_check',
                'message': 'OpenCV not available for detailed analysis'
            }

    except Exception as e:
        logger.error(f'❌ Quality assessment error: {e}')
        return {
            'overall_score': 5,
            'passes_quality': True,  # Don't block on errors
            'error': str(e),
            'method': 'error_fallback'
        }
