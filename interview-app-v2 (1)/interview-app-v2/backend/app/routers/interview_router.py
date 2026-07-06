"""
Candidate-facing interview endpoints (all require a valid JWT):

  POST /api/interview/session/start            - generates N AI questions
                                                   tailored to the candidate's
                                                   skills/experience (N = admin
                                                   configured question_limit)
  POST /api/interview/session/{id}/answer        - upload one recorded audio
                                                   answer (Whisper transcribes it)
  POST /api/interview/session/{id}/evaluate       - scores all answers with Gemini
                                                   and returns ONLY a submission
                                                   confirmation (no scores/PDF -
                                                   results are admin-only, see
                                                   admin_router.py)
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app import models, schemas, auth
from app.services import whisper_service, groq_service, metrics_service

router = APIRouter(prefix="/api/interview", tags=["interview"])


@router.post("/session/start", response_model=schemas.SessionStartOut)
def start_session(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role != models.UserRole.candidate:
        raise HTTPException(status_code=403, detail="Only candidates can start an interview")

    settings_row = db.query(models.AdminSettings).filter(models.AdminSettings.id == 1).first()
    question_limit = settings_row.question_limit if settings_row else 5

    generated = groq_service.generate_questions(
        skills=current_user.skills or [],
        experience_years=current_user.experience_years or 0,
        count=question_limit,
    )

    session = models.InterviewSession(user_id=current_user.id, question_count=len(generated))
    db.add(session)
    db.flush()  # get session.id without committing yet

    session_questions = []
    for idx, q in enumerate(generated):
        sq = models.SessionQuestion(
            session_id=session.id,
            question_index=idx,
            topic=q["topic"],
            question_text=q["question_text"],
            ideal_points=q["ideal_points"],
            time_limit_seconds=q["time_limit_seconds"],
        )
        db.add(sq)
        session_questions.append(sq)

    db.commit()
    for sq in session_questions:
        db.refresh(sq)

    return {
        "session_id": session.id,
        "questions": [
            {
                "question_index": sq.question_index,
                "topic": sq.topic,
                "question_text": sq.question_text,
                "time_limit_seconds": sq.time_limit_seconds,
            }
            for sq in session_questions
        ],
    }


@router.post("/session/{session_id}/answer", response_model=schemas.AnswerUploadOut)
async def submit_answer(
    session_id: int,
    question_index: int = Form(...),
    time_taken_seconds: int = Form(...),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    session = _get_owned_session(db, session_id, current_user)
    sq = (
        db.query(models.SessionQuestion)
        .filter(models.SessionQuestion.session_id == session.id, models.SessionQuestion.question_index == question_index)
        .first()
    )
    if not sq:
        raise HTTPException(status_code=404, detail="Question not found for this session")

    audio_bytes = await audio.read()
    transcript = whisper_service.transcribe_audio(audio_bytes, filename_hint=audio.filename or "answer.webm")
    metrics = metrics_service.compute_metrics(transcript, time_taken_seconds)

    answer = models.Answer(
        session_id=session.id,
        session_question_id=sq.id,
        transcript=transcript,
        time_taken_seconds=time_taken_seconds,
        words_per_minute=metrics["wpm"],
        filler_word_count=metrics["filler_word_count"],
        filler_rate_percent=metrics["filler_rate_percent"],
    )
    db.add(answer)
    db.commit()

    return {
        "question_index": question_index,
        "transcript": transcript,
        "time_taken_seconds": time_taken_seconds,
    }


@router.post("/session/{session_id}/evaluate", response_model=schemas.InterviewSubmittedOut)
def evaluate_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    session = _get_owned_session(db, session_id, current_user, with_answers=True)
    if not session.answers:
        raise HTTPException(status_code=400, detail="No answers submitted for this session yet")

    # Sort so results map back to the right answer in the same order
    sorted_answers = sorted(session.answers, key=lambda a: a.session_question.question_index)

    batch_items = [
        {
            "question_text": ans.session_question.question_text,
            "ideal_points": ans.session_question.ideal_points,
            "transcript": ans.transcript,
            "time_taken": ans.time_taken_seconds,
            "time_limit": ans.session_question.time_limit_seconds,
            "wpm": ans.words_per_minute,
            "filler_count": ans.filler_word_count,
            "filler_rate": ans.filler_rate_percent,
        }
        for ans in sorted_answers
    ]

    # ONE Gemini call scores every answer in this session (instead of one
    # call per answer) - keeps daily quota usage low on the free tier.
    results = groq_service.score_batch(batch_items)

    technical_scores, communication_scores = [], []
    for ans, result in zip(sorted_answers, results):
        ans.technical_score = result["technicalScore"]
        ans.communication_score = result["communicationScore"]
        ans.feedback = result["feedback"]
        ans.missed_concepts = result["missedConcepts"]

        technical_scores.append(ans.technical_score)
        communication_scores.append(ans.communication_score)

    avg_technical = sum(technical_scores) / len(technical_scores)
    avg_communication = sum(communication_scores) / len(communication_scores)
    overall = round(avg_technical * 0.7 + avg_communication * 0.3, 1)

    session.avg_technical_score = round(avg_technical, 1)
    session.avg_communication_score = round(avg_communication, 1)
    session.overall_score = overall
    session.verdict = _get_verdict(overall)
    session.completed_at = datetime.utcnow()

    db.commit()

    # Candidate never sees scores or a PDF - just a confirmation.
    # Results are only visible to admins via /api/admin/candidates/*
    return {
        "message": "Your interview has been submitted successfully. Our team will review your results.",
        "session_id": session.id,
    }


# ---------------- helpers (also used by admin_router) ----------------
def _get_owned_session(db: Session, session_id: int, user: models.User, with_answers: bool = False):
    query = db.query(models.InterviewSession)
    if with_answers:
        query = query.options(
            joinedload(models.InterviewSession.answers).joinedload(models.Answer.session_question)
        )
    session = query.filter(models.InterviewSession.id == session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your interview session")
    return session


def _get_verdict(score: float) -> str:
    if score >= 8:
        return "Strong Hire"
    if score >= 6.5:
        return "Hire"
    if score >= 5:
        return "Borderline"
    return "No Hire"
