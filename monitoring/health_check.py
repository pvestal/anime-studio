#!/usr/bin/env python3
"""
Anime Production System Health Monitor
Performs comprehensive health checks on all components
"""

import asyncio
import json
import sys
from datetime import datetime
import psycopg2
import redis
import requests
import jwt
from typing import Dict, List, Tuple

class AnimeHealthMonitor:
    def __init__(self):
        self.results = []
        self.services = {
            "secured_api": "http://localhost:8331/api/anime/health",
            "tower_auth": "http://localhost:8088/health",
            "comfyui": "http://localhost:8188/system_stats",
            "vault": "http://localhost:8200/v1/sys/health"
        }

        self.systemd_services = [
            "anime-secured-api",
            "anime-file-organizer",
            "anime-job-monitor",
            "anime-job-worker",
            "anime-websocket",
            "tower-auth",
            "vault"
        ]

    def check_service_health(self, name: str, url: str) -> Tuple[str, bool, str]:
        """Check HTTP service health"""
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return name, True, "✅ Healthy"
            else:
                return name, False, f"❌ Status: {response.status_code}"
        except requests.RequestException as e:
            return name, False, f"❌ Error: {str(e)[:50]}"

    def check_systemd_service(self, service_name: str) -> Tuple[str, bool, str]:
        """Check systemd service status"""
        import subprocess
        try:
            result = subprocess.run(
                ["systemctl", "status", service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            if "active (running)" in result.stdout:
                return service_name, True, "✅ Running"
            else:
                return service_name, False, "❌ Not running"
        except Exception as e:
            return service_name, False, f"❌ Check failed: {str(e)[:50]}"

    def check_database(self) -> Tuple[str, bool, str]:
        """Check PostgreSQL connection and tables"""
        try:
            conn = psycopg2.connect(
                host="localhost",
                database="anime_production",
                user="patrick",
                password="***REMOVED***"
            )
            cursor = conn.cursor()

            # Check critical tables
            tables = ["anime_api.production_jobs", "anime_api.anime_files",
                     "anime_api.projects", "anime_api.characters"]

            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]

            cursor.close()
            conn.close()
            return "PostgreSQL", True, f"✅ Connected, {len(tables)} tables verified"
        except Exception as e:
            return "PostgreSQL", False, f"❌ Database error: {str(e)[:50]}"

    def check_redis(self) -> Tuple[str, bool, str]:
        """Check Redis connection"""
        try:
            r = redis.Redis(host='localhost', port=6379, decode_responses=True)
            r.ping()
            keys = r.keys('anime:*')
            return "Redis", True, f"✅ Connected, {len(keys)} anime keys"
        except Exception as e:
            return "Redis", False, f"❌ Redis error: {str(e)[:50]}"

    def check_gpu_memory(self) -> Tuple[str, bool, str]:
        """Check GPU VRAM availability"""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            free_mb = int(result.stdout.strip())

            if free_mb > 4000:  # Need at least 4GB free
                return "GPU VRAM", True, f"✅ {free_mb}MB free"
            else:
                return "GPU VRAM", False, f"⚠️ Low: {free_mb}MB free"
        except Exception as e:
            return "GPU VRAM", False, f"❌ GPU check failed: {str(e)[:50]}"

    def check_file_organization(self) -> Tuple[str, bool, str]:
        """Check if file organization is working"""
        import os
        from datetime import datetime

        try:
            today = datetime.now().strftime("%Y%m%d")
            org_path = f"/mnt/1TB-storage/anime-projects/unorganized/images/{today}"

            if os.path.exists(org_path):
                files = len([f for f in os.listdir(org_path) if f.endswith('.png')])
                return "File Organization", True, f"✅ {files} files organized today"
            else:
                return "File Organization", True, "✅ Ready (no files today)"
        except Exception as e:
            return "File Organization", False, f"❌ Check failed: {str(e)[:50]}"

    def generate_jwt_token(self) -> str:
        """Generate test JWT token"""
        from datetime import timedelta

        payload = {
            "user": "monitor",
            "email": "monitor@system.local",
            "exp": int((datetime.now() + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now().timestamp()),
            "roles": ["admin", "user"]
        }
        return jwt.encode(payload, "tower_jwt_secret_2025", algorithm="HS256")

    def check_api_authentication(self) -> Tuple[str, bool, str]:
        """Test API authentication"""
        try:
            token = self.generate_jwt_token()
            headers = {"Authorization": f"Bearer {token}"}

            response = requests.get(
                "http://localhost:8331/api/anime/jobs",
                headers=headers,
                timeout=5
            )

            if response.status_code == 200:
                return "API Auth", True, "✅ JWT authentication working"
            else:
                return "API Auth", False, f"❌ Auth failed: {response.status_code}"
        except Exception as e:
            return "API Auth", False, f"❌ Auth test failed: {str(e)[:50]}"

    def run_health_checks(self):
        """Run all health checks"""
        print("\n🏥 ANIME PRODUCTION SYSTEM HEALTH CHECK")
        print("=" * 60)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # Check HTTP services
        print("\n📡 HTTP Services:")
        for name, url in self.services.items():
            result = self.check_service_health(name, url)
            self.results.append(result)
            print(f"  {result[0]:20} {result[2]}")

        # Check systemd services
        print("\n⚙️ Systemd Services:")
        for service in self.systemd_services:
            result = self.check_systemd_service(service)
            self.results.append(result)
            print(f"  {result[0]:20} {result[2]}")

        # Check infrastructure
        print("\n🏗️ Infrastructure:")

        result = self.check_database()
        self.results.append(result)
        print(f"  {result[0]:20} {result[2]}")

        result = self.check_redis()
        self.results.append(result)
        print(f"  {result[0]:20} {result[2]}")

        result = self.check_gpu_memory()
        self.results.append(result)
        print(f"  {result[0]:20} {result[2]}")

        # Check features
        print("\n✨ Features:")

        result = self.check_api_authentication()
        self.results.append(result)
        print(f"  {result[0]:20} {result[2]}")

        result = self.check_file_organization()
        self.results.append(result)
        print(f"  {result[0]:20} {result[2]}")

        # Summary
        healthy = sum(1 for r in self.results if r[1])
        total = len(self.results)
        health_score = (healthy / total) * 100

        print("\n" + "=" * 60)
        print(f"📊 Health Score: {health_score:.1f}% ({healthy}/{total} checks passed)")

        if health_score == 100:
            print("✅ System is fully operational!")
        elif health_score >= 80:
            print("⚠️ System is operational with minor issues")
        else:
            print("❌ System has critical issues requiring attention")

        print("=" * 60 + "\n")

        return health_score

    def save_health_report(self):
        """Save health report to file"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "checks": [
                {"name": r[0], "healthy": r[1], "message": r[2]}
                for r in self.results
            ],
            "health_score": sum(1 for r in self.results if r[1]) / len(self.results) * 100
        }

        with open("/opt/tower-anime-production/logs/health_report.json", "w") as f:
            json.dump(report, f, indent=2)

        print(f"📄 Report saved to /opt/tower-anime-production/logs/health_report.json")

def main():
    monitor = AnimeHealthMonitor()
    health_score = monitor.run_health_checks()
    monitor.save_health_report()

    # Exit with appropriate code
    if health_score == 100:
        sys.exit(0)
    elif health_score >= 80:
        sys.exit(1)  # Warning
    else:
        sys.exit(2)  # Critical

if __name__ == "__main__":
    main()