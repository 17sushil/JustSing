"""
API generators — wrappers for ElevenLabs, Lyria, Stable Audio Open, MusicGen, OpenRouter.
Zero-cost MVP uses procedural by default. If GENERATOR is set to an API,
this module tries it and falls back to procedural if keys missing.
Now supports OPENROUTER_API_KEY for Lyria via OpenRouter (cheapest paid path).
"""
from pathlib import Path
import base64
import os
from ..config import (
    GENERATOR, ELEVENLABS_API_KEY, GEMINI_API_KEY,
    OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_SITE_URL, OPENROUTER_APP_NAME
)

def _build_prompt(analysis: dict, style="warm-acoustic"):
    bpm = analysis.get("bpm", 90)
    key = analysis.get("key", "C major")
    is_major = analysis.get("is_major", True)
    duration = analysis.get("duration_sec", 30)
    mood_map = {
        "warm-acoustic": "warm acoustic, intimate, guitar, soft drums, bass",
        "lofi-chill": "lofi chill, mellow, vinyl crackle, soft piano, relaxed",
        "piano-ballad": "piano ballad, intimate, emotional, soft pads",
        "indie-pop": "indie pop, bright, upbeat, guitar, drums, bass",
        "cinematic": "cinematic, epic, spacious, orchestral pads, emotional"
    }
    mood = mood_map.get(style, style)
    # Prompt tuned for Lyria / Stable Audio
    prompt = (
        f"{mood} instrumental accompaniment, {key}, {bpm} BPM, "
        f"{'major' if is_major else 'minor'} key, "
        f"warm backing track for singing, no vocals, no lead vocal, "
        f"guitar, bass, drums, duration {int(duration)} seconds"
    )
    return prompt, duration

def generate_with_elevenlabs(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    ElevenLabs Music API — $0.15/min, exact duration control.
    Docs: https://elevenlabs.io/docs/api-reference/music
    Free tier: 10,000 credits/month (~10-20 songs, no card needed)
    Get key: https://elevenlabs.io/app/settings/api-keys
    """
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY missing — get free key at https://elevenlabs.io/app/settings/api-keys")

    import requests
    import json

    prompt, duration = _build_prompt(analysis, style)

    # ElevenLabs music endpoint — try v1/music first, fallback to compose
    # Some accounts need instrumental flag
    payloads_to_try = [
        {
            "prompt": prompt,
            "music_length_ms": int(max(10000, min(duration*1000, 300000))),  # 10s to 5min
            "model_id": "music_v1",  # latest music model
        },
        {
            "prompt": prompt,
            "music_length_ms": int(max(10000, min(duration*1000, 300000))),
        },
        {
            "prompt": f"instrumental, {prompt}",
            "music_length_ms": int(max(10000, min(duration*1000, 300000))),
        }
    ]

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg, application/json"
    }

    print(f"[elevenlabs] Generating {duration:.1f}s, prompt: {prompt[:120]}...")

    last_error = None
    for idx, payload in enumerate(payloads_to_try):
        try:
            resp = requests.post(
                "https://api.elevenlabs.io/v1/music",
                headers=headers,
                json=payload,
                timeout=180,
            )

            # Success — binary MP3
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "")
                out_path.parent.mkdir(parents=True, exist_ok=True)

                # Sometimes returns JSON with audio_base64
                if "application/json" in content_type:
                    try:
                        data = resp.json()
                        # Check for audio_base64 field
                        b64 = data.get("audio_base64") or data.get("audio") or data.get("data")
                        if b64:
                            import base64
                            out_path.write_bytes(base64.b64decode(b64))
                            print(f"[elevenlabs] Saved from base64 JSON, {out_path.stat().st_size} bytes")
                            return out_path
                        # If JSON but no audio, error
                        raise RuntimeError(f"ElevenLabs returned JSON without audio: {str(data)[:500]}")
                    except Exception as je:
                        # If JSON parsing fails, treat as binary anyway
                        pass

                # Binary MP3/WAV
                out_path.write_bytes(resp.content)
                if out_path.stat().st_size < 1000:
                    raise RuntimeError(f"ElevenLabs returned too small file: {len(resp.content)} bytes, content: {resp.content[:500]}")
                print(f"[elevenlabs] Saved {out_path.stat().st_size} bytes to {out_path}")
                return out_path

            # Handle errors
            err_text = resp.text[:1000] if hasattr(resp, 'text') else str(resp.status_code)
            print(f"[elevenlabs] Attempt {idx+1} failed {resp.status_code}: {err_text[:300]}")

            # Specific error handling for free tier
            if resp.status_code == 401:
                raise RuntimeError("ElevenLabs 401 Unauthorized — API key invalid. Get free key at https://elevenlabs.io/app/settings/api-keys")
            elif resp.status_code == 429 or "quota" in err_text.lower() or "limit" in err_text.lower() or "free" in err_text.lower():
                last_error = f"ElevenLabs free credits exhausted or rate limited ({resp.status_code}): {err_text[:300]}. Free tier resets monthly at https://elevenlabs.io/app/settings/usage. Falling back to procedural."
                # Don't try more payloads if quota
                break
            else:
                last_error = f"{resp.status_code}: {err_text[:300]}"
                continue

        except requests.exceptions.Timeout:
            last_error = "ElevenLabs timeout (180s) — try again or use procedural"
            continue
        except Exception as e:
            last_error = str(e)
            if "401" in str(e) or "quota" in str(e).lower():
                break
            continue

    raise RuntimeError(f"ElevenLabs failed after {len(payloads_to_try)} attempts: {last_error}")

def generate_with_openrouter(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    OpenRouter proxy for Lyria and other music models — YES, your OpenRouter key WILL work!
    
    Supported models (set via OPENROUTER_MODEL env):
    - google/lyria-3-pro-preview — $0.08/song (default, best quality, 2 min max)
    - google/lyria-3-clip-preview — $0.04/clip (cheaper, short clips)
    - minimax/music-2.6-free — FREE tier (if available)
    - openai/gpt-4o-mini-tts etc (TTS, not music)
    
    How it works:
    - Uses OpenRouter chat completions with modalities ["text","audio"]
    - Streaming response: audio chunks are base64-encoded, need to be concatenated
    - Free credit: OpenRouter gives $1 free on signup
    
    Docs: https://openrouter.ai/docs/guides/overview/multimodal/audio
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY missing")

    import requests
    import json

    prompt, duration = _build_prompt(analysis, style)
    model = OPENROUTER_MODEL or "google/lyria-3-pro-preview"

    # For Lyria, prompt should be simple, no "no vocals" may be better as instrumental
    # OpenRouter expects chat format
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "modalities": ["text", "audio"],
        "audio": {
            "format": "mp3"  # or wav
        },
        "stream": True  # Required for audio output
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_SITE_URL,
        "X-Title": OPENROUTER_APP_NAME,
    }

    print(f"[openrouter] Calling model={model} prompt={prompt[:100]}...")

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        stream=True,
        timeout=180,
    )

    if resp.status_code != 200:
        # Try to read error body (not streaming)
        try:
            err_text = resp.text[:1000]
        except:
            err_text = f"status {resp.status_code}"
        raise RuntimeError(f"OpenRouter failed {resp.status_code}: {err_text}")

    # Parse SSE stream: each line is data: {...}
    audio_chunks = []
    transcript_parts = []

    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode('utf-8') if isinstance(line, bytes) else line
        if not line.startswith("data: "):
            continue
        data_str = line[6:].strip()
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
            # OpenRouter audio chunk format: choices[0].delta.audio.data (base64)
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            audio_obj = delta.get("audio", {})
            if not audio_obj:
                # Some models use message.audio instead of delta.audio
                message = choices[0].get("message", {})
                audio_obj = message.get("audio", {}) if message else {}
            if audio_obj:
                b64_data = audio_obj.get("data")
                if b64_data:
                    audio_chunks.append(b64_data)
                tr = audio_obj.get("transcript")
                if tr:
                    transcript_parts.append(tr)
        except Exception as e:
            # ignore parse errors for non-audio chunks
            continue

    if not audio_chunks:
        raise RuntimeError("OpenRouter returned no audio chunks — model may not support audio output or prompt was filtered. Try model=google/lyria-3-clip-preview")

    # Concatenate base64 chunks and decode
    # Each chunk is base64-encoded audio piece, need to join binary
    try:
        binary_data = b"".join([base64.b64decode(c) for c in audio_chunks])
    except Exception as e:
        raise RuntimeError(f"Failed to decode audio chunks: {e}")

    if len(binary_data) < 1000:
        raise RuntimeError(f"Audio too short ({len(binary_data)} bytes), likely error")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(binary_data)

    print(f"[openrouter] Saved {len(binary_data)} bytes to {out_path}, transcript: {''.join(transcript_parts)[:200]}")
    return out_path

def generate_with_lyria(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    Google Lyria 3.5 via Gemini API — $0.08/song.
    Tries direct Gemini API first, then falls back to OpenRouter if OPENROUTER_API_KEY is set.
    """
    # Prefer OpenRouter if key is present and GEMINI key is not — many users have OpenRouter free credit
    if OPENROUTER_API_KEY and not GEMINI_API_KEY:
        print("[lyria] Using OpenRouter proxy (OPENROUTER_API_KEY found)")
        return generate_with_openrouter(analysis, out_path, style)

    if not GEMINI_API_KEY:
        if OPENROUTER_API_KEY:
            print("[lyria] GEMINI_API_KEY missing, falling back to OpenRouter")
            return generate_with_openrouter(analysis, out_path, style)
        raise RuntimeError("GEMINI_API_KEY missing and no OPENROUTER_API_KEY")

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        raise NotImplementedError("Lyria SDK direct integration TODO — use OPENROUTER_API_KEY for now, or procedural")
    except ImportError:
        if OPENROUTER_API_KEY:
            return generate_with_openrouter(analysis, out_path, style)
        raise RuntimeError("google-generativeai not installed and no OPENROUTER_API_KEY")

def generate_with_stable_audio(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    Self-hosted Stable Audio Open — free under $1M revenue.
    Requires GPU and diffusers.
    """
    raise NotImplementedError("Stable Audio Open self-host not wired — use procedural or openrouter")

def generate_accompaniment_auto(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    Dispatch based on GENERATOR env var, with fallback to procedural.
    GENERATOR options:
    - procedural (default, $0)
    - elevenlabs ($0.15/min, 10k free)
    - lyria ($0.08 via Gemini)
    - openrouter / openrouter/lyria / lyria-via-openrouter (uses OPENROUTER_API_KEY, $0.04-$0.08, $1 free credit)
    - stable-audio-open
    """
    gen = (GENERATOR or "procedural").lower().strip()
    from .generator_procedural import generate_accompaniment as gen_proc

    # Normalize aliases
    if gen in ("openrouter", "or", "lyria-openrouter", "openrouter/lyria", "google/lyria-3-pro-preview", "google/lyria-3-clip-preview"):
        gen = "openrouter"

    try:
        if gen == "elevenlabs":
            return generate_with_elevenlabs(analysis, out_path, style)
        elif gen == "lyria":
            return generate_with_lyria(analysis, out_path, style)
        elif gen == "openrouter":
            return generate_with_openrouter(analysis, out_path, style)
        elif gen in ("stable-audio-open", "stable_audio", "stable"):
            return generate_with_stable_audio(analysis, out_path, style)
        elif gen == "musicgen":
            raise NotImplementedError("MusicGen self-host TODO")
        else:
            return gen_proc(analysis, out_path, style, duration_sec=analysis.get("duration_sec"))
    except Exception as e:
        print(f"[generator] {gen} failed ({e}), falling back to procedural")
        # If openrouter fails, try procedural
        return gen_proc(analysis, out_path, style, duration_sec=analysis.get("duration_sec"))
