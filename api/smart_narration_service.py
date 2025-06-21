"""
Smart Narration Service for Hybrid Strategy
Just-in-time generation with intelligent caching and preloading
"""

import asyncio
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from .hybrid_models import (
    NarrationCache, NarrationCacheCreate, SmartNarrationRequest, 
    SmartNarrationResponse
)
import httpx
import json

logger = logging.getLogger(__name__)

class SmartNarrationService:
    """Service for intelligent narration generation and caching"""
    
    def __init__(self, supabase_service=None, api_base_url="http://localhost:8000"):
        self.supabase = supabase_service
        self.api_base_url = api_base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.cache_duration_hours = 24  # Cache narrations for 24 hours
    
    async def get_smart_narration(self, request: SmartNarrationRequest) -> SmartNarrationResponse:
        """
        Get narration with smart caching and preloading
        1. Check cache for current narration
        2. Generate if not cached
        3. Start preloading next narration in background
        """
        try:
            logger.info(f"=== Smart narration request for user {request.user_id}, step {request.current_step_id} ===")
            logger.info(f"Script: '{request.current_script[:100]}...'")
            logger.info(f"Voice ID: {request.voice_id}")
            
            # Check cache for current narration
            cached_audio = await self._get_cached_narration(
                request.user_id, request.current_step_id, request.current_script
            )
            
            if cached_audio:
                # Cache hit - return immediately and maybe preload next
                logger.info(f"Cache hit for user {request.user_id}, step {request.current_step_id}")
                
                response = SmartNarrationResponse(
                    current_audio_url=cached_audio['audio_url'],
                    current_audio_type="audio/mpeg",
                    cache_hit=True,
                    message="Loaded from cache"
                )
                
                # Start preloading next narration if provided
                if request.preload_next_step_id and request.preload_next_script:
                    asyncio.create_task(self._preload_narration(
                        request.user_id, request.preload_next_step_id, 
                        request.preload_next_script, request.voice_id
                    ))
                    response.preload_started = True
                
                return response
            
            else:
                # Cache miss - generate now
                logger.info(f"Cache miss for user {request.user_id}, step {request.current_step_id}")
                
                audio_url = await self._generate_and_cache_narration(
                    request.user_id, request.current_step_id, 
                    request.current_script, request.voice_id
                )
                
                response = SmartNarrationResponse(
                    current_audio_url=audio_url,
                    current_audio_type="audio/mpeg", 
                    cache_hit=False,
                    message="Generated fresh"
                )
                
                # Start preloading next narration if provided
                if request.preload_next_step_id and request.preload_next_script:
                    asyncio.create_task(self._preload_narration(
                        request.user_id, request.preload_next_step_id,
                        request.preload_next_script, request.voice_id
                    ))
                    response.preload_started = True
                
                return response
                
        except Exception as e:
            logger.error(f"Smart narration failed for user {request.user_id}: {e}")
            raise Exception(f"Failed to get narration: {str(e)}")
    
    async def _get_cached_narration(self, user_id: int, step_id: str, script: str) -> Optional[Dict]:
        """Check if narration exists in cache and is still valid"""
        if not self.supabase:
            return None
            
        try:
            script_hash = hashlib.sha256(script.encode()).hexdigest()
            
            logger.info(f"Cache lookup for user {user_id}, step {step_id}")
            logger.info(f"  - Script: '{script[:50]}...'")
            logger.info(f"  - Script hash: {script_hash}")
            logger.info(f"  - Script length: {len(script)}")
            
            # Query cache table
            cached = await self.supabase.get_narration_cache(user_id, step_id, script_hash)
            
            if cached and cached['expires_at'] > datetime.now():
                logger.info(f"  - CACHE HIT: Found valid cached entry (expires: {cached['expires_at']})")
                # Update access count and timestamp
                await self.supabase.update_narration_cache_access(cached['id'])
                return cached
            
            elif cached:
                logger.info(f"  - CACHE EXPIRED: Found entry but expired (expires: {cached['expires_at']})")
                # Expired cache entry - clean it up
                await self.supabase.delete_narration_cache(cached['id'])
            else:
                logger.info(f"  - CACHE MISS: No cached entry found for hash {script_hash}")
                
        except Exception as e:
            logger.warning(f"Cache lookup failed for user {user_id}, step {step_id}: {e}")
        
        return None
    
    async def _generate_and_cache_narration(self, user_id: int, step_id: str, 
                                          script: str, voice_id: str) -> str:
        """Generate narration and store in cache"""
        try:
            # Call existing narration API
            response = await self.client.post(f"{self.api_base_url}/api/generate-narration", json={
                "script": script,
                "voiceId": voice_id
            })
            
            if response.status_code != 200:
                raise Exception(f"Narration API failed: {response.status_code}")
            
            result = response.json()
            
            # Convert base64 audio to URL (upload to S3 or create blob URL)
            audio_url = await self._convert_audio_to_url(result['audioData'], user_id, step_id)
            
            # Cache the result
            await self._cache_narration(user_id, step_id, script, audio_url)
            
            return audio_url
            
        except Exception as e:
            logger.error(f"Failed to generate and cache narration: {e}")
            raise
    
    async def _preload_narration(self, user_id: int, step_id: str, script: str, voice_id: str):
        """Preload next narration in background"""
        try:
            logger.info(f"Preloading narration for user {user_id}, step {step_id}")
            
            # Check if already cached
            cached = await self._get_cached_narration(user_id, step_id, script)
            if cached:
                logger.info(f"Next narration already cached for step {step_id}")
                return
            
            # Generate and cache
            await self._generate_and_cache_narration(user_id, step_id, script, voice_id)
            logger.info(f"Successfully preloaded narration for step {step_id}")
            
        except Exception as e:
            logger.warning(f"Preload failed for user {user_id}, step {step_id}: {e}")
            # Don't raise - preloading is optional
    
    async def _convert_audio_to_url(self, base64_audio: str, user_id: int, step_id: str) -> str:
        """Convert base64 audio to accessible URL (upload to S3 or create blob)"""
        try:
            # Import S3 service
            from .s3_service import upload_audio_to_s3
            
            # Convert base64 to bytes
            import base64
            audio_bytes = base64.b64decode(base64_audio)
            
            # Upload to S3
            s3_key = f"narration_cache/{user_id}/{step_id}_{int(datetime.now().timestamp())}.mp3"
            s3_url = await upload_audio_to_s3(audio_bytes, s3_key)
            
            return s3_url
            
        except Exception as e:
            logger.warning(f"S3 upload failed, creating local blob URL: {e}")
            # Fallback: return base64 data URL (less efficient but works)
            return f"data:audio/mpeg;base64,{base64_audio}"
    
    async def _cache_narration(self, user_id: int, step_id: str, script: str, audio_url: str):
        """Store narration in cache table"""
        if not self.supabase:
            return
            
        try:
            cache_create = NarrationCacheCreate(
                user_id=user_id,
                step_id=step_id, 
                script=script,
                audio_url=audio_url
            )
            
            logger.info(f"Caching narration for user {user_id}, step {step_id}")
            logger.info(f"  - Script: '{script[:50]}...'")
            logger.info(f"  - Script hash: {cache_create.script_hash}")
            logger.info(f"  - Audio URL: {audio_url[:50]}...")
            
            cache_data = {
                'user_id': user_id,
                'step_id': step_id,
                'script_hash': cache_create.script_hash,
                'audio_url': audio_url,
                'expires_at': datetime.now() + timedelta(hours=self.cache_duration_hours)
            }
            
            await self.supabase.create_narration_cache(cache_data)
            logger.info(f"  - ✅ Successfully cached with expires_at: {cache_data['expires_at']}")
            
        except Exception as e:
            logger.warning(f"Failed to cache narration for user {user_id}, step {step_id}: {e}")
    
    async def cleanup_expired_cache(self) -> int:
        """Clean up expired cache entries"""
        if not self.supabase:
            return 0
            
        try:
            deleted_count = await self.supabase.cleanup_expired_narration_cache()
            logger.info(f"Cleaned up {deleted_count} expired cache entries")
            return deleted_count
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
            return 0
    
    async def get_cache_stats(self, user_id: int) -> Dict[str, Any]:
        """Get cache statistics for user"""
        if not self.supabase:
            return {}
            
        try:
            stats = await self.supabase.get_narration_cache_stats(user_id)
            return stats
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}
    
    async def warm_cache_for_module(self, user_id: int, module_steps: list, voice_id: str):
        """Pre-warm cache for entire module (optional optimization)"""
        try:
            logger.info(f"Warming cache for user {user_id}, {len(module_steps)} steps")
            
            # Generate first few narrations in background
            for i, step in enumerate(module_steps[:3]):  # Pre-generate first 3 steps
                if step.get('type') == 'narration' and step.get('narrationScript'):
                    asyncio.create_task(self._preload_narration(
                        user_id, step['id'], step['narrationScript'], voice_id
                    ))
                    # Small delay to avoid overwhelming the API
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.warning(f"Cache warming failed: {e}")
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

class NarrationCacheManager:
    """Utility class for cache management operations"""
    
    def __init__(self, supabase_service):
        self.supabase = supabase_service
    
    async def get_user_cache_summary(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive cache summary for user"""
        if not self.supabase:
            return {}
            
        cache_entries = await self.supabase.get_user_narration_cache(user_id)
        
        return {
            'total_cached': len(cache_entries),
            'expired': len([e for e in cache_entries if e['expires_at'] < datetime.now()]),
            'active': len([e for e in cache_entries if e['expires_at'] >= datetime.now()]),
            'most_accessed': max(cache_entries, key=lambda x: x['access_count']) if cache_entries else None,
            'cache_size_estimate_mb': sum([e.get('audio_duration', 30) for e in cache_entries]) * 0.5 / 60  # Rough estimate
        }
    
    async def clear_user_cache(self, user_id: int) -> int:
        """Clear all cache entries for user"""
        if not self.supabase:
            return 0
            
        return await self.supabase.clear_user_narration_cache(user_id)