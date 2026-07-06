"""
LLM service using Groq (https://console.groq.com) instead of Gemini.

Why Groq: it hosts open-source models (Llama 3.3 70B, etc.) on custom
inference hardware - very fast, and its free tier has a much higher daily
request limit than Gemini's free tier (which caps at 20 requests/day for
gemini-2.5-flash). The API is OpenAI-compatible.

Same two responsibilities as before, with the SAME function signatures
(generate_questions, score_batch) so nothing else in the app needed to
change when we swapped providers - only interview_router.py's import line
changed from `gemini_service` to `groq_service`.

Groq's JSON mode (response_format={"type": "json_object"}) requires the
model to return a JSON OBJECT, not a bare array - so both prompts ask for
a wrapper object ({"questions": [...]} / {"results": [...]}) and we unwrap
it after parsing.
"""
import json

from groq import Groq

from app.config import settings

_client = Groq(api_key=settings.GROQ_API_KEY)


def _call_groq(prompt: str, max_tokens: int = 4096, temperature: float = 0.4) -> str:
    """Calls Groq's chat completion endpoint and returns the raw text content."""
    response = _client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or ""


def _experience_level(years: int) -> str:
    if years <= 1:
        return "fresher / entry-level (0-1 years)"
    if years <= 3:
        return "junior (1-3 years)"
    if years <= 6:
        return "mid-level (3-6 years)"
    return "senior (6+ years)"


# ---------------------------------------------------------------
# 1. Question generation
# ---------------------------------------------------------------
def generate_questions(skills: list[str], experience_years: int, count: int) -> list[dict]:
    """
    Returns a list of dicts:
    [{ "topic": str, "question_text": str, "ideal_points": [str, ...], "time_limit_seconds": int }, ...]
    """
    skills_str = ", ".join(skills) if skills else "Java (general)"
    level = _experience_level(experience_years)

    prompt = f"""You are a senior technical interviewer designing a SPOKEN technical interview.

CANDIDATE PROFILE:
- Experience level: {level} ({experience_years} years)
- Skills to focus on: {skills_str}

Generate exactly {count} technical interview questions tailored to this candidate's skills and
experience level. Questions should be answerable verbally in under 2 minutes each (no coding-on-
paper questions, no whiteboard diagrams - concept explanations, comparisons, trade-offs, and
"how would you approach X" style questions only). Vary the topics across the candidate's listed
skills. Increase conceptual depth for higher experience levels.

For each question also provide a short scoring rubric (3-4 key points a strong answer should
cover) and an appropriate spoken-answer time limit in seconds (60-120 depending on complexity).

Respond with ONLY a valid JSON object (this is required - your response must be a JSON object,
not a bare array), in exactly this shape, with exactly {count} items in the "questions" array:
{{
  "questions": [
    {{
      "topic": "<short topic label>",
      "question_text": "<the interview question>",
      "ideal_points": ["<key point 1>", "<key point 2>", "<key point 3>"],
      "time_limit_seconds": <integer 60-120>
    }}
  ]
}}"""

    try:
        raw_text = _call_groq(prompt, max_tokens=4096, temperature=0.4)
    except Exception as e:
        print("=" * 60)
        print("[groq_service] GROQ QUESTION GENERATION FAILED")
        print("Error:", repr(e))
        print("=" * 60)
        return _fallback_questions(count)

    try:
        data = json.loads(raw_text)
        questions = data.get("questions", [])
        if not isinstance(questions, list) or len(questions) == 0:
            raise ValueError("Groq did not return a non-empty 'questions' array")
        normalized = []
        for q in questions[:count]:
            normalized.append({
                "topic": q.get("topic", "General"),
                "question_text": q.get("question_text", "Tell me about a Java project you've worked on."),
                "ideal_points": q.get("ideal_points", []),
                "time_limit_seconds": int(q.get("time_limit_seconds", 90)),
            })
        return normalized
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print("=" * 60)
        print("[groq_service] FAILED TO PARSE GENERATED QUESTIONS")
        print("Error:", e)
        print("Raw text:", raw_text)
        print("=" * 60)
        return _fallback_questions(count)


def _fallback_questions(count: int) -> list[dict]:
    """Used only if Groq fails entirely, so the interview can still proceed."""
    bank = [
        {
            "topic": "OOP Basics",
            "question_text": "What is the difference between an abstract class and an interface in Java?",
            "ideal_points": ["Abstract classes can have state/constructors", "Interfaces define contracts", "A class can implement multiple interfaces"],
            "time_limit_seconds": 90,
        },
        {
            "topic": "Collections",
            "question_text": "Explain the difference between ArrayList and LinkedList, and when you'd use each.",
            "ideal_points": ["ArrayList: O(1) random access", "LinkedList: O(1) insert/delete at ends", "Use case guidance"],
            "time_limit_seconds": 90,
        },
        {
            "topic": "Exception Handling",
            "question_text": "What is the difference between checked and unchecked exceptions?",
            "ideal_points": ["Checked exceptions are compile-time enforced", "Unchecked extend RuntimeException", "Examples of each"],
            "time_limit_seconds": 90,
        },
        {
            "topic": "Multithreading",
            "question_text": "How do you achieve thread safety in Java?",
            "ideal_points": ["synchronized keyword", "java.util.concurrent classes", "Immutability/volatile/atomics"],
            "time_limit_seconds": 100,
        },
        {
            "topic": "Core Concepts",
            "question_text": "How do equals() and hashCode() work together, and why override both?",
            "ideal_points": ["hashCode determines bucket placement", "equals determines logical equality", "Contract between them"],
            "time_limit_seconds": 90,
        },
    ]
    return (bank * ((count // len(bank)) + 1))[:count]


# ---------------------------------------------------------------
# 2. Batch scoring - scores ALL answers in a session with ONE Groq call
# ---------------------------------------------------------------
def build_batch_scoring_prompt(items: list[dict]) -> str:
    blocks = []
    for i, item in enumerate(items):
        points = "\n".join(f"  - {p}" for p in item["ideal_points"])
        blocks.append(f"""ANSWER #{i}:
QUESTION: {item['question_text']}
KEY POINTS A STRONG ANSWER SHOULD COVER:
{points}
CANDIDATE'S TRANSCRIBED ANSWER: \"\"\"{item['transcript'] or '(No answer given / silence)'}\"\"\"
TIMING: {item['time_taken']}s out of {item['time_limit']}s allotted.
COMMUNICATION METRICS: {item['wpm']} words/min, {item['filler_count']} filler words ({item['filler_rate']}% of words)
""")

    joined = "\n".join(blocks)
    return f"""You are a strict but fair senior technical interviewer scoring MULTIPLE spoken answers
from ONE interview (transcribed from voice via Whisper, so minor grammar/punctuation noise from
speech-to-text should NOT be penalized).

{joined}

For EACH answer above (there are {len(items)} of them, indexed #0 to #{len(items) - 1}), score:
1. technicalScore: correctness/completeness of the explanation (0-10)
2. communicationScore: clarity, structure, fluency (0-10, factor in wpm/filler metrics)

Respond with ONLY a valid JSON object (required - must be an object, not a bare array), in
exactly this shape, with EXACTLY {len(items)} objects in the "results" array, in the SAME ORDER
as the answers above. Keep feedback to ONE sentence each, and AT MOST 3 missedConcepts each:
{{
  "results": [
    {{
      "technicalScore": <number 0-10>,
      "communicationScore": <number 0-10>,
      "missedConcepts": [<at most 3 short strings>],
      "feedback": "<ONE concise, actionable sentence>"
    }}
  ]
}}"""


def score_batch(items: list[dict]) -> list[dict]:
    """
    items: list of dicts, each with keys:
      question_text, ideal_points, transcript, time_taken, time_limit, wpm, filler_count, filler_rate
    Returns a list of score dicts in the SAME ORDER as items.
    """
    if not items:
        return []

    prompt = build_batch_scoring_prompt(items)

    try:
        raw_text = _call_groq(prompt, max_tokens=max(4096, 1000 * len(items)), temperature=0.2)
    except Exception as e:
        print("=" * 60)
        print("[groq_service] GROQ BATCH SCORING CALL FAILED")
        print("Error:", repr(e))
        print("=" * 60)
        return [_zero_score(f"Groq API call failed: {e}") for _ in items]

    return _safe_parse_batch_json(raw_text, expected_count=len(items))


def _safe_parse_batch_json(text: str, expected_count: int) -> list[dict]:
    try:
        data = json.loads(text)
        results_raw = data.get("results", [])
        if not isinstance(results_raw, list):
            raise ValueError("Expected 'results' to be a list")
        results = []
        for i in range(expected_count):
            if i < len(results_raw):
                item = results_raw[i]
                results.append({
                    "technicalScore": float(item.get("technicalScore", 0)),
                    "communicationScore": float(item.get("communicationScore", 0)),
                    "missedConcepts": item.get("missedConcepts", []),
                    "feedback": item.get("feedback", "No feedback generated."),
                })
            else:
                results.append(_zero_score("Groq returned fewer results than expected."))
        return results
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print("=" * 60)
        print("[groq_service] FAILED TO PARSE BATCH SCORING RESPONSE")
        print("Error:", e)
        print("Raw text received from Groq:")
        print(text)
        print("=" * 60)
        return [_zero_score("Could not parse AI evaluation for this answer.") for _ in range(expected_count)]


def _zero_score(feedback: str) -> dict:
    return {"technicalScore": 0.0, "communicationScore": 0.0, "missedConcepts": [], "feedback": feedback}
