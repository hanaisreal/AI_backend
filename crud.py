from sqlalchemy.orm import Session
import models, schemas

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user: schemas.UserCreate):
    db_user = models.User(name=user.name, age=user.age, gender=user.gender)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def create_user_quiz_answer(db: Session, quiz_answer: schemas.QuizAnswerCreate):
    db_quiz_answer = models.QuizAnswer(**quiz_answer.dict())
    db.add(db_quiz_answer)
    db.commit()
    db.refresh(db_quiz_answer)
    return db_quiz_answer 