#!/bin/bash

echo "=========================================="
echo "TESTING ALL CHARACTER ENDPOINTS"
echo "=========================================="

echo -e "\n=== CHARACTER STUDIO (Port 8329) ==="

endpoints=(
    "/"
    "/health"
    "/characters"
    "/api/characters"
    "/character/1"
    "/api/character/1"
    "/character"
    "/api/character"
    "/docs"
)

for endpoint in "${endpoints[@]}"; do
    echo -n "Testing http://localhost:8329$endpoint: "
    response=$(curl -s -w "STATUS:%{http_code}" http://localhost:8329$endpoint)
    status="${response##*STATUS:}"
    body="${response%STATUS:*}"
    echo "Status $status"
    if [ "$status" = "200" ]; then
        echo "$body" | head -50
    fi
    echo
done

echo -e "\n=== MAIN API (Port 8328) ==="

endpoints=(
    "/characters"
    "/api/anime/characters"
    "/api/characters"
    "/api/anime/character/1"
    "/api/anime/character-versions"
    "/api/anime/bible/characters"
)

for endpoint in "${endpoints[@]}"; do
    echo -n "Testing http://localhost:8328$endpoint: "
    response=$(curl -s -w "STATUS:%{http_code}" http://localhost:8328$endpoint)
    status="${response##*STATUS:}"
    body="${response%STATUS:*}"
    echo "Status $status"
    if [ "$status" = "200" ]; then
        echo "$body" | head -50
    fi
    echo
done

echo -e "\n=== TESTING CREATE/UPDATE/DELETE ==="

echo "Creating test character on 8328:"
curl -X POST http://localhost:8328/api/anime/characters \
    -H "Content-Type: application/json" \
    -d '{"name": "Test Character", "description": "Test"}' \
    -s -w " [Status: %{http_code}]\n"

echo -e "\nCreating test character on 8329:"
curl -X POST http://localhost:8329/api/characters \
    -H "Content-Type: application/json" \
    -d '{"name": "Test Character", "description": "Test"}' \
    -s -w " [Status: %{http_code}]\n"