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
    r.raise_for_status()
    _cache[ck] = r.content
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return r.content
