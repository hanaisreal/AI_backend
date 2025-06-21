"""
Scenario Pre-generation Service for Hybrid Strategy
Generates face swaps, talking photos, and voice dubs after caricature completion
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from .hybrid_models import ScenarioGenerationJob, ScenarioGenerationJobCreate, ScenarioGenerationJobUpdate
import httpx
import json

logger = logging.getLogger(__name__)

class ScenarioPreGenerationService:
    """Service to handle background generation of scenario content"""
    
    SCENARIO_JOBS = {
        # Face swap jobs (3 total) - Only for Module 1 scenarios
        'lottery_faceswap': {
            'type': 'face_swap',
            'base_image_male': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/fakenews-case1-male.png',
            'base_image_female': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/fakenews-case1-female.png'
        },
        'crime_faceswap': {
            'type': 'face_swap', 
            'base_image_male': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/fakenews-case2-male.png',
            'base_image_female': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/fakenews-case2-female.png'
        },
        
        # Talking photo jobs (3 total) - Only for Module 1 scenarios
        'lottery_video': {
            'type': 'talking_photo',
            'script': '1등 당첨돼서 정말 기뻐요! 감사합니다!',
            'depends_on': 'lottery_faceswap'
        },
        'crime_video': {
            'type': 'talking_photo',
            'script': '제가 한 거 아니에요... 찍지 마세요. 죄송합니다…',
            'depends_on': 'crime_faceswap'
        },
        
        # Voice dub jobs (2 total) - For Module 2 scenarios
        'investment_call_audio': {
            'type': 'voice_dub',
            'source_audio_url': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/voice1.mp3'
        },
        'accident_call_audio': {
            'type': 'voice_dub',
            'source_audio_url': 'https://d3srmxrzq4dz1v.cloudfront.net/video-url/voice2.mp3'
        }
    }
    
    def __init__(self, supabase_service=None, api_base_url="http://localhost:8000"):
        self.supabase = supabase_service
        self.api_base_url = api_base_url
        self.client = httpx.AsyncClient(timeout=900.0)  # 15 minute timeout for long video generation
    
    async def start_scenario_pregeneration(self, user_id: int, user_image_url: str, 
                                         voice_id: str, gender: str) -> bool:
        """Start background generation of all scenario content"""
        try:
            logger.info(f"Starting scenario pre-generation for user {user_id}")
            
            # Update user status to in_progress
            await self._update_user_scenario_status(user_id, 'in_progress')
            
            # Create all jobs in database
            jobs = await self._create_scenario_jobs(user_id)
            
            # Start generation process
            asyncio.create_task(self._process_scenario_jobs(
                user_id, user_image_url, voice_id, gender, jobs
            ))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scenario pre-generation for user {user_id}: {e}")
            await self._update_user_scenario_status(user_id, 'failed', str(e))
            return False
    
    async def _create_scenario_jobs(self, user_id: int) -> List[ScenarioGenerationJob]:
        """Create all scenario generation jobs in database"""
        jobs = []
        
        for job_key, job_config in self.SCENARIO_JOBS.items():
            job_create = ScenarioGenerationJobCreate(
                user_id=user_id,
                job_type=job_config['type'], 
                job_key=job_key
            )
            
            # Insert into database via supabase service
            if self.supabase:
                job = await self.supabase.create_scenario_job(job_create.dict())
                jobs.append(job)
        
        return jobs
    
    async def _process_scenario_jobs(self, user_id: int, user_image_url: str, 
                                   voice_id: str, gender: str, jobs: List[ScenarioGenerationJob]):
        """Process all scenario jobs sequentially with dependencies"""
        try:
            completed_jobs = {}
            
            # Phase 1: Generate all face swaps first (parallel)
            face_swap_jobs = [job for job in jobs if job.job_type == 'face_swap']
            face_swap_results = await self._process_face_swaps(
                face_swap_jobs, user_id, user_image_url, gender
            )
            completed_jobs.update(face_swap_results)
            
            # Phase 2: Generate talking photos (depends on face swaps)
            talking_photo_jobs = [job for job in jobs if job.job_type == 'talking_photo']
            talking_photo_results = await self._process_talking_photos(
                talking_photo_jobs, user_id, voice_id, completed_jobs
            )
            completed_jobs.update(talking_photo_results)
            
            # Phase 3: Generate voice dubs (parallel)
            voice_dub_jobs = [job for job in jobs if job.job_type == 'voice_dub']
            voice_dub_results = await self._process_voice_dubs(
                voice_dub_jobs, user_id, voice_id
            )
            completed_jobs.update(voice_dub_results)
            
            # Update user with all generated URLs
            await self._update_user_with_results(user_id, completed_jobs)
            
            # Mark scenario generation as completed
            await self._update_user_scenario_status(user_id, 'completed')
            
            logger.info(f"Scenario pre-generation completed for user {user_id}")
            
        except Exception as e:
            logger.error(f"Scenario pre-generation failed for user {user_id}: {e}")
            await self._update_user_scenario_status(user_id, 'failed', str(e))
    
    async def _process_face_swaps(self, jobs: List[ScenarioGenerationJob], 
                                user_id: int, user_image_url: str, gender: str) -> Dict[str, str]:
        """Process face swap jobs in parallel"""
        results = {}
        
        tasks = []
        for job in jobs:
            task = self._generate_face_swap(job, user_image_url, gender)
            tasks.append(task)
        
        face_swap_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for job, result in zip(jobs, face_swap_results):
            if isinstance(result, Exception):
                logger.error(f"Face swap failed for {job.job_key}: {result}")
                await self._update_job_status(job.id, 'failed', error_message=str(result))
            else:
                results[job.job_key] = result
                await self._update_job_status(job.id, 'completed', result_url=result)
        
        return results
    
    async def _process_talking_photos(self, jobs: List[ScenarioGenerationJob], 
                                    user_id: int, voice_id: str, 
                                    face_swap_results: Dict[str, str]) -> Dict[str, str]:
        """Process talking photo jobs (depends on face swaps)"""
        results = {}
        
        for job in jobs:
            job_config = self.SCENARIO_JOBS[job.job_key]
            depends_on = job_config.get('depends_on')
            
            if depends_on and depends_on in face_swap_results:
                faceswap_url = face_swap_results[depends_on]
                script = job_config['script']
                
                try:
                    await self._update_job_status(job.id, 'in_progress')
                    result_url = await self._generate_talking_photo(faceswap_url, voice_id, script)
                    
                    # Validate that we got a real URL, not a sample fallback
                    if result_url and 'sample' not in result_url.lower():
                        results[job.job_key] = result_url
                        await self._update_job_status(job.id, 'completed', result_url=result_url)
                        logger.info(f"✅ Talking photo completed successfully for {job.job_key}")
                    else:
                        # This means we got a sample video due to API failure/timeout
                        logger.warning(f"⚠️ Talking photo returned sample video for {job.job_key}: {result_url}")
                        results[job.job_key] = result_url  # Still save the sample URL
                        await self._update_job_status(job.id, 'completed_with_fallback', 
                                                    result_url=result_url, 
                                                    error_message="API timeout - using sample video")
                    
                except Exception as e:
                    logger.error(f"❌ Talking photo failed for {job.job_key}: {e}")
                    await self._update_job_status(job.id, 'failed', error_message=str(e))
                    # Don't add to results - this job completely failed
            else:
                logger.warning(f"Dependency {depends_on} not found for {job.job_key}")
                await self._update_job_status(job.id, 'failed', 
                                            error_message=f"Dependency {depends_on} failed")
        
        return results
    
    async def _process_voice_dubs(self, jobs: List[ScenarioGenerationJob], 
                                user_id: int, voice_id: str) -> Dict[str, str]:
        """Process voice dub jobs in parallel"""
        results = {}
        
        tasks = []
        for job in jobs:
            job_config = self.SCENARIO_JOBS[job.job_key]
            source_audio_url = job_config['source_audio_url']
            task = self._generate_voice_dub(job, source_audio_url, voice_id)
            tasks.append(task)
        
        voice_dub_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for job, result in zip(jobs, voice_dub_results):
            if isinstance(result, Exception):
                logger.error(f"Voice dub failed for {job.job_key}: {result}")
                await self._update_job_status(job.id, 'failed', error_message=str(result))
            else:
                results[job.job_key] = result
                await self._update_job_status(job.id, 'completed', result_url=result)
        
        return results
    
    async def _generate_face_swap(self, job: ScenarioGenerationJob, 
                                user_image_url: str, gender: str) -> str:
        """Generate face swap using existing API"""
        job_config = self.SCENARIO_JOBS[job.job_key]
        base_image = job_config[f'base_image_{gender.lower()}']
        
        await self._update_job_status(job.id, 'in_progress')
        
        response = await self.client.post(f"{self.api_base_url}/api/generate-faceswap-image", json={
            "userImageUrl": user_image_url,
            "baseImageUrl": base_image
        })
        
        if response.status_code == 200:
            result = response.json()
            return result.get('faceswapImageUrl')
        else:
            raise Exception(f"Face swap API failed: {response.status_code}")
    
    async def _generate_talking_photo(self, caricature_url: str, voice_id: str, script: str) -> str:
        """Generate talking photo with extended timeout for pre-generation"""
        
        # For pre-generation, we need longer timeout than the regular endpoint
        # Call the endpoint with extended timeout flag or use direct API calls
        response = await self.client.post(f"{self.api_base_url}/api/generate-talking-photo", json={
            "caricatureUrl": caricature_url,
            "userName": "User",
            "voiceId": voice_id,
            "audioScript": script,
            "scenarioType": "pregenerated",
            "extendedTimeout": True  # Signal for longer timeout in pre-generation
        })
        
        if response.status_code == 200:
            result = response.json()
            video_url = result.get('videoUrl')
            if not video_url:
                raise Exception("No video URL returned from talking photo API")
            return video_url
        else:
            error_text = ""
            try:
                error_data = response.json()
                error_text = error_data.get('detail', response.text)
            except:
                error_text = response.text
            raise Exception(f"Talking photo API failed ({response.status_code}): {error_text}")
    
    async def _generate_voice_dub(self, job: ScenarioGenerationJob, 
                                source_audio_url: str, voice_id: str) -> str:
        """Generate voice dub using existing API"""
        await self._update_job_status(job.id, 'in_progress')
        
        response = await self.client.post(f"{self.api_base_url}/api/generate-voice-dub", json={
            "audioUrl": source_audio_url,
            "voiceId": voice_id,
            "scenarioType": job.job_key
        })
        
        if response.status_code == 200:
            result = response.json()
            return result.get('audioData')  # Base64 audio data
        else:
            raise Exception(f"Voice dub API failed: {response.status_code}")
    
    async def _update_job_status(self, job_id: int, status: str, 
                               result_url: Optional[str] = None, 
                               error_message: Optional[str] = None):
        """Update job status in database"""
        if self.supabase:
            update_data = {
                'status': status,
                'updated_at': datetime.now()
            }
            
            if status == 'in_progress':
                update_data['start_time'] = datetime.now()
            elif status in ['completed', 'failed']:
                update_data['completion_time'] = datetime.now()
                
            if result_url:
                update_data['result_url'] = result_url
            if error_message:
                update_data['error_message'] = error_message
                
            await self.supabase.update_scenario_job(job_id, update_data)
    
    async def _update_user_scenario_status(self, user_id: int, status: str, 
                                         error: Optional[str] = None):
        """Update user's scenario generation status"""
        if self.supabase:
            update_data = {
                'scenario_generation_status': status,
                'scenario_generation_started_at': datetime.now() if status == 'in_progress' else None,
                'scenario_generation_completed_at': datetime.now() if status == 'completed' else None,
                'scenario_generation_error': error
            }
            await self.supabase.update_user(user_id, update_data)
    
    async def _update_user_with_results(self, user_id: int, results: Dict[str, str]):
        """Update user record with all generated URLs"""
        if self.supabase:
            update_data = {}
            
            # Map job keys to user fields
            job_to_field_mapping = {
                'lottery_faceswap': 'lottery_faceswap_url',
                'crime_faceswap': 'crime_faceswap_url', 
                'lottery_video': 'lottery_video_url',
                'crime_video': 'crime_video_url',
                'investment_call_audio': 'investment_call_audio_url',
                'accident_call_audio': 'accident_call_audio_url'
            }
            
            for job_key, url in results.items():
                if job_key in job_to_field_mapping:
                    update_data[job_to_field_mapping[job_key]] = url
            
            await self.supabase.update_user(user_id, update_data)
    
    async def get_scenario_generation_status(self, user_id: int) -> Dict:
        """Get current scenario generation status for user"""
        if self.supabase:
            user = await self.supabase.get_user(user_id)
            jobs = await self.supabase.get_scenario_jobs(user_id)
            
            return {
                'status': user.get('scenario_generation_status', 'pending'),
                'started_at': user.get('scenario_generation_started_at'),
                'completed_at': user.get('scenario_generation_completed_at'),
                'error': user.get('scenario_generation_error'),
                'jobs': jobs
            }
        return {'status': 'unknown'}
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()