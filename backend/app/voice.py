"""ElevenLabs text-to-speech for the briefs. One call -> MP3 bytes.

Two built-in voices (the free plan can use these; "library" voices need a paid plan):
community brief -> Sarah, developer brief -> George. Clips are cached in memory so replays cost no credits.
"""
import hashlib
import os
import re
from collections import OrderedDict

import requests

VOICES = {
    "community": lambda: os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),      # Sarah
    "developer": lambda: os.getenv("ELEVENLABS_DEV_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"),  # George
}
_cache = OrderedDict()   # (voice, text hash) -> mp3 bytes; last 50 clips
CACHE_SIZE = 50
ENV_NAME = {"community": "ELEVENLABS_VOICE_ID", "developer": "ELEVENLABS_DEV_VOICE_ID"}


class VoiceError(Exception):
    """ElevenLabs refused the request; the message says why in plain words (safe to show users)."""


def explain(r, who, voice):
    """Turn an ElevenLabs error response into a short reason."""
    try:
        d = r.json().get("detail") or {}
    except ValueError:
        d = {}
    status = (d.get("status") or "") if isinstance(d, dict) else ""
    message = (d.get("message") if isinstance(d, dict) else str(d)) or r.reason
    print(f"[voice] ElevenLabs {r.status_code} {status}: {message}")
    if status == "quota_exceeded":
        return "The ElevenLabs credits for this month are used up."
    if r.status_code == 401 or status in ("invalid_api_key", "missing_permissions"):
        return f"ElevenLabs rejected the API key ({status or r.status_code}). Check ELEVENLABS_API_KEY."
    if status == "detected_unusual_activity":
        return "ElevenLabs paused free-plan access for this key (unusual activity, often a VPN or shared IP)."
    if "voice" in status or "voice" in message.lower() or r.status_code in (402, 404):
        return (f"The {who} voice ({voice}) isn't available on this ElevenLabs plan. "
                f"Remove {ENV_NAME[who]} from backend/.env or set it to a default voice.")
    return f"ElevenLabs error {r.status_code}: {message}"


def tts(text, who="community"):
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        return None
    voice = VOICES[who]()
    clean = re.sub(r"\s*\[[A-Z]+\d*\]", "", text)  # don't read citation tags aloud
    ck = (voice, hashlib.sha256(clean.encode()).hexdigest())
    if ck in _cache:
        _cache.move_to_end(ck)
        return _cache[ck]
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        # Flash model: fast and about half the credits per character
        json={"text": clean, "model_id": os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")},
        timeout=30,
    )
    if not r.ok:
        raise VoiceError(explain(r, who, voice))
    _cache[ck] = r.content
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return r.content
