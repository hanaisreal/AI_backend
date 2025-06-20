import os
import uuid
import asyncio
import time
import re
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from dotenv import load_dotenv
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from typing import Optional, Dict, Any, List
from urllib.parse import quote
from pydantic import BaseModel

# Define base models that will always be available (before any import attempts)
class UserCreate(BaseModel):
    name: str
    age: int
    gender: str
    image_url: Optional[str] = None
    voice_id: Optional[str] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    image_url: Optional[str] = None
    voice_id: Optional[str] = None
    caricature_url: Optional[str] = None
    talking_photo_url: Optional[str] = None
    current_page: Optional[str] = None
    current_step: Optional[int] = None
    completed_modules: Optional[List[str]] = None

class UserProgressUpdate(BaseModel):
    currentPage: Optional[str] = None
    currentStep: Optional[int] = None
    caricatureUrl: Optional[str] = None
    talkingPhotoUrl: Optional[str] = None
    completedModules: Optional[List[str]] = None

class QuizAnswerCreate(BaseModel):
    user_id: int
    module: str
    answers: Dict[str, Any]

class User(BaseModel):
    id: int
    name: str
    age: int
    gender: str
    image_url: Optional[str] = None
    voice_id: Optional[str] = None
    caricature_url: Optional[str] = None
    talking_photo_url: Optional[str] = None
    current_page: Optional[str] = None
    current_step: Optional[int] = 0
    completed_modules: Optional[List[str]] = []

class QuizAnswer(BaseModel):
    id: int
    user_id: int
    module: str
    answers: Dict[str, Any]
# Initialize Supabase service
try:
    from .supabase_service import SupabaseService
    print("✅ Supabase service module imported successfully")
    
    # Initialize Supabase service
    print("🔄 Initializing Supabase service...")
    print(f"   SUPABASE_URL: {os.getenv('SUPABASE_URL', 'NOT_SET')}")
    print(f"   SUPABASE_KEY: {'SET' if os.getenv('SUPABASE_KEY') else 'NOT_SET'}")
    
    # Only initialize if we have both URL and key
    if os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_KEY'):
        supabase_service = SupabaseService()
        print("✅ Supabase service initialized successfully")
        supabase_available = True
    else:
        print("⚠️ Skipping Supabase initialization - missing credentials")
        supabase_service = None
        supabase_available = False
except Exception as e:
    print(f"⚠️ Warning: Supabase service failed to initialize: {e}")
    supabase_service = None
    supabase_available = False
from io import BytesIO
import base64
import json
import httpx

# Load environment variables first
load_dotenv()

# AI Service SDKs
try:
    from elevenlabs.client import ElevenLabs
    elevenlabs_import_available = True
except ImportError as e:
    print(f"⚠️ ElevenLabs import failed: {e}")
    ElevenLabs = None
    elevenlabs_import_available = False

try:
    from openai import OpenAI
    openai_import_available = True
except ImportError as e:
    print(f"⚠️ OpenAI import failed: {e}")
    OpenAI = None
    openai_import_available = False

try:
    from .s3_service import s3_service
    s3_service_available = True
except ImportError as e:
    print(f"⚠️ S3 service import failed: {e}")
    s3_service = None
    s3_service_available = False

# Environment variables
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
CLOUDFRONT_DOMAIN = os.getenv("CLOUDFRONT_DOMAIN", "d3srmxrzq4dz1v.cloudfront.net")  # CDN domain
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AKOOL_CLIENT_ID = os.getenv("AKOOL_CLIENT_ID")
AKOOL_CLIENT_SECRET = os.getenv("AKOOL_CLIENT_SECRET")
AKOOL_API_KEY = os.getenv("AKOOL_API_KEY")  # Keep for backward compatibility


# Initialize Supabase tables on startup
# Tables will be created when first accessed

app = FastAPI(
    title="AI Awareness Backend API",
    description="Backend API for AI awareness education platform",
    version="1.0.0"
)

# Progress tracking storage
progress_tracking: Dict[str, Dict[str, Any]] = {}

# CORS configuration
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://ai-awareness-project-git-main-hanaisreals-projects.vercel.app",
    "https://ai-awareness-project.vercel.app",
    "https://ai-frontend-gules.vercel.app",
    "https://ai-frontend-ck6r8pnui-hanaisreals-projects.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler to ensure CORS headers are always included
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get('origin')
    if origin in origins:
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error: {str(exc)}"},
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
            }
        )
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    origin = request.headers.get('origin')
    if origin in origins:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
            }
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

# Add OPTIONS handler for preflight requests
@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
    origin = request.headers.get('origin')
    if origin in origins:
        return JSONResponse(
            content={},
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Max-Age": "86400",
            }
        )
    return JSONResponse(content={"detail": "Forbidden"}, status_code=403)

# S3 Client Initialization and CORS Configuration
s3_client = None
try:
    if all([S3_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION]):
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        print("✅ S3 client initialized successfully.")
        
        # Skip CORS setup to avoid crashes
        print("⚠️ S3 CORS setup skipped to prevent startup issues")
    else:
        print("⚠️ S3 client not initialized - missing AWS credentials")
except Exception as e:
    print(f"⚠️ Warning: S3 initialization failed: {e}")
    s3_client = None

# ElevenLabs Client Initialization
elevenlabs_client = None
if elevenlabs_import_available and ELEVENLABS_API_KEY:
    try:
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("✅ ElevenLabs client initialized successfully.")
    except Exception as e:
        print(f"⚠️ Error initializing ElevenLabs client: {e}")
else:
    print("⚠️ ElevenLabs client not initialized (import failed or missing API key)")

# OpenAI Client Initialization
openai_client = None
if openai_import_available and OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        print("✅ OpenAI client initialized successfully.")
    except Exception as e:
        print(f"⚠️ Error initializing OpenAI client: {e}")
else:
    print("⚠️ OpenAI client not initialized (import failed or missing API key)")

# Akool Token Management
akool_token = None
akool_token_expiry = 0

async def get_akool_token():
    """Get or refresh Akool API token"""
    global akool_token, akool_token_expiry
    
    # Check if we have a valid token
    current_time = time.time()
    if akool_token and current_time < akool_token_expiry:
        return akool_token
    
    # If we have a direct API key, use it
    if AKOOL_API_KEY and not AKOOL_CLIENT_ID:
        print("Using direct AKOOL_API_KEY for authentication")
        return AKOOL_API_KEY
    
    # Generate new token using clientId/clientSecret
    if not AKOOL_CLIENT_ID or not AKOOL_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Akool credentials not configured. Need AKOOL_CLIENT_ID and AKOOL_CLIENT_SECRET.")
    
    try:
        print(f"🔑 Getting new Akool token with clientId: {AKOOL_CLIENT_ID[:10]}...")
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_response = await client.post(
                "https://openapi.akool.com/api/open/v3/getToken",
                headers={"Content-Type": "application/json"},
                json={
                    "clientId": AKOOL_CLIENT_ID,
                    "clientSecret": AKOOL_CLIENT_SECRET
                }
            )
            
            if token_response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Failed to get Akool token: {token_response.status_code}")
            
            token_data = token_response.json()
            if token_data.get("code") != 1000:
                raise HTTPException(status_code=500, detail=f"Akool token error: {token_data.get('msg', 'Unknown error')}")
            
            akool_token = token_data.get("token")
            akool_token_expiry = current_time + (365 * 24 * 60 * 60)  # 1 year from now
            
            print(f"✅ Got new Akool token: {akool_token[:20]}...")
            return akool_token
            
    except Exception as e:
        print(f"❌ Error getting Akool token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to authenticate with Akool: {str(e)}")

# Helper function for S3 upload (using consolidated S3 service)
async def upload_to_s3(file: UploadFile, bucket_name: str, object_name: Optional[str] = None) -> str:
    file_data = await file.read()
    filename = object_name.split('/')[-1] if object_name else None
    folder = object_name.split('/')[0] if object_name and '/' in object_name else 'user_uploads'
    
    return s3_service.upload_file(file_data, file.content_type, folder, filename)

@app.get("/")
async def read_root():
    return {
        "message": "AI Awareness Backend API is running",
        "status": "healthy",
        "version": "1.0.0",
        "imports": {
            "supabase": supabase_available,
            "elevenlabs": elevenlabs_import_available,
            "openai": openai_import_available,
            "s3_service": s3_service_available
        }
    }

@app.get("/test")
async def test_endpoint():
    """Simple test endpoint that doesn't depend on any services"""
    return {
        "status": "working",
        "message": "Backend is responding correctly",
        "timestamp": time.time()
    }

@app.get("/api/health")
async def health_check():
    """Comprehensive health check for all services"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "s3": s3_client is not None,
            "elevenlabs": elevenlabs_client is not None,
            "openai": openai_client is not None,
            "supabase": supabase_service.health_check() if supabase_available and supabase_service else False
        },
        "database": "supabase",
        "version": "2.0.0"
    }

# Progress tracking endpoints
@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    """Get progress for a specific task"""
    if task_id not in progress_tracking:
        raise HTTPException(status_code=404, detail="Task not found")
    return progress_tracking[task_id]

@app.post("/api/progress/{task_id}")
async def update_progress(task_id: str, progress: int, message: str = "", completed: bool = False):
    """Update progress for a specific task"""
    progress_tracking[task_id] = {
        "progress": progress,
        "message": message,
        "completed": completed,
        "timestamp": time.time()
    }
    return {"success": True}

@app.get("/api/akool-token-test")
async def test_akool_token():
    """Test Akool authentication"""
    try:
        token = await get_akool_token()
        return {
            "success": True,
            "token_preview": f"{token[:20]}..." if token else None,
            "auth_method": "client_credentials" if AKOOL_CLIENT_ID else "direct_token"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "auth_method": "client_credentials" if AKOOL_CLIENT_ID else "direct_token"
        }


@app.get("/api/users/{user_id}")
def read_user(user_id: int):
    """Get user by ID from Supabase"""
    if not supabase_available or not supabase_service:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    user = supabase_service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/api/quiz-answers")
def create_quiz_answer(quiz_answer: QuizAnswerCreate):
    """Save quiz answers to Supabase"""
    try:
        # Verify user exists first
        if not supabase_available or not supabase_service:
            raise HTTPException(status_code=503, detail="Database service unavailable")
        user = supabase_service.get_user(quiz_answer.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        result = supabase_service.save_quiz_answer(
            quiz_answer.user_id, 
            quiz_answer.module, 
            quiz_answer.answers
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save quiz answer: {str(e)}")

@app.put("/api/users/{user_id}/progress")
def update_user_progress(user_id: int, progress: UserProgressUpdate):
    """Update user progress in Supabase"""
    try:
        if not supabase_available or not supabase_service:
            raise HTTPException(status_code=503, detail="Database service unavailable")
        updated_user = supabase_service.update_user_progress(user_id, progress.dict(exclude_unset=True))
        if updated_user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return updated_user
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update user progress: {str(e)}")


# User Info endpoint with correct response format (kept for backward compatibility)
@app.post("/api/user-info")
async def save_user_info(user: UserCreate):
    """Save user information and return success status with user ID"""
    try:
        if not supabase_available or not supabase_service:
            raise HTTPException(status_code=503, detail="Database service unavailable")
        db_user = supabase_service.create_user(user.dict())
        return {"success": True, "userId": str(db_user["id"])}
    except Exception as e:
        print(f"Error saving user info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save user info: {str(e)}")

# Complete onboarding endpoint - handles everything in one atomic operation
@app.post("/api/complete-onboarding")
async def complete_onboarding(
    name: str = Form(...),
    age: int = Form(...),
    gender: str = Form(...),
    image: UploadFile = File(...),
    voice: UploadFile = File(...)
):
    """Complete user onboarding: save user info, upload image, clone voice - all in one atomic operation"""
    
    print(f"\n🚀 STARTING: Complete onboarding for {name}")
    print(f"  - Age: {age}, Gender: {gender}")
    print(f"  - Image: {image.filename} ({image.content_type})")
    print(f"  - Voice: {voice.filename} ({voice.content_type})")
    
    # Validate inputs
    if not image.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Image file must be an image")
    if not voice.content_type.startswith('audio/'):
        raise HTTPException(status_code=400, detail="Voice file must be an audio file")
    
    try:
        # Step 1: Upload image to S3
        print(f"\n📤 STEP 1: Uploading image to S3")
        if not s3_client:
            raise HTTPException(status_code=500, detail="S3 client not initialized")
        
        image_url = await upload_to_s3(image, S3_BUCKET_NAME)
        print(f"✅ Image uploaded: {image_url}")
        
        # Step 2: Clone voice with ElevenLabs
        print(f"\n🎤 STEP 2: Cloning voice with ElevenLabs")
        if not elevenlabs_client:
            raise HTTPException(status_code=500, detail="ElevenLabs client not initialized")
        
        # Reset file pointer for voice cloning
        voice.file.seek(0)
        voice_clone_result = elevenlabs_client.voices.ivc.create(
            name=f"UserClonedVoice_{uuid.uuid4().hex[:6]}",
            description="Voice cloned from user recording for AI awareness education.",
            files=[voice.file],
        )
        
        voice_id = getattr(voice_clone_result, 'voice_id', None) or getattr(voice_clone_result, 'id', None)
        voice_name = getattr(voice_clone_result, 'name', None) or f"UserClonedVoice_{uuid.uuid4().hex[:6]}"
        
        if not voice_id:
            raise HTTPException(status_code=500, detail="Failed to get voice ID from ElevenLabs")
        
        print(f"✅ Voice cloned: {voice_id} ({voice_name})")
        
        # Step 3: Create complete user record in Supabase
        print(f"\n💾 STEP 3: Creating user record with all data")
        user_data = {
            "name": name,
            "age": age,
            "gender": gender,
            "image_url": image_url,
            "voice_id": voice_id
        }
        if not supabase_available or not supabase_service:
            raise HTTPException(status_code=503, detail="Database service unavailable")
        db_user = supabase_service.create_user(user_data)
        
        print(f"✅ User created: ID {db_user['id']}")
        print(f"🎉 COMPLETE: Onboarding finished successfully for {name}")
        
        # Trigger scenario pre-generation immediately during onboarding
        user_id = db_user["id"]
        print(f"🚀 STARTING: Scenario pre-generation for user {user_id}")
        
        # Use asyncio.create_task to run in background without blocking the response
        if supabase_available and supabase_service:
            asyncio.create_task(trigger_scenario_pregeneration(user_id, image_url, voice_id, gender))
            print(f"✅ Scenario pre-generation task started for user {user_id}")
        else:
            print(f"⚠️ Scenario pre-generation skipped - Supabase unavailable")
        
        return {
            "success": True,
            "userId": str(db_user["id"]),
            "user": {
                "id": db_user["id"],
                "name": db_user["name"],
                "age": db_user["age"],
                "gender": db_user["gender"],
                "image_url": db_user["image_url"],
                "voice_id": db_user["voice_id"]
            },
            "imageUrl": image_url,
            "voiceId": voice_id,
            "voiceName": voice_name,
            "message": "Onboarding completed. Scenario generation started in background."
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        print(f"❌ Error in complete onboarding: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to complete onboarding: {str(e)}")

# AI Service endpoints
@app.post("/api/generate-narration")
async def generate_narration(request: dict):
    """Generate custom narration using ElevenLabs TTS with cloned voice"""
    script = request.get("script", "")
    voice_id = request.get("voiceId", "")
    
    print(f"\n🎙️ STARTING: Generate Custom Narration")
    print(f"  - Script: {script[:50]}...")
    print(f"  - Voice ID: {voice_id}")
    
    if not elevenlabs_client:
        print("❌ ERROR: ElevenLabs client not initialized.")
        raise HTTPException(status_code=500, detail="ElevenLabs client not initialized.")
    
    if not voice_id:
        print("❌ ERROR: Voice ID is required for narration generation.")
        raise HTTPException(status_code=400, detail="Voice ID is required.")
    
    try:
        print(f"🚀 Calling ElevenLabs TTS API")
        print(f"  - Model: eleven_multilingual_v2")
        print(f"  - Voice ID: {voice_id}")
        
        # Generate speech using ElevenLabs with the cloned voice
        audio_stream = elevenlabs_client.text_to_speech.convert(
            text=script,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            voice_settings={
                "stability": 0.6,
                "similarity_boost": 0.7,
                "speed": 1.1  # 10% faster
            }
        )
        
        # Return audio data directly as base64 for immediate playback
        audio_bytes = b"".join(audio_stream)
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        print(f"✅ Custom narration generated successfully!")
        print(f"  - Audio size: {len(audio_bytes)} bytes")
        
        return {
            "audioData": audio_base64,
            "audioType": "audio/mpeg"
        }
        
    except Exception as e:
        print(f"❌ Error generating narration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate narration: {str(e)}")

@app.post("/api/generate-voice-dub")
async def generate_voice_dub(request: dict):
    """Generate voice dubbing using ElevenLabs Dubbing API with user's cloned voice"""
    audio_url = request.get("audioUrl", "")
    voice_id = request.get("voiceId", "")
    scenario_type = request.get("scenarioType", "")
    
    print(f"\n🎙️ STARTING: Generate Voice Dubbing")
    print(f"  - Audio URL: {audio_url}")
    print(f"  - Voice ID: {voice_id}")
    print(f"  - Scenario Type: {scenario_type}")
    
    if not elevenlabs_client:
        print("❌ ERROR: ElevenLabs client not initialized.")
        raise HTTPException(status_code=500, detail="ElevenLabs client not initialized.")
    
    if not voice_id:
        print("❌ ERROR: Voice ID is required for voice dubbing.")
        raise HTTPException(status_code=400, detail="Voice ID is required.")
    
    if not audio_url:
        print("❌ ERROR: Audio URL is required for voice dubbing.")
        raise HTTPException(status_code=400, detail="Audio URL is required.")
    
    try:
        print(f"🔄 STEP 1: Downloading audio from URL")
        
        # Download audio file from URL
        async with httpx.AsyncClient(timeout=60.0) as client:
            audio_response = await client.get(audio_url)
            audio_response.raise_for_status()
            audio_content = audio_response.content
        
        print(f"  - Downloaded audio size: {len(audio_content)} bytes")
        
        print(f"🔄 STEP 2: Creating dubbing with ElevenLabs")
        print(f"  - Audio URL extension: {audio_url.split('.')[-1]}")
        
        # Create a BytesIO object from the audio content
        from io import BytesIO
        audio_data = BytesIO(audio_content)
        
        # Set appropriate filename based on URL extension
        file_extension = audio_url.split('.')[-1].lower()
        audio_data.name = f"scenario_{scenario_type}.{file_extension}"
        
        # Reset position to beginning of the stream
        audio_data.seek(0)
        
        print(f"  - File name: {audio_data.name}")
        print(f"  - Audio data size: {len(audio_content)} bytes")
        
        try:
            # Start dubbing - dub to Korean using user's voice
            dubbed = elevenlabs_client.dubbing.create(
                file=audio_data,
                target_lang="ko",  # Korean
                source_lang="ko",  # Source is also Korean
                num_speakers=1,    # Single speaker
                watermark=False,   # No watermark
                drop_background_audio=True  # Clean audio for better quality
            )
        except Exception as dubbing_error:
            print(f"❌ ElevenLabs dubbing failed: {dubbing_error}")
            raise HTTPException(
                status_code=400, 
                detail=f"ElevenLabs dubbing API error: {str(dubbing_error)}"
            )
        
        print(f"  - Dubbing started with ID: {dubbed.dubbing_id}")
        print(f"  - Expected duration: {dubbed.expected_duration_sec} seconds")
        
        print(f"🔄 STEP 3: Polling for dubbing completion")
        
        # Poll for completion (max 5 minutes)
        max_attempts = 60  # 5 minutes with 5-second intervals
        for attempt in range(max_attempts):
            if attempt > 0:
                await asyncio.sleep(5)
            
            print(f"  - Polling attempt {attempt + 1}/{max_attempts}")
            
            status_response = elevenlabs_client.dubbing.get(dubbed.dubbing_id)
            print(f"  - Status: {status_response.status}")
            
            if status_response.status == "dubbed":
                print(f"✅ STEP 4: Dubbing completed! Retrieving audio")
                
                # Get the dubbed audio file (this returns a generator)
                dubbed_audio_generator = elevenlabs_client.dubbing.audio.get(dubbed.dubbing_id, "ko")
                
                # Collect all bytes from the generator
                dubbed_audio = b"".join(dubbed_audio_generator)
                
                # Convert to base64 for frontend
                audio_base64 = base64.b64encode(dubbed_audio).decode('utf-8')
                
                print(f"✅ Voice dubbing completed successfully!")
                print(f"  - Dubbed audio size: {len(dubbed_audio)} bytes")
                
                return {
                    "audioData": audio_base64,
                    "audioType": "audio/mpeg",
                    "dubbingId": dubbed.dubbing_id
                }
            
            elif status_response.status == "failed":
                print(f"❌ ERROR: Dubbing failed")
                raise HTTPException(status_code=500, detail="Voice dubbing failed")
        
        # If we reach here, dubbing timed out
        print(f"❌ ERROR: Dubbing timed out after 5 minutes")
        raise HTTPException(status_code=504, detail="Voice dubbing timed out")
        
    except Exception as e:
        print(f"❌ Error generating voice dub: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate voice dub: {str(e)}")

@app.post("/api/generate-faceswap-image")
async def generate_faceswap_image(request: dict):
    """Generate face-swapped image using Akool high-quality API with face detection"""
    base_image_url = request.get("baseImageUrl", "")
    user_image_url = request.get("userImageUrl", "")
    
    print("\n" + "="*80)
    print("🔄 STARTING: Generate Face Swap Image (High Quality)")
    print(f"  - Base Image URL: {base_image_url}")
    print(f"  - User Image URL: {user_image_url}")
    print("="*80)
    
    # Get valid Akool token
    try:
        akool_auth_token = await get_akool_token()
    except Exception as e:
        print(f"❌ ERROR: Failed to get Akool token: {e}")
        raise HTTPException(status_code=500, detail="Akool authentication failed.")
    
    if not base_image_url:
        print("❌ ERROR: Base image URL is required.")
        raise HTTPException(status_code=400, detail="Base image URL is required.")
        
    if not user_image_url:
        print("❌ ERROR: User image URL is required.")
        raise HTTPException(status_code=400, detail="User image URL is required.")
    
    try:
        # Load face swap configuration
        import json
        import os
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "face_swap_config.json")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print("\n" + "-"*80)
        print("🔍 STEP 1: Get base image face opts from config")
        
        # Find base image configuration
        base_image_config = None
        for key, img_config in config["base_images"].items():
            if img_config["url"] == base_image_url:
                base_image_config = img_config
                print(f"  - Found config for: {key}")
                break
        
        if not base_image_config:
            print(f"❌ ERROR: Base image not found in config: {base_image_url}")
            raise HTTPException(status_code=400, detail="Base image not configured")
        
        base_image_opts = base_image_config.get("opts", "")
        if not base_image_opts:
            print(f"❌ ERROR: Face opts not configured for base image")
            raise HTTPException(status_code=400, detail="Face opts not configured for base image. Please run detect API first.")
        
        print(f"  - Base image opts: {base_image_opts}")
        
        print("\n" + "-"*80)
        print("🔍 STEP 2: Get or detect face opts for user image")
        
        # Try to get cached face opts from database first
        user_image_opts = None
        if supabase_available and supabase_service:
            try:
                # Find user by image URL to get cached face opts
                users_result = supabase_service.client.table('users').select('id, face_opts').eq('image_url', user_image_url).execute()
                if users_result.data:
                    cached_opts = users_result.data[0].get('face_opts')
                    if cached_opts:
                        user_image_opts = cached_opts
                        print(f"  - ✅ Using cached face opts: {user_image_opts}")
            except Exception as cache_error:
                print(f"  - ⚠️ Cache lookup failed: {cache_error}")
        
        # If no cached opts, detect face in user image
        if not user_image_opts:
            print(f"  - 🔄 No cached face opts found, detecting face...")
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                detect_response = await client.post(
                    "https://sg3.akool.com/detect",
                    headers={"Content-Type": "application/json"},
                    json={"image_url": user_image_url}
                )
                
                print(f"  - Detect API status: {detect_response.status_code}")
                
                if detect_response.status_code != 200:
                    print(f"❌ ERROR: Face detection failed: {detect_response.text}")
                    raise HTTPException(status_code=500, detail="Face detection failed")
                
                detect_data = detect_response.json()
                user_image_opts = detect_data.get("landmarks_str", "")
                
                if not user_image_opts:
                    print(f"❌ ERROR: No face detected in user image")
                    raise HTTPException(status_code=400, detail="No face detected in user image")
                
                print(f"  - ✅ Detected face opts: {user_image_opts}")
                
                # Cache the face opts in database for future use
                if supabase_available and supabase_service:
                    try:
                        supabase_service.client.table('users').update({'face_opts': user_image_opts}).eq('image_url', user_image_url).execute()
                        print(f"  - 💾 Cached face opts for future use")
                    except Exception as cache_error:
                        print(f"  - ⚠️ Failed to cache face opts: {cache_error}")
        
        print("\n" + "-"*80)
        print("🎭 STEP 3: Submit high-quality face swap job")
        
        # Submit face swap job using high-quality API
        async with httpx.AsyncClient(timeout=120.0) as client:
            akool_headers = {
                "Authorization": f"Bearer {akool_auth_token}",
                "Content-Type": "application/json"
            }
            
            faceswap_payload = {
                "targetImage": [{  # Original image (base)
                    "path": base_image_url,
                    "opts": base_image_opts
                }],
                "sourceImage": [{  # Replacement face (user)
                    "path": user_image_url,
                    "opts": user_image_opts
                }],
                "face_enhance": 1,  # Enable face enhancement
                "modifyImage": base_image_url  # The image to modify
            }
            
            print(f"  - Payload: {json.dumps(faceswap_payload, indent=2)}")
            print(f"  - Making request to Akool high-quality face swap API...")
            
            response = await client.post(
                "https://openapi.akool.com/api/open/v3/faceswap/highquality/specifyimage",
                headers=akool_headers,
                json=faceswap_payload
            )
            
            print(f"  - Response status: {response.status_code}")
            print(f"  - Response: {response.text}")
            
            if response.status_code != 200:
                print(f"❌ ERROR: Akool API returned {response.status_code}")
                raise HTTPException(status_code=500, detail=f"Akool API error: {response.status_code}")
            
            response_data = response.json()
            
            if response_data.get("code") != 1000:
                error_msg = response_data.get("msg", "Unknown Akool error")
                print(f"❌ ERROR: Akool API error: {error_msg}")
                raise HTTPException(status_code=500, detail=f"Akool error: {error_msg}")
            
            # Check if result is immediately available or needs polling
            data = response_data.get("data", {})
            result_url = data.get("url")
            job_id = data.get("job_id")
            task_id = data.get("_id")
            
            if result_url:
                print(f"✅ Face swap completed immediately! Result URL: {result_url}")
            else:
                print(f"⏳ Face swap job queued, job_id: {job_id}, task_id: {task_id}")
                # For now, return an error since we need to implement polling
                raise HTTPException(status_code=202, detail="Face swap job submitted but polling not implemented yet")
        
        print("\n" + "-"*80)
        print("📁 STEP 4: Handle result URL")
        print(f"  - Akool result URL: {result_url}")
        
        # Try multiple approaches to access the image
        image_data = None
        s3_url = None
        
        # Approach 1: Try downloading with various authentication methods
        download_attempts = [
            # Method 1: Standard headers
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "image/*,*/*;q=0.8",
                "Referer": "https://openapi.akool.com/"
            },
            # Method 2: With Akool authorization
            {
                "Authorization": f"Bearer {akool_auth_token}",
                "User-Agent": "Akool-Client/1.0",
                "Accept": "image/*"
            },
            # Method 3: Simple browser-like request
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Cache-Control": "no-cache"
            }
        ]
        
        for i, headers in enumerate(download_attempts, 1):
            try:
                print(f"  - Attempt {i}: Trying download with method {i}")
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                    download_response = await client.get(result_url, headers=headers)
                    print(f"    Status: {download_response.status_code}")
                    
                    if download_response.status_code == 200:
                        image_data = download_response.content
                        if len(image_data) > 0:
                            print(f"    ✅ Successfully downloaded {len(image_data)} bytes")
                            break
                        else:
                            print(f"    ⚠️ Downloaded but data is empty")
                    else:
                        print(f"    ❌ Failed with status {download_response.status_code}")
                        
            except Exception as e:
                print(f"    ❌ Error in attempt {i}: {e}")
                continue
        
        # If download failed, use the Akool URL directly
        if not image_data or len(image_data) == 0:
            print("⚠️ All download attempts failed. Using Akool URL directly.")
            print(f"  - This means the image will be served from Akool's CDN")
            s3_url = result_url  # Use Akool URL directly
        else:
            # Upload to our S3
            try:
                print(f"  - Uploading {len(image_data)} bytes to S3...")
                
                # Determine file extension
                if result_url.lower().endswith('.png'):
                    file_ext = 'png'
                    mime_type = 'image/png'
                else:
                    file_ext = 'jpg'
                    mime_type = 'image/jpeg'
                
                filename = f"faceswap_result_{uuid.uuid4().hex[:8]}.{file_ext}"
                s3_url = s3_service.upload_file(image_data, mime_type, "faceswap", filename)
                print(f"✅ Face swap image stored in S3: {s3_url}")
                
            except Exception as e:
                print(f"❌ S3 upload failed: {e}")
                print("  - Falling back to Akool URL")
                s3_url = result_url
        
        print("\n" + "="*80)
        print("🎉 Face swap generation completed!")
        print(f"  - Final URL: {s3_url}")
        print("="*80)
        
        return {"resultUrl": s3_url}
        
    except Exception as e:
        print(f"❌ Error generating faceswap image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate faceswap image: {str(e)}")

@app.post("/api/generate-talking-photo")
async def generate_talking_photo(request: dict):
    """Generate talking photo using Akool API with user's cloned voice and store video in S3"""
    caricature_url = request.get("caricatureUrl", "")
    user_name = request.get("userName", "")
    voice_id = request.get("voiceId", "")
    audio_script = request.get("audioScript", "")  # Custom audio script for scenarios
    scenario_type = request.get("scenarioType", "default")  # For different sample videos
    extended_timeout = request.get("extendedTimeout", False)  # For pre-generation with longer timeout
    
    print("\n" + "="*80)
    print("🎬 STARTING: Generate Talking Photo")
    print(f"  - Caricature URL: {caricature_url}")
    print(f"  - User Name: {user_name}")
    print(f"  - Voice ID: {voice_id}")
    print(f"  - Audio Script: {audio_script}")
    print("="*80)

    # Get valid Akool token
    try:
        akool_auth_token = await get_akool_token()
    except Exception as e:
        print(f"❌ ERROR: Failed to get Akool token: {e}")
        raise HTTPException(status_code=500, detail="Akool authentication failed.")
    
    if not caricature_url:
        print("❌ ERROR: Caricature URL is required.")
        raise HTTPException(status_code=400, detail="Caricature URL is required.")
        
    if not user_name:
        print("❌ ERROR: User name is required.")
        raise HTTPException(status_code=400, detail="User name is required.")
        
    if not voice_id:
        print("❌ ERROR: Voice ID is required.")
        raise HTTPException(status_code=400, detail="Voice ID is required.")
        
    if not elevenlabs_client:
        print("❌ ERROR: ElevenLabs client not initialized.")
        raise HTTPException(status_code=500, detail="ElevenLabs client not initialized.")
    
    try:
        # Step 1: Use custom audio script or generate default
        if audio_script:
            korean_script = audio_script
            print(f"  - Using custom audio script: {korean_script}")
        else:
            korean_script = f"안녕하세요, 저는 {user_name} 선생님이에요. 만나서 반가워요~"
            print(f"  - Using default script: {korean_script}")
        
        print("\n" + "-"*80)
        print("🎙️ STEP 1: Generate personalized audio with ElevenLabs")
        print(f"  - Script: {korean_script}")
        print(f"  - Voice ID: {voice_id}")
        print("-"*80)
        
        # Generate speech using ElevenLabs with the cloned voice
        audio_stream = elevenlabs_client.text_to_speech.convert(
            text=korean_script,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            voice_settings={
                "stability": 0.5,
                "similarity_boost": 0.8,
                "speed": 1.1  # 10% faster
            }
        )
        
        # Save audio to S3 with user-specific naming
        audio_bytes = b"".join(audio_stream)
        # Create unique filename with user name and timestamp
        timestamp = int(time.time())
        # Convert Korean/non-ASCII characters to ASCII-safe format
        import unicodedata
        safe_user_name = unicodedata.normalize('NFKD', user_name).encode('ascii', 'ignore').decode('ascii')
        safe_user_name = "".join(c for c in safe_user_name if c.isalnum() or c in (' ', '-', '_')).rstrip()[:20]
        if not safe_user_name:  # If no ASCII characters remain, use generic name
            safe_user_name = "user"
        audio_filename = f"talking_photo_audio_{safe_user_name}_{timestamp}_{uuid.uuid4().hex[:6]}.mp3"
        
        # Upload to S3 with user-specific path
        audio_object_name = f"talking_photo_audio/{safe_user_name}/{audio_filename}"
        
        print(f"📤 Uploading generated audio to S3: {audio_object_name}")
        
        # Create temporary file-like object for S3 upload
        audio_file = BytesIO(audio_bytes)
        audio_file.name = audio_filename
        s3_client.upload_fileobj(
            audio_file,
            S3_BUCKET_NAME,
            audio_object_name,
            ExtraArgs={'ACL': 'public-read', 'ContentType': 'audio/mpeg'}
        )
        
        # Use CloudFront CDN URL for faster audio delivery
        audio_url = f"https://{CLOUDFRONT_DOMAIN}/{audio_object_name}"
        print(f"✅ Audio generated and uploaded to S3")
        print(f"  - S3 Object: {audio_object_name}")
        print(f"  - Safe user name: '{safe_user_name}'")
        print(f"  - Full URL: {audio_url}")
        
        import httpx
        akool_headers = {
            "Authorization": f"Bearer {akool_auth_token}",
            "Content-Type": "application/json"
        }
        
        akool_payload = {
            "talking_photo_url": caricature_url,
            "audio_url": audio_url
        }
        
        # Validate URLs before sending to Akool
        print("\n" + "-"*80)
        print("🚀 STEP 2: Validating URLs and calling Akool API")
        print(f"  - Caricature URL: {caricature_url}")
        print(f"  - Audio URL: {audio_url}")
        
        # Test if URLs are accessible
        try:
            print("📋 Testing URL accessibility...")
            async with httpx.AsyncClient(timeout=30.0) as test_client:
                # Test caricature URL
                caricature_response = await test_client.head(caricature_url)
                print(f"  - Caricature URL status: {caricature_response.status_code}")
                
                # Test audio URL  
                audio_response = await test_client.head(audio_url)
                print(f"  - Audio URL status: {audio_response.status_code}")
                
                if caricature_response.status_code != 200:
                    raise HTTPException(status_code=400, detail=f"Caricature URL not accessible: {caricature_response.status_code}")
                if audio_response.status_code != 200:
                    raise HTTPException(status_code=400, detail=f"Audio URL not accessible: {audio_response.status_code}")
        except Exception as url_error:
            print(f"⚠️  URL validation failed: {url_error}")
            print("  - Proceeding anyway, but this may cause Akool job failure")
        
        print(f"  - Endpoint: POST https://openapi.akool.com/api/open/v3/content/video/createbytalkingphoto")
        print(f"  - Payload: {json.dumps(akool_payload, indent=2)}")
        print("-"*80)
        
        # Single attempt - if it fails, use scenario-specific sample video
        sample_video_urls = {
            "lottery": f"https://{CLOUDFRONT_DOMAIN}/video-url/scenario1_sample.mp4",
            "criminal": f"https://{CLOUDFRONT_DOMAIN}/video-url/scenario1_sample.mp4", 
            "accident_call": f"https://{CLOUDFRONT_DOMAIN}/video-url/scenario2_sample.mp4",
            "default": f"https://{CLOUDFRONT_DOMAIN}/sample/talking_photo_sample.mp4"
        }
        sample_video_url = sample_video_urls.get(scenario_type, sample_video_urls["default"])
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                print(f"🔄 STEP 3: Calling Akool API (single attempt)")
                akool_response = await client.post(
                    "https://openapi.akool.com/api/open/v3/content/video/createbytalkingphoto",
                    headers=akool_headers,
                    json=akool_payload
                )
                
                print("\n" + "-"*80)
                print("📬 STEP 3: Received response from Akool creation API")
                print(f"  - Status Code: {akool_response.status_code}")
                try:
                    akool_result = akool_response.json()
                    print(f"  - Response Body: {json.dumps(akool_result, indent=2)}")
                except json.JSONDecodeError:
                    akool_result = {}
                    print(f"  - Response Body (non-JSON): {akool_response.text}")
                print("-"*80)

                if akool_response.status_code != 200:
                    print(f"❌ Akool API failed (status {akool_response.status_code}), using sample video")
                    return {
                        "videoUrl": sample_video_url,
                        "message": "서버 과부하로 인해 샘플 영상을 보여드립니다",
                        "isSample": True
                    }
                    
        except Exception as e:
            print(f"❌ Akool API call failed: {e}, using sample video")
            return {
                "videoUrl": sample_video_url,
                "message": "서버 과부하로 인해 샘플 영상을 보여드립니다",
                "isSample": True
            }

        if akool_result.get("code") != 1000:
            print(f"❌ Akool API returned business error code: {akool_result.get('code')}, using sample video")
            return {
                "videoUrl": sample_video_url,
                "message": "서버 과부하로 인해 샘플 영상을 보여드립니다",
                "isSample": True
            }

        task_data = akool_result.get("data", {})
        task_id = task_data.get("_id") or task_data.get("video_id")
        if not task_id:
            print("❌ ERROR: Akool API response did not contain a task ID.")
            raise HTTPException(status_code=500, detail="Akool API did not return a task ID.")
            
        print(f"\n" + "-"*80)
        print(f"🔄 STEP 4: Starting to poll for video status (Task ID: {task_id})")
        
        # Use extended timeout for pre-generation scenarios
        if extended_timeout:
            print(f"  - Strategy: Extended timeout for pre-generation (5s, 10s, 15s, 20s, 30s intervals)")
            print(f"  - Max Duration: 13 minutes total")
            polling_intervals = [5, 10, 15, 20, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30]  # ~13 minutes
        else:
            print(f"  - Strategy: Standard timeout (5s, 10s, 15s, 20s, 30s intervals)")
            print(f"  - Max Duration: 8 minutes total")
            polling_intervals = [5, 10, 15, 20, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30]  # ~8 minutes
            
        print(f"  - Initial delay: 5 seconds to allow job initialization")
        print("-"*80)
            
        # Give Akool time to initialize the job
        await asyncio.sleep(5)
        for attempt, interval in enumerate(polling_intervals):
            if attempt > 0:  # Skip sleep on first attempt since we already waited 5 seconds
                await asyncio.sleep(interval)
                print(f"  - Next poll in {polling_intervals[attempt] if attempt < len(polling_intervals)-1 else 30}s")
                
            status_url = f"https://openapi.akool.com/api/open/v3/content/video/infobymodelid?video_model_id={task_id}"
            print(f"\n[Polling - Attempt {attempt + 1}/{len(polling_intervals)}]")
            print(f"  - Calling: GET {status_url}")
            
            polling_headers = {"Authorization": f"Bearer {akool_auth_token}"}
            print(f"  - Using headers: Authorization: Bearer {akool_auth_token[:10]}...")
            
            async with httpx.AsyncClient(timeout=30.0) as status_client:
                status_response = await status_client.get(
                    status_url,
                    headers=polling_headers
                )
                
                if status_response.status_code == 200:
                    try:
                        status_result = status_response.json()
                        print(f"  - Response: {status_result}")
                        
                        # Handle cases where Akool returns a non-1000 code in a 200 OK response
                        if status_result.get("code") != 1000:
                            print(f"  - Akool returned non-success code {status_result.get('code')}: {status_result.get('msg')}")
                            # This could mean the job is still processing, not necessarily a final error.
                            # We'll rely on the video_status field.
                            pass

                        status_data = status_result.get("data", {})
                        if not status_data:
                            print("  - Status: Job still initializing or in queue...")
                            continue

                        video_status = status_data.get("video_status")

                    except json.JSONDecodeError:
                        print(f"  - Invalid JSON response: {status_response.text}")
                        continue
                    
                    status_map = {1: "Queueing", 2: "Processing", 3: "Completed", 4: "Failed"}
                    print(f"  - Received Status: {video_status} ({status_map.get(video_status, 'Unknown')})")

                    if video_status == 1:  # Queueing
                        print("  - Status: Queueing...")
                        continue  # Keep polling for queueing status
                    elif video_status == 2:  # Processing
                        print("  - Status: Processing...")
                        continue  # Keep polling for processing status

                    if video_status == 3:  # Completed
                        print("\n" + "-"*80)
                        print("✅ STEP 5: Video generation completed!")
                        akool_video_url = status_data.get("video", "") # Per docs, URL is in 'video'
                        print(f"  - Akool Video URL: {akool_video_url}")

                        if not akool_video_url:
                            raise HTTPException(status_code=500, detail="Akool response missing video URL")
                        
                        print("\n" + "-"*80)
                        print("📥 STEP 6: Downloading video from Akool and uploading to our S3")
                        
                        try:
                            # Use a new client for downloading since the polling client might be closed
                            async with httpx.AsyncClient(timeout=120.0) as download_client:
                                video_response = await download_client.get(akool_video_url, follow_redirects=True)
                                video_response.raise_for_status()
                                
                                video_file = BytesIO(video_response.content)
                                video_filename = f"talking_photo_{safe_user_name}_{timestamp}_{uuid.uuid4().hex[:6]}.mp4"
                                video_object_name = f"talking_photos/{safe_user_name}/{video_filename}"
                                
                                s3_client.upload_fileobj(
                                    video_file, S3_BUCKET_NAME, video_object_name,
                                    ExtraArgs={
                                        'ACL': 'public-read', 
                                        'ContentType': 'video/mp4',
                                        'CacheControl': 'max-age=31536000',  # Cache for 1 year
                                        'Metadata': {
                                            'optimized-for': 'web-delivery',
                                            'generated-by': 'ai-awareness-platform'
                                        }
                                    }
                                )
                                
                                # Use CloudFront CDN URL for faster delivery
                                cloudfront_url = f"https://{CLOUDFRONT_DOMAIN}/{video_object_name}"
                                
                                print(f"  - Uploaded to S3: {video_object_name}")
                                print(f"  - CloudFront URL: {cloudfront_url}")
                                print("-"*80)

                                print("\n" + "="*80)
                                print("🎉 SUCCESS: Talking Photo generation complete (using CDN).")
                                print("="*80)

                                # Trigger scenario pre-generation after first talking photo
                                await trigger_scenario_pregeneration_after_first_talking_photo(user_name, voice_id)

                                return {"videoUrl": cloudfront_url}
                                
                        except Exception as upload_error:
                            print(f"❌ S3 upload failed: {upload_error}")
                            print("💡 Using Akool URL directly as fallback")
                            
                            print("\n" + "="*80)
                            print("🎉 SUCCESS: Using Akool video URL directly.")
                            print("="*80)
                            
                            # Trigger scenario pre-generation after first talking photo
                            await trigger_scenario_pregeneration_after_first_talking_photo(user_name, voice_id)
                            
                            return {"videoUrl": akool_video_url}
                        
                    elif video_status == 4:  # Failed
                        error_message = status_data.get("error_msg", "Akool video generation failed")
                        print(f"❌ ERROR: {error_message}, using sample video")
                        
                        # Still trigger scenario pre-generation even with sample video
                        await trigger_scenario_pregeneration_after_first_talking_photo(user_name, voice_id)
                        
                        return {
                            "videoUrl": sample_video_url,
                            "message": "서버 과부하로 인해 샘플 영상을 보여드립니다",
                            "isSample": True
                        }
                else:
                    print(f"  - Received non-200 status on poll: {status_response.status_code} - {status_response.text}")
        
        # This timeout logic should only run AFTER the for loop completes (all polling attempts exhausted)
        timeout_duration = "13 minutes" if extended_timeout else "8 minutes"
        print("\n" + "!"*80)
        print(f"⏰ TIMEOUT: Akool video generation timed out after {timeout_duration}.")
        print("💡 Using sample video fallback due to timeout")
        print(f"   - Task ID: {task_id}")
        print(f"   - Total attempts: {len(polling_intervals)}")
        print(f"   - Extended timeout: {extended_timeout}")
        print("!"*80)
        
        # Still trigger scenario pre-generation even with timeout sample video
        await trigger_scenario_pregeneration_after_first_talking_photo(user_name, voice_id)
        
        return {
            "videoUrl": sample_video_url,
            "message": "서버 과부하로 인해 샘플 영상을 보여드립니다",
            "isSample": True
        }
            
    except Exception as e:
        print("\n" + "!"*80)
        print(f"🔥 UNHANDLED ERROR in generate_talking_photo: {e}")
        print("!"*80)
        raise HTTPException(status_code=500, detail=f"Failed to generate talking photo: {str(e)}")

@app.post("/api/analyze-face")
async def analyze_face(request: dict):
    """Analyze image for artistic elements to create educational caricature"""
    image_url = request.get("imageUrl", "")
    
    print("\n" + "="*80)
    print("🔬 STARTING: Analyze Face for Caricature")
    print(f"  - Image URL: {image_url}")
    print("="*80)

    try:
        # For educational purposes about AI-generated content, we'll create a 
        # general artistic description suitable for caricature generation
        # This avoids OpenAI's facial recognition restrictions while still
        # demonstrating AI capabilities for educational purposes
        
        if openai_client:
            try:
                print("\n" + "-"*80)
                print("🚀 Calling OpenAI Vision API (gpt-4.1-mini)")
                # Attempt to get general artistic description
                response = openai_client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """Analyze this person for caricature creation. Be concise but specific.

Format response as:
- Gender: [Male/Female] 
- Face: [Shape, jawline, cheeks]
- Eyes: [Size, shape, color, brows]
- Nose: [Size, shape, bridge]
- Mouth: [Lip size, width, smile]
- Hair: [Color, style, length]
- Key Feature 1: [Most distinctive trait]
- Key Feature 2: [Second distinctive trait]

Keep each point under 15 words. Focus on what makes this face unique for caricature art."""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_url}
                                }
                            ]
                        }
                    ],
                    max_tokens=500
                )
                
                visual_description = response.choices[0].message.content
                
                print("\n" + "-"*80)
                print("📬 Received response from OpenAI Vision API")
                print(f"  - Analysis Result:\n{visual_description}")
                print("-"*80)

                # Create educational description for caricature generation
                educational_description = f"""Educational caricature features based on uploaded image analysis:

{visual_description}

This analysis will be used to create a stylized black and white caricature suitable for educational purposes about AI-generated content."""
                
                return {
                    "facialFeatures": {
                        "description": educational_description,
                        "analysis_type": "educational_artistic_interpretation",
                        "suitable_for_caricature": True,
                        "educational_purpose": True
                    }
                }
                
            except Exception as vision_error:
                print("\n" + "!"*80)
                print(f"⚠️  OpenAI Vision analysis failed (This may be expected due to safety restrictions): {vision_error}")
                print("!"*80)
                # Fall back to educational mock analysis
                pass
        
        # Fallback: Create concise mock analysis for caricature generation
        educational_mock_description = """- Gender: Female
- Face: Oval shape, soft jawline, balanced cheeks
- Eyes: Medium almond-shaped, brown, arched brows
- Nose: Straight bridge, rounded tip, proportional
- Mouth: Medium lips, gentle smile, balanced width
- Hair: Brown wavy, shoulder-length, natural part
- Key Feature 1: Warm friendly expression
- Key Feature 2: Balanced harmonious features"""
        
        return {
            "facialFeatures": {
                "description": educational_mock_description,
                "analysis_type": "educational_demonstration",
                "suitable_for_caricature": True,
                "educational_purpose": True,
                "privacy_conscious": True
            }
        }
        
    except Exception as e:
        print("\n" + "!"*80)
        print(f"🔥 UNHANDLED ERROR in analyze_face: {e}")
        print("!"*80)
        raise HTTPException(status_code=500, detail=f"Failed to create educational analysis: {str(e)}")

# Removed broken Responses API function - using DALL-E 3 directly

async def generate_caricature_with_dalle3(features_description: str, prompt_details: str, task_id: str = None) -> str:
    """Generate personalized caricature using DALL-E 3 with detailed features"""
    print("\n" + "="*80)
    print("🎨 STARTING: Generate Caricature with DALL-E 3")
    print("="*80)

    try:
        print("\n" + "-"*80)
        print("📝 Preparing DALL-E 3 Prompt using structured features")
        print(f"  - Features Received:\n{features_description}")
        print("-"*80)
        
        # Create optimized DALL-E 3 prompt for Korean users
        caricature_prompt = f"""Professional caricature portrait of a Korean person based on:
{features_description}

Style: Modern cartoon caricature, Disney-Pixar inspired, vibrant colors, clean lines
Background: Pure white (#FFFFFF), no shadows or objects
Composition: Head, neck, and shoulders included, single person, centered frame
Ethnicity: Korean facial features and characteristics
Technical: 85mm lens, studio lighting, high quality
Requirements: Respectful exaggeration of key features, friendly expression, gender-appropriate styling, include visible neck area
{prompt_details if prompt_details else ''}"""
        
        print("\n" + "-"*80)
        print("🚀 Calling DALL-E 3 API")
        print(f"  - Prompt Snippet: {caricature_prompt[:300]}...")
        print("-"*80)
        
        # Generate image using DALL-E 3 with optimized parameters
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=caricature_prompt,
            size="1024x1024",
            quality="hd",  # Use HD quality for better facial detail
            style="natural",  # Natural style for better realistic caricatures
            n=1,
        )
        
        generated_image_url = response.data[0].url

        print("\n" + "-"*80)
        print("📬 Received response from DALL-E 3 API")
        print(f"  - Generated Image URL: {generated_image_url}")
        print("-"*80)

        # Download and upload to S3
        print("\n" + "-"*80)
        print("📥 Downloading image from DALL-E and uploading to S3")
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Update progress: Downloading generated image
            if task_id:
                progress_tracking[task_id]["progress"] = 70
                progress_tracking[task_id]["message"] = "Downloading generated image..."
            
            try:
                image_response = await client.get(generated_image_url)
                image_response.raise_for_status()
                print(f"  - Downloaded {len(image_response.content)} bytes from DALL-E")
            except Exception as download_error:
                print(f"❌ Failed to download image from DALL-E: {download_error}")
                raise Exception(f"Failed to download generated image: {download_error}")
            
            # Update progress: Uploading to S3
            if task_id:
                progress_tracking[task_id]["progress"] = 90
                progress_tracking[task_id]["message"] = "Uploading to secure storage..."
            
            try:
                image_filename = f"caricature_{uuid.uuid4().hex[:8]}.png"
                
                # Upload using consolidated S3 service
                caricature_url = s3_service.upload_file(
                    image_response.content, 
                    'image/png', 
                    'caricatures', 
                    image_filename
                )
                print(f"  - Uploaded to S3: {caricature_url}")
                print("-"*80)

                print("\n" + "="*80)
                print("🎉 SUCCESS: Caricature generation complete.")
                print("="*80)
                
                return caricature_url
            except Exception as s3_error:
                print(f"❌ Failed to upload to S3: {s3_error}")
                raise Exception(f"Failed to upload caricature to S3: {s3_error}")
            
    except Exception as e:
        print("\n" + "!"*80)
        print(f"🔥 DALL-E 3 ERROR: {e}")
        print("!"*80)
        raise e

@app.post("/api/generate-caricature")
async def generate_caricature(request: dict):
    """Generate caricature using DALL-E 3 and store in S3"""
    facial_features = request.get("facialFeatures", {})
    prompt_details = request.get("promptDetails", "")
    
    # Generate task ID for progress tracking
    task_id = f"caricature_{uuid.uuid4().hex[:8]}"
    progress_tracking[task_id] = {
        "progress": 0,
        "message": "Starting caricature generation...",
        "completed": False,
        "timestamp": time.time()
    }
    
    if not openai_client:
        raise HTTPException(status_code=500, detail="OpenAI client not initialized.")
    
    try:
        # Update progress: Starting analysis
        progress_tracking[task_id]["progress"] = 20
        progress_tracking[task_id]["message"] = "Analyzing facial features..."
        
        features_description = facial_features.get("description", "")
        
        # Update progress: Starting DALL-E generation
        progress_tracking[task_id]["progress"] = 40
        progress_tracking[task_id]["message"] = "Generating caricature with DALL-E 3..."
        
        # Use DALL-E 3 directly with improved prompts
        caricature_url = await generate_caricature_with_dalle3(features_description, prompt_details, task_id)
        
        # Final progress update
        progress_tracking[task_id]["progress"] = 100
        progress_tracking[task_id]["message"] = "Caricature generation completed!"
        progress_tracking[task_id]["completed"] = True
        progress_tracking[task_id]["caricatureUrl"] = caricature_url
        
        return {"caricatureUrl": caricature_url, "taskId": task_id}
        
    except Exception as e:
        # Update progress on error
        progress_tracking[task_id]["progress"] = -1
        progress_tracking[task_id]["message"] = f"Error: {str(e)}"
        progress_tracking[task_id]["completed"] = True
        
        print(f"Error generating caricature: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate caricature: {str(e)}")

@app.post("/api/generate-faceswap-video")
async def generate_faceswap_video(request: dict):
    """Generate face-swapped video using Akool API and store in S3"""
    base_video_url = request.get("baseVideoUrl", "")
    user_image_url = request.get("userImageUrl", "")
    
    if not AKOOL_API_KEY:
        raise HTTPException(status_code=500, detail="Akool API key not configured.")
    
    try:
        # TODO: Implement actual Akool face swap video API call
        # For now, return mock result stored in S3
        
        result_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/faceswap_videos/mock_video_{uuid.uuid4().hex[:8]}.mp4"
        return {"resultUrl": result_url}
        
    except Exception as e:
        print(f"Error generating faceswap video: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate faceswap video: {str(e)}")

# ===================================================================================
# HYBRID STRATEGY ENDPOINTS
# ===================================================================================

# Import hybrid services
try:
    from .hybrid_api_endpoints import (
        initialize_hybrid_services, start_scenario_pregeneration_endpoint,
        smart_narration_endpoint, get_scenario_status_endpoint, 
        get_cache_stats_endpoint, cleanup_cache_endpoint
    )
    from .hybrid_models import SmartNarrationRequest
    
    # Initialize hybrid services if supabase is available
    if supabase_available and supabase_service:
        initialize_hybrid_services(supabase_service, "http://localhost:8000")
        print("✅ Hybrid services initialized successfully")
        print("📍 Creating FULL smart-narration endpoint with SmartNarrationRequest")
        
        # Define hybrid endpoints only when services are available
        @app.post("/api/smart-narration")
        async def smart_narration(request: SmartNarrationRequest):
            """Smart narration with caching and preloading"""
            try:
                return await smart_narration_endpoint(request)
            except Exception as e:
                print(f"❌ Smart narration error: {e}")
                # Fallback to regular narration
                try:
                    legacy_result = await generate_narration({
                        "script": request.current_script,
                        "voiceId": request.voice_id
                    })
                    return {
                        "current_audio_url": f"data:audio/mpeg;base64,{legacy_result['audioData']}",
                        "current_audio_type": legacy_result["audioType"],
                        "cache_hit": False,
                        "preload_started": False,
                        "message": "Fallback to legacy narration"
                    }
                except Exception as fallback_error:
                    raise HTTPException(status_code=500, detail=f"Smart narration failed: {str(e)}")
    else:
        print("⚠️ Hybrid services not initialized - Supabase unavailable")
        print("📍 Creating FALLBACK smart-narration endpoint with BasicSmartNarrationRequest")
        
        # Define fallback endpoints when services are not available  
        # Need to create a basic request model for the fallback
        from pydantic import BaseModel
        
        class BasicSmartNarrationRequest(BaseModel):
            user_id: int
            current_step_id: str
            current_script: str
            voice_id: str
            preload_next_step_id: Optional[str] = None
            preload_next_script: Optional[str] = None
        
        @app.post("/api/smart-narration")
        async def smart_narration_fallback(request: BasicSmartNarrationRequest):
            """Fallback smart narration endpoint when hybrid services unavailable"""
            try:
                legacy_result = await generate_narration({
                    "script": request.current_script,
                    "voiceId": request.voice_id
                })
                return {
                    "current_audio_url": f"data:audio/mpeg;base64,{legacy_result['audioData']}",
                    "current_audio_type": legacy_result["audioType"],
                    "cache_hit": False,
                    "preload_started": False,
                    "message": "Using legacy narration (hybrid services unavailable)"
                }
            except Exception as fallback_error:
                raise HTTPException(status_code=500, detail=f"Narration failed: {str(fallback_error)}")

    @app.get("/api/scenario-status/{user_id}")
    async def get_scenario_status(user_id: int):
        """Get scenario generation status for user"""
        try:
            return await get_scenario_status_endpoint(user_id)
        except Exception as e:
            print(f"❌ Scenario status error: {e}")
            return {"status": "unknown", "error": str(e)}

    @app.get("/api/cache-stats/{user_id}")
    async def get_cache_stats(user_id: int):
        """Get narration cache statistics for user"""
        try:
            return await get_cache_stats_endpoint(user_id)
        except Exception as e:
            print(f"❌ Cache stats error: {e}")
            return {"error": str(e)}

    @app.post("/api/cleanup-cache")
    async def cleanup_cache():
        """Clean up expired cache entries"""
        try:
            return await cleanup_cache_endpoint()
        except Exception as e:
            print(f"❌ Cache cleanup error: {e}")
            return {"error": str(e)}

except Exception as e:
    print(f"⚠️ Warning: Hybrid services failed to initialize: {e}")
    # Endpoints are already defined conditionally in the try block above
    pass

# Trigger scenario pre-generation after caricature completion
async def trigger_scenario_pregeneration_after_first_talking_photo(user_name: str, voice_id: str):
    """Trigger scenario pre-generation after first talking photo is complete"""
    try:
        if not supabase_available or not supabase_service:
            print("⚠️ Scenario pre-generation skipped - Supabase unavailable")
            return
            
        # Find user by voice_id since that's unique and available
        user = supabase_service.get_user_by_voice_id(voice_id)
        if not user:
            print(f"⚠️ User not found with voice_id {voice_id} for scenario pre-generation")
            return
            
        user_id = user['id']
        user_image_url = user['image_url']
        gender = user['gender']
        
        print(f"🚀 First talking photo complete - triggering scenario pre-generation for user {user_id}")
        
        # Use asyncio.create_task to run in background without blocking the response
        asyncio.create_task(trigger_scenario_pregeneration(user_id, user_image_url, voice_id, gender))
        
    except Exception as e:
        print(f"❌ Error triggering scenario pre-generation after talking photo: {e}")

async def trigger_scenario_pregeneration(user_id: int, user_image_url: str, voice_id: str, gender: str):
    """Trigger scenario pre-generation in background"""
    try:
        if supabase_available and supabase_service:
            result = await start_scenario_pregeneration_endpoint(user_id, user_image_url, voice_id, gender)
            if result and result.get("status") == "in_progress":
                print(f"✅ Scenario pre-generation started for user {user_id}")
            else:
                print(f"⚠️ Scenario pre-generation failed to start for user {user_id}")
        else:
            print("⚠️ Scenario pre-generation skipped - Supabase unavailable")
    except Exception as e:
        print(f"❌ Error starting scenario pre-generation: {e}")

