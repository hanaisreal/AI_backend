from sqlalchemy.orm import Session
import models, schemas

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user: schemas.UserCreate, image_url: str = None, voice_id: str = None):
    """Create a user with optional image_url and voice_id"""
    db_user = models.User(
        name=user.name, 
        age=user.age, 
        gender=user.gender,
        image_url=image_url,
        voice_id=voice_id
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_progress(db: Session, progress: schemas.UserProgressUpdate):
    user = db.query(models.User).filter(models.User.id == progress.user_id).first()
    if not user:
        return None
    
    update_data = progress.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        if key == "completed_modules" and value is not None:
            # Ensure existing modules are a list
            existing_modules = user.completed_modules
            if isinstance(existing_modules, str):
                try:
                    import json
                    existing_modules = json.loads(existing_modules)
                except:
                    existing_modules = []
            elif not isinstance(existing_modules, list):
                existing_modules = []
            
            # Merge and remove duplicates
            updated_modules = sorted(list(set(existing_modules + value)))
            setattr(user, key, updated_modules)
        elif key != "user_id": # Avoid trying to set user_id
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


def create_user_quiz_answer(db: Session, quiz_answer: schemas.QuizAnswerCreate):
    db_quiz_answer = models.QuizAnswer(**quiz_answer.model_dump())
    db.add(db_quiz_answer)
    db.commit()
    db.refresh(db_quiz_answer)
    return db_quiz_answer 