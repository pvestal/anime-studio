#!/usr/bin/env python3
"""
Music Synchronization System Deployment Script
Automated deployment and configuration of the complete music-video synchronization system.

Author: Claude Code
Created: 2025-12-15
Purpose: Deploy and configure anime music synchronization system
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MusicSyncDeployment:
    """Complete deployment and configuration of music synchronization system"""

    def __init__(self):
        self.base_dir = Path("/opt/tower-anime-production")
        self.api_dir = self.base_dir / "api"
        self.config_dir = self.base_dir / "config"
        self.logs_dir = self.base_dir / "logs"

        # Service configurations
        self.services = {
            "music-sync": {
                "port": 8316,
                "script": "music_synchronization_service.py",
                "description": "Core music synchronization engine"
            },
            "ai-music-selector": {
                "port": 8317,
                "script": "ai_music_selector.py",
                "description": "AI-powered music selection"
            },
            "video-music-integration": {
                "port": 8318,
                "script": "video_music_integration.py",
                "description": "Complete video-music integration pipeline"
            }
        }

        # System dependencies
        self.python_packages = [
            "librosa",
            "numpy",
            "scipy",
            "httpx",
            "redis",
            "fastapi",
            "uvicorn",
            "pydantic",
            "pytest"
        ]

        self.system_packages = [
            "ffmpeg",
            "redis-server",
            "python3-dev",
            "libsndfile1-dev"
        ]

    async def deploy_complete_system(self) -> bool:
        """Deploy the complete music synchronization system"""

        logger.info("🚀 Starting music synchronization system deployment")

        try:
            # 1. Check prerequisites
            logger.info("📋 Checking prerequisites...")
            await self._check_prerequisites()

            # 2. Install dependencies
            logger.info("📦 Installing dependencies...")
            await self._install_dependencies()

            # 3. Configure directories
            logger.info("📁 Setting up directories...")
            await self._setup_directories()

            # 4. Configure services
            logger.info("⚙️ Configuring services...")
            await self._configure_services()

            # 5. Create systemd services
            logger.info("🔧 Creating systemd services...")
            await self._create_systemd_services()

            # 6. Configure nginx routing
            logger.info("🌐 Configuring nginx routing...")
            await self._configure_nginx()

            # 7. Start services
            logger.info("▶️ Starting services...")
            await self._start_services()

            # 8. Validate deployment
            logger.info("✅ Validating deployment...")
            validation_result = await self._validate_deployment()

            if validation_result:
                logger.info("🎉 Music synchronization system deployed successfully!")
                await self._print_deployment_summary()
                return True
            else:
                logger.error("❌ Deployment validation failed")
                return False

        except Exception as e:
            logger.error(f"❌ Deployment failed: {e}")
            return False

    async def _check_prerequisites(self):
        """Check system prerequisites"""

        # Check if running as root/sudo
        if os.geteuid() != 0:
            raise RuntimeError("Deployment must be run as root/sudo for system configuration")

        # Check existing services
        required_services = ["redis-server", "nginx"]
        for service in required_services:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                logger.warning(f"Service {service} not running - will attempt to start")

        # Check Python version
        python_version = sys.version_info
        if python_version < (3, 8):
            raise RuntimeError(f"Python 3.8+ required, found {python_version.major}.{python_version.minor}")

        logger.info("✅ Prerequisites check completed")

    async def _install_dependencies(self):
        """Install system and Python dependencies"""

        # Install system packages
        logger.info("Installing system packages...")
        for package in self.system_packages:
            try:
                result = subprocess.run(
                    ["apt", "install", "-y", package],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    logger.warning(f"Failed to install {package}: {result.stderr}")
                else:
                    logger.info(f"✅ Installed {package}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout installing {package}")

        # Create virtual environment if it doesn't exist
        venv_path = self.base_dir / "venv_music_sync"
        if not venv_path.exists():
            logger.info("Creating Python virtual environment...")
            subprocess.run([
                "python3", "-m", "venv", str(venv_path)
            ], check=True)

        # Install Python packages
        pip_path = venv_path / "bin" / "pip"
        requirements_content = "\n".join(self.python_packages)

        # Create requirements file
        requirements_file = self.base_dir / "requirements_music_sync.txt"
        with open(requirements_file, 'w') as f:
            f.write(requirements_content)

        # Install packages
        logger.info("Installing Python packages...")
        result = subprocess.run([
            str(pip_path), "install", "-r", str(requirements_file)
        ], capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            logger.error(f"Failed to install Python packages: {result.stderr}")
            raise RuntimeError("Python package installation failed")

        logger.info("✅ Dependencies installed")

    async def _setup_directories(self):
        """Set up required directories and permissions"""

        directories = [
            self.config_dir,
            self.logs_dir,
            self.base_dir / "cache" / "music_sync",
            self.base_dir / "output" / "audio",
            self.base_dir / "output" / "final",
            self.base_dir / "test_data"
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            os.chown(directory, 1000, 1000)  # Set to user ownership

        logger.info("✅ Directories configured")

    async def _configure_services(self):
        """Configure service settings"""

        # Create configuration files for each service
        for service_name, config in self.services.items():
            config_file = self.config_dir / f"{service_name}.json"

            service_config = {
                "service_name": service_name,
                "port": config["port"],
                "host": "127.0.0.1",
                "log_level": "info",
                "workers": 1,
                "timeout": 300,
                "dependencies": {
                    "redis": {"host": "localhost", "port": 6379, "db": 0},
                    "database": {
                        "path": str(self.base_dir / "database" / "anime_production.db")
                    },
                    "apple_music": {"base_url": "http://localhost:8315"},
                    "echo_brain": {"base_url": "http://localhost:8309"},
                    "anime_api": {"base_url": "http://localhost:8328"}
                },
                "paths": {
                    "cache_dir": str(self.base_dir / "cache" / "music_sync"),
                    "output_dir": str(self.base_dir / "output"),
                    "logs_dir": str(self.logs_dir)
                }
            }

            with open(config_file, 'w') as f:
                json.dump(service_config, f, indent=2)

            logger.info(f"✅ Configured {service_name}")

    async def _create_systemd_services(self):
        """Create systemd service files"""

        venv_python = self.base_dir / "venv_music_sync" / "bin" / "python"

        for service_name, config in self.services.items():
            service_file_name = f"tower-{service_name}.service"
            service_file_path = Path("/etc/systemd/system") / service_file_name

            script_path = self.api_dir / config["script"]

            service_content = f"""[Unit]
Description=Tower {config['description']}
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=patrick
Group=patrick
WorkingDirectory={self.api_dir}
Environment=PATH={self.base_dir}/venv_music_sync/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH={self.api_dir}
Environment=CONFIG_PATH={self.config_dir}/{service_name}.json
ExecStart={venv_python} {script_path}
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths={self.base_dir} /tmp

# Resource limits
MemoryMax=1G
CPUQuota=50%

[Install]
WantedBy=multi-user.target
"""

            with open(service_file_path, 'w') as f:
                f.write(service_content)

            logger.info(f"✅ Created systemd service for {service_name}")

        # Reload systemd daemon
        subprocess.run(["systemctl", "daemon-reload"], check=True)

    async def _configure_nginx(self):
        """Configure nginx routing for music sync services"""

        nginx_config_path = Path("/etc/nginx/sites-available/tower.conf")

        # Read existing config
        if nginx_config_path.exists():
            with open(nginx_config_path, 'r') as f:
                existing_config = f.read()
        else:
            existing_config = ""

        # Music sync routing configuration
        music_sync_config = """
    # Music Synchronization Services
    location /api/music-sync/ {
        proxy_pass http://127.0.0.1:8316/api/music-sync/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 10;
        proxy_send_timeout 300;
    }

    location /api/ai-music/ {
        proxy_pass http://127.0.0.1:8317/api/ai-music/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 10;
        proxy_send_timeout 300;
    }

    location /api/integrated/ {
        proxy_pass http://127.0.0.1:8318/api/integrated/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600;
        proxy_connect_timeout 10;
        proxy_send_timeout 600;

        # WebSocket support for real-time updates
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
"""

        # Add music sync config if not already present
        if "Music Synchronization Services" not in existing_config:
            # Find the server block and add routing
            if "server {" in existing_config:
                # Insert before the closing brace of the server block
                lines = existing_config.split('\n')
                for i, line in enumerate(lines):
                    if line.strip() == '}' and i > 10:  # Find the last closing brace
                        lines.insert(i, music_sync_config)
                        break

                updated_config = '\n'.join(lines)

                # Backup existing config
                backup_path = nginx_config_path.with_suffix('.conf.backup')
                with open(backup_path, 'w') as f:
                    f.write(existing_config)

                # Write updated config
                with open(nginx_config_path, 'w') as f:
                    f.write(updated_config)

                logger.info("✅ Updated nginx configuration")

                # Test and reload nginx
                result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
                if result.returncode == 0:
                    subprocess.run(["systemctl", "reload", "nginx"], check=True)
                    logger.info("✅ Nginx reloaded successfully")
                else:
                    logger.error(f"Nginx configuration test failed: {result.stderr}")
                    # Restore backup
                    with open(backup_path, 'r') as f:
                        original_config = f.read()
                    with open(nginx_config_path, 'w') as f:
                        f.write(original_config)
            else:
                logger.warning("Could not find nginx server block to update")
        else:
            logger.info("Music sync nginx configuration already exists")

    async def _start_services(self):
        """Start all music synchronization services"""

        # Ensure dependencies are running
        for dependency in ["redis-server", "nginx"]:
            subprocess.run(["systemctl", "start", dependency], check=True)
            subprocess.run(["systemctl", "enable", dependency], check=True)

        # Start music sync services
        for service_name in self.services.keys():
            systemd_service_name = f"tower-{service_name}"

            try:
                subprocess.run(["systemctl", "enable", systemd_service_name], check=True)
                subprocess.run(["systemctl", "start", systemd_service_name], check=True)

                # Wait a moment for startup
                time.sleep(2)

                # Check status
                result = subprocess.run(
                    ["systemctl", "is-active", systemd_service_name],
                    capture_output=True, text=True
                )

                if result.returncode == 0:
                    logger.info(f"✅ {service_name} started successfully")
                else:
                    logger.error(f"❌ {service_name} failed to start")
                    # Show recent logs
                    log_result = subprocess.run(
                        ["journalctl", "-u", systemd_service_name, "--no-pager", "-n", "10"],
                        capture_output=True, text=True
                    )
                    logger.error(f"Recent logs for {service_name}:\n{log_result.stdout}")

            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to start {service_name}: {e}")

    async def _validate_deployment(self) -> bool:
        """Validate the deployment by testing services"""

        import httpx

        validation_success = True

        for service_name, config in self.services.items():
            try:
                url = f"http://localhost:{config['port']}/api/{service_name.replace('_', '-')}/health"
                if service_name == "video-music-integration":
                    url = f"http://localhost:{config['port']}/api/integrated/health"

                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(url)

                    if response.status_code == 200:
                        health_data = response.json()
                        logger.info(f"✅ {service_name} is healthy")
                        logger.info(f"   Status: {health_data.get('status')}")
                        logger.info(f"   Features: {len(health_data.get('features', []))}")
                    else:
                        logger.error(f"❌ {service_name} health check failed: HTTP {response.status_code}")
                        validation_success = False

            except Exception as e:
                logger.error(f"❌ {service_name} validation failed: {e}")
                validation_success = False

        # Test nginx routing
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get("https://192.168.50.135/api/music-sync/health")
                if response.status_code == 200:
                    logger.info("✅ Nginx routing working")
                else:
                    logger.warning(f"⚠️ Nginx routing test failed: HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"⚠️ Nginx routing test failed: {e}")

        return validation_success

    async def _print_deployment_summary(self):
        """Print deployment summary"""

        print("\n" + "="*60)
        print("🎵 MUSIC SYNCHRONIZATION SYSTEM DEPLOYED")
        print("="*60)

        print("\n📋 SERVICES:")
        for service_name, config in self.services.items():
            print(f"  {service_name}: http://localhost:{config['port']}")
            print(f"    └─ {config['description']}")

        print("\n🌐 NGINX ROUTES:")
        print("  https://192.168.50.135/api/music-sync/     → Music Synchronization Engine")
        print("  https://192.168.50.135/api/ai-music/       → AI Music Selection")
        print("  https://192.168.50.135/api/integrated/     → Complete Integration Pipeline")

        print("\n⚙️ MANAGEMENT COMMANDS:")
        print("  # Check service status")
        print("  sudo systemctl status tower-music-sync")
        print("  sudo systemctl status tower-ai-music-selector")
        print("  sudo systemctl status tower-video-music-integration")
        print("")
        print("  # View service logs")
        print("  sudo journalctl -u tower-music-sync -f")
        print("  sudo journalctl -u tower-ai-music-selector -f")
        print("  sudo journalctl -u tower-video-music-integration -f")
        print("")
        print("  # Restart services")
        print("  sudo systemctl restart tower-music-sync")
        print("  sudo systemctl restart tower-ai-music-selector")
        print("  sudo systemctl restart tower-video-music-integration")

        print("\n🧪 TESTING:")
        print("  # Run test suite")
        print(f"  cd {self.api_dir}")
        print(f"  {self.base_dir}/venv_music_sync/bin/python test_music_synchronization.py")

        print("\n📁 IMPORTANT PATHS:")
        print(f"  Configuration: {self.config_dir}")
        print(f"  Logs: {self.logs_dir}")
        print(f"  Cache: {self.base_dir}/cache/music_sync")
        print(f"  Output: {self.base_dir}/output")

        print("\n✨ FEATURES AVAILABLE:")
        print("  ✅ BPM Analysis and Tempo Detection")
        print("  ✅ AI-Powered Music Selection via Echo Brain")
        print("  ✅ Apple Music Catalog Integration")
        print("  ✅ Frame-Accurate Video-Music Synchronization")
        print("  ✅ Real-time Progress Tracking via WebSocket")
        print("  ✅ Complete Anime Video Generation Integration")

        print("\n" + "="*60)


async def main():
    """Main deployment function"""

    print("🎵 Music Synchronization System Deployment")
    print("=" * 50)

    # Check if running as root
    if os.geteuid() != 0:
        print("❌ This script must be run with sudo/root privileges")
        print("Usage: sudo python3 deploy_music_sync_system.py")
        return False

    deployment = MusicSyncDeployment()

    try:
        success = await deployment.deploy_complete_system()

        if success:
            print("\n🎉 Deployment completed successfully!")
            print("The music synchronization system is now ready for use.")
            return True
        else:
            print("\n❌ Deployment failed. Check the logs above for details.")
            return False

    except KeyboardInterrupt:
        print("\n⏹️ Deployment cancelled by user")
        return False
    except Exception as e:
        print(f"\n❌ Deployment failed with error: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)