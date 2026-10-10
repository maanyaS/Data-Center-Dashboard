"""Stretch: ElevenLabs text-to-speech for the community brief. One call -> MP3 bytes."""
import os
import re

import requests


def tts(text):
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        return None
    voice = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    clean = re.sub(r"\s*\[(F\d+|R\d+|EST)\]", "", text)  # don't read citation tags aloud
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": clean, "model_id": "eleven_multilingual_v2"},
        timeout=60,
    )
    r.raise_for_status()
    return r.content
