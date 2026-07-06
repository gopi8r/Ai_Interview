# AI Interview Helper v2 — AI-Generated Questions + Admin-Only Results

Major changes from v1:
- **Registration now collects skills + years of experience** — these are sent to Gemini to generate a **tailored set of questions per candidate**, instead of a fixed static question bank.
- **Candidates never see their scores or a PDF.** After the interview, they just get a "thank you, submitted for review" screen.
- **New admin dashboard** (`admin.html`) — a separate login for recruiters/admins to view all candidates' results, drill into per-question breakdowns, and download the PDF report.
- **Admin can configure how many questions** each interview generates (`question_limit`), applied to all future interviews.
- Fresh, modern UI on both the candidate site and admin dashboard.

## Tech stack

| Component | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript, Bootstrap 5 (colorful glassmorphism theme) |
| Backend | FastAPI |
| Database | MySQL |
| ORM | SQLAlchemy |
| Authentication | JWT |
| Speech-to-Text | Whisper (local) - transcript used for scoring only, never shown in the UI |
| LLM | **Groq** (Llama 3.3 70B) - question generation + scoring, much higher free daily limit than Gemini |
| Text-to-Speech | Browser SpeechSynthesis API |
| PDF Generation | ReportLab (admin-only) |

### Why Groq instead of Gemini
Gemini's free tier caps at 20 requests/day for `gemini-2.5-flash`, which gets used up fast (each
interview makes 2 calls: 1 to generate questions, 1 to batch-score all answers). Groq runs
open-source models (Llama 3.3 70B) on custom inference hardware — it's fast, OpenAI-compatible,
and its free tier has a much higher daily cap. Get a free key at https://console.groq.com.

### UI change: no raw transcript shown to candidates
Whisper still transcribes every answer (needed for scoring), but the candidate-facing screen now
shows an **animated avatar** instead of the raw transcript text — it changes state as the
interview progresses: 🗣️ speaking the question → 🎙️ ready → 👂 listening → 🤔 processing → ✅ done.
This is purely a frontend change (`app.js`'s `setAvatarState()`); the transcript is still sent to
and stored by the backend exactly as before, just never rendered on screen.

## Project structure

```
interview-app-v2/
├── backend/
│   ├── app/
│   │   ├── main.py                  # registers auth, interview, and admin routers
│   │   ├── config.py                 # includes admin seed creds + default question limit
│   │   ├── database.py
│   │   ├── models.py                 # User (+skills/experience), AdminSettings,
│   │   │                              # SessionQuestion (AI-generated per session), Answer
│   │   ├── schemas.py
│   │   ├── auth.py                   # + get_current_admin dependency
│   │   ├── seed_admin.py             # creates the admin account + default settings row
│   │   ├── services/
│   │   │   ├── whisper_service.py
│   │   │   ├── gemini_service.py     # + generate_questions(skills, experience, count)
│   │   │   ├── metrics_service.py
│   │   │   └── pdf_service.py        # only ever called from admin_router
│   │   └── routers/
│   │       ├── auth_router.py        # register now takes experience_years + skills
│   │       ├── interview_router.py   # candidate flow - NO scores in responses
│   │       └── admin_router.py       # NEW: settings, candidate list/detail, PDF
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── index.html                    # candidate site: home -> auth -> interview -> "thank you"
    ├── admin.html                    # NEW: admin login + dashboard
    ├── css/style.css                 # shared, redesigned styling
    └── js/
        ├── app.js                    # candidate logic
        └── admin.js                  # NEW: admin dashboard logic
```

## How AI question generation works

When a candidate clicks **Start Interview**, the backend (`interview_router.py` →
`start_session`) calls `gemini_service.generate_questions(skills, experience_years, count)`,
where `count` comes from the admin's configured `question_limit`. Gemini returns a JSON array of
questions, each with a topic, the question text, a scoring rubric (`ideal_points` — never shown to
the candidate), and an appropriate time limit. These are saved to a new `session_questions` table
tied to that specific interview session, so:
- Two candidates with different skills get different questions
- The exact question asked is preserved for scoring and the admin PDF report
- Re-generating never overwrites past sessions

## How admin-only results work

- `POST /api/interview/session/{id}/evaluate` still scores every answer with Gemini (same as v1),
  but the response returned to the **candidate** only contains a success message — no scores.
- All score data lives in the `answers` and `interview_sessions` tables regardless.
- `admin_router.py` exposes `/api/admin/candidates` (list) and `/api/admin/candidates/{id}`
  (full breakdown) and `/api/admin/candidates/{id}/report` (PDF) — all behind
  `auth.get_current_admin`, which checks the JWT's user has `role == admin` and returns 403 otherwise.

---

## Step-by-step setup

### 1. Prerequisites (same as before)
- Python 3.11 or 3.12 (avoid Python 3.13+ for now — some packages like `torch`/`pydantic-core` may lack pre-built wheels)
- MySQL Server running
- ffmpeg installed and on PATH (required by Whisper)
- A Groq API key from https://console.groq.com (free, higher daily limits than Gemini)

### 2. Create the database
```sql
CREATE DATABASE ai_interview_db CHARACTER SET utf8mb4;
```

### 3. Backend setup
```bash
cd backend
python -m venv venv
venv\Scripts\Activate.ps1        # Windows PowerShell
# source venv/bin/activate       # Mac/Linux

pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

Copy the environment template and fill in your real values:
```bash
copy .env.example .env
```
Edit `.env`:
```
DATABASE_URL=mysql+pymysql://root:yourpassword@localhost:3306/ai_interview_db
JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
GROQ_API_KEY=<your real Groq key>
GROQ_MODEL=llama-3.3-70b-versatile
WHISPER_MODEL_SIZE=base
FRONTEND_ORIGIN=http://127.0.0.1:5500

ADMIN_NAME=Admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=ChangeMe123!
DEFAULT_QUESTION_LIMIT=5
```

### 4. Seed the admin account and default settings
```bash
python -m app.seed_admin
```
This creates the admin login (using the credentials from `.env`) and the default
`question_limit` row. **Change `ADMIN_PASSWORD` to something real before running this** —
whatever is in `.env` at the time becomes the actual admin password.

### 5. Run the backend
```bash
uvicorn app.main:app --reload
```
Check http://127.0.0.1:8000/docs to confirm it's up. First run downloads the Whisper model.

### 6. Run the frontend
```bash
cd frontend
python -m http.server 5500
```

### 7. Try it out
- **Candidate flow**: open http://127.0.0.1:5500 → Get Started → Register (include skills +
  experience) → Start Interview → answer the AI-generated questions → see the "thank you" screen
  (no scores shown).
- **Admin flow**: open http://127.0.0.1:5500/admin.html → log in with the `ADMIN_EMAIL` /
  `ADMIN_PASSWORD` from your `.env` → see the candidate results table → click **View** on a
  completed interview → see the full breakdown → click **Download PDF**.
- **Change question count**: in the admin dashboard's Settings panel, update "Number of Questions
  per Interview" and click Save — this applies to the next candidate who starts an interview.

---

## Things you must configure

1. **MySQL** running and reachable via `DATABASE_URL`
2. **GROQ_API_KEY** — valid key from console.groq.com; used for both question generation and scoring
3. **ffmpeg** on PATH for Whisper
4. **JWT_SECRET_KEY** — a real random string
5. **ADMIN_EMAIL / ADMIN_PASSWORD** in `.env` before running `seed_admin.py` — this becomes your
   actual login. Re-running the script afterward won't reset the password (it skips existing
   admins) — to change it, update the DB directly or delete the row and re-run.
6. **API_BASE** at the top of both `frontend/js/app.js` and `frontend/js/admin.js` — must point to
   wherever FastAPI actually runs
7. **FRONTEND_ORIGIN** in backend `.env` — must match the exact origin the frontend is served from (CORS)

## Known considerations carried over from v1

- Gemini 2.5 Flash spends part of its token budget on internal "thinking" — both
  `generate_questions()` and `score_answer()` use `max_output_tokens: 4096` and
  `response_mime_type: application/json` to avoid truncated/malformed JSON.
- MediaRecorder's `onstop` event is awaited before uploading audio, to avoid submitting a
  corrupt/incomplete webm file (this was the cause of "EBML header parsing failed" ffmpeg errors
  in earlier testing).
- Whisper on CPU with the `base` model takes noticeable time per answer; switch
  `WHISPER_MODEL_SIZE=tiny` in `.env` for faster (slightly less accurate) transcription.

## Extending further

- **Retry/regenerate questions**: if Gemini fails entirely during question generation, a small
  hardcoded fallback bank in `gemini_service.py` (`_fallback_questions`) keeps the interview
  usable rather than erroring out.
- **Multiple admins**: run `seed_admin.py` again with different `.env` values, or insert directly
  into the `users` table with `role='admin'`.
- **Export all results**: add a `/api/admin/candidates/export` CSV endpoint if you need bulk data
  outside the dashboard.
