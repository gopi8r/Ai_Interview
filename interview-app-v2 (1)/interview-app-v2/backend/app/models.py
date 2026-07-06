"""
ORM models -> MySQL tables.

users               : candidates (with skills/experience for AI question generation)
                      and admins (role='admin', created via seed_admin.py)
admin_settings      : a single-row table holding runtime-configurable settings
                      (currently just the number of questions per interview)
interview_sessions  : one row per interview attempt by a candidate
session_questions   : the AI-generated questions for one specific session
                      (generated fresh each time, tailored to that candidate's
                      skills + experience - NOT a shared static question bank)
answers             : one row per answered question within a session
"""
from datetime import datetime
import enum

from sqlalchemy import (
    Column, Integer, String, Text, Float, ForeignKey, DateTime, JSON, Enum, Boolean
)
from sqlalchemy.orm import relationship

from app.database import Base


class UserRole(str, enum.Enum):
    candidate = "candidate"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.candidate, nullable=False)

    # Candidate profile fields - used to tailor AI-generated questions
    experience_years = Column(Integer, nullable=True)
    skills = Column(JSON, nullable=True)  # list[str], e.g. ["Java", "Spring Boot", "MySQL"]

    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("InterviewSession", back_populates="user")


class AdminSettings(Base):
    """Single-row table (id is always 1) holding admin-configurable settings."""
    __tablename__ = "admin_settings"

    id = Column(Integer, primary_key=True, default=1)
    question_limit = Column(Integer, default=5, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    question_count = Column(Integer, nullable=False)  # how many questions this session used

    avg_technical_score = Column(Float, nullable=True)
    avg_communication_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    verdict = Column(String(50), nullable=True)

    user = relationship("User", back_populates="sessions")
    questions = relationship("SessionQuestion", back_populates="session", cascade="all, delete-orphan")
    answers = relationship("Answer", back_populates="session", cascade="all, delete-orphan")


class SessionQuestion(Base):
    """
    An AI-generated question belonging to exactly one interview session.
    Generated fresh at session start based on the candidate's skills/experience,
    so different candidates - or even the same candidate on a retake - get
    different questions.
    """
    __tablename__ = "session_questions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("interview_sessions.id"), nullable=False)
    question_index = Column(Integer, nullable=False)  # 0-based order within the session

    topic = Column(String(100), nullable=False)
    question_text = Column(Text, nullable=False)
    ideal_points = Column(JSON, nullable=False)  # list[str] rubric key-points, used for scoring only
    time_limit_seconds = Column(Integer, default=90)

    session = relationship("InterviewSession", back_populates="questions")
    answer = relationship("Answer", back_populates="session_question", uselist=False)


class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("interview_sessions.id"), nullable=False)
    session_question_id = Column(Integer, ForeignKey("session_questions.id"), nullable=False)

    transcript = Column(Text, nullable=True)
    time_taken_seconds = Column(Integer, nullable=True)

    words_per_minute = Column(Integer, nullable=True)
    filler_word_count = Column(Integer, nullable=True)
    filler_rate_percent = Column(Float, nullable=True)

    technical_score = Column(Float, nullable=True)     # 0-10
    communication_score = Column(Float, nullable=True) # 0-10
    feedback = Column(Text, nullable=True)
    missed_concepts = Column(JSON, nullable=True)       # list[str]

    session = relationship("InterviewSession", back_populates="answers")
    session_question = relationship("SessionQuestion", back_populates="answer")
