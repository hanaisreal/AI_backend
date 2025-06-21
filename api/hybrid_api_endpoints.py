"""
Hybrid Strategy API Endpoints
Add these endpoints to your main.py FastAPI application
"""

import asyncio
from fastapi import HTTPException
from .hybrid_models import SmartNarrationRequest, SmartNarrationResponse
from .scenario_pregeneration_service import ScenarioPreGenerationService
from .smart_narration_service import SmartNarrationService

# Initialize services (add these to your main.py imports and startup)
scenario_service = None
narration_service = None

def initialize_hybrid_services(supabase_service, api_base_url="http://localhost:8000"):
    """Initialize hybrid services - call this in your main.py startup"""
    global scenario_service, narration_service
    scenario_service = ScenarioPreGenerationService(supabase_service, api_base_url)
    narration_service = SmartNarrationService(supabase_service, api_base_url)

# Add these endpoints to your FastAPI app

async def start_scenario_pregeneration_endpoint(user_id: int, user_image_url: str, 
                                              voice_id: str, gender: str):
    """
    Start scenario pre-generation after caricature completion
    Call this from your existing complete_onboarding or caricature generation endpoint
    """
    if not scenario_service:
        raise HTTPException(status_code=503, detail="Scenario service not available")
    
    try:
        success = await scenario_service.start_scenario_pregeneration(
            user_id, user_image_url, voice_id, gender
        )
        
        if success:
            return {"message": "Scenario pre-generation started", "status": "in_progress"}
        else:
            raise HTTPException(status_code=500, detail="Failed to start scenario pre-generation")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scenario pre-generation failed: {str(e)}")

async def smart_narration_endpoint(request: SmartNarrationRequest):
    """
    Smart narration endpoint with caching and preloading
    Replace or supplement your existing /api/generate-narration endpoint
    """
    if not narration_service:
        raise HTTPException(status_code=503, detail="Narration service not available")
    
    try:
        response = await narration_service.get_smart_narration(request)
        return response.dict()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Smart narration failed: {str(e)}")

async def get_scenario_status_endpoint(user_id: int):
    """Get scenario generation status for user"""
    if not scenario_service:
        raise HTTPException(status_code=503, detail="Scenario service not available")
    
    try:
        status = await scenario_service.get_scenario_generation_status(user_id)
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")

async def get_cache_stats_endpoint(user_id: int):
    """Get narration cache statistics for user"""
    if not narration_service:
        raise HTTPException(status_code=503, detail="Narration service not available")
    
    try:
        stats = await narration_service.get_cache_stats(user_id)
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")

async def cleanup_cache_endpoint():
    """Clean up expired cache entries"""
    if not narration_service:
        raise HTTPException(status_code=503, detail="Narration service not available")
    
    try:
        deleted_count = await narration_service.cleanup_expired_cache()
        return {"deleted_count": deleted_count, "message": "Cache cleanup completed"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache cleanup failed: {str(e)}")

# FastAPI route definitions to add to your main.py:

"""
from hybrid_api_endpoints import (
    initialize_hybrid_services, start_scenario_pregeneration_endpoint,
    smart_narration_endpoint, get_scenario_status_endpoint, 
    get_cache_stats_endpoint, cleanup_cache_endpoint
)
from hybrid_models import SmartNarrationRequest

# In your startup event
@app.on_event("startup")
async def startup_event():
    # ... your existing startup code ...
    initialize_hybrid_services(supabase_service, "http://localhost:8000")

# Add these routes to your FastAPI app:

@app.post("/api/smart-narration")
async def smart_narration(request: SmartNarrationRequest):
    return await smart_narration_endpoint(request)

@app.get("/api/scenario-status/{user_id}")
async def get_scenario_status(user_id: int):
    return await get_scenario_status_endpoint(user_id)

@app.get("/api/cache-stats/{user_id}")
async def get_cache_stats(user_id: int):
    return await get_cache_stats_endpoint(user_id)

@app.post("/api/cleanup-cache")
async def cleanup_cache():
    return await cleanup_cache_endpoint()

# Modify your existing complete_onboarding endpoint to trigger scenario pre-generation:

@app.post("/api/complete-onboarding")
async def complete_onboarding(
    name: str = Form(...),
    age: int = Form(...),
    gender: str = Form(...),
    image: UploadFile = File(...),
    voice: UploadFile = File(...)
):
    # ... your existing onboarding logic ...
    # After successful user creation and caricature generation:
    
    # Start scenario pre-generation in background
    asyncio.create_task(start_scenario_pregeneration_endpoint(
        user_id, user_image_url, voice_id, gender
    ))
    
    return {
        "success": True,
        "userId": str(user_id),
        "imageUrl": user_image_url,
        "voiceId": voice_id,
        "voiceName": voice_name,
        "caricatureUrl": caricature_url,
        "message": "Onboarding completed. Scenario generation started in background."
    }
"""