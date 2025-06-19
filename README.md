# AI Awareness Project Backend

A FastAPI-based backend service that handles user data processing, AI integrations, and content generation for the AI Awareness Project. The backend now uses Supabase for database management and includes comprehensive AI-powered features for deepfake education.

## 🏗️ Project Structure

```
backend/
├── main.py                        # FastAPI application entry point
├── supabase_service.py            # Supabase client and database operations
├── supabase_models.py             # Supabase table models and schemas
├── s3_service.py                  # AWS S3 operations for media storage
├── face_swap_config.json          # Face swap configuration for Akool API
├── requirements.txt               # Python dependencies
├── init_supabase.py               # Supabase initialization and setup
├── supabase_schema.sql            # Database schema for Supabase
├── vercel.json                    # Vercel deployment configuration
└── README.md                      # This file
```

## 🚀 API Endpoints

### User Management
- `POST /api/complete-onboarding`
  - Complete user onboarding with photo, voice, and personal data
  - Uploads user image and voice to S3
  - Generates caricature and talking photo
  - Returns: user object with IDs and URLs

- `GET /api/users/{user_id}`
  - Retrieve user information and progress from Supabase
  - Returns: user data with current page, step, and completed modules

- `PUT /api/users/{user_id}/progress`
  - Update user progress (current page, step, completed modules)
  - Required fields: user_id, current_page, current_step

### AI Content Generation

#### Voice & Narration
- `POST /api/generate-narration`
  - Generate personalized narration using ElevenLabs
  - Uses user's cloned voice for natural speech
  - Returns: audio data as base64

- `POST /api/generate-voice-dub`
  - Dub pre-recorded audio with user's voice using ElevenLabs Dubbing API
  - Used for scenario simulations (investment calls, emergency calls)
  - Returns: dubbed audio as base64

#### Visual Content Generation
- `POST /api/analyze-face`
  - Analyze facial features using OpenAI Vision API
  - Extracts facial landmarks for caricature generation
  - Returns: facial features data

- `POST /api/generate-caricature`
  - Create personalized caricature using DALL-E
  - Based on user's facial features and preferences
  - Returns: caricature URL

- `POST /api/generate-faceswap-image`
  - Perform high-quality face swap using Akool API
  - Swaps user's face onto scenario base images
  - Returns: faceswapped image URL

- `POST /api/generate-talking-photo`
  - Create talking video using Akool Talking Photo API
  - Combines caricature with generated voice
  - Supports scenario-specific content (lottery, crime, etc.)
  - Returns: video URL with fallback to sample videos

- `POST /api/generate-talking-photo`
  - Create talking video using Akool Talking Photo API
  - Combines caricature with generated voice
  - Supports scenario-specific content (lottery, crime, etc.)
  - Returns: video URL with fallback to sample videos

#### Progress Tracking
- `GET /api/progress/{task_id}`
  - Check status of AI generation tasks
  - Used for polling long-running operations
  - Returns: progress percentage and completion status

## 🛠️ Technology Stack

### Core Framework
- **Python 3.11+**
- **FastAPI** - Modern web framework for APIs
- **Uvicorn** - ASGI server for production deployment

### Database
- **Supabase** - PostgreSQL database with real-time features
- **Supabase Python Client** - Official Python SDK
- **SQLAlchemy** - Legacy ORM (being phased out)

### AI Services
- **OpenAI API** - Face analysis and DALL-E image generation
- **ElevenLabs API** - Voice cloning and text-to-speech
- **ElevenLabs Dubbing API** - Voice dubbing for scenarios
- **Akool API** - Face swap and talking photo generation

### Cloud Services
- **Amazon S3** - Media storage (images, videos, audio)
- **CloudFront** - CDN for fast media delivery
- **Vercel** - Deployment platform

## 🚀 Getting Started

### 1. Environment Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Variables
Create a `.env` file with the following variables:

```env
# Supabase Configuration
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# AI Service Keys
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
AKOOL_API_KEY=your_akool_api_key
AKOOL_CLIENT_ID=your_akool_client_id
AKOOL_CLIENT_SECRET=your_akool_client_secret

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
S3_BUCKET_NAME=your_s3_bucket_name
AWS_REGION=us-east-1

# CDN Configuration
CLOUDFRONT_DOMAIN=your_cloudfront_domain
```

### 3. Database Setup
```bash
# Initialize Supabase tables
python init_supabase.py
```

### 4. Start Development Server
```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## 📊 Database Schema

### Users Table
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    age INTEGER NOT NULL,
    gender VARCHAR(50) NOT NULL,
    image_url TEXT,
    voice_id VARCHAR(255),
    caricature_url TEXT,
    talking_photo_url TEXT,
    current_page VARCHAR(100),
    current_step INTEGER DEFAULT 0,
    completed_modules TEXT[] DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Quiz Answers Table
```sql
CREATE TABLE quiz_answers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    module VARCHAR(100) NOT NULL,
    answers JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 🔄 API Workflow Examples

### Complete User Onboarding
1. `POST /api/complete-onboarding` - Upload photo/voice, generate caricature
2. `PUT /api/users/{id}/progress` - Set initial page to ModuleSelection

### Scenario Generation
1. `POST /api/generate-faceswap-image` - Swap user face onto scenario image
2. `POST /api/generate-talking-photo` - Create talking video with scenario script
3. `PUT /api/users/{id}/progress` - Update to next step

### Voice Dubbing for Scenarios
1. `POST /api/generate-voice-dub` - Dub pre-recorded audio with user's voice
2. Return base64 audio for immediate playback

## 🚀 Deployment

### Vercel Deployment
The project includes `vercel.json` for easy deployment to Vercel:

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel --prod
```

### Local Production
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 📝 API Documentation

Once the server is running, API documentation is available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## 🔧 Development Notes

### Fallback Strategy
The system implements a robust fallback strategy for AI services:
1. **Primary**: S3 upload with CloudFront delivery
2. **Secondary**: Direct Akool URL if S3 fails
3. **Tertiary**: Scenario-specific sample videos if API fails

### Polling Mechanism
Long-running AI tasks use polling with exponential backoff:
- Initial delay: 5 seconds
- Polling interval: 10 seconds
- Maximum attempts: 24 (4 minutes total)

### Error Handling
- Graceful degradation with sample content
- User-friendly error messages in Korean
- Comprehensive logging for debugging

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly with the frontend
5. Submit a pull request

## 📄 License

This project is part of the AI Awareness educational platform. 