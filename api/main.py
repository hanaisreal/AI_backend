import os
import uuid
import asyncio
import time
import re
import warnings
import logging
from datetime import datetime, timezone

# Suppress Vercel's asyncio deprecation warning
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*loop argument is deprecated.*")

# Reduce httpx logging noise (set to WARNING to only show actual issues)
logging.getLogger("httpx").setLevel(logging.WARNING)
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
print(f"🔍 ElevenLabs API Key loaded: {'Yes' if ELEVENLABS_API_KEY else 'No'}")
if ELEVENLABS_API_KEY:
    print(f"🔍 API Key starts with: {ELEVENLABS_API_KEY[:10]}...")
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

@app.get("/api/debug/elevenlabs-info")
async def debug_elevenlabs_info():
    """Debug endpoint to check ElevenLabs subscription and capabilities"""
    try:
        if not elevenlabs_client:
            return {"error": "ElevenLabs client not initialized"}
        
        # Try different methods to get user info
        user_info = None
        error_messages = []
        
        # Method 1: Try user.get_subscription()
        try:
            subscription_info = elevenlabs_client.user.get_subscription()
            user_info = {"subscription": subscription_info}
        except Exception as e:
            error_messages.append(f"get_subscription failed: {e}")
        
        # Method 2: Try voices.get_all() to test API access
        try:
            voices = elevenlabs_client.voices.get_all()
            voice_count = len(voices.voices) if hasattr(voices, 'voices') else len(voices)
        except Exception as e:
            voice_count = f"Error: {e}"
            error_messages.append(f"get_voices failed: {e}")
        
        # Method 3: Try to get user info another way
        try:
            user_data = elevenlabs_client.user.get()
            user_info = user_data
        except Exception as e:
            error_messages.append(f"user.get failed: {e}")
        
        return {
            "api_key_loaded": bool(ELEVENLABS_API_KEY),
            "api_key_prefix": ELEVENLABS_API_KEY[:10] + "..." if ELEVENLABS_API_KEY else None,
            "client_available": bool(elevenlabs_client),
            "available_voices": voice_count,
            "user_info": user_info,
            "error_messages": error_messages,
            "client_methods": [method for method in dir(elevenlabs_client) if not method.startswith('_')]
        }
    except Exception as e:
        return {"error": f"Failed to get ElevenLabs info: {str(e)}"}

@app.get("/api/debug/test-voice-clone")
async def test_voice_clone():
    """Test voice cloning with a minimal example"""
    try:
        if not elevenlabs_client:
            return {"error": "ElevenLabs client not initialized"}
        
        # Try to create a voice clone with minimal data
        # Note: This won't actually work without a real audio file, but it will show us the exact error
        test_result = {"status": "attempting voice clone..."}
        
        # Check what voice cloning methods are available
        ivc_available = hasattr(elevenlabs_client.voices, 'ivc')
        
        if not ivc_available:
            return {"error": "IVC method not available on voices client"}
        
        # Try to access the voice cloning API to see what happens
        try:
            # This should fail gracefully and show us the error format
            clone_result = elevenlabs_client.voices.ivc.create(
                name="TestVoice", 
                description="Test voice clone",
                files=[]  # Empty files to trigger an error and see the response format
            )
            return {"unexpected_success": str(clone_result)}
        except Exception as clone_error:
            # Also try to get more info about the user's current usage
            try:
                user_data = elevenlabs_client.user.get()
                usage_info = {
                    "character_count": getattr(user_data, 'character_count', 'Unknown'),
                    "voice_slots_used": getattr(user_data.subscription if hasattr(user_data, 'subscription') else None, 'voice_slots_used', 'Unknown'),
                    "can_use_ivc": getattr(user_data.subscription if hasattr(user_data, 'subscription') else None, 'can_use_instant_voice_cloning', 'Unknown')
                }
            except:
                usage_info = {"error": "Could not get usage info"}
                
            return {
                "expected_error": str(clone_error),
                "error_type": type(clone_error).__name__,
                "has_ivc_method": True,
                "ivc_methods": dir(elevenlabs_client.voices.ivc),
                "current_usage": usage_info
            }
            
    except Exception as e:
        return {"error": f"Test failed: {str(e)}"}

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

@app.post("/api/start-voice-generation")
async def start_voice_generation(request: dict):
    """Start voice dub generation separately - trigger at second next button in deepfake introduction"""
    try:
        voice_id = request.get("voiceId")
        if not voice_id:
            raise HTTPException(status_code=400, detail="voiceId is required")
        
        if not supabase_available or not supabase_service:
            print("⚠️ Supabase not available - skipping voice generation")
            return {"message": "Voice generation skipped - database not available", "status": "skipped"}
        
        # Get user by voice_id
        user = supabase_service.get_user_by_voice_id(voice_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"User not found with voice_id: {voice_id}")
        
        user_id = user['id']
        user_name = user.get('name', 'User')
        
        # Check if voice dubs already exist
        existing_investment = user.get('investment_call_audio_url')
        existing_accident = user.get('accident_call_audio_url')
        
        if existing_investment and existing_accident:
            print(f"🛑 Voice generation already COMPLETED for user {user_id}")
            return {
                "message": f"Voice generation already completed for user {user_id}",
                "status": "already_completed"
            }
        
        print("🎵 VOICE GENERATION TRIGGER CALLED - Second Next Button")
        print(f"   - User ID: {user_id}")
        print(f"   - Voice ID: {voice_id}")
        print(f"   - User Name: {user_name}")
        print("🎤 Starting background voice generation task...")
        
        # Start voice generation in background
        asyncio.create_task(generate_voice_dubs_only(user_id, user_name, voice_id))
        
        return {
            "message": f"Voice generation started for user {user_id}",
            "status": "started",
            "user_data": {
                "name": user_name
            }
        }
    
    except Exception as e:
        print(f"❌ Error triggering voice generation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger voice generation: {str(e)}")

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
        
        # Complete scenario generation flow (synchronous for Vercel)
        try:
            print("🚀 STARTING: Complete scenario generation")
            
            # Get user name from user data
            user_name = user.get('name', 'User')
            
            # Update status to in_progress (with error handling for missing columns)
            try:
                supabase_service.update_user(user_id, {
                    "pre_generation_status": "in_progress"
                })
                print("✅ Status updated to in_progress")
            except Exception as db_error:
                print(f"⚠️ DB update warning: {db_error}")
                # Continue even if status update fails
            
            # PHASE 1: Generate face swaps (lottery + crime)
            print("🔥 PHASE_1: Starting face swap generation (lottery + crime)")
            
            scenarios = {
                'lottery': f'https://d3srmxrzq4dz1v.cloudfront.net/video-url/fakenews-case1-{gender.lower()}.png',
                'crime': f'https://d3srmxrzq4dz1v.cloudfront.net/video-url/fakenews-case2-{gender.lower()}.png'
            }
            
            generated_content = {}
            
            # Generate face swaps sequentially (to avoid timeout)
            for scenario_key, base_image_url in scenarios.items():
                print(f"🔄 Generating {scenario_key} face swap...")
                try:
                    faceswap_result = await generate_faceswap_image({
                        "userImageUrl": user_image_url,
                        "baseImageUrl": base_image_url
                    })
                    
                    if faceswap_result and faceswap_result.get('resultUrl'):
                        generated_content[f'{scenario_key}_faceswap_url'] = faceswap_result['resultUrl']
                        print(f"✅ {scenario_key} face swap completed")
                    else:
                        print(f"❌ {scenario_key} face swap failed")
                        
                except Exception as faceswap_error:
                    print(f"❌ {scenario_key} face swap error: {faceswap_error}")
            
            # PHASE 2: Generate talking photos from face swaps
            print("🔥 PHASE_2: Starting talking photo generation")
            
            scenario_scripts = {
                'lottery': '1등 당첨돼서 정말 기뻐요! 감사합니다!',
                'crime': '제가 한 거 아니에요... 찍지 마세요. 죄송합니다…'
            }
            
            for scenario_key in scenarios.keys():
                faceswap_url = generated_content.get(f'{scenario_key}_faceswap_url')
                if faceswap_url:
                    print(f"🔄 Generating {scenario_key} talking photo...")
                    try:
                        talking_result = await generate_talking_photo({
                            "caricatureUrl": faceswap_url,
                            "userName": user_name,
                            "voiceId": voice_id,
                            "audioScript": scenario_scripts[scenario_key],
                            "scenarioType": scenario_key,
                            "extendedTimeout": True
                        })
                        
                        if talking_result and talking_result.get('videoUrl'):
                            generated_content[f'{scenario_key}_video_url'] = talking_result['videoUrl']
                            print(f"✅ {scenario_key} talking photo completed")
                        else:
                            print(f"❌ {scenario_key} talking photo failed")
                            
                    except Exception as talking_error:
                        print(f"❌ {scenario_key} talking photo error: {talking_error}")
            
            # PHASE 3: Generate voice dubs for module 2
            print("🔥 PHASE_3: Starting voice dub generation")
            
            voice_sources = {
                'investment_call_audio': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/voice1.mp3',
                'accident_call_audio': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/voice2.mp3'
            }
            
            for dub_key, source_url in voice_sources.items():
                print(f"🔄 Generating {dub_key}...")
                try:
                    voice_result = await generate_voice_dub({
                        "audioUrl": source_url,
                        "voiceId": voice_id,
                        "scenarioType": dub_key.replace('_audio', '')
                    })
                    
                    if voice_result and voice_result.get('audioData'):
                        # Upload voice dub to S3 and get CDN URL
                        try:
                            import base64
                            from io import BytesIO
                            import time
                            import uuid
                            
                            # Decode base64 audio data
                            audio_bytes = base64.b64decode(voice_result['audioData'])
                            
                            # Create unique filename
                            timestamp = int(time.time())
                            safe_user_name = user_name.replace(' ', '_')[:20] if user_name else "user"
                            audio_filename = f"voice_dub_{dub_key}_{safe_user_name}_{timestamp}_{uuid.uuid4().hex[:6]}.mp3"
                            audio_object_name = f"voice_dubs/{safe_user_name}/{audio_filename}"
                            
                            # Upload to S3
                            audio_file = BytesIO(audio_bytes)
                            audio_file.name = audio_filename
                            
                            s3_client.upload_fileobj(
                                audio_file, S3_BUCKET_NAME, audio_object_name,
                                ExtraArgs={
                                    'ACL': 'public-read',
                                    'ContentType': 'audio/mpeg',
                                    'CacheControl': 'max-age=31536000'
                                }
                            )
                            
                            # Use CloudFront CDN URL
                            cdn_url = f"https://{CLOUDFRONT_DOMAIN}/{audio_object_name}"
                            generated_content[dub_key + '_url'] = cdn_url
                            print(f"✅ {dub_key} completed - uploaded to CDN: {cdn_url}")
                            
                        except Exception as upload_error:
                            print(f"⚠️ S3 upload failed for {dub_key}: {upload_error}")
                            # Fallback to base64 data URL
                            audio_data_url = f"data:audio/mpeg;base64,{voice_result['audioData']}"
                            generated_content[dub_key + '_url'] = audio_data_url
                            print(f"✅ {dub_key} completed - using base64 fallback")
                    else:
                        print(f"❌ {dub_key} failed")
                        
                except Exception as voice_error:
                    print(f"❌ {dub_key} error: {voice_error}")
            
            # Save all generated content to database
            print("💾 Saving all generated content to database...")
            generated_content['pre_generation_status'] = 'completed'
            
            try:
                supabase_service.update_user(user_id, generated_content)
                print(f"✅ COMPLETE: Generated {len(generated_content)} items saved to database")
            except Exception as db_error:
                print(f"⚠️ DB save warning: {db_error}")
                print(f"✅ COMPLETE: Generated {len(generated_content)} items (DB save failed but content generated)")
                # Don't fail the entire process if DB save fails
                
        except Exception as e:
            print(f"🚨 SCENARIO GENERATION FAILED: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"🚨 FULL TRACEBACK: {traceback.format_exc()}")
            
            # Update status to failed
            try:
                supabase_service.update_user(user_id, {
                    "pre_generation_status": "failed",
                    "pre_generation_error": str(e),
                    "pre_generation_completed_at": "now()"
                })
            except Exception as db_error:
                print(f"Failed to update status to failed: {db_error}")
                
            return {
                "message": f"Scenario generation failed for user {user_id}: {str(e)}",
                "status": "failed",
                "error": str(e)
            }
        
        return {
            "message": f"Scenario generation completed for user {user_id}",
            "status": "completed",
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
    
    # Validate inputs with iOS compatibility
    # iOS-friendly image validation - iOS Safari might send different content types
    valid_image_types = ['image/', 'application/octet-stream']
    is_valid_image = any(image.content_type.startswith(img_type) for img_type in valid_image_types)
    
    # Additional filename-based validation for iOS images
    if not is_valid_image and image.filename:
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif']
        is_valid_image = any(image.filename.lower().endswith(ext) for ext in image_extensions)
    
    if not is_valid_image:
        raise HTTPException(status_code=400, detail=f"Image file must be an image. Received: {image.content_type}, filename: {image.filename}")
    
    # iOS-friendly audio validation - iOS Safari might send different content types
    valid_audio_types = ['audio/', 'video/mp4', 'video/quicktime', 'application/octet-stream']
    is_valid_audio = any(voice.content_type.startswith(audio_type) for audio_type in valid_audio_types)
    
    # Additional filename-based validation for iOS
    if not is_valid_audio and voice.filename:
        audio_extensions = ['.wav', '.mp3', '.m4a', '.webm', '.ogg', '.aac']
        is_valid_audio = any(voice.filename.lower().endswith(ext) for ext in audio_extensions)
    
    if not is_valid_audio:
        raise HTTPException(status_code=400, detail=f"Voice file must be an audio file. Received: {voice.content_type}, filename: {voice.filename}")
    
    # Check file sizes - iOS has different limits
    MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB for images (iOS can send large HEIC files)
    MAX_AUDIO_SIZE = 100 * 1024 * 1024  # 100MB for audio (iOS recordings can be large)
    
    image_size = len(await image.read())
    image.file.seek(0)  # Reset file pointer
    
    audio_size = len(await voice.read()) 
    voice.file.seek(0)  # Reset file pointer
    
    print(f"🔍 File size check:")
    print(f"   - Image: {image_size / (1024*1024):.2f} MB (max: {MAX_IMAGE_SIZE / (1024*1024):.0f} MB)")
    print(f"   - Audio: {audio_size / (1024*1024):.2f} MB (max: {MAX_AUDIO_SIZE / (1024*1024):.0f} MB)")
    
    if image_size > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail=f"Image file too large: {image_size / (1024*1024):.1f}MB. Maximum: {MAX_IMAGE_SIZE / (1024*1024):.0f}MB")
    
    if audio_size > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=400, detail=f"Audio file too large: {audio_size / (1024*1024):.1f}MB. Maximum: {MAX_AUDIO_SIZE / (1024*1024):.0f}MB")
    
    if image_size < 1024:  # Less than 1KB is suspicious
        raise HTTPException(status_code=400, detail="Image file appears to be corrupted or empty")
    
    if audio_size < 1024:  # Less than 1KB is suspicious  
        raise HTTPException(status_code=400, detail="Audio file appears to be corrupted or empty")
    
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
        
        # Debug: Test API key by getting user info
        try:
            user_info = elevenlabs_client.user.get()
            print(f"🔍 ElevenLabs user info:")
            print(f"   - Subscription: {getattr(user_info, 'subscription', 'Unknown')}")
            print(f"   - Character count: {getattr(user_info, 'character_count', 'Unknown')}")
            print(f"   - Character limit: {getattr(user_info, 'character_limit', 'Unknown')}")
            print(f"   - Can use instant voice cloning: {getattr(user_info, 'can_use_instant_voice_cloning', 'Unknown')}")
        except Exception as user_info_error:
            print(f"⚠️ Could not get user info: {user_info_error}")
            # Try alternative method
            try:
                subscription_info = elevenlabs_client.user.get_subscription()
                print(f"🔍 ElevenLabs subscription info: {subscription_info}")
            except Exception as sub_error:
                print(f"⚠️ Could not get subscription info: {sub_error}")
        
        # Reset file pointer for voice cloning
        voice.file.seek(0)
        
        # Debug: Check file size and type
        print(f"🔍 Voice file debug:")
        print(f"   - Filename: {voice.filename}")
        print(f"   - Content-Type: {voice.content_type}")
        print(f"   - File size: {len(await voice.read())} bytes")
        voice.file.seek(0)  # Reset after reading for size
        
        # Additional debugging for iOS compatibility
        print(f"🔍 ElevenLabs compatibility check:")
        print(f"   - Is iOS format: {voice.content_type in ['video/mp4', 'video/quicktime', 'audio/mp4', 'audio/m4a']}")
        print(f"   - Is standard audio: {voice.content_type.startswith('audio/')}")
        print(f"   - File extension: {voice.filename.split('.')[-1] if voice.filename and '.' in voice.filename else 'none'}")
        
        # Convert audio to ElevenLabs-compatible format if needed
        audio_data = await voice.read()
        voice.file.seek(0)
        
        # Multi-format retry system for ElevenLabs compatibility
        def create_audio_variants(audio_data: bytes, original_content_type: str, original_filename: str):
            """Create multiple audio format variants to try with ElevenLabs"""
            import io
            import tempfile
            import subprocess
            import os
            
            variants = []
            
            # 1. Try original format first
            original_file = io.BytesIO(audio_data)
            if original_filename:
                original_file.name = original_filename
            elif original_content_type == 'audio/mp4' or original_content_type == 'video/mp4':
                original_file.name = 'audio.m4a'
            elif original_content_type == 'audio/webm':
                original_file.name = 'audio.webm'
            else:
                original_file.name = 'audio.wav'
            
            variants.append(('Original', original_file, original_content_type))
            
            # 2. Try as WAV format (just rename, many formats work)
            try:
                wav_file = io.BytesIO(audio_data)
                wav_file.name = 'audio.wav'
                variants.append(('WAV-renamed', wav_file, 'audio/wav'))
            except Exception as e:
                print(f"⚠️ WAV rename failed: {e}")
            
            # 3. Try as MP3 format (just rename)
            try:
                mp3_file = io.BytesIO(audio_data)
                mp3_file.name = 'audio.mp3'
                variants.append(('MP3-renamed', mp3_file, 'audio/mp3'))
            except Exception as e:
                print(f"⚠️ MP3 rename failed: {e}")
            
            # 4. Advanced conversion with ffmpeg (if available)
            try:
                # Check if ffmpeg is available
                subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
                
                # Convert to WAV using ffmpeg
                with tempfile.NamedTemporaryFile(delete=False) as temp_input:
                    temp_input.write(audio_data)
                    temp_input_path = temp_input.name
                
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                    temp_wav_path = temp_wav.name
                
                result = subprocess.run([
                    'ffmpeg', '-i', temp_input_path,
                    '-ar', '44100',  # 44.1kHz
                    '-ac', '1',      # Mono
                    '-c:a', 'pcm_s16le',  # 16-bit PCM
                    '-f', 'wav',
                    temp_wav_path
                ], capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    with open(temp_wav_path, 'rb') as f:
                        wav_data = f.read()
                    wav_converted_file = io.BytesIO(wav_data)
                    wav_converted_file.name = 'audio_converted.wav'
                    variants.append(('WAV-converted', wav_converted_file, 'audio/wav'))
                
                # Clean up
                os.unlink(temp_input_path)
                os.unlink(temp_wav_path)
                
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
                print(f"⚠️ FFmpeg WAV conversion not available: {e}")
            
            # 5. Try MP3 conversion with ffmpeg (if available)
            try:
                with tempfile.NamedTemporaryFile(delete=False) as temp_input:
                    temp_input.write(audio_data)
                    temp_input_path = temp_input.name
                
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_mp3:
                    temp_mp3_path = temp_mp3.name
                
                result = subprocess.run([
                    'ffmpeg', '-i', temp_input_path,
                    '-ar', '44100',
                    '-ac', '1',
                    '-b:a', '192k',  # 192kbps as recommended by ElevenLabs
                    '-f', 'mp3',
                    temp_mp3_path
                ], capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    with open(temp_mp3_path, 'rb') as f:
                        mp3_data = f.read()
                    mp3_converted_file = io.BytesIO(mp3_data)
                    mp3_converted_file.name = 'audio_converted.mp3'
                    variants.append(('MP3-converted', mp3_converted_file, 'audio/mp3'))
                
                # Clean up
                os.unlink(temp_input_path)
                os.unlink(temp_mp3_path)
                
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
                print(f"⚠️ FFmpeg MP3 conversion not available: {e}")
            
            return variants
        
        # Create audio format variants
        print(f"🔄 Creating multiple audio format variants for ElevenLabs compatibility")
        audio_variants = create_audio_variants(audio_data, voice.content_type, voice.filename)
        
        print(f"📋 Available audio format variants: {[f'{name} ({content_type})' for name, _, content_type in audio_variants]}")
        
        # Try each audio format variant until one works
        voice_id = None
        voice_name = None
        last_error = None
        
        for format_name, audio_file, content_type in audio_variants:
            try:
                print(f"🎯 Trying ElevenLabs voice cloning with {format_name} format ({content_type})")
                audio_file.seek(0)  # Reset file pointer
                
                voice_clone_result = elevenlabs_client.voices.ivc.create(
                    name=f"UserClonedVoice_{uuid.uuid4().hex[:6]}",
                    description="Voice cloned from user recording for AI awareness education.",
                    files=[audio_file],
                )
                
                voice_id = getattr(voice_clone_result, 'voice_id', None) or getattr(voice_clone_result, 'id', None)
                voice_name = getattr(voice_clone_result, 'name', None) or f"UserClonedVoice_{uuid.uuid4().hex[:6]}"
                
                if voice_id:
                    print(f"✅ Voice cloning SUCCESS with {format_name} format!")
                    print(f"✅ Voice ID: {voice_id} ({voice_name})")
                    break
                else:
                    print(f"⚠️ {format_name} format: No voice ID returned")
                    continue
                    
            except Exception as format_error:
                print(f"❌ {format_name} format failed: {format_error}")
                print(f"❌ Error type: {type(format_error).__name__}")
                last_error = format_error
                continue
        
        # If all formats failed, raise the last error
        if not voice_id:
            error_msg = f"Voice cloning failed with all audio formats. Last error: {str(last_error)}"
            print(f"❌ FINAL FAILURE: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
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
    """Generate voice dubbing using ElevenLabs Speech-to-Speech API with user's cloned voice"""
    audio_url = request.get("audioUrl", "")
    voice_id = request.get("voiceId", "")
    scenario_type = request.get("scenarioType", "")
    
    print(f"\n🎙️ STARTING: Generate Voice Dubbing (Speech-to-Speech)")
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
        
        print(f"🔄 STEP 2: Converting voice using Speech-to-Speech API")
        print(f"  - Target Voice ID: {voice_id}")
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
            # Use Speech-to-Speech API to convert audio with user's cloned voice
            converted_audio = elevenlabs_client.speech_to_speech.convert(
                voice_id=voice_id,  # User's cloned voice ID
                audio=audio_data,   # Original audio content
                model_id="eleven_multilingual_sts_v2",  # Multilingual model for Korean
                output_format="mp3_44100_128"  # High quality MP3 output
            )
            
            print(f"✅ Speech-to-Speech conversion completed successfully!")
            
        except Exception as conversion_error:
            print(f"❌ ElevenLabs Speech-to-Speech failed: {conversion_error}")
            raise HTTPException(
                status_code=400, 
                detail=f"ElevenLabs Speech-to-Speech API error: {str(conversion_error)}"
            )
        
        print(f"🔄 STEP 3: Processing converted audio")
        
        # Convert audio generator to bytes if needed
        if hasattr(converted_audio, '__iter__') and not isinstance(converted_audio, (bytes, bytearray)):
            # If it's a generator, collect all bytes
            converted_audio_bytes = b"".join(converted_audio)
        else:
            # If it's already bytes
            converted_audio_bytes = converted_audio
        
        # Convert to base64 for frontend
        import base64
        audio_base64 = base64.b64encode(converted_audio_bytes).decode('utf-8')
        
        print(f"✅ Voice dubbing completed successfully!")
        print(f"  - Converted audio size: {len(converted_audio_bytes)} bytes")
        print(f"  - Using user's cloned voice: {voice_id}")
        
        return {
            "audioData": audio_base64,
            "audioType": "audio/mpeg",
            "dubbingId": f"sts_{scenario_type}_{voice_id[:8]}"  # Generate unique ID for tracking
        }
        
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
        
        # Skip face opts caching for now (column doesn't exist in current schema)
        user_image_opts = None
        
        # Always detect face in user image (no caching until face_opts column is added)
        if True:
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
                
                # Skip face opts caching (column doesn't exist yet)
                # TODO: Add face_opts column to users table for caching
                pass
        
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
        
        # Skip URL validation - Akool validates URLs internally
        print("\n" + "-"*80)
        
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
    """Analyze image for artistic elements to create zepeto style cartoon avatar"""
    image_url = request.get("imageUrl", "")

    try:        
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
                                    "text": """Analyze this Korean person's facial features for cartoon character creation. Use this exact format without bold text, introductions, or extra explanations:

BASIC INFO: Age range, gender, Korean ethnicity
FACE STRUCTURE: Face shape, jawline definition, cheekbone prominence, forehead size
EYES: Shape, size, color, eyelash thickness, eyebrow details, eye spacing
NOSE: Shape, size, bridge height, tip shape
MOUTH: Lip fullness, shape, smile width, mouth size
HAIR: Color, texture, length(ear-cut, pixie-cut, shoulder-length), style, hairline, volume
GLASSES: Frame details if present, or "None"
FACIAL HAIR: Type and coverage if present, or "Clean shaven"
SKIN: Tone, texture, complexion
DISTINCTIVE FEATURES: Unique characteristics, memorable traits

Output only the analysis in plain text format."""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_url}
                                }
                            ]
                        }
                    ],
                    max_tokens=250
                )
                
                visual_description = response.choices[0].message.content
                
                print("\n" + "-"*80)
                print("📬 Received response from OpenAI Vision API")
                print(f"  - Analysis Result:\n{visual_description}")
                print("-"*80)

                return {
                    "facialFeatures": {
                        "description": visual_description,
                        "analysis_type": "ai_vision_enhanced",
                        "suitable_for_caricature": True,
                        "educational_purpose": True,
                        "detailed_analysis": True
                    }
                }
                
            except Exception as vision_error:
                print("\n" + "!"*80)
                print(f"⚠️  OpenAI Vision analysis failed (This may be expected due to safety restrictions): {vision_error}")
                print("!"*80)
                # Fall back to educational mock analysis
                pass
        
        # Fallback: Create varied mock analysis for different demographics
        import random
        
        # Create more varied and realistic descriptions
        age_ranges = ["Young Adult", "Adult", "Middle-aged"]
        genders = ["Male", "Female"]
        face_shapes = ["Oval", "Round", "Square", "Heart-shaped"]
        
        selected_age = random.choice(age_ranges)
        selected_gender = random.choice(genders)
        selected_face_shape = random.choice(face_shapes)
        
        # Comprehensive hair style variations for detailed character analysis
        hair_options = [
            "Short black hair, ear-length with natural texture",
            "Curly brown hair, shoulder-length with volume",
            "Straight dark hair, chin-length bob cut",
            "Wavy salt-and-pepper hair, short and layered",
            "Black hair with natural curl, cropped close to head",
            "Medium brown hair, side-swept with gentle waves",
            "Short silver hair, neatly styled with side part",
            "Dark hair with loose curls, just above shoulders",
            "Straight black hair, pixie cut style",
            "Wavy brown hair, ear-length with natural bounce",
            "Salt-and-pepper hair, thinning on top, shorter on sides",
            "Curly dark hair, medium length with natural texture"
        ]
        glasses_options = [
            "None", 
            "Black rectangular frames with medium thickness", 
            "Round gold-rimmed glasses with thin frames", 
            "Brown tortoiseshell frames with clear lenses",
            "Modern silver frames with blue light coating"
        ]
        facial_hair_options = [
            "Clean shaven", 
            "Light stubble with 5 o'clock shadow", 
            "Well-groomed goatee with matching mustache", 
            "Short beard with neat trimming",
            "Mustache only, well-maintained"
        ]
        eye_options = [
            "Deep brown, almond-shaped with natural sparkle",
            "Dark brown, slightly hooded with thick lashes",
            "Medium brown, round shape with expressive quality",
            "Black, narrow almond shape with strong presence"
        ]
        nose_options = [
            "Straight bridge, proportional size, refined tip",
            "Slightly elevated bridge, medium width, soft tip",
            "Well-defined bridge, narrow profile, pointed tip",
            "Gentle slope, wider base, rounded tip"
        ]
        
        educational_mock_description = f"""BASIC INFO: {selected_age}, {selected_gender}, Korean ethnicity
FACE STRUCTURE: {selected_face_shape} face, defined jawline, moderate cheekbones, proportional forehead
EYES: {random.choice(eye_options)}, arched eyebrows, well-spaced
NOSE: {random.choice(nose_options)}
MOUTH: Medium-full lips, natural curve, warm smile
HAIR: {random.choice(hair_options)}, healthy hairline
GLASSES: {random.choice(glasses_options)}
FACIAL HAIR: {random.choice(facial_hair_options)}
SKIN: Warm undertone, smooth texture, flawless complexion
DISTINCTIVE FEATURES: Expressive eyes, friendly demeanor, youthful appearance"""
        
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


    try:
        print("\n" + "-"*80)
        print("📝 Preparing DALL-E 3 Prompt using structured features")
        print(f"  - Features Received:\n{features_description}")
        print("-"*80)
        
        # Create stylized cartoon character prompt in Zepeto/Mario style
        caricature_prompt = f"""60 years old Korean3D cartoon character in Zepeto Korean mobile app style on PLAIN WHITE BACKGROUND.
MANDATORY FACIAL FEATURES - COPY EXACTLY:
{features_description}

HAIR STYLE REQUIREMENTS (CRITICAL):
- If description says "ear-length" hair, make hair END AT THE EARS
- If description says "pixie-cut" hair, make hair VERY SHORT close to head
- If description says "shoulder-length" hair, make hair END AT THE SHOULDERS
- If description says "chin-length" hair, make hair END AT THE CHIN
- HAIR LENGTH IS MANDATORY - DO NOT IGNORE

FACE REQUIREMENTS (CRITICAL):
- Copy the EXACT eye shape, size, and color from description, no exaggeration
- Copy the EXACT nose shape and size from description  
- Copy the EXACT mouth and lip shape from description
- If glasses are mentioned, MUST include glasses with exact frame style
- Show the EXACT age specified (mature features for 50s+)

BACKGROUND: SOLID WHITE BACKGROUND ONLY - NO OTHER COLORS OR PATTERNS

STYLE: 3D cartoon, Zepeto Korean mobile aesthetic, cel-shading, bright colors, front-facing portrait head to shoulders.

- The character must be above 60 years old.
COMPLIANCE REQUIRED: The character must look exactly like the description or the image is rejected.

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
            style="vivid",  # Vivid style for better cartoon characters
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
        
        # Voice dubs are now generated separately via /api/start-voice-generation
        # This function now only handles video generation (face swaps + talking photos)
        
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
            """Generate voice dub using Speech-to-Speech API and save immediately"""
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
        
        # Voice dub tasks removed - now handled separately by /api/start-voice-generation
        
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

async def generate_voice_dubs_only(user_id: int, user_name: str, voice_id: str):
    """Generate only voice dubs (separated from video generation for parallel processing)"""
    try:
        print(f"🎤 STARTING VOICE-ONLY GENERATION for user {user_id}")
        print(f"   - User: {user_name}")
        print(f"   - Voice ID: {voice_id}")
        
        voice_sources = {
            'investment_call_audio': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/voice1.mp3',
            'accident_call_audio': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/voice2.mp3'
        }
        
        generated_voice_content = {}
        
        for dub_key, source_url in voice_sources.items():
            print(f"🔄 Generating {dub_key}...")
            try:
                # Add timeout protection for voice dub generation
                voice_result = await asyncio.wait_for(
                    generate_voice_dub({
                        "audioUrl": source_url,
                        "voiceId": voice_id,
                        "scenarioType": dub_key.replace('_audio', '')
                    }),
                    timeout=360  # 6 minutes timeout for voice dub
                )
                
                if voice_result and voice_result.get('audioData'):
                    # Upload voice dub to S3 and get CDN URL
                    try:
                        import base64
                        from io import BytesIO
                        import time
                        import uuid
                        
                        # Decode base64 audio data
                        audio_bytes = base64.b64decode(voice_result['audioData'])
                        
                        # Create unique filename
                        timestamp = int(time.time())
                        safe_user_name = user_name.replace(' ', '_')[:20] if user_name else "user"
                        audio_filename = f"voice_dub_{dub_key}_{safe_user_name}_{timestamp}_{uuid.uuid4().hex[:6]}.mp3"
                        audio_object_name = f"voice_dubs/{safe_user_name}/{audio_filename}"
                        
                        # Upload to S3
                        audio_file = BytesIO(audio_bytes)
                        audio_file.name = audio_filename
                        
                        s3_client.upload_fileobj(
                            audio_file, S3_BUCKET_NAME, audio_object_name,
                            ExtraArgs={
                                'ACL': 'public-read',
                                'ContentType': 'audio/mpeg',
                                'CacheControl': 'max-age=31536000'
                            }
                        )
                        
                        # Use CloudFront CDN URL
                        cdn_url = f"https://{CLOUDFRONT_DOMAIN}/{audio_object_name}"
                        generated_voice_content[dub_key + '_url'] = cdn_url
                        print(f"✅ {dub_key} completed - uploaded to CDN: {cdn_url}")
                        
                        # Save individual voice dub immediately
                        try:
                            partial_update = {f'{dub_key}_url': cdn_url}
                            supabase_service.update_user(user_id, partial_update)
                            print(f"✅ {dub_key} URL saved to database")
                        except Exception as save_error:
                            print(f"⚠️ DB save warning for {dub_key}: {save_error}")
                        
                    except Exception as upload_error:
                        print(f"⚠️ S3 upload failed for {dub_key}: {upload_error}")
                        # Fallback to base64 data URL
                        audio_data_url = f"data:audio/mpeg;base64,{voice_result['audioData']}"
                        generated_voice_content[dub_key + '_url'] = audio_data_url
                        print(f"✅ {dub_key} completed - using base64 fallback")
                        
                        # Save fallback URL
                        try:
                            partial_update = {f'{dub_key}_url': audio_data_url}
                            supabase_service.update_user(user_id, partial_update)
                            print(f"✅ {dub_key} fallback URL saved to database")
                        except Exception as save_error:
                            print(f"⚠️ DB save warning for {dub_key}: {save_error}")
                else:
                    print(f"❌ {dub_key} failed")
                    
            except asyncio.TimeoutError:
                print(f"⏰ {dub_key} timed out after 6 minutes")
            except Exception as voice_error:
                print(f"❌ {dub_key} error: {voice_error}")
        
        print(f"🎤 VOICE GENERATION COMPLETE: Generated {len(generated_voice_content)} voice dubs")
        return generated_voice_content
        
    except Exception as e:
        print(f"🚨 VOICE GENERATION FAILED: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"🚨 FULL TRACEBACK: {traceback.format_exc()}")
        return {}

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


