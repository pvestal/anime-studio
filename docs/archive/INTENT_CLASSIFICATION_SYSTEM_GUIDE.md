# Intent Classification System - Complete Implementation Guide

## Overview

This comprehensive intent classification system addresses the critical routing failures in the anime production pipeline by properly classifying user requests between image and video generation workflows. The system provides intelligent routing, natural language processing, and guided user interactions.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Interface Layer                         │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐   │
│  │ IntentClassification│  │     Guided Wizards &            │   │
│  │     Wizard.vue      │  │    Clarification UI             │   │
│  └─────────────────────┘  └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                       API Layer                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           FastAPI Endpoints                             │   │
│  │   • /api/intent/classify                               │   │
│  │   • /api/intent/clarify                                │   │
│  │   • /api/workflow/route                                │   │
│  │   • /api/templates/quick                               │   │
│  │   • /api/preferences/{user_id}                         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Classification Engine                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Pattern Matcher │  │ Echo Brain NLP  │  │ User Preference │ │
│  │    System       │  │   Integration   │  │    Manager      │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                Ambiguity Resolution System                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   Ambiguity     │  │   Resolution    │  │   Progressive   │ │
│  │   Detection     │  │   Strategies    │  │   Refinement    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Database Layer                               │
│  • Intent Classifications  • User Preferences                  │
│  • Pattern Learning       • Workflow Performance              │
│  • Ambiguity Resolution   • Quick Templates                   │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Intent Classification Engine (`intent_classification_system.py`)

**Purpose**: Main classification engine that processes user requests and determines intent.

**Key Features**:
- Multi-tier classification (Content Type, Generation Scope, Style Preference, etc.)
- Pattern-based detection with regex matching
- Echo Brain integration for advanced NLP
- User preference learning
- Confidence scoring and validation

**Usage Example**:
```python
from intent_classification_system import create_intent_classifier

# Initialize
classifier = create_intent_classifier(db_manager)

# Classify user intent
classification = await classifier.classify_intent(
    "Create a character named Kai with silver hair and blue eyes",
    user_id="user123"
)

print(f"Content Type: {classification.content_type.value}")
print(f"Scope: {classification.generation_scope.value}")
print(f"Confidence: {classification.confidence_score}")
```

### 2. Echo Brain NLP Integration (`echo_nlp_integration.py`)

**Purpose**: Advanced natural language processing using Echo Brain for contextual understanding.

**Key Features**:
- Contextual analysis of user requests
- Character entity extraction
- Prompt optimization
- Style and quality analysis
- Multi-model selection for different analysis types

**Usage Example**:
```python
from echo_nlp_integration import EchoNLPProcessor

nlp = EchoNLPProcessor()

# Perform intent analysis
intent = await nlp.perform_intent_analysis(
    "Generate a 30-second action scene with robots"
)

# Optimize prompt
optimization = await nlp.optimize_prompt(
    "anime girl with pink hair",
    target_style="photorealistic_anime"
)
```

### 3. FastAPI Endpoints (`intent_classification_api.py`)

**Purpose**: RESTful API layer providing access to classification services.

**Key Endpoints**:

#### POST `/api/intent/classify`
Classify user intent from natural language input.

```json
{
  "user_prompt": "Create a character named Kai with silver hair",
  "user_id": "user123",
  "preferred_style": "traditional_anime",
  "quality_preference": "high"
}
```

Response:
```json
{
  "request_id": "intent_1699123456_1234",
  "classification_successful": true,
  "confidence_score": 0.85,
  "content_type": "image",
  "generation_scope": "character_profile",
  "style_preference": "traditional_anime",
  "character_names": ["Kai"],
  "target_service": "comfyui_character",
  "estimated_time_minutes": 3,
  "processed_prompt": "Anime character portrait of Kai with silver hair and blue eyes, traditional anime style, high quality"
}
```

#### POST `/api/workflow/route`
Route classified intent to appropriate generation workflow.

#### GET `/api/templates/quick`
Get quick classification templates for common requests.

### 4. Vue.js Frontend (`IntentClassificationWizard.vue`)

**Purpose**: Interactive user interface for guided intent classification.

**Key Features**:
- Step-by-step wizard interface
- Quick template selection
- Real-time input validation and hints
- Clarification question handling
- Progress visualization
- Responsive design

**Integration**:
```vue
<template>
  <IntentClassificationWizard
    @generation-complete="handleGenerationComplete"
    @classification-update="handleClassificationUpdate"
  />
</template>
```

### 5. Ambiguity Resolution System (`ambiguity_resolution_system.py`)

**Purpose**: Handles unclear or ambiguous user requests through intelligent strategies.

**Key Features**:
- Pattern-based ambiguity detection
- Multiple resolution strategies (clarification, defaults, templates)
- Progressive refinement for complex cases
- Context-aware decision making

## Database Schema

### Core Tables

#### `intent_classifications`
Stores all classification results for learning and analytics.
```sql
CREATE TABLE intent_classifications (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(255) UNIQUE,
    user_prompt TEXT NOT NULL,
    content_type VARCHAR(50) NOT NULL,
    generation_scope VARCHAR(50) NOT NULL,
    style_preference VARCHAR(50) NOT NULL,
    confidence_score DECIMAL(3,2),
    classification_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `user_preferences`
User-specific preferences for classification.
```sql
CREATE TABLE user_preferences (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE,
    preferences_data JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `quick_classification_templates`
Pre-defined templates for common generation types.

#### `ambiguity_resolution_strategies`
Strategies for handling unclear requests.

## Setup and Installation

### 1. Database Setup
```bash
# Create database schema
psql -h 192.168.50.135 -U patrick -d anime_production -f intent_classification_schema.sql
```

### 2. Install Dependencies
```bash
cd /opt/tower-anime-production
pip install fastapi uvicorn aiohttp psycopg2-binary pydantic
```

### 3. Start the API Service
```bash
cd /opt/tower-anime-production
python intent_classification_api.py
```
Service will start on port 8330.

### 4. Frontend Integration
Copy the Vue.js components to your frontend project and import:
```javascript
import IntentClassificationWizard from './components/IntentClassificationWizard.vue'
```

## User Scenarios Handled

### Scenario 1: Clear Character Request
**User Input**: "Create a character named Kai with silver hair and blue eyes"

**System Response**:
- Content Type: Image
- Scope: Character Profile
- Style: Traditional Anime (from user preferences)
- Confidence: 0.92
- No clarification needed

### Scenario 2: Video with Missing Duration
**User Input**: "Generate an action scene with Kai fighting robots"

**System Response**:
- Content Type: Video (detected)
- Scope: Action Sequence
- Ambiguity: Duration not specified
- Clarification: "How long should the video be?"
- Options: ["5 seconds", "15 seconds", "30 seconds", "1 minute"]

### Scenario 3: Ambiguous Content Type
**User Input**: "Make a cool image video of a cyberpunk city"

**System Response**:
- Ambiguity: Conflicting content type indicators
- Clarification: "Would you like an image or video?"
- Default: Image (based on ambiguity resolution rules)

### Scenario 4: Insufficient Detail
**User Input**: "Create something anime"

**System Response**:
- Progressive Refinement Strategy
- Follow-up questions:
  1. "What type of anime content? (Character, Scene, Background)"
  2. "What style? (Traditional, Photorealistic, Artistic)"
  3. "Any specific details? (Characters, colors, mood)"

### Scenario 5: Template Selection
**User Input**: User selects "Character Profile Image" template

**System Response**:
- Pre-populated classification
- Content Type: Image
- Scope: Character Profile
- Style: Traditional Anime
- Quality: High
- Ready for generation

## API Integration Examples

### Python Integration
```python
import requests

# Classify intent
response = requests.post('http://localhost:8330/api/intent/classify', json={
    "user_prompt": "Create a magical girl character with pink hair",
    "user_id": "user123"
})

classification = response.json()

# Route to workflow
routing_response = requests.post('http://localhost:8330/api/workflow/route', json={
    "classification": classification
})

workflow_info = routing_response.json()
print(f"Target service: {workflow_info['target_service']}")
print(f"Estimated time: {workflow_info['estimated_time']} minutes")
```

### JavaScript Frontend Integration
```javascript
// Classify user intent
async function classifyIntent(userPrompt, userId = 'default') {
    const response = await fetch('/api/intent/classify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_prompt: userPrompt,
            user_id: userId
        })
    });

    return await response.json();
}

// Handle clarification if needed
async function handleClarification(requestId, answers) {
    const response = await fetch('/api/intent/clarify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            request_id: requestId,
            clarification_responses: answers
        })
    });

    return await response.json();
}
```

## Performance and Optimization

### Caching Strategy
- Echo Brain responses cached for 5 minutes
- User preferences cached in memory
- Pattern match results cached per session

### Echo Brain Model Selection
- **Quick Classification**: `llama3.2:latest` (fast response)
- **Intent Analysis**: `qwen2.5-coder:32b` (balanced accuracy/speed)
- **Complex Analysis**: `llama3.1:70b` (maximum accuracy)
- **Prompt Optimization**: `mixtral:8x7b` (creative enhancement)

### Database Optimization
- Indexes on frequently queried fields
- JSON indexes for preference and classification data
- Automatic cleanup of old classification records

## Monitoring and Analytics

### Available Metrics
- Classification accuracy over time
- Most common request types
- Ambiguity resolution success rates
- User preference evolution
- Service response times

### Analytics Endpoints
```bash
# Get classification statistics
GET /api/analytics/classification?days_back=30

# Response includes:
# - Request counts by type and scope
# - Average confidence scores
# - Ambiguity trends
# - User behavior patterns
```

## Error Handling

### Classification Failures
- Fallback to default classification with low confidence
- Graceful degradation to manual workflow selection
- Error logging for system improvement

### Echo Brain Unavailable
- Local pattern matching fallback
- Cached response utilization
- User notification of degraded service

### Database Connection Issues
- SQLite fallback for critical operations
- Operation queuing for later sync
- Service health monitoring

## Troubleshooting

### Common Issues

#### 1. Low Classification Confidence
**Symptoms**: Classification results with confidence < 0.5
**Solutions**:
- Check Echo Brain service status
- Verify user prompt length and detail
- Review pattern matching rules
- Check user preference data

#### 2. Clarification Questions Not Appearing
**Symptoms**: Ambiguous requests processed without clarification
**Solutions**:
- Verify ambiguity detection rules
- Check resolution strategy configuration
- Review frontend clarification handling

#### 3. Slow Response Times
**Symptoms**: API responses > 5 seconds
**Solutions**:
- Check Echo Brain service load
- Review database query performance
- Verify caching configuration
- Monitor system resources

### Debug Mode
Enable debug logging:
```python
import logging
logging.getLogger('intent_classification').setLevel(logging.DEBUG)
```

## Future Enhancements

### Planned Features
1. **Advanced Learning**: ML model training on user feedback
2. **Voice Input**: Speech-to-text integration
3. **Image Analysis**: Visual prompt analysis for style detection
4. **Multi-language**: Support for non-English prompts
5. **Workflow Optimization**: Dynamic routing based on system load

### Integration Opportunities
1. **Character Consistency Engine**: Link with character database
2. **Project Management**: Integration with episode/series tracking
3. **Quality Assessment**: Automatic quality evaluation
4. **Resource Management**: Dynamic VRAM and processing allocation

## Support and Maintenance

### Regular Maintenance Tasks
1. **Database Cleanup**: Remove old classification records (monthly)
2. **Cache Optimization**: Clear stale cache entries (weekly)
3. **Pattern Updates**: Review and update detection patterns (quarterly)
4. **User Feedback**: Analyze feedback and update strategies (monthly)

### Monitoring Checklist
- [ ] API response times < 2 seconds average
- [ ] Classification confidence > 0.7 average
- [ ] Echo Brain integration success rate > 95%
- [ ] Database connection stability
- [ ] Frontend error rates < 1%

## Contact and Support

For issues, questions, or feature requests:
- Create issues in the Tower project repository
- Check the Knowledge Base for common solutions
- Review system logs for detailed error information

---

This intent classification system transforms the anime production pipeline from a broken, single-path workflow into an intelligent, user-friendly system that properly routes requests based on natural language understanding and user intent.