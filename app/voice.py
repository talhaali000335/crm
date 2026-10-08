import os, uuid, requests
from django.conf import settings

def synthesize(text):
    """ElevenLabs TTS -> saves mp3, returns media URL. Returns '' if no key/failure
    (the UI then falls back to free browser speech synthesis)."""
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        return ""
    voice = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    try:
        r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                          headers={"xi-api-key": key}, timeout=60,
                          json={"text": text[:2500], "model_id": "eleven_multilingual_v2"})
        r.raise_for_status()
        d = settings.MEDIA_ROOT / "calls"; d.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.mp3"
        (d / name).write_bytes(r.content)
        return f"{settings.MEDIA_URL}calls/{name}"
    except Exception:
        return ""
