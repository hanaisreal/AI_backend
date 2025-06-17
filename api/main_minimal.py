import os
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(
    title="AI Awareness Backend API - Minimal Test",
    description="Minimal backend API for debugging Vercel deployment",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers={"Access-Control-Allow-Origin": "*"}
    )

@app.get("/")
async def read_root():
    return {
        "message": "AI Awareness Backend API - Minimal Test Version",
        "status": "healthy",
        "version": "1.0.0-minimal",
        "timestamp": time.time()
    }

@app.get("/test")
async def test_endpoint():
    return {
        "status": "working",
        "message": "Minimal backend is responding correctly",
        "timestamp": time.time(),
        "environment": {
            "supabase_url": "SET" if os.getenv("SUPABASE_URL") else "NOT_SET",
            "supabase_key": "SET" if os.getenv("SUPABASE_KEY") else "NOT_SET"
        }
    }

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "minimal": True
        },
        "version": "1.0.0-minimal"
    }

@app.post("/api/complete-onboarding")
async def minimal_onboarding():
    return {
        "success": True,
        "message": "Minimal onboarding endpoint - testing only",
        "userId": "test-123",
        "imageUrl": "https://example.com/test.jpg",
        "voiceId": "test-voice",
        "voiceName": "Test Voice"
    }