# AI Awareness Project Backend

FastAPI-based backend service that handles AI integrations, database operations, and optimized content generation for deepfake education scenarios.

## 🏗️ Project Structure

```
backend/
├── api/                        # Core API module
│   ├── main.py                 # FastAPI application entry point
│   ├── supabase_service.py     # Database operations
│   ├── supabase_models.py      # Database models and schemas
│   ├── s3_service.py           # AWS S3 media storage
│   ├── face_swap_config.json   # Akool API configuration
│   └── requirements.txt        # Python dependencies
├── vercel.json                 # Vercel deployment configuration
└── README.md                   # This file
```

## ⚡ Quick Start

### Prerequisites
- **Python 3.11+**
- **Supabase** account and project
- **AWS S3** bucket with CloudFront CDN
- **AI Service APIs**: OpenAI, ElevenLabs, Akool

### Installation
```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r api/requirements.txt

# Set up environment variables
cp .env.example .env  # Configure with your API keys
```

### Environment Variables (.env)
```env
# Database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key

# AI Services
OPENAI_API_KEY=sk-your-openai-key
ELEVENLABS_API_KEY=your-elevenlabs-key
AKOOL_CLIENT_ID=your-akool-client-id
AKOOL_CLIENT_SECRET=your-akool-client-secret

# Storage
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
S3_BUCKET_NAME=your-s3-bucket-name
AWS_REGION=us-east-1
CLOUDFRONT_DOMAIN=your-cloudfront-domain
```

### Run Development Server
```bash
# Option 1: Direct uvicorn (recommended)
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Option 2: Python module
python -m api.main

# Option 3: npm script (if package.json exists)
npm run dev
```

Access the API:
- **API Server**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔌 API Endpoints

### Basic Health & Testing
- `GET /` - Root endpoint with API status and service health
- `GET /test` - Simple connectivity test endpoint  
- `GET /api/health` - Comprehensive health check for all services
- `GET /api/akool-token-test` - Test Akool API authentication

### User Management
- `POST /api/complete-onboarding` - Complete user setup with photo/voice (primary onboarding)
- `GET /api/users/{user_id}` - Retrieve user data by ID
- `PUT /api/users/{user_id}/progress` - Update user progress in modules
- `POST /api/user-info` - Save basic user information (legacy)

### AI Content Generation (Real-time)
- `POST /api/analyze-face` - Extract facial features from uploaded photo
- `POST /api/generate-caricature` - Create personalized caricature using DALL-E 3
- `POST /api/generate-talking-photo` - Create talking video + **trigger scenario pre-generation**
- `POST /api/generate-narration` - Generate voice narration with user's cloned voice

### AI Content Generation (Scenarios)
- `POST /api/generate-faceswap-image` - High-quality face swapping using Akool
- `POST /api/generate-faceswap-video` - Face-swapped video generation
- `POST /api/generate-voice-dub` - Voice dubbing with ElevenLabs Dubbing API

### Scenario Management (Pre-Generation Strategy)
- `POST /api/start-scenario-generation` - Trigger background scenario generation 
- `GET /api/scenario-status/{user_id}` - Check scenario generation progress
- `POST /api/trigger-scenario-generation/{user_id}` - Manual scenario triggering (testing)
- `GET /api/debug-scenario-generation/{user_id}` - Debug scenario generation status

### Progress Tracking
- `GET /api/progress/{task_id}` - Get AI generation task progress
- `POST /api/progress/{task_id}` - Update task progress (internal)

### Educational Content
- `POST /api/quiz-answers` - Save quiz answers to database

### Maintenance & Debug
- `POST /api/fix-voice-dub-permissions/{user_id}` - Fix S3 permissions for audio files

## 🤖 AI Integration Architecture

### Optimized Pre-Generation Strategy

The backend uses an intelligent pre-generation approach that triggers after the first talking photo:

```python
# Trigger Point: After first talking photo completion
async def trigger_scenario_pregeneration_after_first_talking_photo(user_name: str, voice_id: str):
    user = await get_user_by_voice_id(voice_id)
    
    # Background generation (non-blocking)
    asyncio.create_task(generate_scenario_content_simple(user.id, user.name, voice_id))
```

**Key Benefits:**
- **67% Faster First Experience**: First talking photo: 4-6min → 1-3min
- **Zero Module Wait Time**: All scenarios ready when user reaches modules
- **Better Resource Allocation**: No API competition during critical first impression
- **Robust Fallback**: Triggers in all cases (success, failure, timeout)

### Concurrent Generation Pipeline

```python
# Phase 1: Face Swaps (Concurrent)
faceswap_tasks = [
    generate_faceswap_image(user_image, lottery_base, "lottery"),
    generate_faceswap_image(user_image, crime_base, "crime")
]
faceswap_results = await asyncio.gather(*faceswap_tasks, return_exceptions=True)

# Phase 2: Videos + Audio (Concurrent)  
concurrent_tasks = [
    generate_talking_photo(lottery_faceswap, lottery_script),
    generate_talking_photo(crime_faceswap, crime_script),
    generate_voice_dub(investment_audio, voice_id, "investment_call"),
    generate_voice_dub(accident_audio, voice_id, "accident_call")
]
final_results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
```

### AI Service Integrations

#### OpenAI Integration
- **Face Analysis**: Vision API extracts facial features for caricature generation
- **Caricature Generation**: DALL-E 3 creates personalized educational avatars
- **Korean Optimization**: Prompts optimized for Korean educational content
- **Fallback Handling**: Sample caricatures when generation fails

#### ElevenLabs Integration  
- **Voice Cloning**: 10-second sample creates custom voice (setup during onboarding)
- **Text-to-Speech**: Real-time Korean narration with user's voice
- **Voice Dubbing API**: Advanced audio replacement for educational scenarios
- **Quality Settings**: Optimized for Korean language with background audio removal

#### Akool Integration
- **High-Quality Face Swapping**: Precise face replacement for educational scenarios
- **Talking Photos**: Lip-synced speaking videos combining face swap + voice
- **Face Detection**: Automatic coordinate extraction for accurate swapping
- **Timeout Handling**: 13+ minute polling with graceful fallback to sample content

### Database Schema (Supabase)

```sql
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  age INTEGER,
  gender TEXT,
  image_url TEXT,
  voice_id TEXT,
  voice_name TEXT,
  caricature_url TEXT,
  talking_photo_url TEXT,
  
  -- Pre-Generated Scenario Content URLs
  lottery_faceswap_url TEXT,
  crime_faceswap_url TEXT,
  lottery_video_url TEXT,
  crime_video_url TEXT,
  investment_call_audio_url TEXT,
  accident_call_audio_url TEXT,
  
  -- Progress Tracking
  current_page TEXT DEFAULT 'Landing',
  current_step INTEGER DEFAULT 0,
  completed_modules TEXT[] DEFAULT '{}',
  
  -- Pre-Generation Status Tracking
  pre_generation_status VARCHAR(50) DEFAULT 'pending',
  pre_generation_started_at TIMESTAMPTZ,
  pre_generation_completed_at TIMESTAMPTZ,
  pre_generation_error TEXT,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE quiz_answers (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  module TEXT NOT NULL,
  answers JSONB NOT NULL,
  score INTEGER,
  completed_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 🗄️ Storage Architecture

### AWS S3 + CloudFront Structure
```
deepfake-videomaking/
├── user_uploads/{user_id}/           # User uploaded photos/audio
├── caricatures/{user_id}/            # Generated caricatures
├── talking_photos/{user_id}/         # Talking photo videos
├── faceswap/{user_id}/              # Face-swapped images/videos
├── voice_dubs/{user_id}/            # Dubbed audio files
├── talking_photo_audio/{user_id}/   # Generated audio for talking photos
└── video-url/                       # Sample/fallback content
    ├── scenario1_sample.mp4         # Lottery scenario fallback
    ├── scenario2_sample.mp4         # Crime scenario fallback
    ├── voice_1.m4a                  # Investment call source audio
    └── voice_2.m4a                  # Accident call source audio
```

### CDN Configuration
All media served through CloudFront (`d3srmxrzq4dz1v.cloudfront.net`) for:
- **Global Edge Caching**: Fast delivery worldwide
- **HTTPS Security**: Secure content access
- **Performance Optimization**: Reduced latency and bandwidth usage

## 🔧 Key Technical Features

### Backend Guards & Optimization
```python
# Prevent duplicate generation and credit waste
if user.pre_generation_status == "completed":
    logger.info(f"[USER {user.id}] ⚠️ SCENARIO_GEN: Already completed, skipping")
    return user

if user.pre_generation_status == "in_progress":
    logger.info(f"[USER {user.id}] ⚠️ SCENARIO_GEN: Already in progress, skipping")
    return user
```

### Multi-Tier Fallback System
1. **Primary**: S3 upload with CloudFront delivery
2. **Secondary**: Direct Akool URL if S3 fails  
3. **Tertiary**: Scenario-specific sample videos/audio
4. **Quaternary**: Clear error messages in Korean

### Error Handling & Logging
```python
# Structured logging for monitoring
logger.info(f"[USER {user_id}] 🚀 SCENARIO_GEN: Starting background generation")
logger.info(f"[USER {user_id}] ✅ FACESWAP_LOTTERY: Generation completed")
logger.info(f"[USER {user_id}] 💾 DATABASE: All URLs saved successfully")
logger.info(f"[USER {user_id}] ✅ SCENARIO_GEN: FINISHED - Status: completed, Items: 6/6")
```

## 🚀 Development Tools

### Testing API Endpoints
```bash
# Health check
curl http://localhost:8000/api/health

# Test user onboarding
curl -X POST http://localhost:8000/api/complete-onboarding \
  -H "Content-Type: multipart/form-data" \
  -F "name=Test User" \
  -F "age=25" \
  -F "gender=Female" \
  -F "image=@test_photo.jpg" \
  -F "voice=@test_voice.wav"

# Test talking photo generation
curl -X POST http://localhost:8000/api/generate-talking-photo \
  -H "Content-Type: application/json" \
  -d '{
    "caricatureUrl": "https://example.com/caricature.jpg",
    "userName": "Test User",
    "voiceId": "voice_123",
    "audioScript": "안녕하세요! 저는 AI로 생성된 영상입니다.",
    "scenarioType": "introduction"
  }'

# Test voice dubbing
curl -X POST http://localhost:8000/api/generate-voice-dub \
  -H "Content-Type: application/json" \
  -d '{
    "audioUrl": "https://deepfake-videomaking.s3.us-east-1.amazonaws.com/video-url/voice_1.m4a",
    "voiceId": "voice_123",
    "scenarioType": "investment_call"
  }'

# Check scenario generation status
curl http://localhost:8000/api/scenario-status/16
```

### Database Management
```bash
# Connect to Supabase (using psql)
psql "postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"

# Check user data
SELECT id, name, pre_generation_status, created_at FROM users ORDER BY id DESC LIMIT 5;

# Check scenario URLs
SELECT id, name, lottery_video_url, crime_video_url, investment_call_audio_url FROM users WHERE id = 16;
```

### Debugging Tips
```bash
# Enable debug logging
export LOGGING_LEVEL=DEBUG
uvicorn api.main:app --reload --log-level debug

# Monitor scenario generation
tail -f logs/scenario_generation.log

# Check service availability
curl http://localhost:8000/api/health | jq
```

## 🚀 Deployment

### Vercel Deployment
```bash
# Install Vercel CLI
npm i -g vercel

# Deploy to production
vercel --prod

# Environment variables in Vercel Dashboard:
# https://vercel.com/[team]/[project]/settings/environment-variables
```

### Production Configuration
Ensure all environment variables are configured:
- **Database**: Supabase URL and key
- **AI Services**: OpenAI, ElevenLabs, Akool credentials
- **Storage**: AWS S3 access keys and bucket configuration  
- **CDN**: CloudFront domain for media delivery

### Performance Monitoring
- **Async Operations**: All AI generation runs asynchronously
- **Connection Pooling**: Optimized database connections
- **CDN Caching**: Global media delivery optimization
- **Background Tasks**: Non-blocking scenario generation

## 📊 Current Implementation Status

### ✅ Optimized Pre-Generation Flow
**Recent Optimization (Latest Update):**
- **Trigger Point**: Moved from onboarding to after first talking photo completion
- **Performance Gain**: 67% faster first user experience (4-6min → 1-3min)  
- **Resource Efficiency**: Prevents API competition during critical first impression
- **Zero Module Wait**: All scenario content ready when user reaches modules

### ✅ Completed Features
- **Multi-AI Integration**: OpenAI + ElevenLabs + Akool
- **Optimized Concurrent Generation**: Parallel processing for 6 scenario items
- **Smart Fallback Systems**: Multi-tier content delivery
- **Progress Tracking**: Real-time status updates
- **Background Processing**: Non-blocking scenario creation
- **Database Optimization**: Efficient data storage and retrieval

### 🔄 Continuous Improvements
- **Error Recovery**: Enhanced resilience for AI API failures
- **Performance Monitoring**: Structured logging and status tracking  
- **Security**: Input validation and authentication
- **Scalability**: Optimized for production deployment

## 🤝 Contributing

1. Follow Python PEP 8 style guidelines
2. Add comprehensive type hints for all functions
3. Write detailed docstrings for API endpoints
4. Test thoroughly with all AI service integrations
5. Update documentation for new features
6. Ensure proper error handling and logging

## 📄 License

MIT License - See LICENSE file for details.