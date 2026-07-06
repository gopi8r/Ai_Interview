"""
Pydantic schemas: define the shape of request bodies and JSON responses.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict, Field


# ---------- Auth ----------
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    experience_years: int = Field(ge=0, le=50)
    skills: List[str]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    role: str
    experience_years: Optional[int] = None
    skills: Optional[List[str]] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str


# ---------- Questions (AI-generated per session) ----------
class QuestionOut(BaseModel):
    question_index: int
    topic: str
    question_text: str
    time_limit_seconds: int


class SessionStartOut(BaseModel):
    session_id: int
    questions: List[QuestionOut]


# ---------- Answer submission ----------
class AnswerUploadOut(BaseModel):
    question_index: int
    transcript: str
    time_taken_seconds: int


# Candidate only gets a simple confirmation - NOT scores or a PDF.
class InterviewSubmittedOut(BaseModel):
    message: str
    session_id: int


# ---------- Admin: settings ----------
class AdminSettingsOut(BaseModel):
    question_limit: int


class AdminSettingsUpdate(BaseModel):
    question_limit: int = Field(ge=1, le=20)


# ---------- Admin: candidate results ----------
class CandidateSessionSummary(BaseModel):
    session_id: int
    candidate_name: str
    candidate_email: str
    experience_years: Optional[int]
    skills: Optional[List[str]]
    started_at: datetime
    completed_at: Optional[datetime]
    overall_score: Optional[float]
    avg_technical_score: Optional[float]
    avg_communication_score: Optional[float]
    verdict: Optional[str]


class AnswerDetailOut(BaseModel):
    question_index: int
    question_text: str
    transcript: str
    time_taken_seconds: int
    words_per_minute: int
    filler_word_count: int
    technical_score: float
    communication_score: float
    feedback: str
    missed_concepts: List[str]


class CandidateSessionDetailOut(CandidateSessionSummary):
    answers: List[AnswerDetailOut]
