from pydantic import BaseModel, field_validator
from typing import List, Dict, Optional
import json

class UserBase(BaseModel):
    name: str
    age: int
    gender: str

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    image_url: Optional[str] = None
    voice_id: Optional[str] = None
    caricature_url: Optional[str] = None
    talking_photo_url: Optional[str] = None
    current_page: Optional[str] = None
    current_step: int = 0
    completed_modules: List[str] = []

    @field_validator('completed_modules', mode='before')
    @classmethod
    def ensure_completed_modules_is_list(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [] # Return empty list if string is not valid JSON
        if v is None:
            return []
        return v

    class Config:
        from_attributes = True

class UserProgressUpdate(BaseModel):
    user_id: int
    current_page: Optional[str] = None
    current_step: Optional[int] = None
    caricature_url: Optional[str] = None
    talking_photo_url: Optional[str] = None
    completed_modules: Optional[List[str]] = None

class QuizAnswerBase(BaseModel):
    user_id: int
    module: str
    answers: Dict

class QuizAnswerCreate(QuizAnswerBase):
    pass

class QuizAnswer(QuizAnswerBase):
    id: int

    class Config:
        from_attributes = True 