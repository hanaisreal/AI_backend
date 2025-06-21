from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib

class UserBase(BaseModel):
    name: str
    age: int
    gender: str
    image_url: Optional[str] = None
    voice_id: Optional[str] = None
    voice_name: Optional[str] = None
    caricature_url: Optional[str] = None
    talking_photo_url: Optional[str] = None
    current_page: Optional[str] = None
    current_step: Optional[int] = 0
    completed_modules: Optional[List[str]] = []
    
    # Pre-generated face swap images (hybrid strategy)
    lottery_faceswap_url: Optional[str] = None
    crime_faceswap_url: Optional[str] = None
    investment_faceswap_url: Optional[str] = None
    accident_faceswap_url: Optional[str] = None
    
    # Pre-generated talking photos (hybrid strategy)
    lottery_video_url: Optional[str] = None
    crime_video_url: Optional[str] = None
    investment_video_url: Optional[str] = None
    accident_video_url: Optional[str] = None
    
    # Pre-generated voice dubs (hybrid strategy)
    investment_call_audio_url: Optional[str] = None
    accident_call_audio_url: Optional[str] = None
    
    # Scenario generation status tracking (hybrid strategy)
    scenario_generation_status: Optional[str] = 'pending'
    scenario_generation_started_at: Optional[datetime] = None
    scenario_generation_completed_at: Optional[datetime] = None
    scenario_generation_error: Optional[str] = None

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    image_url: Optional[str] = None
    voice_id: Optional[str] = None
    voice_name: Optional[str] = None
    caricature_url: Optional[str] = None
    talking_photo_url: Optional[str] = None
    current_page: Optional[str] = None
    current_step: Optional[int] = None
    completed_modules: Optional[List[str]] = None
    
    # Pre-generated scenario content URLs (hybrid strategy)
    lottery_faceswap_url: Optional[str] = None
    crime_faceswap_url: Optional[str] = None
    investment_faceswap_url: Optional[str] = None
    accident_faceswap_url: Optional[str] = None
    lottery_video_url: Optional[str] = None
    crime_video_url: Optional[str] = None
    investment_video_url: Optional[str] = None
    accident_video_url: Optional[str] = None
    investment_call_audio_url: Optional[str] = None
    accident_call_audio_url: Optional[str] = None
    
    # Scenario generation status (hybrid strategy)
    scenario_generation_status: Optional[str] = None
    scenario_generation_started_at: Optional[datetime] = None
    scenario_generation_completed_at: Optional[datetime] = None
    scenario_generation_error: Optional[str] = None

class User(UserBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class QuizAnswerBase(BaseModel):
    user_id: int
    module: str
    answers: Dict[str, Any]

class QuizAnswerCreate(QuizAnswerBase):
    pass

class QuizAnswer(QuizAnswerBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class UserProgressUpdate(BaseModel):
    currentPage: Optional[str] = None
    currentStep: Optional[int] = None
    caricatureUrl: Optional[str] = None
    talkingPhotoUrl: Optional[str] = None
    completedModules: Optional[List[str]] = None

# Hybrid Strategy Models

class NarrationCache(BaseModel):
    id: int
    user_id: int
    step_id: str
    script_hash: str
    audio_url: str
    audio_duration: Optional[int] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class NarrationCacheCreate(BaseModel):
    user_id: int
    step_id: str
    script: str
    audio_url: str
    audio_duration: Optional[int] = None
    
    @property
    def script_hash(self) -> str:
        return hashlib.sha256(self.script.encode()).hexdigest()

class ScenarioGenerationJob(BaseModel):
    id: int
    user_id: int
    job_type: str  # 'face_swap', 'talking_photo', 'voice_dub'
    job_key: str   # specific scenario (e.g., 'lottery_faceswap', 'crime_video')
    status: str    # 'pending', 'in_progress', 'completed', 'failed'
    start_time: Optional[datetime] = None
    completion_time: Optional[datetime] = None
    result_url: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class ScenarioGenerationJobCreate(BaseModel):
    user_id: int
    job_type: str
    job_key: str
    max_retries: Optional[int] = 2

class ScenarioGenerationJobUpdate(BaseModel):
    status: Optional[str] = None
    start_time: Optional[datetime] = None
    completion_time: Optional[datetime] = None
    result_url: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: Optional[int] = None

# Smart narration request model
class SmartNarrationRequest(BaseModel):
    user_id: int
    current_step_id: str
    current_script: str
    voice_id: str
    preload_next_step_id: Optional[str] = None
    preload_next_script: Optional[str] = None

class SmartNarrationResponse(BaseModel):
    current_audio_url: str
    current_audio_type: str
    cache_hit: bool = False
    preload_started: bool = False
    message: Optional[str] = None