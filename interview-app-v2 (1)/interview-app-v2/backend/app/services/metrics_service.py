"""
Deterministic communication metrics computed from transcript + timing.
"""
import re

FILLER_REGEX = re.compile(
    r"\b(um+|uh+|like|you know|actually|basically|so yeah|kind of|sort of)\b",
    re.IGNORECASE,
)


def compute_metrics(transcript: str, time_taken_seconds: int) -> dict:
    words = re.findall(r"\S+", transcript or "")
    word_count = len(words)
    minutes = max(time_taken_seconds / 60, 0.05)
    wpm = round(word_count / minutes)

    filler_matches = FILLER_REGEX.findall(transcript or "")
    filler_count = len(filler_matches)
    filler_rate = round((filler_count / word_count) * 100, 1) if word_count else 0.0

    return {
        "word_count": word_count,
        "wpm": wpm,
        "filler_word_count": filler_count,
        "filler_rate_percent": filler_rate,
    }
