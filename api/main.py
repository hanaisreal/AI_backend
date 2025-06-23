import os
import uuid
import asyncio
import time
import re
from datetime import datetime, timezone
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
import httpx

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
    "https://ai-frontend-4mxmgszte-hanaisreals-projects.vercel.app",
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

@app.post("/api/trigger-scenario-generation/{user_id}")
async def trigger_scenario_generation_manual(user_id: int):
    """Manually trigger scenario generation for testing"""
    try:
        if not supabase_available or not supabase_service:
            raise HTTPException(status_code=503, detail="Database service unavailable")
        
        user = supabase_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_image_url = user.get('image_url')
        voice_id = user.get('voice_id')
        gender = user.get('gender')
        
        if not user_image_url or not voice_id or not gender:
            raise HTTPException(status_code=400, detail="User missing required data (image_url, voice_id, gender)")
        
        # Start scenario generation in background
        asyncio.create_task(generate_scenario_content_simple(user_id, user_image_url, voice_id, gender))
        
        return {
            "message": f"Scenario generation started for user {user_id}",
            "status": "in_progress",
            "user_data": {
                "name": user.get('name'),
                "gender": gender,
                "pre_generation_status": user.get('pre_generation_status', 'pending')
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error triggering scenario generation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger scenario generation: {str(e)}")

@app.post("/api/start-scenario-generation")
async def start_scenario_generation(request: dict):
    """Start scenario pre-generation during deepfake introduction"""
    try:
        voice_id = request.get("voiceId")
        if not voice_id:
            raise HTTPException(status_code=400, detail="voiceId is required")
        
        if not supabase_available or not supabase_service:
            print("⚠️ Supabase not available - skipping scenario generation")
            return {"message": "Scenario generation skipped - database not available", "status": "skipped"}
        
        # Get user by voice_id
        user = supabase_service.get_user_by_voice_id(voice_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"User not found with voice_id: {voice_id}")
        
        user_id = user['id']
        user_image_url = user.get('image_url')
        gender = user.get('gender')
        # Use existing database field name (until migration is run)
        current_status = user.get('pre_generation_status', 'pending')
        
        if not user_image_url or not gender:
            raise HTTPException(status_code=400, detail="User missing required data (image_url, gender)")
        
        # BACKEND GUARD: Check if scenario generation is already completed, in progress, or recently triggered
        if current_status == 'completed':
            print(f"🛑 BACKEND GUARD: Scenario generation already COMPLETED for user {user_id}")
            print(f"   - Status: {current_status}")
            print("   - Skipping duplicate generation to prevent credit waste")
            return {
                "message": f"Scenario generation already completed for user {user_id}",
                "status": "already_completed",
                "user_data": {
                    "name": user.get('name'),
                    "gender": gender,
                    "pre_generation_status": current_status
                }
            }
        
        if current_status == 'in_progress':
            # Check if the process has been running for too long (stuck prevention)
            started_at = user.get('pre_generation_started_at')
            current_time = datetime.now()
            
            if started_at:
                if isinstance(started_at, str):
                    # Parse ISO format datetime string
                    try:
                        started_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    except:
                        started_dt = datetime.fromisoformat(started_at)
                else:
                    started_dt = started_at
                
                # Convert to timezone-aware if needed
                if started_dt.tzinfo is None:
                    started_dt = started_dt.replace(tzinfo=timezone.utc)
                if current_time.tzinfo is None:
                    current_time = current_time.replace(tzinfo=timezone.utc)
                    
                time_running = (current_time - started_dt).total_seconds() / 60  # minutes
                
                # If running for more than 20 minutes, consider it stuck and allow restart
                if time_running > 20:
                    print(f"⚠️ BACKEND GUARD: Process appears stuck (running {time_running:.1f} minutes)")
                    print(f"   - Allowing restart for user {user_id}")
                else:
                    print(f"🛑 BACKEND GUARD: Scenario generation IN PROGRESS for user {user_id}")
                    print(f"   - Status: {current_status} (running {time_running:.1f} minutes)")
                    print("   - Skipping duplicate generation to prevent credit waste")
                    return {
                        "message": f"Scenario generation already in progress for user {user_id} ({time_running:.1f} min)",
                        "status": "already_in_progress",
                        "user_data": {
                            "name": user.get('name'),
                            "gender": gender,
                            "pre_generation_status": current_status
                        }
                    }
            else:
                print(f"🛑 BACKEND GUARD: Scenario generation IN PROGRESS for user {user_id}")
                print(f"   - Status: {current_status} (no start time recorded)")
                print("   - Skipping duplicate generation to prevent credit waste")
                return {
                    "message": f"Scenario generation already in progress for user {user_id}",
                    "status": "already_in_progress",
                    "user_data": {
                        "name": user.get('name'),
                        "gender": gender,
                        "pre_generation_status": current_status
                    }
                }
        
        # BACKEND GUARD: Check for rapid successive calls when status is 'pending'
        if current_status == 'pending':
            last_updated = user.get('updated_at')
            if last_updated:
                if isinstance(last_updated, str):
                    try:
                        last_updated_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    except:
                        last_updated_dt = datetime.fromisoformat(last_updated)
                else:
                    last_updated_dt = last_updated
                
                # Convert to timezone-aware if needed
                if last_updated_dt.tzinfo is None:
                    last_updated_dt = last_updated_dt.replace(tzinfo=timezone.utc)
                
                current_time = datetime.now(timezone.utc)
                time_since_update = (current_time - last_updated_dt).total_seconds()
                
                # Prevent rapid successive calls (less than 10 seconds apart)
                if time_since_update < 10:
                    print(f"🛑 BACKEND GUARD: Rapid successive call detected for user {user_id}")
                    print(f"   - Status: {current_status} (last updated {time_since_update:.1f}s ago)")
                    print("   - Preventing rapid duplicate calls")
                    return {
                        "message": f"Please wait before retrying (last call {time_since_update:.1f}s ago)",
                        "status": "rate_limited",
                        "user_data": {
                            "name": user.get('name'),
                            "gender": gender,
                            "pre_generation_status": current_status
                        }
                    }
        
        print("🚀 SCENARIO GENERATION TRIGGER CALLED from DeepfakeIntroduction page")
        print(f"   - User ID: {user_id}")
        print(f"   - Voice ID: {voice_id}")
        print(f"   - Gender: {gender}")
        print(f"   - Current Status: {current_status}")
        print(f"   - Image URL: {user_image_url[:50]}...")
        print("🎬 Starting background scenario generation task...")
        
        # Start scenario generation in background with exception logging
        async def safe_generate_scenario_content():
            try:
                print("🚀 SAFE WRAPPER: Starting scenario generation")
                await generate_scenario_content_simple(user_id, user_image_url, voice_id, gender)
                print("✅ SAFE WRAPPER: Scenario generation completed successfully")
            except Exception as e:
                print(f"🚨 BACKGROUND TASK CRASH: {type(e).__name__}: {str(e)}")
                import traceback
                print(f"🚨 FULL TRACEBACK: {traceback.format_exc()}")
                # Update status to failed in database
                try:
                    if supabase_available and supabase_service:
                        supabase_service.update_user(user_id, {"scenario_generation_status": "failed"})
                except Exception as db_error:
                    print(f"Failed to update status to failed: {db_error}")
        
        asyncio.create_task(safe_generate_scenario_content())
        print("✅ Background task created successfully")
        
        return {
            "message": f"Scenario generation started for user {user_id}",
            "status": "in_progress",
            "user_data": {
                "name": user.get('name'),
                "gender": gender,
                "pre_generation_status": user.get('pre_generation_status', 'pending')
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error starting scenario generation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scenario generation: {str(e)}")

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
        
        # Scenario content will be generated after the first talking photo is created
        user_id = db_user["id"]
        print(f"✅ User {user_id} created. Scenario generation will start after talking photo.")
        
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
                "speed": 1.10,  # 10% faster
                "use_speaker_boost": True   # Enhance speaker characteristics
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
    
    # Generate face swap image (logging handled by scenario generation)
    
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
        config_path = os.path.join(os.path.dirname(__file__), "face_swap_config.json")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Load face swap configuration
        
        # Find base image configuration
        base_image_config = None
        for key, img_config in config["base_images"].items():
            if img_config["url"] == base_image_url:
                base_image_config = img_config
                # Config found for base image
                break
        
        if not base_image_config:
            raise HTTPException(status_code=400, detail="Base image not configured")
        
        base_image_opts = base_image_config.get("opts", "")
        if not base_image_opts:
            raise HTTPException(status_code=400, detail="Face opts not configured for base image. Please run detect API first.")
        
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
                        pass  # Using cached face opts
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
                
                if detect_response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Face detection failed")
                
                detect_data = detect_response.json()
                user_image_opts = detect_data.get("landmarks_str", "")
                
                if not user_image_opts:
                    raise HTTPException(status_code=400, detail="No face detected in user image")
                
                # Try to cache the face opts (optional)
                if supabase_available and supabase_service:
                    try:
                        supabase_service.client.table('users').update({'face_opts': user_image_opts}).eq('image_url', user_image_url).execute()
                    except Exception:
                        pass  # Caching failed, continue
        
        # Submit high-quality face swap job
        
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
            
            # Check response status
            
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Akool API error: {response.status_code}")
            
            response_data = response.json()
            
            if response_data.get("code") != 1000:
                error_msg = response_data.get("msg", "Unknown Akool error")
                raise HTTPException(status_code=500, detail=f"Akool error: {error_msg}")
            
            # Check if result is immediately available or needs polling
            data = response_data.get("data", {})
            result_url = data.get("url")
            job_id = data.get("job_id")
            task_id = data.get("_id")
            
            print(f"\n🔍 DEBUG: Akool response analysis:")
            print(f"  - Response data keys: {list(response_data.keys())}")
            print(f"  - Data keys: {list(data.keys()) if data else 'No data object'}")
            print(f"  - result_url: {result_url}")
            print(f"  - job_id: {job_id}")
            print(f"  - task_id: {task_id}")
            
            if result_url:
                # Face swap completed immediately
                print(f"✅ Face swap completed immediately")
            else:
                # Face swap needs polling - simple implementation
                if not task_id:
                    print(f"❌ No task ID returned from Akool, but this might be normal for immediate results")
                    raise HTTPException(status_code=500, detail="Face swap failed - no result or task ID")
                
                print(f"⏳ Face swap job submitted for polling. Task ID: {task_id}")
                
                # Simple polling - check every 10 seconds for up to 2 minutes
                max_attempts = 12  # 2 minutes with 10-second intervals
                
                for attempt in range(max_attempts):
                    await asyncio.sleep(10)  # Wait 10 seconds between checks
                    
                    print(f"[Face Swap Poll {attempt + 1}/{max_attempts}] Checking status...")
                    
                    try:
                        status_url = f"https://openapi.akool.com/api/open/v3/faceswap/highquality/specifyimage/status?task_id={task_id}"
                        
                        async with httpx.AsyncClient(timeout=30.0) as status_client:
                            status_response = await status_client.get(
                                status_url, 
                                headers={"Authorization": f"Bearer {akool_auth_token}"}
                            )
                            
                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                
                                if status_data.get("code") == 1000:
                                    job_data = status_data.get("data", {})
                                    job_status = job_data.get("status")
                                    
                                    print(f"  - Status: {job_status}")
                                    
                                    if job_status == "completed":
                                        result_url = job_data.get("url") or job_data.get("result_url")
                                        if result_url:
                                            print(f"✅ Face swap polling completed")
                                            break
                                    elif job_status == "failed":
                                        raise HTTPException(status_code=500, detail="Face swap failed")
                                    # Continue polling for other statuses
                                
                    except Exception as poll_error:
                        print(f"  - Polling error: {poll_error}")
                        if attempt == max_attempts - 1:
                            raise HTTPException(status_code=500, detail="Face swap polling failed")
                
                if not result_url:
                    raise HTTPException(status_code=500, detail="Face swap timed out")
        
        # Handle result URL
        
        # Use Akool CDN URL directly (download attempts always fail with 403)
        final_url = result_url
        
        # Log only the final result
        print(f"✅ FaceSwap result: {final_url}")
        
        return {"resultUrl": final_url}
        
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
    # Generate talking photo (logging handled by scenario generation)

    # Get valid Akool token
    try:
        akool_auth_token = await get_akool_token()
    except Exception as e:
        print(f"❌ ERROR: Failed to get Akool token: {e}")
        raise HTTPException(status_code=500, detail="Akool authentication failed.")
    
    if not caricature_url:
        raise HTTPException(status_code=400, detail="Caricature URL is required.")
    if not user_name:
        raise HTTPException(status_code=400, detail="User name is required.")
    if not voice_id:
        raise HTTPException(status_code=400, detail="Voice ID is required.")
    if not elevenlabs_client:
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
        # Generate personalized audio with ElevenLabs
        
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
        # Validating URLs and calling Akool API
        
        # Test if URLs are accessible
        try:
            # Testing URL accessibility
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

                                # Note: Scenario pre-generation now triggered during deepfake introduction

                                return {"videoUrl": cloudfront_url}
                                
                        except Exception as upload_error:
                            print(f"❌ S3 upload failed: {upload_error}")
                            print("💡 Using Akool URL directly as fallback")
                            
                            print("\n" + "="*80)
                            print("🎉 SUCCESS: Using Akool video URL directly.")
                            print("="*80)
                            
                            # Note: Scenario pre-generation now triggered during deepfake introduction
                            
                            return {"videoUrl": akool_video_url}
                        
                    elif video_status == 4:  # Failed
                        error_message = status_data.get("error_msg", "Akool video generation failed")
                        print(f"❌ ERROR: {error_message}, using sample video")
                        
                        # Note: Scenario pre-generation now triggered during deepfake introduction
                        
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
        
        # Note: Scenario pre-generation now triggered during deepfake introduction
        
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

This analysis will be used to create a stylized colorful caricature suitable for educational purposes about AI-generated content."""
                
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

Style: Modern cartoon caricature, Disney-Pixar inspired, full color with vibrant natural skin tones, clean lines
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
# Simple scenario status endpoint
@app.get("/api/scenario-status/{user_id}")
async def get_scenario_status(user_id: int):
    """Get scenario generation status for user"""
    try:
        if not supabase_available or not supabase_service:
            return {"status": "unknown", "error": "Database unavailable"}
        
        user = supabase_service.get_user(user_id)
        if not user:
            return {"status": "user_not_found"}
            
        return {
            'status': user.get('pre_generation_status', 'pending'),
            'started_at': user.get('pre_generation_started_at'),
            'completed_at': user.get('pre_generation_completed_at'),
            'error': user.get('pre_generation_error'),
            'pre_generation_urls': {
                'lottery_faceswap_url': user.get('lottery_faceswap_url'),
                'crime_faceswap_url': user.get('crime_faceswap_url'),
                'lottery_video_url': user.get('lottery_video_url'),
                'crime_video_url': user.get('crime_video_url'),
                'investment_call_audio_url': user.get('investment_call_audio_url'),
                'accident_call_audio_url': user.get('accident_call_audio_url')
            }
        }
    except Exception as e:
        print(f"❌ Scenario status error: {e}")
        return {"status": "unknown", "error": str(e)}

# Trigger scenario pre-generation after caricature completion

async def generate_scenario_content_simple(user_id: int, user_image_url: str, voice_id: str, gender: str):
    """Generate scenario content using existing functions - robust version that saves partial results"""
    
    def log_progress(step: str, message: str, status: str = "INFO"):
        """Clean progress logging with consistent format"""
        status_icon = {
            "START": "🚀",
            "SUCCESS": "✅", 
            "ERROR": "❌",
            "SAVE": "💾",
            "INFO": "ℹ️",
            "PHASE": "🔥"
        }.get(status, "•")
        print(f"[USER {user_id}] {status_icon} {step}: {message}")
    
    try:
        log_progress("SCENARIO_GEN", "Starting background scenario generation", "START")
        log_progress("SETUP", f"Gender: {gender}, Voice: {voice_id[:8]}...", "INFO")
        
        # Update user status to in_progress with timestamp
        try:
            supabase_service.update_user(user_id, {
                'pre_generation_status': 'in_progress',
                'pre_generation_started_at': datetime.now(timezone.utc).isoformat()
            })
            log_progress("DB_UPDATE", "Status set to 'in_progress'", "SAVE")
        except Exception as status_error:
            log_progress("DB_ERROR", f"Could not update status: {status_error}", "ERROR")
        
        # Scenario configuration
        scenarios = {
            'lottery': {
                'base_image': f'https://d3srmxrzq4dz1v.cloudfront.net/video-url/fakenews-case1-{gender.lower()}.png',
                'script': '1등 당첨돼서 정말 기뻐요! 감사합니다!'
            },
            'crime': {
                'base_image': f'https://d3srmxrzq4dz1v.cloudfront.net/video-url/fakenews-case2-{gender.lower()}.png',
                'script': '제가 한 거 아니에요... 찍지 마세요. 죄송합니다…'
            }
        }
        
        # Voice dub configurations  
        voice_dubs = {
            'investment_call_audio': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/voice1.mp3',
            'accident_call_audio': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/voice2.mp3'
        }
        
        generated_urls = {}
        generation_errors = []
        
        # Helper functions for concurrent execution with partial saves
        async def generate_faceswap_with_save(scenario_key: str, config: dict):
            """Generate face swap and save immediately"""
            try:
                log_progress(f"FACESWAP_{scenario_key.upper()}", "Starting generation", "INFO")
                print(f"🔍 DEBUG: About to call generate_faceswap_image for {scenario_key}")
                print(f"  - User Image: {user_image_url}")
                print(f"  - Base Image: {config['base_image']}")
                
                # Add timeout protection for face swap generation
                faceswap_result = await asyncio.wait_for(
                    generate_faceswap_image({
                        "userImageUrl": user_image_url,
                        "baseImageUrl": config['base_image']
                    }),
                    timeout=360  # 6 minutes timeout for face swap (allows for 5-minute polling + buffer)
                )
                
                faceswap_url = faceswap_result.get('resultUrl')
                if faceswap_url:
                    log_progress(f"FACESWAP_{scenario_key.upper()}", "Generation completed", "SUCCESS")
                    
                    # Save partial result immediately
                    try:
                        partial_update = {f'{scenario_key}_faceswap_url': faceswap_url}
                        supabase_service.update_user(user_id, partial_update)
                        log_progress(f"FACESWAP_{scenario_key.upper()}", "URL saved to database", "SAVE")
                    except Exception as save_error:
                        log_progress(f"FACESWAP_{scenario_key.upper()}", f"Save failed: {save_error}", "ERROR")
                    
                    return scenario_key, faceswap_url, config
                else:
                    raise Exception(f"No resultUrl in faceswap response: {faceswap_result}")
                    
            except asyncio.TimeoutError:
                log_progress(f"FACESWAP_{scenario_key.upper()}", "Timeout after 5 minutes", "ERROR")
                return scenario_key, None, config
            except Exception as e:
                log_progress(f"FACESWAP_{scenario_key.upper()}", f"Failed: {str(e)}", "ERROR")
                print(f"🚨 CRITICAL ERROR in generate_faceswap_with_save({scenario_key}): {e}")
                print(f"  - Error type: {type(e).__name__}")
                import traceback
                print(f"  - Traceback: {traceback.format_exc()}")
                return scenario_key, None, config
                
        async def generate_talking_photo_with_save(scenario_key: str, faceswap_url: str, config: dict):
            """Generate talking photo and save immediately"""
            try:
                log_progress(f"VIDEO_{scenario_key.upper()}", f"Starting with script: '{config['script'][:30]}...'", "INFO")
                
                # Add timeout protection for talking photo generation
                talking_result = await asyncio.wait_for(
                    generate_talking_photo({
                        "caricatureUrl": faceswap_url,
                        "userName": f"User-{user_id}",  
                        "voiceId": voice_id,
                        "audioScript": config['script'],
                        "scenarioType": scenario_key
                    }),
                    timeout=480  # 8 minutes timeout for talking photo
                )
                
                video_url = talking_result.get('videoUrl')
                if video_url:
                    log_progress(f"VIDEO_{scenario_key.upper()}", "Generation completed", "SUCCESS")
                    
                    # Save partial result immediately
                    try:
                        partial_update = {f'{scenario_key}_video_url': video_url}
                        supabase_service.update_user(user_id, partial_update)
                        log_progress(f"VIDEO_{scenario_key.upper()}", "URL saved to database", "SAVE")
                    except Exception as save_error:
                        log_progress(f"VIDEO_{scenario_key.upper()}", f"Save failed: {save_error}", "ERROR")
                    
                    return scenario_key, video_url
                else:
                    raise Exception(f"No videoUrl in talking photo response: {talking_result}")
                    
            except asyncio.TimeoutError:
                log_progress(f"VIDEO_{scenario_key.upper()}", "Timeout after 8 minutes", "ERROR")
                return scenario_key, None
            except Exception as e:
                log_progress(f"VIDEO_{scenario_key.upper()}", f"Failed: {str(e)}", "ERROR")
                return scenario_key, None
                
        async def generate_voice_dub_with_save(dub_key: str, source_url: str):
            """Generate voice dub and save immediately"""
            try:
                log_progress(f"AUDIO_{dub_key.upper()}", "Starting voice dubbing", "INFO")
                
                # Add timeout protection for voice dub generation
                voice_result = await asyncio.wait_for(
                    generate_voice_dub({
                        "audioUrl": source_url,
                        "voiceId": voice_id,
                        "scenarioType": dub_key.replace('_audio', '')
                    }),
                    timeout=360  # 6 minutes timeout for voice dub (matches 5-minute polling + buffer)
                )
                
                # Fix: Check for the correct response format from voice dub API
                if voice_result and 'audioData' in voice_result:
                    # Handle S3 upload if we have binary audio data
                    try:
                        audio_bytes = base64.b64decode(voice_result['audioData'])
                        # Use direct S3 client upload (same as talking photo) to ensure proper permissions
                        timestamp = int(time.time())
                        audio_filename = f"voice_dub_{dub_key}_{user_id}_{timestamp}.mp3"
                        audio_object_name = f"voice_dubs/{audio_filename}"
                        
                        # Create temporary file-like object for S3 upload
                        from io import BytesIO
                        audio_file = BytesIO(audio_bytes)
                        audio_file.name = audio_filename
                        
                        # Upload using direct S3 client with explicit permissions (same as talking photo)
                        if not s3_client:
                            raise Exception("S3 client not available")
                        s3_client.upload_fileobj(
                            audio_file,
                            S3_BUCKET_NAME,
                            audio_object_name,
                            ExtraArgs={'ACL': 'public-read', 'ContentType': 'audio/mpeg'}
                        )
                        
                        # Use CloudFront CDN URL for faster audio delivery
                        final_url = f"https://{CLOUDFRONT_DOMAIN}/{audio_object_name}"
                        log_progress(f"AUDIO_{dub_key.upper()}", "Generated and uploaded to S3 (direct method)", "SUCCESS")
                    except Exception as s3_error:
                        log_progress(f"AUDIO_{dub_key.upper()}", "S3 upload failed, using base64 fallback", "ERROR")
                        audio_type = voice_result.get('audioType', 'audio/mpeg')
                        final_url = f"data:{audio_type};base64,{voice_result['audioData']}"
                        log_progress(f"AUDIO_{dub_key.upper()}", "Generated (base64 fallback)", "SUCCESS")
                    
                    # Save partial result immediately
                    try:
                        partial_update = {f'{dub_key}_url': final_url}
                        supabase_service.update_user(user_id, partial_update)
                        log_progress(f"AUDIO_{dub_key.upper()}", "URL saved to database", "SAVE")
                    except Exception as save_error:
                        log_progress(f"AUDIO_{dub_key.upper()}", f"Save failed: {save_error}", "ERROR")
                    
                    return dub_key, final_url
                else:
                    raise Exception(f"Voice dub failed or returned invalid format: {voice_result}")
                    
            except asyncio.TimeoutError:
                log_progress(f"AUDIO_{dub_key.upper()}", "Timeout after 3 minutes", "ERROR")
                return dub_key, None
            except Exception as e:
                log_progress(f"AUDIO_{dub_key.upper()}", f"Failed: {str(e)}", "ERROR")
                return dub_key, None
        
        log_progress("PHASE_1", "Starting concurrent face swap generation (lottery + crime)", "PHASE")
        
        # Phase 1: Generate face swaps concurrently
        faceswap_tasks = [
            generate_faceswap_with_save(scenario_key, config) 
            for scenario_key, config in scenarios.items()
        ]
        
        print(f"🔍 CRITICAL DEBUG: About to run asyncio.gather with {len(faceswap_tasks)} tasks")
        print(f"  - Scenarios: {list(scenarios.keys())}")
        print(f"  - Task types: {[type(task).__name__ for task in faceswap_tasks]}")
        
        try:
            log_progress("GATHER_START", f"Starting asyncio.gather for {len(faceswap_tasks)} face swap tasks", "INFO")
            faceswap_results = await asyncio.gather(*faceswap_tasks, return_exceptions=True)
            log_progress("GATHER_SUCCESS", f"asyncio.gather completed with {len(faceswap_results)} results", "SUCCESS")
            print(f"🔍 GATHER SUCCESS: Got {len(faceswap_results)} results")
            print(f"  - Results types: {[type(r).__name__ for r in faceswap_results]}")
        except Exception as gather_error:
            log_progress("GATHER_CRASH", f"asyncio.gather failed: {type(gather_error).__name__}: {str(gather_error)}", "ERROR")
            print(f"🚨 GATHER FAILED: {type(gather_error).__name__}: {str(gather_error)}")
            import traceback
            print(f"🚨 GATHER TRACEBACK: {traceback.format_exc()}")
            raise
        
        # Process face swap results
        successful_faceswaps = []
        for result in faceswap_results:
            if isinstance(result, Exception):
                generation_errors.append(f"Face swap exception: {str(result)}")
                log_progress("PHASE_1", f"Exception caught: {result}", "ERROR")
            elif result and len(result) == 3:
                scenario_key, faceswap_url, config = result
                if faceswap_url:
                    successful_faceswaps.append((scenario_key, faceswap_url, config))
                    generated_urls[f'{scenario_key}_faceswap_url'] = faceswap_url
                else:
                    generation_errors.append(f"Face swap failed for {scenario_key}")
        
        log_progress("PHASE_1", f"Completed: {len(successful_faceswaps)}/2 face swaps successful", "INFO")
        
        log_progress("PHASE_2", "Starting concurrent videos + audio (up to 4 tasks)", "PHASE")
        
        # Phase 2: Generate talking photos and voice dubs concurrently
        concurrent_tasks = []
        
        # Add talking photo tasks (using successful face swaps)
        for scenario_key, faceswap_url, config in successful_faceswaps:
            task = generate_talking_photo_with_save(scenario_key, faceswap_url, config)
            concurrent_tasks.append(('talking_photo', task))
        
        # Add voice dub tasks (independent of face swaps)
        for dub_key, source_url in voice_dubs.items():
            task = generate_voice_dub_with_save(dub_key, source_url)
            concurrent_tasks.append(('voice_dub', task))
        
        # Execute all tasks concurrently
        if concurrent_tasks:
            all_tasks = [task for _, task in concurrent_tasks]
            all_results = await asyncio.gather(*all_tasks, return_exceptions=True)
            
            # Process results
            phase2_success = 0
            for i, result in enumerate(all_results):
                task_type, _ = concurrent_tasks[i]
                
                if isinstance(result, Exception):
                    generation_errors.append(f"{task_type} exception: {str(result)}")
                    log_progress("PHASE_2", f"{task_type} exception: {result}", "ERROR")
                elif result and len(result) == 2:
                    key, url = result
                    if url:
                        if task_type == 'talking_photo':
                            generated_urls[f'{key}_video_url'] = url
                        else:  # voice_dub
                            generated_urls[f'{key}_url'] = url
                        phase2_success += 1
                    else:
                        generation_errors.append(f"{task_type} failed for {key}")
            
            log_progress("PHASE_2", f"Completed: {phase2_success}/{len(concurrent_tasks)} tasks successful", "INFO")
        
        # Summary of generation results
        log_progress("SUMMARY", f"Generated {len(generated_urls)}/6 total items, {len(generation_errors)} errors", "INFO")
        
        # Show what was successfully generated
        success_items = []
        for url_key in generated_urls.keys():
            if 'faceswap' in url_key:
                success_items.append(f"Face swap: {url_key.replace('_faceswap_url', '')}")
            elif 'video' in url_key:
                success_items.append(f"Video: {url_key.replace('_video_url', '')}")
            elif 'audio' in url_key:
                success_items.append(f"Audio: {url_key.replace('_url', '')}")
        
        if success_items:
            log_progress("SUCCESS_LIST", ", ".join(success_items), "SUCCESS")
        
        # Final status update
        final_status = 'completed' if len(generation_errors) == 0 else 'partial_success'
        
        if generated_urls:
            # Final status update with error summary
            try:
                status_update = {'pre_generation_status': final_status}
                if generation_errors:
                    status_update['pre_generation_error'] = f"Partial success: {'; '.join(generation_errors[:3])}"  # Limit error length
                supabase_service.update_user(user_id, status_update)
                log_progress("FINAL_STATUS", f"Set to '{final_status}' in database", "SAVE")
            except Exception as final_error:
                log_progress("FINAL_STATUS", f"Database update failed: {final_error}", "ERROR")
        else:
            try:
                supabase_service.update_user(user_id, {
                    'pre_generation_status': 'failed',
                    'pre_generation_error': f"Complete failure: {'; '.join(generation_errors[:3])}"
                })
                log_progress("FINAL_STATUS", "Set to 'failed' - no content generated", "ERROR")
            except Exception as final_error:
                log_progress("FINAL_STATUS", f"Database update failed: {final_error}", "ERROR")
                
        log_progress("SCENARIO_GEN", f"FINISHED - Status: {final_status}, Items: {len(generated_urls)}/6", "SUCCESS")
            
    except Exception as e:
        log_progress("FATAL_ERROR", f"Scenario generation crashed: {type(e).__name__}: {str(e)}", "ERROR")
        
        try:
            supabase_service.update_user(user_id, {
                'pre_generation_status': 'failed',
                'pre_generation_error': str(e)
            })
            log_progress("ERROR_STATUS", "Database updated with fatal error", "SAVE")
        except Exception as db_error:
            log_progress("ERROR_STATUS", f"Could not update database: {db_error}", "ERROR")

@app.post("/api/fix-voice-dub-permissions/{user_id}")
async def fix_voice_dub_permissions(user_id: int):
    """Fix S3 permissions for existing voice dub audio files"""
    try:
        if not supabase_available or not supabase_service:
            raise HTTPException(status_code=503, detail="Database service unavailable")
        
        if not s3_client:
            raise HTTPException(status_code=503, detail="S3 client not available")
        
        user = supabase_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        print(f"🔧 STARTING: Fix voice dub permissions for user {user_id}")
        
        # Get the current voice dub URLs
        investment_url = user.get('investment_call_audio_url')
        accident_url = user.get('accident_call_audio_url')
        
        fixed_urls = {}
        errors = []
        
        def extract_s3_key_from_url(url: str) -> str:
            """Extract S3 key from CloudFront or S3 URL"""
            if not url:
                return None
            # Remove CloudFront domain and extract the key
            if CLOUDFRONT_DOMAIN in url:
                return url.split(f"https://{CLOUDFRONT_DOMAIN}/")[-1]
            elif ".amazonaws.com" in url:
                # Handle direct S3 URLs
                parts = url.split(".amazonaws.com/")
                if len(parts) > 1:
                    return parts[1]
            return None
        
        def fix_s3_object_permissions(s3_key: str, url_type: str):
            """Fix permissions for a single S3 object by copying to new location with proper permissions"""
            try:
                print(f"  🔧 Fixing permissions for {url_type}: {s3_key}")
                
                # First, try to update ACL directly
                try:
                    s3_client.put_object_acl(
                        Bucket=S3_BUCKET_NAME,
                        Key=s3_key,
                        ACL='public-read'
                    )
                    new_url = f"https://{CLOUDFRONT_DOMAIN}/{s3_key}"
                    print(f"  ✅ Fixed permissions via ACL for {url_type}")
                    return new_url
                    
                except Exception as acl_error:
                    print(f"  ⚠️ ACL method failed ({acl_error}), trying copy method...")
                    
                    # If ACL update fails (bucket blocks public ACLs), copy object with new permissions
                    # Generate new filename with timestamp
                    timestamp = int(time.time())
                    path_parts = s3_key.split('/')
                    original_filename = path_parts[-1]
                    folder = '/'.join(path_parts[:-1])
                    
                    # Create new filename
                    name_parts = original_filename.rsplit('.', 1)
                    if len(name_parts) == 2:
                        new_filename = f"{name_parts[0]}_fixed_{timestamp}.{name_parts[1]}"
                    else:
                        new_filename = f"{original_filename}_fixed_{timestamp}"
                    
                    new_s3_key = f"{folder}/{new_filename}"
                    
                    # Copy object with public-read permissions
                    copy_source = {'Bucket': S3_BUCKET_NAME, 'Key': s3_key}
                    
                    s3_client.copy_object(
                        CopySource=copy_source,
                        Bucket=S3_BUCKET_NAME,
                        Key=new_s3_key,
                        MetadataDirective='COPY',
                        ACL='public-read'
                    )
                    
                    new_url = f"https://{CLOUDFRONT_DOMAIN}/{new_s3_key}"
                    print(f"  ✅ Fixed permissions via copy for {url_type}: {new_s3_key}")
                    return new_url
                
            except Exception as e:
                error_msg = f"Failed to fix permissions for {url_type}: {str(e)}"
                print(f"  ❌ {error_msg}")
                errors.append(error_msg)
                return None
        
        # Fix investment call audio permissions
        if investment_url:
            investment_key = extract_s3_key_from_url(investment_url)
            if investment_key:
                new_investment_url = fix_s3_object_permissions(investment_key, "investment_call_audio")
                if new_investment_url:
                    fixed_urls['investment_call_audio_url'] = new_investment_url
            else:
                errors.append("Could not extract S3 key from investment_call_audio_url")
        else:
            errors.append("No investment_call_audio_url found in user data")
        
        # Fix accident call audio permissions
        if accident_url:
            accident_key = extract_s3_key_from_url(accident_url)
            if accident_key:
                new_accident_url = fix_s3_object_permissions(accident_key, "accident_call_audio")
                if new_accident_url:
                    fixed_urls['accident_call_audio_url'] = new_accident_url
            else:
                errors.append("Could not extract S3 key from accident_call_audio_url")
        else:
            errors.append("No accident_call_audio_url found in user data")
        
        # Update database with any fixed URLs
        if fixed_urls:
            try:
                supabase_service.update_user(user_id, fixed_urls)
                print(f"  ✅ Updated database with {len(fixed_urls)} fixed URLs")
            except Exception as db_error:
                error_msg = f"Failed to update database: {str(db_error)}"
                print(f"  ❌ {error_msg}")
                errors.append(error_msg)
        
        # Test accessibility of fixed URLs
        accessible_urls = {}
        if fixed_urls:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for url_type, url in fixed_urls.items():
                    try:
                        response = await client.head(url)
                        accessible_urls[url_type] = {
                            "url": url,
                            "status_code": response.status_code,
                            "accessible": response.status_code == 200
                        }
                        print(f"  🔍 {url_type} accessibility test: {response.status_code}")
                    except Exception as test_error:
                        accessible_urls[url_type] = {
                            "url": url,
                            "status_code": None,
                            "accessible": False,
                            "error": str(test_error)
                        }
                        print(f"  ❌ {url_type} accessibility test failed: {test_error}")
        
        print(f"🔧 COMPLETED: Voice dub permission fix for user {user_id}")
        print(f"  - Fixed URLs: {len(fixed_urls)}")
        print(f"  - Errors: {len(errors)}")
        
        return {
            "success": len(fixed_urls) > 0,
            "user_id": user_id,
            "fixed_urls": fixed_urls,
            "accessibility_tests": accessible_urls,
            "errors": errors,
            "summary": {
                "total_urls_processed": len([u for u in [investment_url, accident_url] if u]),
                "urls_fixed": len(fixed_urls),
                "errors_count": len(errors)
            }
        }
        
    except Exception as e:
        print(f"❌ Error fixing voice dub permissions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix voice dub permissions: {str(e)}")

@app.get("/api/debug-scenario-generation/{user_id}")
async def debug_scenario_generation(user_id: int):
    """Debug endpoint to check scenario generation status and logs"""
    try:
        if not supabase_available or not supabase_service:
            return {"error": "Database service unavailable"}
        
        user = supabase_service.get_user(user_id)
        if not user:
            return {"error": "User not found"}
        
        # Check what URLs have been generated so far
        scenario_urls = {
            'lottery_faceswap_url': user.get('lottery_faceswap_url'),
            'crime_faceswap_url': user.get('crime_faceswap_url'),
            'lottery_video_url': user.get('lottery_video_url'),
            'crime_video_url': user.get('crime_video_url'),
            'investment_call_audio_url': user.get('investment_call_audio_url'),
            'accident_call_audio_url': user.get('accident_call_audio_url'),
        }
        
        # Count how many are completed
        completed_count = len([url for url in scenario_urls.values() if url])
        
        return {
            "user_id": user_id,
            "pre_generation_status": user.get('pre_generation_status', 'unknown'),
            "pre_generation_error": user.get('pre_generation_error'),
            "scenario_urls": scenario_urls,
            "completion_progress": f"{completed_count}/6",
            "debug_info": {
                "voice_id": user.get('voice_id'),
                "image_url": user.get('image_url')[:100] + "..." if user.get('image_url') else None,
                "gender": user.get('gender'),
                "created_at": user.get('created_at'),
                "updated_at": user.get('updated_at')
            }
        }
        
    except Exception as e:
        return {"error": f"Debug failed: {str(e)}"}


