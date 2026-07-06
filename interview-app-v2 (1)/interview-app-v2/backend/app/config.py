"""
Central configuration for the app. All secrets/URLs come from environment
variables (loaded from a .env file via python-dotenv).
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ---- MySQL ----
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:password@localhost:3306/ai_interview_db",
    )

    # ---- JWT auth ----
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_TO_A_RANDOM_SECRET")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))

    # ---- Groq (LLM: question generation + scoring) ----
    # Free API key at https://console.groq.com - much higher free daily limits
    # than Gemini's free tier, and runs on Groq's fast custom hardware.
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # ---- Whisper (speech-to-text) ----
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")

    # ---- CORS ----
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5500")

    # ---- Admin seed account (created by seed_admin.py) ----
    ADMIN_NAME: str = os.getenv("ADMIN_NAME", "Admin")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@example.com")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")

    # ---- Default number of interview questions (admin can change at runtime) ----
    DEFAULT_QUESTION_LIMIT: int = int(os.getenv("DEFAULT_QUESTION_LIMIT", "5"))


settings = Settings()
