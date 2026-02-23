#!/bin/bash
# Fix Echo Brain for Production Use

echo "🔧 Fixing Echo Brain for Production..."

# 1. Create Kai Nakamura character
echo "1. Creating Kai Nakamura character..."
PGPASSWORD='***REMOVED***' psql -h localhost -U patrick -d anime_production << 'EOF'
INSERT INTO characters (project_id, name, description, personality, background)
VALUES (
    29,  -- Cyberpunk Goblin Slayer project
    'Kai Nakamura',
    'Cyberpunk goblin hunter with cybernetic enhancements. Pink hair, glowing eye implant.',
    'Determined, ruthless against goblins, protective of innocents. Haunted by past.',
    'Former corporate security turned vigilante after goblins destroyed her district in Frankfurt.'
) ON CONFLICT DO NOTHING;
EOF

# 2. Fix Echo Brain to use better model
echo "2. Updating Echo Brain to use better model..."
cat > /tmp/update_echo_config.py << 'EOF'
#!/usr/bin/env python3
import sys
sys.path.append('/opt/anime-studio/services')

# Update the echo_brain_integration.py to use better model
with open('/opt/anime-studio/services/echo_brain_integration.py', 'r') as f:
    content = f.read()

# Replace tinyllama with qwen2.5-coder
content = content.replace('model: str = "tinyllama:latest"', 'model: str = "qwen2.5-coder:7b"')

with open('/opt/anime-studio/services/echo_brain_integration.py', 'w') as f:
    f.write(content)

print("✅ Updated Echo Brain to use qwen2.5-coder:7b")
EOF

python3 /tmp/update_echo_config.py

# 3. Create LoRA entry for Kai (placeholder until trained)
echo "3. Creating LoRA entry for Kai..."
PGPASSWORD='***REMOVED***' psql -h localhost -U patrick -d anime_production << 'EOF'
INSERT INTO ai_models (model_name, model_type, character_name, status, model_path)
VALUES (
    'kai_nakamura_v1',
    'lora',
    'Kai Nakamura',
    'pending',
    'kai_nakamura_v1.safetensors'
) ON CONFLICT DO NOTHING;
EOF

# 4. Restart services
echo "4. Restarting services..."
sudo systemctl restart tower-anime-production

echo "✅ Fixes applied. Testing..."
sleep 3

# 5. Test improved Echo Brain
echo "5. Testing Echo Brain with better model..."
curl -X POST http://localhost:8328/api/echo-brain/scenes/suggest \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 29,
    "current_prompt": "Kai Nakamura hunts cyber goblins in neon Frankfurt subway"
  }' | python3 -m json.tool

echo "
📋 NEXT STEPS:
1. Train LoRA for Kai Nakamura character
2. Generate more episodes for Cyberpunk Goblin Slayer
3. Test full generation pipeline with new character
"