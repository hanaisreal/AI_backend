# AI Awareness Project Backend

FastAPI-based backend service that handles AI integrations, database operations, and concurrent content generation for deepfake education scenarios.

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

### User Management
- `POST /api/complete-onboarding` - Complete user setup with photo/voice
- `GET /api/users/{user_id}` - Get user data and progress
- `PUT /api/users/{user_id}/progress` - Update user progress

### AI Generation (Real-time)
- `POST /api/analyze-face` - Extract facial features from photo
- `POST /api/generate-caricature` - Create personalized caricature
- `POST /api/generate-talking-photo` - Create talking video + trigger scenarios
- `POST /api/generate-narration` - Generate voice narration with caching

### AI Generation (Background/Scenarios)
- `POST /api/start-scenario-generation` - Trigger concurrent scenario generation
- `POST /api/generate-faceswap-image` - Swap faces using Akool
- `POST /api/generate-voice-dub` - Dub audio with user's voice

### Progress Tracking
- `GET /api/scenario-status/{user_id}` - Check scenario generation progress
- `GET /api/progress/{task_id}` - Check AI generation task status

## 🤖 AI Integration Architecture

### Concurrent Generation Strategy
The backend uses a sophisticated concurrent generation approach:

```python
# Phase 1: Face Swaps (Concurrent)
faceswap_tasks = [lottery_faceswap, crime_faceswap]
await asyncio.gather(*faceswap_tasks)

# Phase 2: Videos + Audio (Concurrent)
concurrent_tasks = [
    lottery_talking_photo,
    crime_talking_photo, 
    investment_voice_dub,
    accident_voice_dub
]
await asyncio.gather(*concurrent_tasks)
```

### AI Service Integrations

#### OpenAI Integration
- **Face Analysis**: Vision API for facial feature extraction
- **Caricature Generation**: DALL-E 3 for personalized avatars
- **Korean Prompts**: Optimized for Korean educational content

#### ElevenLabs Integration  
- **Voice Cloning**: 10-second sample creates custom voice
- **Text-to-Speech**: Multilingual Korean voice generation
- **Voice Dubbing**: Audio replacement with user's voice

#### Akool Integration
- **Face Swapping**: High-quality face replacement 
- **Talking Photos**: Lip-synced speaking videos
- **Face Detection**: Coordinate extraction for precise swapping

### Database Schema (Supabase)

```sql
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  age INTEGER,
  gender TEXT,
  image_url TEXT,
  voice_id TEXT,
  caricature_url TEXT,
  talking_photo_url TEXT,
  
  -- Scenario Content URLs
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
  
  -- Generation Status
  pre_generation_status VARCHAR(50) DEFAULT 'pending',
  pre_generation_started_at TIMESTAMPTZ,
  pre_generation_completed_at TIMESTAMPTZ,
  pre_generation_error TEXT,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 🗄️ Storage Architecture

### AWS S3 + CloudFront
- **User Uploads**: `user_uploads/{user_id}/`
- **Caricatures**: `caricatures/`  
- **Talking Photos**: `talking_photos/`
- **Face Swaps**: `faceswap/`
- **Voice Dubs**: `voice_dubs/`
- **Audio**: `talking_photo_audio/`

### CDN Configuration
All media served through CloudFront for:
- **Global delivery** with edge caching
- **HTTPS** secure access
- **Performance optimization**

## 🔧 Development Tools

### Database Management
```bash
# Connect to Supabase (using psql)
psql "postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"

# Or use Supabase Dashboard
# https://app.supabase.co/project/[project-id]
```

### Testing API Endpoints
```bash
# Health check
curl http://localhost:8000/health

# Test user creation
curl -X POST http://localhost:8000/api/complete-onboarding \
  -H "Content-Type: multipart/form-data" \
  -F "name=Test User" \
  -F "age=25" \
  -F "gender=Female"

# Test scenario generation
curl -X POST http://localhost:8000/api/start-scenario-generation \
  -H "Content-Type: application/json" \
  -d '{"voiceId": "voice_123"}'
```

### Debugging Tips
```bash
# Enable debug logging
export LOGGING_LEVEL=DEBUG
uvicorn api.main:app --reload --log-level debug

# Monitor scenario generation
tail -f logs/scenario_generation.log

# Check database connections
export SUPABASE_LOG_LEVEL=debug
```

## 🚀 Deployment

### Vercel Deployment
```bash
# Install Vercel CLI
npm i -g vercel

# Deploy to production
vercel --prod

# Set environment variables in Vercel dashboard
# https://vercel.com/[team]/[project]/settings/environment-variables
```

### Environment Configuration
Ensure all environment variables are configured in Vercel:
- Database credentials
- AI service API keys  
- AWS storage credentials
- Domain configurations

### Performance Optimization
- **Async operations** for AI generation
- **Connection pooling** for database
- **CDN caching** for media files
- **Background tasks** for scenarios

## 📊 Monitoring & Logging

### Structured Logging
The backend uses clean, structured logging:
```
[USER 16] 🚀 SCENARIO_GEN: Starting background generation
[USER 16] ✅ FACESWAP_LOTTERY: Generation completed
[USER 16] 💾 FACESWAP_LOTTERY: URL saved to database
[USER 16] ✅ SCENARIO_GEN: FINISHED - Status: completed, Items: 6/6
```

### Error Handling
- **Graceful degradation** for AI service failures
- **Partial success** tracking for concurrent operations
- **Comprehensive error logging** with context
- **User-friendly error messages** in Korean

## 🤝 Contributing

1. Follow Python PEP 8 style guidelines
2. Add type hints for all functions
3. Write comprehensive docstrings
4. Test API endpoints thoroughly
5. Update documentation for new features

## 📄 License

MIT License - See LICENSE file for details.