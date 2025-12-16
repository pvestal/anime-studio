#!/usr/bin/env python3
"""
Anime Quality Gates Test Runner
Orchestrates all four quality gates for comprehensive anime production testing
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from pydantic import BaseModel

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gate_1_asset_readiness import Gate1AssetReadinessChecker
from gate_2_frame_generation import Gate2FrameQualityChecker
from gate_3_temporal_consistency import Gate3TemporalChecker
from gate_4_final_video import Gate4FinalVideoChecker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProductionTestConfig(BaseModel):
    """Configuration for production pipeline test"""
    # Gate 1: Asset Readiness
    required_assets: List[str]
    asset_paths: List[str]

    # Gate 2: Frame Generation
    frame_paths: List[str]
    character_name: str
    generation_prompt: str

    # Gate 3: Temporal Consistency
    frame_sequence: List[str]
    sequence_name: str

    # Gate 4: Final Video
    video_path: str
    intended_story: str
    audio_path: Optional[str] = None
    dialogue_timestamps: Optional[List[Dict]] = None
    scene_description: Optional[str] = None

class QualityGatesTestRunner:
    """Main orchestrator for all anime production quality gates"""

    def __init__(self, project_root: Path, echo_brain_url: str = "http://localhost:8309"):
        self.project_root = Path(project_root)
        self.echo_brain_url = echo_brain_url

        # Initialize all gate checkers
        self.gate1_checker = Gate1AssetReadinessChecker(project_root, echo_brain_url)
        self.gate2_checker = Gate2FrameQualityChecker(project_root, echo_brain_url)
        self.gate3_checker = Gate3TemporalChecker(project_root, echo_brain_url)
        self.gate4_checker = Gate4FinalVideoChecker(project_root, echo_brain_url)

        # Create results directory
        (self.project_root / "quality" / "comprehensive_results").mkdir(parents=True, exist_ok=True)

    async def run_all_gates(self, config: ProductionTestConfig,
                          parallel_execution: bool = False) -> Dict:
        """
        Run all quality gates for a complete production pipeline test

        Args:
            config: Test configuration with all required parameters
            parallel_execution: If True, run gates in parallel (faster but uses more resources)

        Returns:
            Comprehensive test results with overall pass/fail status
        """
        logger.info("🎬 Starting Comprehensive Anime Production Quality Gates Test")
        logger.info("=" * 80)

        start_time = datetime.now()

        # Validate configuration
        validation_errors = await self._validate_config(config)
        if validation_errors:
            logger.error("❌ Configuration validation failed:")
            for error in validation_errors:
                logger.error(f"   • {error}")

            return {
                "overall_pass": False,
                "error": "Configuration validation failed",
                "validation_errors": validation_errors,
                "timestamp": start_time.isoformat()
            }

        try:
            if parallel_execution:
                results = await self._run_gates_parallel(config, start_time)
            else:
                results = await self._run_gates_sequential(config, start_time)

            # Generate comprehensive report
            report = await self._generate_comprehensive_report(results, config, start_time)

            # Log final results to Echo Brain
            await self._log_comprehensive_results(report)

            # Save comprehensive results
            await self._save_comprehensive_results(report)

            # Print summary
            self._print_test_summary(report)

            return report

        except Exception as e:
            logger.error(f"❌ Critical error during quality gates testing: {e}")

            error_report = {
                "overall_pass": False,
                "error": f"Critical error: {str(e)}",
                "timestamp": start_time.isoformat(),
                "duration_seconds": (datetime.now() - start_time).total_seconds()
            }

            await self._save_comprehensive_results(error_report)
            return error_report

    async def _run_gates_sequential(self, config: ProductionTestConfig, start_time: datetime) -> Dict:
        """Run quality gates sequentially (safer, uses less resources)"""
        logger.info("🔄 Running gates sequentially...")

        results = {}

        # Gate 1: Asset Readiness & Style Consistency
        logger.info("📋 Running Gate 1: Asset Readiness & Style Consistency")
        gate1_start = datetime.now()

        try:
            gate1_results = await self.gate1_checker.run_gate_1_tests(
                config.required_assets, config.asset_paths
            )
            results["gate_1"] = gate1_results
            gate1_duration = (datetime.now() - gate1_start).total_seconds()
            logger.info(f"✅ Gate 1 completed in {gate1_duration:.2f}s")
        except Exception as e:
            logger.error(f"❌ Gate 1 failed: {e}")
            results["gate_1"] = {"pass": False, "error": str(e)}

        # Gate 2: Frame Generation Quality
        logger.info("🖼️ Running Gate 2: Frame Generation Quality")
        gate2_start = datetime.now()

        try:
            gate2_results = await self.gate2_checker.run_gate_2_tests(
                config.frame_paths, config.character_name, config.generation_prompt
            )
            results["gate_2"] = gate2_results
            gate2_duration = (datetime.now() - gate2_start).total_seconds()
            logger.info(f"✅ Gate 2 completed in {gate2_duration:.2f}s")
        except Exception as e:
            logger.error(f"❌ Gate 2 failed: {e}")
            results["gate_2"] = {"pass": False, "error": str(e)}

        # Gate 3: Temporal Consistency & Motion Smoothness
        logger.info("⏱️ Running Gate 3: Temporal Consistency & Motion Smoothness")
        gate3_start = datetime.now()

        try:
            gate3_results = await self.gate3_checker.run_gate_3_tests(
                config.frame_sequence, config.sequence_name
            )
            results["gate_3"] = gate3_results
            gate3_duration = (datetime.now() - gate3_start).total_seconds()
            logger.info(f"✅ Gate 3 completed in {gate3_duration:.2f}s")
        except Exception as e:
            logger.error(f"❌ Gate 3 failed: {e}")
            results["gate_3"] = {"pass": False, "error": str(e)}

        # Gate 4: Final Video Quality & Sync
        logger.info("🎬 Running Gate 4: Final Video Quality & Sync")
        gate4_start = datetime.now()

        try:
            gate4_results = await self.gate4_checker.run_gate_4_tests(
                config.video_path,
                config.intended_story,
                config.audio_path,
                config.dialogue_timestamps,
                config.scene_description
            )
            results["gate_4"] = gate4_results
            gate4_duration = (datetime.now() - gate4_start).total_seconds()
            logger.info(f"✅ Gate 4 completed in {gate4_duration:.2f}s")
        except Exception as e:
            logger.error(f"❌ Gate 4 failed: {e}")
            results["gate_4"] = {"pass": False, "error": str(e)}

        return results

    async def _run_gates_parallel(self, config: ProductionTestConfig, start_time: datetime) -> Dict:
        """Run quality gates in parallel (faster but more resource intensive)"""
        logger.info("🚀 Running gates in parallel...")

        # Create all gate tasks
        gate1_task = self.gate1_checker.run_gate_1_tests(
            config.required_assets, config.asset_paths
        )

        gate2_task = self.gate2_checker.run_gate_2_tests(
            config.frame_paths, config.character_name, config.generation_prompt
        )

        gate3_task = self.gate3_checker.run_gate_3_tests(
            config.frame_sequence, config.sequence_name
        )

        gate4_task = self.gate4_checker.run_gate_4_tests(
            config.video_path,
            config.intended_story,
            config.audio_path,
            config.dialogue_timestamps,
            config.scene_description
        )

        # Run all gates in parallel with error handling
        tasks = [
            ("gate_1", gate1_task),
            ("gate_2", gate2_task),
            ("gate_3", gate3_task),
            ("gate_4", gate4_task)
        ]

        results = {}

        # Execute with individual error handling
        for gate_name, task in tasks:
            try:
                result = await task
                results[gate_name] = result
                logger.info(f"✅ {gate_name.replace('_', ' ').title()} completed")
            except Exception as e:
                logger.error(f"❌ {gate_name.replace('_', ' ').title()} failed: {e}")
                results[gate_name] = {"pass": False, "error": str(e)}

        return results

    async def _validate_config(self, config: ProductionTestConfig) -> List[str]:
        """Validate test configuration and check file existence"""
        errors = []

        # Validate asset paths for Gate 1
        for asset_path in config.asset_paths:
            if not os.path.exists(asset_path):
                errors.append(f"Asset file not found: {asset_path}")

        # Validate frame paths for Gate 2
        for frame_path in config.frame_paths:
            if not os.path.exists(frame_path):
                errors.append(f"Frame file not found: {frame_path}")

        # Validate frame sequence for Gate 3
        for frame_path in config.frame_sequence:
            if not os.path.exists(frame_path):
                errors.append(f"Sequence frame not found: {frame_path}")

        # Validate video file for Gate 4
        if not os.path.exists(config.video_path):
            errors.append(f"Video file not found: {config.video_path}")

        # Validate optional audio file for Gate 4
        if config.audio_path and not os.path.exists(config.audio_path):
            errors.append(f"Audio file not found: {config.audio_path}")

        # Check minimum requirements
        if len(config.frame_paths) < 1:
            errors.append("Need at least 1 frame for Gate 2 testing")

        if len(config.frame_sequence) < 2:
            errors.append("Need at least 2 frames for Gate 3 temporal consistency testing")

        if not config.character_name.strip():
            errors.append("Character name required for Gate 2 testing")

        if not config.generation_prompt.strip():
            errors.append("Generation prompt required for Gate 2 testing")

        if not config.intended_story.strip():
            errors.append("Intended story required for Gate 4 testing")

        return errors

    async def _generate_comprehensive_report(self, gate_results: Dict,
                                          config: ProductionTestConfig,
                                          start_time: datetime) -> Dict:
        """Generate comprehensive test report with overall status and recommendations"""

        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()

        # Extract pass/fail status for each gate
        gate_passes = {}
        gate_scores = {}
        all_issues = []

        for gate_name, result in gate_results.items():
            if isinstance(result, dict) and not result.get("error"):
                gate_passes[gate_name] = result.get("pass", False)

                # Extract scores based on gate type
                if gate_name == "gate_1":
                    # Gate 1 doesn't have a single score, use pass status
                    gate_scores[gate_name] = 1.0 if result.get("pass", False) else 0.0
                elif gate_name == "gate_2":
                    # Gate 2 has per-frame scores, calculate average
                    frames = result.get("frames", {})
                    if frames:
                        scores = [f.get("overall_quality", 0.0) for f in frames.values()]
                        gate_scores[gate_name] = sum(scores) / len(scores)
                    else:
                        gate_scores[gate_name] = 0.0
                elif gate_name == "gate_3":
                    # Gate 3 has overall score in quality metrics
                    quality_metrics = result.get("quality_metrics", {})
                    gate_scores[gate_name] = quality_metrics.get("overall_score", 0.0)
                elif gate_name == "gate_4":
                    # Gate 4 has overall quality in quality metrics
                    quality_metrics = result.get("quality_metrics", {})
                    gate_scores[gate_name] = quality_metrics.get("overall_quality", 0.0)

                # Collect issues
                if "frames" in result:
                    # Gate 2 format
                    for frame_result in result["frames"].values():
                        all_issues.extend(frame_result.get("issues", []))
                elif "quality_metrics" in result:
                    # Gate 3/4 format
                    all_issues.extend(result["quality_metrics"].get("issues", []))
                else:
                    # Gate 1 format - extract from tests
                    tests = result.get("tests", {})
                    for test_result in tests.values():
                        if isinstance(test_result, dict) and not test_result.get("pass", True):
                            all_issues.append(f"Gate {gate_name}: Test failed")

            else:
                # Gate failed with error
                gate_passes[gate_name] = False
                gate_scores[gate_name] = 0.0
                error_msg = result.get("error", "Unknown error")
                all_issues.append(f"Gate {gate_name}: {error_msg}")

        # Calculate overall status
        overall_pass = all(gate_passes.values())
        average_score = sum(gate_scores.values()) / len(gate_scores) if gate_scores else 0.0

        # Generate recommendations
        recommendations = await self._generate_recommendations(gate_results, all_issues)

        # Create comprehensive report
        report = {
            "test_session": {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": total_duration,
                "test_type": "comprehensive_quality_gates",
                "version": "1.0.0"
            },
            "configuration": {
                "character_name": config.character_name,
                "sequence_name": config.sequence_name,
                "intended_story": config.intended_story,
                "asset_count": len(config.asset_paths),
                "frame_count": len(config.frame_paths),
                "sequence_frame_count": len(config.frame_sequence),
                "has_audio": config.audio_path is not None
            },
            "overall_results": {
                "pass": overall_pass,
                "average_score": average_score,
                "gates_passed": sum(1 for p in gate_passes.values() if p),
                "gates_failed": sum(1 for p in gate_passes.values() if not p),
                "total_gates": len(gate_passes)
            },
            "gate_results": gate_results,
            "gate_summary": {
                gate: {
                    "passed": gate_passes.get(gate, False),
                    "score": gate_scores.get(gate, 0.0)
                }
                for gate in ["gate_1", "gate_2", "gate_3", "gate_4"]
            },
            "issues": {
                "total_count": len(all_issues),
                "issues": all_issues
            },
            "recommendations": recommendations,
            "next_steps": await self._generate_next_steps(overall_pass, gate_passes, all_issues)
        }

        return report

    async def _generate_recommendations(self, gate_results: Dict, issues: List[str]) -> List[str]:
        """Generate actionable recommendations based on test results"""
        recommendations = []

        # Analyze patterns in issues
        issue_text = " ".join(issues).lower()

        # Asset-related recommendations
        if "asset" in issue_text or "style" in issue_text:
            recommendations.append("Review and update asset database with proper version control")
            recommendations.append("Ensure style bible is current and all assets conform to guidelines")

        # Character fidelity recommendations
        if "character fidelity" in issue_text or "character" in issue_text:
            recommendations.append("Improve character reference data and training datasets")
            recommendations.append("Consider using ControlNet or similar tools for better character consistency")

        # Temporal consistency recommendations
        if "temporal" in issue_text or "flicker" in issue_text or "motion" in issue_text:
            recommendations.append("Review frame interpolation settings and motion vectors")
            recommendations.append("Consider using AnimateDiff or similar temporal consistency tools")

        # Video quality recommendations
        if "render" in issue_text or "bitrate" in issue_text or "resolution" in issue_text:
            recommendations.append("Optimize video encoding settings for better quality")
            recommendations.append("Ensure adequate bitrate for target resolution and framerate")

        # Audio sync recommendations
        if "sync" in issue_text or "audio" in issue_text:
            recommendations.append("Review audio-video synchronization workflow")
            recommendations.append("Implement proper lip-sync detection and correction")

        # General recommendations if no specific issues
        if not recommendations:
            recommendations.append("Continue monitoring quality metrics for consistency")
            recommendations.append("Consider implementing automated quality thresholds")

        return recommendations

    async def _generate_next_steps(self, overall_pass: bool, gate_passes: Dict, issues: List[str]) -> List[str]:
        """Generate next steps based on test results"""
        next_steps = []

        if overall_pass:
            next_steps.append("🎉 All quality gates passed - proceed to production deployment")
            next_steps.append("📊 Archive successful test results for future reference")
            next_steps.append("🔄 Schedule regular quality gate testing for ongoing productions")
        else:
            next_steps.append("🔧 Address failed quality gates before proceeding")

            # Specific steps for failed gates
            if not gate_passes.get("gate_1", True):
                next_steps.append("📋 Gate 1: Update asset database and style bible compliance")

            if not gate_passes.get("gate_2", True):
                next_steps.append("🖼️ Gate 2: Improve frame generation quality and character consistency")

            if not gate_passes.get("gate_3", True):
                next_steps.append("⏱️ Gate 3: Fix temporal consistency and motion smoothness issues")

            if not gate_passes.get("gate_4", True):
                next_steps.append("🎬 Gate 4: Resolve final video quality and synchronization problems")

            next_steps.append("🔄 Re-run quality gates after addressing issues")

        # Always include monitoring steps
        next_steps.append("📈 Monitor Echo Brain learning from quality gate results")
        next_steps.append("💾 Review saved quality metrics for pattern analysis")

        return next_steps

    async def _log_comprehensive_results(self, report: Dict):
        """Log comprehensive results to Echo Brain for learning"""
        try:
            summary_data = {
                "test_type": "comprehensive_quality_gates",
                "overall_pass": report["overall_results"]["pass"],
                "average_score": report["overall_results"]["average_score"],
                "gates_passed": report["overall_results"]["gates_passed"],
                "gates_failed": report["overall_results"]["gates_failed"],
                "total_issues": report["issues"]["total_count"],
                "duration_seconds": report["test_session"]["duration_seconds"],
                "character_name": report["configuration"]["character_name"],
                "recommendations_count": len(report["recommendations"]),
                "timestamp": report["test_session"]["start_time"]
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.echo_brain_url}/api/echo/query",
                    json={
                        "query": f"Comprehensive anime quality gates test results: {json.dumps(summary_data)}",
                        "conversation_id": "anime_quality_gates_comprehensive",
                        "context": "production_pipeline_testing"
                    },
                    timeout=10.0
                )
                if response.status_code == 200:
                    logger.info("📊 Comprehensive results logged to Echo Brain")

        except Exception as e:
            logger.warning(f"Could not log comprehensive results to Echo Brain: {e}")

    async def _save_comprehensive_results(self, report: Dict):
        """Save comprehensive results to file"""
        results_dir = self.project_root / "quality" / "comprehensive_results"
        results_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = results_dir / f"comprehensive_quality_gates_{timestamp}.json"

        with open(results_file, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"💾 Comprehensive results saved to {results_file}")

    def _print_test_summary(self, report: Dict):
        """Print formatted test summary"""
        logger.info("=" * 80)
        logger.info("🎬 ANIME PRODUCTION QUALITY GATES - COMPREHENSIVE TEST SUMMARY")
        logger.info("=" * 80)

        overall = report["overall_results"]
        session = report["test_session"]
        config = report["configuration"]

        # Test session info
        logger.info(f"📅 Test Duration: {session['duration_seconds']:.2f} seconds")
        logger.info(f"👤 Character: {config['character_name']}")
        logger.info(f"📝 Story: {config['intended_story'][:60]}...")

        # Overall results
        status_icon = "🎉" if overall["pass"] else "💥"
        status_text = "PASSED" if overall["pass"] else "FAILED"
        logger.info(f"{status_icon} Overall Status: {status_text}")
        logger.info(f"📊 Average Score: {overall['average_score']:.3f}")
        logger.info(f"✅ Gates Passed: {overall['gates_passed']}/{overall['total_gates']}")

        # Gate-by-gate summary
        logger.info("\n📋 Gate Summary:")
        gate_summary = report["gate_summary"]
        for gate_name, gate_data in gate_summary.items():
            gate_title = gate_name.replace("_", " ").title()
            status = "✅ PASS" if gate_data["passed"] else "❌ FAIL"
            score = gate_data["score"]
            logger.info(f"   {gate_title}: {status} ({score:.3f})")

        # Issues summary
        issues_count = report["issues"]["total_count"]
        if issues_count > 0:
            logger.info(f"\n⚠️ Total Issues Found: {issues_count}")
            for i, issue in enumerate(report["issues"]["issues"][:5], 1):  # Show first 5
                logger.info(f"   {i}. {issue}")
            if issues_count > 5:
                logger.info(f"   ... and {issues_count - 5} more issues")

        # Recommendations
        if report["recommendations"]:
            logger.info(f"\n💡 Recommendations:")
            for i, rec in enumerate(report["recommendations"][:3], 1):  # Show first 3
                logger.info(f"   {i}. {rec}")

        # Next steps
        if report["next_steps"]:
            logger.info(f"\n🎯 Next Steps:")
            for i, step in enumerate(report["next_steps"][:3], 1):  # Show first 3
                logger.info(f"   {i}. {step}")

        logger.info("=" * 80)

# Example usage and CLI interface
if __name__ == "__main__":
    async def main():
        """Example usage of the comprehensive quality gates runner"""

        # Initialize runner
        runner = QualityGatesTestRunner("/opt/tower-anime-production")

        # Example configuration for testing Yuki turn sequence
        config = ProductionTestConfig(
            # Gate 1: Asset readiness
            required_assets=["yuki_character_sheet", "rain_alley_bg", "neon_signs"],
            asset_paths=[
                "/opt/tower-anime-production/assets/characters/yuki_v3.2.png",
                "/opt/tower-anime-production/assets/backgrounds/rain_alley.png"
            ],

            # Gate 2: Frame generation
            frame_paths=[
                "/opt/tower-anime-production/generated/frames/frame_001.png",
                "/opt/tower-anime-production/generated/frames/frame_002.png",
                "/opt/tower-anime-production/generated/frames/frame_003.png"
            ],
            character_name="yuki",
            generation_prompt="Yuki, medium shot, turning around slowly in rainy alley, neon signs reflecting on wet coat, cinematic",

            # Gate 3: Temporal consistency
            frame_sequence=[
                "/opt/tower-anime-production/generated/frames/frame_001.png",
                "/opt/tower-anime-production/generated/frames/frame_002.png",
                "/opt/tower-anime-production/generated/frames/frame_003.png",
                "/opt/tower-anime-production/generated/frames/frame_004.png",
                "/opt/tower-anime-production/generated/frames/frame_005.png"
            ],
            sequence_name="yuki_turn_sequence",

            # Gate 4: Final video
            video_path="/opt/tower-anime-production/generated/videos/yuki_turn_final.mp4",
            intended_story="Yuki realizes she is being followed and turns around with growing concern",
            scene_description="Medium shot of Yuki in rainy alley, turning slowly with worried expression"
        )

        # Run comprehensive test
        print("🎬 Starting comprehensive anime production quality gates test...")
        results = await runner.run_all_gates(config, parallel_execution=False)

        # Print final status
        if results.get("overall_pass", False):
            print("🎉 All quality gates passed! Ready for production.")
        else:
            print("💥 Quality gates failed. Review issues and retry.")

        return results

    # Run the example
    asyncio.run(main())