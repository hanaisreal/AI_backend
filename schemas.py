from pydantic import BaseModel
from typing import List, Dict

class UserBase(BaseModel):
    name: str
    age: int
    gender: str

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    image_url: str | None = None
    voice_id: str | None = None

    class Config:
        from_attributes = True

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