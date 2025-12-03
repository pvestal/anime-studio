#!/bin/bash
# Stress and reliability tests for anime production system

echo "================================"
echo "🔥 STRESS & RELIABILITY TESTING"
echo "================================"

# Test 1: Check file outputs
echo -e "\n📁 TEST 1: FILE OUTPUT VERIFICATION"
ls -la /mnt/1TB-storage/ComfyUI/output/anime_* 2>/dev/null | tail -5
FILE_COUNT=$(ls /mnt/1TB-storage/ComfyUI/output/anime_* 2>/dev/null | wc -l)
echo "Total anime files generated: $FILE_COUNT"

# Test 2: Crash recovery
echo -e "\n💥 TEST 2: CRASH RECOVERY TEST"
echo "Creating job before crash..."
JOB_ID=$(curl -s -X POST http://localhost:8328/generate -H "Content-Type: application/json" -d '{"prompt": "crash recovery test"}' | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)
echo "Job ID: $JOB_ID"

echo "Simulating crash by killing service..."
sudo systemctl stop tower-anime-production
sleep 2

echo "Restarting service..."
sudo systemctl start tower-anime-production
sleep 5

echo "Checking if job persisted after crash..."
curl -s http://localhost:8328/jobs/$JOB_ID | python3 -m json.tool | grep -E "job_id|status"

# Test 3: Stress test with 20 concurrent requests
echo -e "\n🔥 TEST 3: STRESS TEST (20 concurrent)"
START_TIME=$(date +%s)

for i in {1..20}; do
  curl -s -X POST http://localhost:8328/generate \
    -H "Content-Type: application/json" \
    -d "{\"prompt\": \"stress test $i\"}" > /dev/null 2>&1 &
done

wait
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "20 concurrent requests completed in: ${DURATION}s"

# Test 4: Memory check after stress
echo -e "\n💾 TEST 4: MEMORY AFTER STRESS"
ps aux | grep anime_generation | grep -v grep | awk '{sum+=$6} END {print "Total memory used: " sum/1024 " MB"}'

# Test 5: Database connection pool stress
echo -e "\n🗄️ TEST 5: DATABASE CONNECTION STRESS"
for i in {1..50}; do
  curl -s http://localhost:8328/jobs > /dev/null 2>&1 &
done
wait
echo "50 rapid database queries completed"

# Test 6: Check for orphaned processes
echo -e "\n🧹 TEST 6: ORPHANED PROCESSES CHECK"
ORPHANED=$(ps aux | grep -E "python.*anime|comfyui" | grep -v grep | wc -l)
echo "Python/ComfyUI processes running: $ORPHANED"

# Test 7: Error handling test
echo -e "\n❌ TEST 7: ERROR HANDLING"
echo "Testing malformed request..."
curl -X POST http://localhost:8328/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": null}' 2>&1 | head -1

echo "Testing non-existent job..."
curl -s http://localhost:8328/jobs/fake-job-id 2>&1 | head -1

# Test 8: ComfyUI availability during generation
echo -e "\n🎨 TEST 8: COMFYUI BLOCKING TEST"
curl -s -X POST http://localhost:8328/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "blocking test"}' > /dev/null 2>&1 &

sleep 1
COMFYUI_STATUS=$(curl -s http://localhost:8188/system_stats -w "\n%{http_code}" | tail -1)
if [ "$COMFYUI_STATUS" == "200" ]; then
  echo "ComfyUI accessible during generation: ✅"
else
  echo "ComfyUI blocked during generation: ❌"
fi

# Final summary
echo -e "\n================================"
echo "📊 STRESS TEST SUMMARY"
echo "================================"
echo "Files generated: $FILE_COUNT"
echo "Processes running: $ORPHANED"
echo "Service status: $(sudo systemctl is-active tower-anime-production)"

# Check for any errors in logs
echo -e "\nRecent errors in service log:"
sudo journalctl -u tower-anime-production -n 50 | grep -i error | tail -3