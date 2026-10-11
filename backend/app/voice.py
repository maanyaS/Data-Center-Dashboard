"""Stretch: ElevenLabs text-to-speech for the community brief. One call -> MP3 bytes."""
import os
import re

import requests


def tts(text):
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        return None
    voice = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")   # "Sarah", a default voice (free plan can use it)
    clean = re.sub(r"\s*\[[A-Z]+\d*\]", "", text)  # don't read citation tags aloud
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": clean, "model_id": os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")},
        timeout=30,
    )
    r.raise_for_status()
    return r.content
