#!/usr/bin/env python3
"""
Integrated Error Handling System
Brings together all error handling components into a unified, production-ready system
for comprehensive anime production pipeline with resilient error recovery.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from enhanced_api_handler import (APIConfig, EnhancedAPIHandler,
                                  create_api_handler)
from enhanced_character_system import (CharacterConfig,
                                       EnhancedCharacterSystem,
                                       create_character_system)
# Import all enhanced components
from enhanced_comfyui_integration import (ComfyUIConfig,
                                          EnhancedComfyUIIntegration,
                                          create_comfyui_integration)
from enhanced_database_manager import (DatabaseConfig, EnhancedDatabaseManager,
                                       create_database_manager)
from enhanced_echo_integration import (EchoConfig, EnhancedEchoIntegration,
                                       create_echo_integration)
from enhanced_filesystem_manager import (EnhancedFileSystemManager,
                                         FileSystemConfig,
                                         create_filesystem_manager)
from shared.error_handling import MetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class SystemConfig:
    """Unified system configuration"""

    # Environment settings
    environment: str = "production"  # production, development, testing
    debug_mode: bool = False
    log_level: str = "INFO"

    # Database settings
    database_host: str = "localhost"
    database_name: str = "anime_production"
    database_user: str = "patrick"
    database_password: str = "***REMOVED***"

    # Service URLs
    comfyui_url: str = "http://***REMOVED***:8188"
    echo_brain_url: str = "http://***REMOVED***:8309"

    # Storage paths
    base_storage_path: str = "/mnt/1TB-storage"
    output_directory: str = "/mnt/1TB-storage/ComfyUI/output"
    characters_directory: str = "/opt/tower-anime-production/characters"
    cache_directory: str = "/opt/tower-anime-production/cache"
    temp_directory: str = "/tmp/anime-production"

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8328
    enable_rate_limiting: bool = True
    enable_authentication: bool = False

    # Error handling settings
    enable_circuit_breakers: bool = True
    enable_fallbacks: bool = True
    enable_auto_recovery: bool = True
    max_retry_attempts: int = 3

    # Monitoring settings
    enable_metrics: bool = True
    enable_health_monitoring: bool = True
    health_check_interval: int = 300  # 5 minutes


class IntegratedErrorHandlingSystem:
    """Unified error handling system integrating all components"""

    def __init__(self, config: SystemConfig = None):
        self.config = config or SystemConfig()
        self.setup_logging()

        # Initialize metrics collector
        self.metrics_collector = self._create_metrics_collector()

        # Initialize all components
        self.database_manager = None
        self.comfyui_integration = None
        self.character_system = None
        self.echo_integration = None
        self.filesystem_manager = None
        self.api_handler = None

        # System status
        self.system_status = {
            "initialized": False,
            "healthy": False,
            "last_health_check": None,
            "component_status": {},
        }

    def setup_logging(self):
        """Setup comprehensive logging"""
        log_level = getattr(
            logging, self.config.log_level.upper(), logging.INFO)

        # Create logs directory
        log_dir = Path("/opt/tower-anime-production/logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        # Configure logging
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_dir / "integrated_system.log"),
                logging.StreamHandler(),
            ],
        )

        logger.info(f"🚀 Initializing Integrated Error Handling System")
        logger.info(f"Environment: {self.config.environment}")
        logger.info(f"Debug Mode: {self.config.debug_mode}")

    def _create_metrics_collector(self) -> Optional[MetricsCollector]:
        """Create metrics collector if enabled"""
        if not self.config.enable_metrics:
            return None

        try:
            db_config = {
                "host": self.config.database_host,
                "database": self.config.database_name,
                "user": self.config.database_user,
                "password": self.config.database_password,
            }
            return MetricsCollector(db_config)
        except Exception as e:
            logger.warning(f"Failed to initialize metrics collector: {e}")
            return None

    async def initialize_all_components(self):
        """Initialize all system components with error handling"""
        logger.info("🔧 Initializing all system components...")

        initialization_results = {}

        # Initialize Database Manager
        try:
            db_config = DatabaseConfig(
                primary_host=self.config.database_host,
                primary_database=self.config.database_name,
                primary_user=self.config.database_user,
                primary_password=self.config.database_password,
                fallback_enabled=self.config.enable_fallbacks,
                max_retries=self.config.max_retry_attempts,
            )

            self.database_manager = create_database_manager(
                db_config, self.metrics_collector
            )
            initialization_results["database"] = {
                "status": "success",
                "component": "database_manager",
            }
            logger.info("✅ Database Manager initialized")

        except Exception as e:
            logger.error(f"❌ Database Manager initialization failed: {e}")
            initialization_results["database"] = {
                "status": "failed", "error": str(e)}

        # Initialize ComfyUI Integration
        try:
            comfyui_config = ComfyUIConfig(
                base_url=self.config.comfyui_url,
                output_dir=self.config.output_directory,
                max_retries=self.config.max_retry_attempts,
            )

            self.comfyui_integration = create_comfyui_integration()
            initialization_results["comfyui"] = {
                "status": "success",
                "component": "comfyui_integration",
            }
            logger.info("✅ ComfyUI Integration initialized")

        except Exception as e:
            logger.error(f"❌ ComfyUI Integration initialization failed: {e}")
            initialization_results["comfyui"] = {
                "status": "failed", "error": str(e)}

        # Initialize Character System
        try:
            char_config = CharacterConfig(
                characters_dir=self.config.characters_directory,
                cache_dir=f"{self.config.cache_directory}/characters",
                enable_auto_generation=self.config.enable_fallbacks,
            )

            self.character_system = create_character_system(
                char_config, self.metrics_collector
            )
            initialization_results["character"] = {
                "status": "success",
                "component": "character_system",
            }
            logger.info("✅ Character System initialized")

        except Exception as e:
            logger.error(f"❌ Character System initialization failed: {e}")
            initialization_results["character"] = {
                "status": "failed", "error": str(e)}

        # Initialize Echo Integration
        try:
            echo_config = EchoConfig(
                base_url=self.config.echo_brain_url,
                enable_local_fallback=self.config.enable_fallbacks,
                circuit_breaker_threshold=(
                    5 if self.config.enable_circuit_breakers else 999
                ),
            )

            self.echo_integration = create_echo_integration(
                echo_config, self.metrics_collector
            )
            initialization_results["echo"] = {
                "status": "success",
                "component": "echo_integration",
            }
            logger.info("✅ Echo Integration initialized")

        except Exception as e:
            logger.error(f"❌ Echo Integration initialization failed: {e}")
            initialization_results["echo"] = {
                "status": "failed", "error": str(e)}

        # Initialize File System Manager
        try:
            fs_config = FileSystemConfig(
                output_dir=self.config.output_directory,
                cache_dir=self.config.cache_directory,
                temp_dir=self.config.temp_directory,
                auto_cleanup_enabled=True,
            )

            self.filesystem_manager = create_filesystem_manager(
                fs_config, self.metrics_collector
            )
            initialization_results["filesystem"] = {
                "status": "success",
                "component": "filesystem_manager",
            }
            logger.info("✅ File System Manager initialized")

        except Exception as e:
            logger.error(f"❌ File System Manager initialization failed: {e}")
            initialization_results["filesystem"] = {
                "status": "failed", "error": str(e)}

        # Initialize API Handler
        try:
            api_config = APIConfig(
                host=self.config.api_host,
                port=self.config.api_port,
                rate_limit_enabled=self.config.enable_rate_limiting,
                require_auth=self.config.enable_authentication,
                circuit_breaker_enabled=self.config.enable_circuit_breakers,
                debug=self.config.debug_mode,
            )

            self.api_handler = create_api_handler(
                api_config, self.metrics_collector)
            initialization_results["api"] = {
                "status": "success",
                "component": "api_handler",
            }
            logger.info("✅ API Handler initialized")

        except Exception as e:
            logger.error(f"❌ API Handler initialization failed: {e}")
            initialization_results["api"] = {
                "status": "failed", "error": str(e)}

        # Update system status
        successful_components = len(
            [r for r in initialization_results.values() if r["status"]
             == "success"]
        )
        total_components = len(initialization_results)

        self.system_status.update(
            {
                "initialized": True,
                "healthy": successful_components
                >= (total_components * 0.7),  # 70% threshold
                "component_status": initialization_results,
                "initialization_time": datetime.utcnow().isoformat(),
            }
        )

        logger.info(
            f"🎯 System initialization complete: {successful_components}/{total_components} components successful"
        )

        return initialization_results

    async def perform_comprehensive_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check across all components"""
        logger.info("🏥 Performing comprehensive health check...")

        health_results = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "unknown",
            "components": {},
            "error_rates": {},
            "performance_metrics": {},
            "recommendations": [],
        }

        # Check Database Manager
        if self.database_manager:
            try:
                db_health = await self.database_manager.get_system_health()
                health_results["components"]["database"] = {
                    "status": (
                        "healthy"
                        if db_health.get("database_status") == "healthy"
                        else "degraded"
                    ),
                    "details": db_health,
                }
            except Exception as e:
                health_results["components"]["database"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }

        # Check ComfyUI Integration
        if self.comfyui_integration:
            try:
                comfyui_status = await self.comfyui_integration.get_service_status()
                health_results["components"]["comfyui"] = {
                    "status": comfyui_status.get("health_status", "unknown"),
                    "details": comfyui_status,
                }
            except Exception as e:
                health_results["components"]["comfyui"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }

        # Check Character System
        if self.character_system:
            try:
                char_health = await self.character_system.get_system_health()
                char_status = (
                    "healthy"
                    if char_health.get("total_characters", 0) > 0
                    else "degraded"
                )
                health_results["components"]["character"] = {
                    "status": char_status,
                    "details": char_health,
                }
            except Exception as e:
                health_results["components"]["character"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }

        # Check Echo Integration
        if self.echo_integration:
            try:
                echo_status = await self.echo_integration.get_service_status()
                health_results["components"]["echo"] = {
                    "status": echo_status.get("service_status", "unknown"),
                    "details": echo_status,
                }
            except Exception as e:
                health_results["components"]["echo"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }

        # Check File System Manager
        if self.filesystem_manager:
            try:
                fs_health = await self.filesystem_manager.get_system_health()
                health_results["components"]["filesystem"] = {
                    "status": fs_health.get("overall_status", "unknown"),
                    "details": fs_health,
                }
            except Exception as e:
                health_results["components"]["filesystem"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }

        # Check API Handler
        if self.api_handler:
            try:
                api_health = await self.api_handler.get_api_health()
                health_results["components"]["api"] = {
                    "status": api_health.get("api_status", "unknown"),
                    "details": api_health,
                }
            except Exception as e:
                health_results["components"]["api"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }

        # Determine overall status
        component_statuses = [
            comp.get("status", "unknown")
            for comp in health_results["components"].values()
        ]
        healthy_count = len([s for s in component_statuses if s == "healthy"])
        total_count = len(component_statuses)

        if healthy_count >= total_count * 0.8:
            health_results["overall_status"] = "healthy"
        elif healthy_count >= total_count * 0.5:
            health_results["overall_status"] = "degraded"
        else:
            health_results["overall_status"] = "unhealthy"

        # Generate recommendations
        health_results["recommendations"] = self._generate_health_recommendations(
            health_results
        )

        # Update system status
        self.system_status.update(
            {
                "healthy": health_results["overall_status"] == "healthy",
                "last_health_check": datetime.utcnow().isoformat(),
                "component_status": health_results["components"],
            }
        )

        logger.info(
            f"🎯 Health check complete: {health_results['overall_status']} ({healthy_count}/{total_count} components healthy)"
        )

        return health_results

    def _generate_health_recommendations(
        self, health_results: Dict[str, Any]
    ) -> List[str]:
        """Generate health recommendations based on status"""
        recommendations = []

        for component, status_info in health_results["components"].items():
            status = status_info.get("status", "unknown")

            if status == "unhealthy":
                recommendations.append(
                    f"URGENT: {component} component is unhealthy - requires immediate attention"
                )
            elif status == "degraded":
                recommendations.append(
                    f"WARNING: {component} component is degraded - monitor closely"
                )

        if health_results["overall_status"] == "unhealthy":
            recommendations.append(
                "CRITICAL: System overall health is poor - consider maintenance mode"
            )
        elif health_results["overall_status"] == "degraded":
            recommendations.append(
                "CAUTION: System performance may be impacted - schedule maintenance"
            )

        if not recommendations:
            recommendations.append(
                "System is healthy - continue normal operations")

        return recommendations

    async def generate_video_with_full_error_handling(
        self,
        prompt: str,
        character_name: str = None,
        duration: int = 5,
        style: str = "anime",
    ) -> Dict[str, Any]:
        """Generate video using the full error handling pipeline"""
        operation_id = f"video_gen_{int(time.time())}"
        logger.info(
            f"🎬 Starting video generation with full error handling: {operation_id}"
        )

        result = {
            "operation_id": operation_id,
            "success": False,
            "stages_completed": [],
            "errors_encountered": [],
            "fallbacks_used": [],
            "final_output": None,
            "processing_time_seconds": 0,
            "recovery_actions": [],
        }

        start_time = time.time()

        try:
            # Stage 1: Character Processing
            logger.info("  📝 Stage 1: Processing character information")
            try:
                if character_name:
                    character_prompt = (
                        await self.character_system.build_generation_prompt_robust(
                            character_name, f"{prompt}, {style}"
                        )
                    )
                    if character_prompt.get("character_found"):
                        final_prompt = character_prompt["prompt"]
                        result["stages_completed"].append(
                            "character_processing")
                        if character_prompt.get("source") != "file":
                            result["fallbacks_used"].append(
                                "character_generation")
                    else:
                        final_prompt = f"{prompt}, {style}"
                        result["errors_encountered"].append(
                            "character_not_found")
                        result["fallbacks_used"].append("basic_prompt")
                else:
                    final_prompt = f"{prompt}, {style}"
                    result["stages_completed"].append("character_processing")

            except Exception as e:
                logger.warning(f"    ⚠️ Character processing failed: {e}")
                final_prompt = f"{prompt}, {style}"
                result["errors_encountered"].append(
                    f"character_error: {str(e)}")
                result["fallbacks_used"].append("basic_prompt")
                result["recovery_actions"].append("Used basic prompt fallback")

            # Stage 2: Echo Brain Enhancement (Optional)
            logger.info("  🧠 Stage 2: Echo Brain prompt enhancement")
            try:
                if self.echo_integration:
                    enhanced_response = (
                        await self.echo_integration.optimize_generation_prompt(
                            final_prompt, style
                        )
                    )
                    if enhanced_response.success:
                        final_prompt = enhanced_response.response
                        result["stages_completed"].append("echo_enhancement")
                        if enhanced_response.fallback_used:
                            result["fallbacks_used"].append(
                                "echo_local_fallback")
                    else:
                        result["errors_encountered"].append(
                            "echo_enhancement_failed")
            except Exception as e:
                logger.warning(f"    ⚠️ Echo enhancement failed: {e}")
                result["errors_encountered"].append(f"echo_error: {str(e)}")
                result["recovery_actions"].append("Skipped Echo enhancement")

            # Stage 3: Pre-generation Checks
            logger.info("  🔍 Stage 3: Pre-generation system checks")
            try:
                # Check disk space
                space_available = await self.filesystem_manager.ensure_space_available(
                    self.config.output_directory, 5.0  # 5GB requirement
                )
                if not space_available:
                    result["errors_encountered"].append(
                        "insufficient_disk_space")
                    result["recovery_actions"].append(
                        "Triggered emergency cleanup")
                else:
                    result["stages_completed"].append("space_check")

                # Check ComfyUI health
                comfyui_status = await self.comfyui_integration.get_service_status()
                if comfyui_status.get("can_accept_jobs"):
                    result["stages_completed"].append("comfyui_health_check")
                else:
                    result["errors_encountered"].append("comfyui_unavailable")

            except Exception as e:
                logger.warning(f"    ⚠️ Pre-generation checks failed: {e}")
                result["errors_encountered"].append(
                    f"precheck_error: {str(e)}")

            # Stage 4: Video Generation
            logger.info("  🎨 Stage 4: Video generation")
            try:
                from enhanced_comfyui_integration import GenerationRequest

                generation_request = GenerationRequest(
                    request_id=operation_id,
                    prompt=final_prompt,
                    duration=duration,
                    style=style,
                )

                generation_result = (
                    await self.comfyui_integration.generate_video_robust(
                        generation_request
                    )
                )

                if generation_result.get("success"):
                    result["stages_completed"].append("video_generation")
                    result["final_output"] = generation_result.get(
                        "output_path")

                    if generation_result.get("is_fallback"):
                        result["fallbacks_used"].append(
                            "comfyui_fallback_generation")
                else:
                    result["errors_encountered"].append(
                        "video_generation_failed")

            except Exception as e:
                logger.error(f"    ❌ Video generation failed: {e}")
                result["errors_encountered"].append(
                    f"generation_error: {str(e)}")

            # Stage 5: Post-processing and Validation
            if result["final_output"]:
                logger.info("  ✅ Stage 5: Post-processing and validation")
                try:
                    # Validate output file
                    output_path = Path(result["final_output"])
                    if (
                        output_path.exists() and output_path.stat().st_size > 1000
                    ):  # > 1KB
                        result["stages_completed"].append("output_validation")
                        result["success"] = True

                        # Store generation record
                        if self.database_manager:
                            await self.database_manager.save_generation_request(
                                {
                                    "id": operation_id,
                                    "prompt": final_prompt,
                                    "character_name": character_name,
                                    "duration": duration,
                                    "style": style,
                                    "status": "completed",
                                }
                            )
                            result["stages_completed"].append(
                                "database_logging")
                    else:
                        result["errors_encountered"].append(
                            "output_validation_failed")

                except Exception as e:
                    logger.warning(f"    ⚠️ Post-processing failed: {e}")
                    result["errors_encountered"].append(
                        f"postprocessing_error: {str(e)}"
                    )

        except Exception as e:
            logger.error(f"❌ Critical error in video generation pipeline: {e}")
            result["errors_encountered"].append(f"critical_error: {str(e)}")

        result["processing_time_seconds"] = time.time() - start_time

        # Generate summary
        stages_count = len(result["stages_completed"])
        errors_count = len(result["errors_encountered"])
        fallbacks_count = len(result["fallbacks_used"])

        logger.info(f"🎯 Generation complete: {operation_id}")
        logger.info(f"  Success: {result['success']}")
        logger.info(
            f"  Stages: {stages_count}, Errors: {errors_count}, Fallbacks: {fallbacks_count}"
        )
        logger.info(f"  Time: {result['processing_time_seconds']:.2f}s")

        return result

    async def start_monitoring_loop(self):
        """Start the system monitoring loop"""
        if not self.config.enable_health_monitoring:
            logger.info("Health monitoring disabled")
            return

        logger.info(
            f"🔄 Starting health monitoring loop (interval: {self.config.health_check_interval}s)"
        )

        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)

                health_results = await self.perform_comprehensive_health_check()

                # Log critical issues
                if health_results["overall_status"] == "unhealthy":
                    logger.error(
                        "🚨 SYSTEM UNHEALTHY - Immediate attention required")
                    for rec in health_results["recommendations"]:
                        if "URGENT" in rec or "CRITICAL" in rec:
                            logger.error(f"  {rec}")

            except Exception as e:
                logger.error(f"Health monitoring loop error: {e}")
                await asyncio.sleep(60)  # Wait before retry

    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status"""
        return {
            "system_status": self.system_status,
            "config": {
                "environment": self.config.environment,
                "debug_mode": self.config.debug_mode,
                "error_handling_enabled": {
                    "circuit_breakers": self.config.enable_circuit_breakers,
                    "fallbacks": self.config.enable_fallbacks,
                    "auto_recovery": self.config.enable_auto_recovery,
                },
            },
            "components": {
                "database_manager": self.database_manager is not None,
                "comfyui_integration": self.comfyui_integration is not None,
                "character_system": self.character_system is not None,
                "echo_integration": self.echo_integration is not None,
                "filesystem_manager": self.filesystem_manager is not None,
                "api_handler": self.api_handler is not None,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }


# Factory function
def create_integrated_system(
    config: SystemConfig = None,
) -> IntegratedErrorHandlingSystem:
    """Create integrated error handling system"""
    return IntegratedErrorHandlingSystem(config)


# Example usage and testing
async def main():
    """Main function demonstrating the integrated system"""
    logger.info("🚀 Starting Integrated Error Handling System Demo")

    # Create system configuration
    config = SystemConfig(
        environment="development",
        debug_mode=True,
        enable_fallbacks=True,
        enable_circuit_breakers=True,
        enable_auto_recovery=True,
    )

    # Create and initialize system
    system = create_integrated_system(config)

    try:
        # Initialize all components
        init_results = await system.initialize_all_components()

        # Perform health check
        health_results = await system.perform_comprehensive_health_check()

        # Get system status
        status = system.get_system_status()

        print("\n" + "=" * 60)
        print("INTEGRATED ERROR HANDLING SYSTEM STATUS")
        print("=" * 60)
        print(json.dumps(status, indent=2, default=str))

        print("\n" + "=" * 60)
        print("SYSTEM HEALTH REPORT")
        print("=" * 60)
        print(f"Overall Status: {health_results['overall_status']}")
        print(f"Components: {len(health_results['components'])} checked")

        for component, health in health_results["components"].items():
            status_emoji = {"healthy": "✅", "degraded": "⚠️", "unhealthy": "❌"}.get(
                health["status"], "❓"
            )
            print(f"  {status_emoji} {component}: {health['status']}")

        print("\nRecommendations:")
        for rec in health_results["recommendations"]:
            print(f"  • {rec}")

        # Test video generation with full error handling
        print("\n" + "=" * 60)
        print("TESTING VIDEO GENERATION WITH ERROR HANDLING")
        print("=" * 60)

        generation_result = await system.generate_video_with_full_error_handling(
            prompt="magical girl transformation scene",
            character_name="TestCharacter",
            duration=5,
            style="anime",
        )

        print(f"Generation Success: {generation_result['success']}")
        print(
            f"Stages Completed: {len(generation_result['stages_completed'])}")
        print(
            f"Errors Encountered: {len(generation_result['errors_encountered'])}")
        print(f"Fallbacks Used: {len(generation_result['fallbacks_used'])}")
        print(
            f"Processing Time: {generation_result['processing_time_seconds']:.2f}s")

        if generation_result["final_output"]:
            print(f"Output File: {generation_result['final_output']}")

        # Start monitoring (would run indefinitely in production)
        # await system.start_monitoring_loop()

    except Exception as e:
        logger.error(f"System demo failed: {e}")

    finally:
        logger.info("🏁 Integrated Error Handling System Demo Complete")


if __name__ == "__main__":
    asyncio.run(main())
