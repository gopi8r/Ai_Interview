"""
Speech-to-Text service using OpenAI's open-source Whisper model, run LOCALLY
(no external API calls, no per-request cost). The model is loaded once at
process startup and reused for every request.

Requires ffmpeg to be installed on the system PATH.
"""
import tempfile
import os
import whisper

from app.config import settings

print(f"[whisper_service] Loading Whisper model '{settings.WHISPER_MODEL_SIZE}' ... "
      f"(first run will download the model, this can take a while)")
_model = whisper.load_model(settings.WHISPER_MODEL_SIZE)
print("[whisper_service] Whisper model loaded.")


def transcribe_audio(audio_bytes: bytes, filename_hint: str = "answer.webm") -> str:
    suffix = os.path.splitext(filename_hint)[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        result = _model.transcribe(tmp_path, fp16=False, language="en")
        return result.get("text", "").strip()
    finally:
        os.remove(tmp_path)
