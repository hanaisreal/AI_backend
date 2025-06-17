from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class UserBase(BaseModel):
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

class UserCreate(UserBase):
    pass

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