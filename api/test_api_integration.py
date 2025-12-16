#!/usr/bin/env python3
"""
Simple test to verify API endpoints work with the database models
"""

import sys

import requests

# Test configuration
API_BASE = "http://localhost:8331/api/anime"


def test_health_endpoint():
    """Test the health endpoint"""
    try:
        response = requests.get(f"{API_BASE}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"   Service: {data.get('service', 'unknown')}")
            return True
        else:
            print(f"   Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"Health endpoint test failed: {e}")
        return False


def main():
    """Run API integration tests"""
    print("Testing API integration...")

    if test_health_endpoint():
        print("✅ Health endpoint working")
    else:
        print("❌ Health endpoint failed")


if __name__ == "__main__":
    main()
