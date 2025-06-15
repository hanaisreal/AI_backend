from sqlalchemy import Column, Integer, String, JSON
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    age = Column(Integer)
    gender = Column(String)
    image_url = Column(String)
    voice_id = Column(String)
    
    # Generated content URLs
    caricature_url = Column(String)
    talking_photo_url = Column(String)
    
    # Progress tracking
    current_page = Column(String)  # Page enum as string
    current_step = Column(Integer, default=0)  # Current step within a page
    completed_modules = Column(JSON, default=lambda: [])  # List of completed module IDs

class QuizAnswer(Base):
    __tablename__ = "quiz_answers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    module = Column(String)
    answers = Column(JSON)
