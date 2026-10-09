"""
API generators — wrappers for ElevenLabs, Lyria, Stable Audio Open, MusicGen.
Zero-cost MVP uses procedural by default. If GENERATOR is set to an API,
this module tries it and falls back to procedural if keys missing.
"""
from pathlib import Path
from ..config import GENERATOR, ELEVENLABS_API_KEY, GEMINI_API_KEY

def generate_with_elevenlabs(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    ElevenLabs Music API — $0.15/min, exact duration control.
    Docs: elevenlabs.io/docs
    """
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY missing")
    import requests
    bpm = analysis.get("bpm", 90)
    key = analysis.get("key", "C major")
    is_major = analysis.get("is_major", True)
    duration = analysis.get("duration_sec", 30)
    mood = style
    prompt = f"{mood} instrumental, {key}, {bpm} BPM, { 'major' if is_major else 'minor'} key, warm accompaniment for singing, guitar, bass, drums, no vocals"
    # ElevenLabs Music endpoint (as of 2026)
    # POST https://api.elevenlabs.io/v1/music
    resp = requests.post(
        "https://api.elevenlabs.io/v1/music",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={
            "prompt": prompt,
            "music_length_ms": int(duration*1000),
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs failed {resp.status_code}: {resp.text[:500]}")
    # response is audio binary (mp3/wav) — save
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)
    return out_path

def generate_with_lyria(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    Google Lyria 3.5 via Gemini API — $0.08/song.
    Model: lyria-3.5 — see blueprint §5.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing")
    # Placeholder: real implementation uses google-generativeai SDK
    # pip install google-generativeai
    # For MVP, raise to trigger fallback unless SDK present
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        # Actual Lyria call pattern (subject to SDK updates):
        # model = genai.GenerativeModel("lyria-3.5")
        # result = model.generate_music(prompt=..., ...)
        # For now, not implemented — fallback
        raise NotImplementedError("Lyria SDK integration TODO — see blueprint §5, use procedural for now")
    except ImportError:
        raise RuntimeError("google-generativeai not installed")

def generate_with_stable_audio(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    Self-hosted Stable Audio Open — free under $1M revenue.
    Requires GPU and diffusers install.
    """
    try:
        # Placeholder for local pipeline
        # from diffusers import StableAudioPipeline etc.
        raise NotImplementedError("Stable Audio Open self-host not wired in this sandbox — use procedural")
    except Exception as e:
        raise RuntimeError(str(e))

def generate_accompaniment_auto(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    Dispatch based on GENERATOR env var, with fallback to procedural.
    """
    gen = GENERATOR
    # Lazy import procedural to avoid circular
    from .generator_procedural import generate_accompaniment as gen_proc

    try:
        if gen == "elevenlabs":
            return generate_with_elevenlabs(analysis, out_path, style)
        elif gen == "lyria":
            return generate_with_lyria(analysis, out_path, style)
        elif gen in ("stable-audio-open", "stable_audio", "stable"):
            return generate_with_stable_audio(analysis, out_path, style)
        elif gen == "musicgen":
            raise NotImplementedError("MusicGen self-host TODO")
        else:
            # procedural default
            return gen_proc(analysis, out_path, style, duration_sec=analysis.get("duration_sec"))
    except Exception as e:
        print(f"[generator] {gen} failed ({e}), falling back to procedural")
        return gen_proc(analysis, out_path, style, duration_sec=analysis.get("duration_sec"))
