"""
FastAPI app entrypoint.
Run with:  uvicorn app.main:app --reload
Interactive API docs at: http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.config import settings
from app.routers import auth_router, interview_router, admin_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Interview Helper API",
    description="AI-generated voice interviews with Whisper STT + Gemini scoring, admin-only results",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(interview_router.router)
app.include_router(admin_router.router)


@app.get("/")
def health_check():
    return {"status": "ok", "message": "AI Interview Helper API is running"}
