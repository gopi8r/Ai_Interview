"""
Admin-only endpoints (require role == admin, enforced by auth.get_current_admin):

  GET  /api/admin/settings               - view the current question limit
  PUT  /api/admin/settings               - update the question limit
  GET  /api/admin/candidates             - list all completed/in-progress
                                            interview sessions with scores
  GET  /api/admin/candidates/{id}         - full breakdown for one session
  GET  /api/admin/candidates/{id}/report   - download the PDF scorecard
                                            (this is the ONLY place a PDF is
                                            ever generated - candidates never
                                            see it)
"""
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app import models, schemas, auth
from app.services import pdf_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------- Settings ----------------
@router.get("/settings", response_model=schemas.AdminSettingsOut)
def get_settings(db: Session = Depends(get_db), _admin: models.User = Depends(auth.get_current_admin)):
    row = _get_or_create_settings(db)
    return {"question_limit": row.question_limit}


@router.put("/settings", response_model=schemas.AdminSettingsOut)
def update_settings(
    payload: schemas.AdminSettingsUpdate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(auth.get_current_admin),
):
    row = _get_or_create_settings(db)
    row.question_limit = payload.question_limit
    db.commit()
    db.refresh(row)
    return {"question_limit": row.question_limit}


def _get_or_create_settings(db: Session) -> models.AdminSettings:
    row = db.query(models.AdminSettings).filter(models.AdminSettings.id == 1).first()
    if not row:
        row = models.AdminSettings(id=1, question_limit=5)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


# ---------------- Candidate results ----------------
@router.get("/candidates", response_model=list[schemas.CandidateSessionSummary])
def list_candidates(db: Session = Depends(get_db), _admin: models.User = Depends(auth.get_current_admin)):
    sessions = (
        db.query(models.InterviewSession)
        .options(joinedload(models.InterviewSession.user))
        .order_by(models.InterviewSession.started_at.desc())
        .all()
    )
    return [_session_to_summary(s) for s in sessions]


@router.get("/candidates/{session_id}", response_model=schemas.CandidateSessionDetailOut)
def get_candidate_detail(
    session_id: int, db: Session = Depends(get_db), _admin: models.User = Depends(auth.get_current_admin)
):
    session = _get_session_or_404(db, session_id)
    summary = _session_to_summary(session)
    sorted_answers = sorted(session.answers, key=lambda a: a.session_question.question_index)
    summary["answers"] = [
        {
            "question_index": a.session_question.question_index,
            "question_text": a.session_question.question_text,
            "transcript": a.transcript,
            "time_taken_seconds": a.time_taken_seconds,
            "words_per_minute": a.words_per_minute,
            "filler_word_count": a.filler_word_count,
            "technical_score": a.technical_score or 0.0,
            "communication_score": a.communication_score or 0.0,
            "feedback": a.feedback or "",
            "missed_concepts": a.missed_concepts or [],
        }
        for a in sorted_answers
    ]
    return summary


@router.get("/candidates/{session_id}/report")
def download_candidate_report(
    session_id: int, db: Session = Depends(get_db), _admin: models.User = Depends(auth.get_current_admin)
):
    session = _get_session_or_404(db, session_id)
    if session.overall_score is None:
        raise HTTPException(status_code=400, detail="This candidate has not completed evaluation yet")

    pdf_bytes = pdf_service.generate_report_pdf(session)
    filename = f"interview-report-{session.user.name.replace(' ', '_')}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------- helpers ----------------
def _get_session_or_404(db: Session, session_id: int) -> models.InterviewSession:
    session = (
        db.query(models.InterviewSession)
        .options(
            joinedload(models.InterviewSession.user),
            joinedload(models.InterviewSession.answers).joinedload(models.Answer.session_question),
        )
        .filter(models.InterviewSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _session_to_summary(session: models.InterviewSession) -> dict:
    return {
        "session_id": session.id,
        "candidate_name": session.user.name,
        "candidate_email": session.user.email,
        "experience_years": session.user.experience_years,
        "skills": session.user.skills,
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "overall_score": session.overall_score,
        "avg_technical_score": session.avg_technical_score,
        "avg_communication_score": session.avg_communication_score,
        "verdict": session.verdict,
    }
