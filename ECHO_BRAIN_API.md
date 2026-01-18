# Echo Brain API Documentation

## Overview
Echo Brain provides AI-powered creative assistance for your anime production system. All processing happens locally on your machine using Ollama, ensuring complete privacy and creative control.

## Base URL
`http://localhost:8328/api/echo-brain`

## Endpoints

### 1. Status & Configuration

#### Check Echo Brain Status
```http
GET /api/echo-brain/status
```
**Response:**
```json
{
    "status": "connected",
    "models": ["tinyllama:latest", "llama3.2", "mistral"],
    "current_model": "tinyllama:latest"
}
```

#### Configure Echo Brain
```http
POST /api/echo-brain/configure
```
**Request:**
```json
{
    "model": "llama3.2",
    "temperature": 0.8,
    "enabled": true
}
```

### 2. Scene Management

#### Suggest Scene Details
```http
POST /api/echo-brain/scenes/suggest
```
**Request:**
```json
{
    "project_id": 24,
    "current_prompt": "A tense meeting in Tokyo skyscraper"
}
```
**Response:**
```json
{
    "suggestions": {
        "lighting": "Neon-drenched with deep shadows",
        "camera_angles": ["Low angle for power", "Close-ups for tension"],
        "character_expressions": "Controlled anger, subtle eye movements",
        "mood": "Tense with underlying threat",
        "environmental_details": "Rain on windows, city lights below"
    },
    "context_summary": {
        "project": "Tokyo Debt Desire",
        "characters_considered": 4
    }
}
```

### 3. Character Development

#### Generate Character Dialogue
```http
POST /api/echo-brain/characters/{character_id}/dialogue
```
**Request:**
```json
{
    "scene_context": "Confrontation in the office",
    "emotion": "angry but controlled"
}
```
**Response:**
```json
{
    "character": "Mei Kobayashi",
    "dialogue": {
        "dialogue": "You think you can just walk away from this?",
        "delivery": "Cold, measured tone with underlying fury",
        "character_notes": "Maintains professional composure despite anger"
    }
}
```

### 4. Episode Management

#### Continue Episode
```http
POST /api/echo-brain/episodes/{episode_id}/continue
```
**Request:**
```json
{
    "direction": "romantic tension",
    "focus_character": "Mei"
}
```
**Response:**
```json
{
    "episode": "Neon Awakening",
    "current_scenes": 5,
    "suggestions": {
        "scene_suggestions": [
            {
                "scene_number": 6,
                "title": "Rooftop Confession",
                "setting": "Corporate building rooftop, sunset",
                "characters": ["Mei", "Kai"],
                "prompt": "Mei confronts her feelings amid the city skyline",
                "story_advancement": "Character relationship development"
            }
        ]
    }
}
```

#### Batch Suggest for Episode
```http
POST /api/echo-brain/episodes/{episode_id}/batch-suggest
```
**Request:**
```json
{
    "focus": "visual_consistency"
}
```
**Response:**
```json
{
    "episode_id": "18c31c2c-4aac-481d-9170-3fc02485f654",
    "suggestions": {
        "batch_count": 5,
        "focus": "visual_consistency",
        "suggestions": {
            "scene-id-1": {
                "visual_notes": "Maintain neon color palette",
                "character_notes": "Keep Mei's hair consistent",
                "narrative_notes": "Build tension gradually"
            }
        }
    }
}
```

### 5. Story Analysis

#### Analyze Storyline
```http
POST /api/echo-brain/storyline/analyze
```
**Request:**
```json
{
    "project_id": 24,
    "focus": "character_arcs"
}
```
**Response:**
```json
{
    "episodes_analyzed": 3,
    "analysis": {
        "character_analysis": "Mei shows consistent growth from cold professional to emotionally engaged",
        "plot_issues": [],
        "pacing_notes": "Good tension buildup in episodes 1-2",
        "theme_coherence": "Debt and redemption themes well maintained",
        "improvements": [
            "Add more Kai backstory",
            "Explore side character motivations"
        ]
    }
}
```

### 6. Creative Brainstorming

#### Brainstorm Project Ideas
```http
POST /api/echo-brain/projects/{project_id}/brainstorm
```
**Request:**
```json
{
    "theme": "cyberpunk debt collection",
    "constraints": ["Must include Mei", "Corporate setting"]
}
```
**Response:**
```json
{
    "project": "Tokyo Debt Desire",
    "ideas": {
        "ideas": [
            {
                "title": "The Data Heist",
                "description": "Mei discovers hidden financial records",
                "theme_fit": "Explores corporate corruption and debt",
                "scene_concept": "Night infiltration of server room"
            }
        ]
    }
}
```

### 7. Feedback System

#### Provide Feedback on Suggestion
```http
POST /api/echo-brain/suggestions/{suggestion_id}/feedback
```
**Request:**
```json
{
    "accepted": true,
    "rating": 4,
    "notes": "Good suggestion, applied with modifications"
}
```
**Response:**
```json
{
    "message": "Feedback saved",
    "suggestion_id": 1
}
```

## Database Schema

All Echo Brain interactions are stored in the `echo_brain_suggestions` table:

```sql
CREATE TABLE echo_brain_suggestions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    episode_id UUID REFERENCES episodes(id),
    character_id INTEGER REFERENCES characters(id),
    scene_id UUID REFERENCES scenes(id),
    request_type VARCHAR(100),
    request_data JSONB,
    response_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_feedback JSONB DEFAULT NULL
);
```

## Configuration

Echo Brain uses these default settings:
- **Model**: `tinyllama:latest` (fast responses)
- **Temperature**: 0.7 (balanced creativity)
- **Max Tokens**: 500 (concise suggestions)
- **Timeout**: 10 seconds

## Error Handling

All endpoints return graceful fallbacks when Echo Brain is offline:
- Status endpoint returns `{"status": "offline"}`
- Suggestion endpoints return generic fallback suggestions
- No external API calls are made - everything stays local

## Privacy Features

1. **Local Processing**: All AI processing happens on localhost:11434 (Ollama)
2. **No External APIs**: Zero data leaves your machine
3. **User Control**: Can be disabled entirely via configuration
4. **Data Ownership**: All suggestions stored in your local PostgreSQL

## Testing

Test all endpoints:
```bash
# Basic endpoints
python3 /opt/tower-anime-production/test_echo_endpoints.py

# Advanced endpoints
python3 /opt/tower-anime-production/test_advanced_echo.py
```

## Integration Example

```javascript
// Frontend Vue.js component
async function getSceneSuggestions(projectId, prompt) {
    const response = await fetch('/api/echo-brain/scenes/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            project_id: projectId,
            current_prompt: prompt
        })
    });

    const data = await response.json();
    return data.suggestions;
}
```

## Next Steps

1. Add UI components in Episode Manager for "Get AI Suggestions" buttons
2. Create a settings panel for Echo Brain configuration
3. Build analytics dashboard for suggestion acceptance rates
4. Implement learning from feedback to improve suggestions

---

**Version**: 1.0.0
**Last Updated**: January 2, 2026
**Author**: Tower Anime Production System