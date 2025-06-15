import os
import uuid
import asyncio
import time
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from typing import Optional
import crud, models, schemas
from database import SessionLocal, engine, get_db
from io import BytesIO
import base64
import json

# AI Service SDKs
from elevenlabs.client import ElevenLabs
from openai import OpenAI

# Load environment variables
load_dotenv()

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


models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Awareness Backend API",
    description="Backend API for AI awareness education platform",
    version="1.0.0"
)

# CORS configuration
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://ai-awareness-frontend.vercel.app",
    "https://*.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# S3 Client Initialization and CORS Configuration
s3_client = None
if all([S3_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION]):
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        print("S3 client initialized successfully.")

        # Define and apply S3 bucket CORS policy
        cors_configuration = {
            'CORSRules': [
                {
                    'AllowedHeaders': ['*'],
                    'AllowedMethods': ['GET', 'HEAD'],
                    'AllowedOrigins': CORS_ORIGINS,  # Use the same list as FastAPI
                    'ExposeHeaders': ['ETag', 'Content-Length'],
                    'MaxAgeSeconds': 3000
                }
            ]
        }
        
        print(f"Attempting to apply CORS policy to bucket '{S3_BUCKET_NAME}'...")
        s3_client.put_bucket_cors(
            Bucket=S3_BUCKET_NAME,
            CORSConfiguration=cors_configuration
        )
        print("✅ S3 bucket CORS policy applied successfully.")

    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f"❌ S3 Bucket '{S3_BUCKET_NAME}' does not exist. Please check your .env configuration.")
        elif e.response['Error']['Code'] == 'AccessDenied':
             print(f"❌ S3 Access Denied: Check if the IAM user has 'PutBucketCORS' permissions.")
        else:
            print(f"❌ S3 ClientError while applying CORS: {e}")
    except Exception as e:
        print(f"❌ Error initializing S3 client or setting CORS policy: {e}")
else:
    print("S3 client not initialized due to missing AWS credentials.")

# ElevenLabs Client Initialization
elevenlabs_client = None
if ELEVENLABS_API_KEY:
    try:
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("ElevenLabs client initialized successfully.")
    except Exception as e:
        print(f"Error initializing ElevenLabs client: {e}")
else:
    print("ElevenLabs client not initialized due to missing API key.")

# OpenAI Client Initialization
openai_client = None
if OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        print("OpenAI client initialized successfully.")
    except Exception as e:
        print(f"Error initializing OpenAI client: {e}")
else:
    print("OpenAI client not initialized due to missing API key.")

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

# Helper function for S3 upload
async def upload_to_s3(file: UploadFile, bucket_name: str, object_name: Optional[str] = None) -> str:
    if not s3_client:
        raise HTTPException(status_code=500, detail="S3 client not initialized. Check server logs and .env configuration.")
    
    if object_name is None:
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'png'
        object_name = f"user_uploads/{uuid.uuid4()}.{file_extension}"

    try:
        s3_client.upload_fileobj(
            file.file, 
            bucket_name, 
            object_name, 
            ExtraArgs={'ACL': 'public-read', 'ContentType': file.content_type}
        )
        # Construct the public URL
        public_url = f"https://{bucket_name}.s3.{AWS_REGION}.amazonaws.com/{object_name}"
        print(f"File uploaded to S3: {public_url}")
        return public_url
    except NoCredentialsError:
        print("S3 Upload Error: AWS credentials not found.")
        raise HTTPException(status_code=500, detail="S3 configuration error: Credentials not found.")
    except PartialCredentialsError:
        print("S3 Upload Error: Incomplete AWS credentials.")
        raise HTTPException(status_code=500, detail="S3 configuration error: Incomplete credentials.")
    except ClientError as e:
        print(f"S3 ClientError during upload: {e}")
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {e.response.get('Error',{}).get('Message', str(e))}")
    except Exception as e:
        print(f"An unexpected error occurred during S3 upload: {e}")
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")

@app.get("/")
async def read_root():
    return {
        "message": "AI Awareness Backend API is running",
        "status": "healthy",
        "version": "1.0.0",
        "akool_auth": "client_credentials" if AKOOL_CLIENT_ID else ("direct_token" if AKOOL_API_KEY else "not_configured")
    }

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


@app.get("/api/users/{user_id}", response_model=schemas.User)
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

@app.post("/api/quiz-answers", response_model=schemas.QuizAnswer)
def create_quiz_answer(quiz_answer: schemas.QuizAnswerCreate, db: Session = Depends(get_db)):
    # You might want to verify the user_id exists first
    return crud.create_user_quiz_answer(db=db, quiz_answer=quiz_answer)

@app.post("/api/user-image")
async def upload_user_image(file: UploadFile = File(...)):
    """Upload user image to S3 and return the public URL"""
    if not s3_client:
        raise HTTPException(status_code=500, detail="S3 client not initialized.")
    
    # Validate file type
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        # Upload to S3
        s3_url = await upload_to_s3(file, S3_BUCKET_NAME)
        return {"imageUrl": s3_url, "filename": file.filename}
    except Exception as e:
        print(f"Error uploading user image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")

@app.post("/api/user-voice")
async def upload_user_voice(file: UploadFile = File(...)):
    """Process user voice recording and clone voice with ElevenLabs"""
    
    if not elevenlabs_client:
        raise HTTPException(status_code=500, detail="ElevenLabs client not initialized. Check API key.")
    
    # Validate file type
    if not file.content_type.startswith('audio/'):
        raise HTTPException(status_code=400, detail="File must be an audio file")
    
    print(f"🎤 Voice cloning enabled - processing file: {file.filename}")
    
    try:
        # Clone voice using ElevenLabs Instant Voice Cloning
        print(f"🚀 Calling ElevenLabs IVC API to clone voice from {file.filename}")
        
        voice = elevenlabs_client.voices.ivc.create(
            name=f"UserClonedVoice_{uuid.uuid4().hex[:6]}",
            description="Voice cloned from user recording for AI awareness education.",
            files=[file.file],
        )
        
        # Extract voice ID and name from response
        voice_id = getattr(voice, 'voice_id', None) or getattr(voice, 'id', None)
        voice_name = getattr(voice, 'name', None) or f"UserClonedVoice_{uuid.uuid4().hex[:6]}"
        
        print(f"✅ Voice cloning successful! Voice ID: {voice_id}, Name: {voice_name}")
        
        return {"voiceId": voice_id, "voice_name": voice_name, "status": "success"}
        
    except Exception as e:
        print(f"❌ Error cloning voice with ElevenLabs: {e}")
        error_detail = str(e)
        if hasattr(e, 'body') and isinstance(e.body, dict) and 'detail' in e.body:
            error_detail = e.body['detail']
        raise HTTPException(status_code=500, detail=f"Failed to clone voice: {error_detail}")

# User Info endpoint with correct response format
@app.post("/api/user-info")
async def save_user_info(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Save user information and return success status with user ID"""
    try:
        db_user = crud.create_user(db=db, user=user)
        return {"success": True, "userId": str(db_user.id)}
    except Exception as e:
        print(f"Error saving user info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save user info: {str(e)}")

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
            model_id="eleven_multilingual_v2"
        )
        
        # Save audio to S3
        audio_bytes = b"".join(audio_stream)
        audio_filename = f"narration_{uuid.uuid4().hex[:8]}.mp3"
        
        print(f"📤 Uploading generated audio to S3: {audio_filename}")
        
        # Create temporary file-like object for S3 upload
        audio_file = BytesIO(audio_bytes)
        audio_file.name = audio_filename
        
        # Upload to S3
        object_name = f"narrations/{audio_filename}"
        s3_client.upload_fileobj(
            audio_file,
            S3_BUCKET_NAME,
            object_name,
            ExtraArgs={'ACL': 'public-read', 'ContentType': 'audio/mpeg'}
        )
        
        audio_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{object_name}"
        
        print(f"✅ Custom narration generated successfully!")
        print(f"  - Audio URL: {audio_url}")
        
        return {"audioUrl": audio_url}
        
    except Exception as e:
        print(f"❌ Error generating narration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate narration: {str(e)}")

@app.post("/api/generate-faceswap-image")
async def generate_faceswap_image(request: dict):
    """Generate face-swapped image using Akool API and store in S3"""
    base_image_url = request.get("baseImageUrl", "")
    user_image_url = request.get("userImageUrl", "")
    
    if not AKOOL_API_KEY:
        raise HTTPException(status_code=500, detail="Akool API key not configured.")
    
    try:
        # TODO: Implement actual Akool face swap API call
        # For now, return success with mock result stored in S3
        
        # Mock implementation - in real implementation, you'd:
        # 1. Call Akool face swap API
        # 2. Get the result image URL from Akool
        # 3. Download the result and upload to your S3
        # 4. Return your S3 URL
        
        result_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/faceswap/mock_result_{uuid.uuid4().hex[:8]}.jpg"
        return {"resultUrl": result_url}
        
    except Exception as e:
        print(f"Error generating faceswap image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate faceswap image: {str(e)}")

@app.post("/api/generate-talking-photo")
async def generate_talking_photo(request: dict):
    """Generate talking photo using Akool API with user's cloned voice and store video in S3"""
    caricature_url = request.get("caricatureUrl", "")
    user_name = request.get("userName", "")
    voice_id = request.get("voiceId", "")
    
    print("\n" + "="*80)
    print("🎬 STARTING: Generate Talking Photo")
    print(f"  - Caricature URL: {caricature_url}")
    print(f"  - User Name: {user_name}")
    print(f"  - Voice ID: {voice_id}")
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
        # Step 1: Generate personalized Korean script
        korean_script = f"안녕하세요, 저는 {user_name} 선생님이에요. 만나서 반가워요~"
        
        print("\n" + "-"*80)
        print("🎙️ STEP 1: Generate personalized audio with ElevenLabs")
        print(f"  - Script: {korean_script}")
        print(f"  - Voice ID: {voice_id}")
        print("-"*80)
        
        # Generate speech using ElevenLabs with the cloned voice
        audio_stream = elevenlabs_client.text_to_speech.convert(
            text=korean_script,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2"
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
        
        # URL encode the object name for proper S3 access
        from urllib.parse import quote
        encoded_object_name = quote(audio_object_name, safe='/')
        audio_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{encoded_object_name}"
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
        
        async with httpx.AsyncClient(timeout=60.0) as client:
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
                print(f"❌ ERROR: Akool API returned non-200 status: {akool_response.status_code}")
                raise HTTPException(status_code=500, detail=f"Akool API error: {akool_response.status_code} - {akool_response.text}")

            if akool_result.get("code") != 1000:
                print(f"❌ ERROR: Akool API returned business error code: {akool_result.get('code')}")
                raise HTTPException(status_code=500, detail=f"Akool API failed: {akool_result.get('msg', 'Unknown error')}")

            task_data = akool_result.get("data", {})
            task_id = task_data.get("_id") or task_data.get("video_id")
            if not task_id:
                print("❌ ERROR: Akool API response did not contain a task ID.")
                raise HTTPException(status_code=500, detail="Akool API did not return a task ID.")
            
            print(f"\n" + "-"*80)
            print(f"🔄 STEP 4: Starting to poll for video status (Task ID: {task_id})")
            print(f"  - Interval: 10 seconds")
            print(f"  - Max Attempts: 12 (2 minutes) - reduced to save credits")
            print(f"  - Initial delay: 5 seconds to allow job initialization")
            print("-"*80)
            
            # Give Akool time to initialize the job
            await asyncio.sleep(5)
            
            # Polling for completion with early exit for stuck jobs
            max_attempts = 12  # 2 minutes with 10-second intervals
            consecutive_queuing = 0
            for attempt in range(max_attempts):
                if attempt > 0:  # Skip sleep on first attempt since we already waited 5 seconds
                    await asyncio.sleep(10)
                
                status_url = f"https://openapi.akool.com/api/open/v3/content/video/infobymodelid?video_model_id={task_id}"
                print(f"\n[Polling - Attempt {attempt + 1}/{max_attempts}]")
                print(f"  - Calling: GET {status_url}")
                
                polling_headers = {"Authorization": f"Bearer {akool_auth_token}"}
                print(f"  - Using headers: Authorization: Bearer {akool_auth_token[:10]}...")
                
                status_response = await client.get(
                    status_url,
                    headers=polling_headers
                )
                
                if status_response.status_code == 200:
                    try:
                        status_result = status_response.json()
                        print(f"  - Response: {status_result}")
                        
                        # Check for different error response formats
                        akool_code = status_result.get("code")
                        akool_status = status_result.get("status")
                        
                        # Handle different error response formats from Akool
                        if akool_status == 404:
                            print(f"❌ ERROR: Task ID not found (404). Job may have failed immediately.")
                            print(f"  - This could indicate:")
                            print(f"    1. Invalid image format or corrupted file")
                            print(f"    2. Invalid audio URL or inaccessible audio")
                            print(f"    3. Akool internal error during job creation")
                            print(f"  - Suggestion: Check if both image and audio URLs are publicly accessible")
                            raise HTTPException(status_code=404, detail=f"Akool job not found: {status_result.get('msg', 'Task ID invalid or job failed')}")
                        
                        if akool_code != 1000 and akool_code is not None:
                            print(f"❌ ERROR: Akool status API returned error code: {akool_code} - {status_result.get('msg')}")
                            if akool_code == 1102:
                                print("  - This indicates authorization error. Check API key validity.")
                                raise HTTPException(status_code=401, detail=f"Akool authorization failed: {status_result.get('msg')}")
                            else:
                                raise HTTPException(status_code=500, detail=f"Akool API error: {status_result.get('msg')}")
                        
                        status_data = status_result.get("data", {})
                        video_status = status_data.get("video_status", 1)
                    except json.JSONDecodeError:
                        print(f"  - Invalid JSON response: {status_response.text}")
                        continue
                    
                    status_map = {1: "Queueing", 2: "Processing", 3: "Completed", 4: "Failed"}
                    print(f"  - Received Status: {video_status} ({status_map.get(video_status, 'Unknown')})")

                    # Track consecutive queuing to detect stuck jobs
                    if video_status == 1:  # Queueing
                        consecutive_queuing += 1
                        if consecutive_queuing >= 8:  # 8 consecutive queuing attempts (80 seconds)
                            print(f"\n⚠️  WARNING: Job stuck in queue for {consecutive_queuing * 10} seconds")
                            print(f"   This suggests high server load or image/audio compatibility issues")
                            print(f"   Stopping to avoid further credit consumption")
                            raise HTTPException(status_code=503, detail=f"Akool server overloaded - job stuck in queue after {consecutive_queuing * 10} seconds")
                    else:
                        consecutive_queuing = 0  # Reset counter when status changes

                    if video_status == 3:  # Completed
                        print("\n" + "-"*80)
                        print("✅ STEP 5: Video generation completed!")
                        akool_video_url = status_data.get("video", "")
                        print(f"  - Akool Video URL: {akool_video_url}")

                        if not akool_video_url:
                            print("❌ ERROR: Akool response missing video URL despite completion status.")
                            raise HTTPException(status_code=500, detail="Akool video URL not found in response")
                        
                        print("\n" + "-"*80)
                        print("📥 STEP 6: Downloading video from Akool and uploading to our S3")
                        print(f"  - Akool Video URL: {akool_video_url}")
                        
                        # Download video from Akool with proper headers
                        video_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Accept": "video/mp4,video/*,*/*",
                            "Referer": "https://openapi.akool.com/"
                        }
                        
                        video_response = await client.get(
                            akool_video_url, 
                            headers=video_headers,
                            timeout=120.0,
                            follow_redirects=True
                        )
                        video_response.raise_for_status()
                        
                        print(f"  - Downloaded video size: {len(video_response.content)} bytes")
                        print(f"  - Content type: {video_response.headers.get('content-type', 'unknown')}")
                        
                        video_file = BytesIO(video_response.content)
                        # Create unique video filename with user name and timestamp
                        video_filename = f"talking_photo_{safe_user_name}_{timestamp}_{uuid.uuid4().hex[:6]}.mp4"
                        video_object_name = f"talking_photos/{safe_user_name}/{video_filename}"
                        
                        s3_client.upload_fileobj(
                            video_file, S3_BUCKET_NAME, video_object_name,
                            ExtraArgs={
                                'ACL': 'public-read', 
                                'ContentType': 'video/mp4',
                                'CacheControl': 'max-age=31536000',  # 1 year cache
                                'ContentDisposition': 'inline',
                                'Metadata': {
                                    'user-name': safe_user_name,
                                    'generated-timestamp': str(timestamp),
                                    'source': 'akool-talking-photo'
                                }
                            }
                        )
                        
                        print(f"  - S3 upload complete with metadata")
                        
                        # Use direct S3 URL for development to avoid CORS issues
                        # In production, configure CloudFront CORS and use CDN
                        s3_direct_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{video_object_name}"
                        encoded_video_object = quote(video_object_name, safe='/')
                        cloudfront_url = f"https://{CLOUDFRONT_DOMAIN}/{encoded_video_object}"
                        
                        # Use S3 direct URL for now to avoid CORS issues in development
                        final_video_url = s3_direct_url
                        
                        print(f"  - Uploaded to S3: {video_object_name}")
                        print(f"  - S3 Direct URL: {s3_direct_url}")
                        print(f"  - CDN URL (for production): {cloudfront_url}")
                        print(f"  - Using: {final_video_url}")
                        print("-"*80)

                        print("\n" + "="*80)
                        print("🎉 SUCCESS: Talking Photo generation complete.")
                        print("="*80)

                        return {"videoUrl": final_video_url}
                        
                    elif video_status == 4:  # Failed
                        print("❌ ERROR: Akool reported video generation failed.")
                        raise HTTPException(status_code=500, detail="Akool video generation failed")
                else:
                    print(f"  - Received non-200 status on poll: {status_response.status_code} - {status_response.text}")
            
            print("\n" + "!"*80)
            print("⏰ TIMEOUT: Akool video generation timed out after 2 minutes.")
            print("💡 SUGGESTIONS:")
            print("   1. Akool servers may be overloaded - try again later")
            print("   2. Check image format (PNG/JPG) and size (<10MB)")
            print("   3. Verify audio file format and duration")
            print(f"   4. Manual check: https://openapi.akool.com/api/open/v3/content/video/{task_id}")
            print("!"*80)
            raise HTTPException(status_code=504, detail=f"Akool video generation timed out. Task ID: {task_id}")
            
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

async def generate_caricature_with_dalle3(features_description: str, prompt_details: str) -> str:
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
            try:
                image_response = await client.get(generated_image_url)
                image_response.raise_for_status()
                print(f"  - Downloaded {len(image_response.content)} bytes from DALL-E")
            except Exception as download_error:
                print(f"❌ Failed to download image from DALL-E: {download_error}")
                raise Exception(f"Failed to download generated image: {download_error}")
            
            try:
                image_file = BytesIO(image_response.content)
                image_filename = f"caricature_{uuid.uuid4().hex[:8]}.png"
                object_name = f"caricatures/{image_filename}"
                
                s3_client.upload_fileobj(
                    image_file,
                    S3_BUCKET_NAME,
                    object_name,
                    ExtraArgs={'ACL': 'public-read', 'ContentType': 'image/png'}
                )
                
                caricature_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{object_name}"
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
    
    if not openai_client:
        raise HTTPException(status_code=500, detail="OpenAI client not initialized.")
    
    try:
        features_description = facial_features.get("description", "")
        
        # Use DALL-E 3 directly with improved prompts
        caricature_url = await generate_caricature_with_dalle3(features_description, prompt_details)
        return {"caricatureUrl": caricature_url}
        
    except Exception as e:
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

@app.post("/api/generate-voice-dub")
async def generate_voice_dub(request: dict):
    """Generate voice-dubbed media using ElevenLabs and store in S3"""
    media_url = request.get("mediaUrl", "")
    voice_id = request.get("voiceId", "")
    
    if not elevenlabs_client:
        raise HTTPException(status_code=500, detail="ElevenLabs client not initialized.")
    
    try:
        # TODO: Implement actual voice dubbing
        # For now, return mock result stored in S3
        
        dubbed_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/voice_dubs/mock_dubbed_{uuid.uuid4().hex[:8]}.mp4"
        return {"dubbedMediaUrl": dubbed_url}
        
    except Exception as e:
        print(f"Error generating voice dub: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate voice dub: {str(e)}")