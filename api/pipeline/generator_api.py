"""
API generators — wrappers for ElevenLabs, Lyria, Stable Audio Open, MusicGen, OpenRouter.
FIXED v0.5: OpenRouter now truly adapts to singer's voice, not same music every time.
"""
from pathlib import Path
import base64
import hashlib
import random
from ..config import (
    GENERATOR, ELEVENLABS_API_KEY, GEMINI_API_KEY,
    OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_SITE_URL, OPENROUTER_APP_NAME
)

def _build_prompt(analysis: dict, style="warm-acoustic"):
    """
    FIXED v0.5: Prompt now truly adapts to singer's voice + unique per song.
    Before: only key/BPM — so same key/BPM = same music.
    Now: includes vocal range, energy, language, lyrics, hash for uniqueness.
    """
    bpm = analysis.get("bpm", 90)
    key = analysis.get("key", "C major")
    is_major = analysis.get("is_major", True)
    duration = analysis.get("duration_sec", 30)
    f0_mean = analysis.get("f0_mean_hz", 180)
    f0_min = analysis.get("f0_min_hz", 100)
    f0_max = analysis.get("f0_max_hz", 300)
    file_hash = analysis.get("file_hash", "00000000")
    language = analysis.get("language", "unknown")
    lyrics = analysis.get("lyrics_preview", "")[:100]
    midi_min = analysis.get("midi_min", 60)
    midi_max = analysis.get("midi_max", 72)

    # Determine voice type for adaptive accompaniment
    if f0_mean > 300:
        voice_type = "high soprano voice, bright and airy"
        acc_adapt = "low warm accompaniment, deep bass, soft pads, leave space for high voice"
    elif f0_mean > 220:
        voice_type = "mid-high voice, clear and expressive"
        acc_adapt = "balanced accompaniment, mid-range guitar and piano, gentle"
    elif f0_mean > 150:
        voice_type = "mid-range voice, warm and natural"
        acc_adapt = "warm accompaniment that complements mid voice, not overpowering"
    else:
        voice_type = "low voice, deep and rich"
        acc_adapt = "higher bright accompaniment, light guitar, airy pads to lift low voice"

    # Determine energy from range
    vocal_range = f0_max - f0_min
    if vocal_range > 200:
        energy = "dynamic and expressive with wide range"
    elif vocal_range > 100:
        energy = "expressive with moderate range"
    else:
        energy = "intimate and gentle, narrow range"

    mood_map = {
        "warm-acoustic": "warm acoustic, intimate, fingerpicked guitar, soft drums, warm bass",
        "lofi-chill": "lofi chill, mellow, vinyl crackle, soft piano, relaxed, jazzy",
        "piano-ballad": "piano ballad, intimate, emotional, soft pads, minimal",
        "indie-pop": "indie pop, bright, upbeat, clean guitar, punchy drums, bouncy bass",
        "cinematic": "cinematic, epic, spacious, orchestral pads, emotional, atmospheric"
    }
    mood = mood_map.get(style, style)

    # Create UNIQUE variation per song using file_hash
    # Use hash to pick from variation phrases so different uploads get different music
    variations = [
        "with subtle variations and gentle dynamics",
        "with evolving chords and soft build",
        "with intimate verses and warm chorus",
        "with delicate arpeggios and spacious feel",
        "with groovy bassline and soft percussion",
        "with dreamy pads and light guitar",
        "with rhythmic pulse and warm harmony",
        "with organic feel and natural dynamics"
    ]
    try:
        var_idx = int(file_hash[:2], 16) % len(variations)
        variation_phrase = variations[var_idx]
    except:
        variation_phrase = "with natural dynamics"

    # Build prompt that is UNIQUE and ADAPTIVE
    # Include hash fragment for uniqueness (Lyria will treat it as variation hint)
    prompt = (
        f"{mood} instrumental backing track, {variation_phrase}, "
        f"{key}, {bpm:.0f} BPM, {'major' if is_major else 'minor'} key, "
        f"for {voice_type} ({energy}), "
        f"vocal range {f0_min:.0f}-{f0_max:.0f}Hz, mean {f0_mean:.0f}Hz, "
        f"{acc_adapt}, "
        f"no vocals, no lead vocal, instrumental only, "
        f"guitar, bass, drums, piano, duration {int(duration)} seconds, "
        f"track {file_hash[:4]}"  # unique ID so Lyria doesn't cache same music
    )

    # If we have lyrics/language, include for mood (but keep instrumental)
    if language != "unknown" and language != "":
        prompt += f", {language} song mood"
    if lyrics:
        # Use first few words for mood, not for singing
        prompt += f", mood inspired by: {lyrics[:40]}"

    print(f"[prompt] {prompt[:200]}... (hash {file_hash}, voice {f0_mean:.0f}Hz {voice_type})")
    return prompt, duration

def generate_with_elevenlabs(analysis: dict, out_path: Path, style="warm-acoustic"):
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY missing — get free key at https://elevenlabs.io/app/settings/api-keys")
    import requests
    prompt, duration = _build_prompt(analysis, style)
    payloads_to_try = [
        {"prompt": prompt, "music_length_ms": int(max(10000, min(duration*1000, 300000))), "model_id": "music_v1"},
        {"prompt": prompt, "music_length_ms": int(max(10000, min(duration*1000, 300000)))},
        {"prompt": f"instrumental, {prompt}", "music_length_ms": int(max(10000, min(duration*1000, 300000)))},
    ]
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg, application/json"}
    print(f"[elevenlabs] Generating {duration:.1f}s, prompt: {prompt[:120]}...")
    last_error = None
    for idx, payload in enumerate(payloads_to_try):
        try:
            resp = requests.post("https://api.elevenlabs.io/v1/music", headers=headers, json=payload, timeout=180)
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if "application/json" in content_type:
                    try:
                        data = resp.json()
                        b64 = data.get("audio_base64") or data.get("audio") or data.get("data")
                        if b64:
                            out_path.write_bytes(base64.b64decode(b64))
                            print(f"[elevenlabs] Saved from base64 JSON, {out_path.stat().st_size} bytes")
                            return out_path
                    except:
                        pass
                out_path.write_bytes(resp.content)
                if out_path.stat().st_size < 1000:
                    raise RuntimeError(f"Too small: {len(resp.content)}")
                print(f"[elevenlabs] Saved {out_path.stat().st_size} bytes")
                return out_path
            err_text = resp.text[:1000] if hasattr(resp, 'text') else str(resp.status_code)
            print(f"[elevenlabs] Attempt {idx+1} failed {resp.status_code}: {err_text[:300]}")
            if resp.status_code == 401:
                raise RuntimeError("ElevenLabs 401 Unauthorized — invalid key")
            elif resp.status_code == 429 or "quota" in err_text.lower() or "limit" in err_text.lower():
                last_error = f"Quota exhausted: {err_text[:300]}"
                break
            else:
                last_error = f"{resp.status_code}: {err_text[:300]}"
        except Exception as e:
            last_error = str(e)
            if "401" in str(e) or "quota" in str(e).lower():
                break
    raise RuntimeError(f"ElevenLabs failed: {last_error}")

def generate_with_openrouter(analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    FIXED v0.5: Now truly adaptive — prompt includes vocal range, voice type, hash for uniqueness.
    Before: same key/BPM = same music. Now: every song gets unique music that fits voice.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY missing")

    import requests
    import json

    prompt, duration = _build_prompt(analysis, style)
    model = OPENROUTER_MODEL or "google/lyria-3-pro-preview"
    file_hash = analysis.get("file_hash", "0000")

    # Use hash as seed for variation
    try:
        seed = int(file_hash[:6], 16) % 100000
    except:
        seed = random.randint(0, 100000)

    # For OpenRouter, add temperature and seed for variation (if supported)
    # Lyria models may ignore temperature, but we include for future models
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "modalities": ["text", "audio"],
        "audio": {
            "format": "mp3"
        },
        "stream": True,
        "temperature": 0.8 + (seed % 20)/100.0,  # 0.8-0.99 varied per song
        "seed": seed,  # for models that support seed
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_SITE_URL,
        "X-Title": OPENROUTER_APP_NAME,
    }

    print(f"[openrouter] Model={model} BPM={analysis.get('bpm')} Key={analysis.get('key')} F0={analysis.get('f0_mean_hz')} Hash={file_hash} Seed={seed}")
    print(f"[openrouter] Prompt: {prompt[:250]}...")

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        stream=True,
        timeout=180,
    )

    if resp.status_code != 200:
        try:
            err_text = resp.text[:1000]
        except:
            err_text = f"status {resp.status_code}"
        raise RuntimeError(f"OpenRouter failed {resp.status_code}: {err_text}")

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
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            audio_obj = delta.get("audio", {})
            if not audio_obj:
                message = choices[0].get("message", {})
                audio_obj = message.get("audio", {}) if message else {}
            if audio_obj:
                b64_data = audio_obj.get("data")
                if b64_data:
                    audio_chunks.append(b64_data)
                tr = audio_obj.get("transcript")
                if tr:
                    transcript_parts.append(tr)
        except:
            continue

    if not audio_chunks:
        raise RuntimeError("OpenRouter returned no audio chunks — try model=google/lyria-3-clip-preview or check prompt")

    try:
        binary_data = b"".join([base64.b64decode(c) for c in audio_chunks])
    except Exception as e:
        raise RuntimeError(f"Failed to decode audio: {e}")

    if len(binary_data) < 1000:
        raise RuntimeError(f"Audio too short ({len(binary_data)} bytes)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(binary_data)
    print(f"[openrouter] Saved {len(binary_data)} bytes to {out_path}, hash {file_hash}, seed {seed}")
    return out_path

def generate_with_lyria(analysis: dict, out_path: Path, style="warm-acoustic"):
    if OPENROUTER_API_KEY and not GEMINI_API_KEY:
        return generate_with_openrouter(analysis, out_path, style)
    if not GEMINI_API_KEY:
        if OPENROUTER_API_KEY:
            return generate_with_openrouter(analysis, out_path, style)
        raise RuntimeError("GEMINI_API_KEY missing and no OPENROUTER_API_KEY")
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        raise NotImplementedError("Lyria direct TODO — use OPENROUTER_API_KEY")
    except ImportError:
        if OPENROUTER_API_KEY:
            return generate_with_openrouter(analysis, out_path, style)
        raise RuntimeError("google-generativeai not installed")

def generate_with_stable_audio(analysis: dict, out_path: Path, style="warm-acoustic"):
    raise NotImplementedError("Stable Audio self-host not wired")

def generate_accompaniment_auto(analysis: dict, out_path: Path, style="warm-acoustic", vocal_path: Path = None):
    """
    FIXED v0.6: Now supports TRUE dynamic voice-adaptive via openrouter-dynamic
    - procedural: $0, varied per song via hash seed
    - openrouter: prompt-based adaptive (key/BPM/range + hash variation)
    - openrouter-dynamic / dynamic: TRUE audio-to-music, OpenRouter LISTENS to voice (2-step: analyze voice via Gemini audio input, then generate music via Lyria)
    """
    gen = (GENERATOR or "procedural").lower().strip()
    from .generator_procedural import generate_accompaniment as gen_proc

    # Normalize aliases
    if gen in ("openrouter", "or", "lyria-openrouter", "openrouter/lyria", "google/lyria-3-pro-preview", "google/lyria-3-clip-preview"):
        gen = "openrouter"
    if gen in ("openrouter-dynamic", "dynamic", "or-dynamic", "sora", "voice-adaptive", "audio-to-music"):
        gen = "openrouter-dynamic"

    try:
        if gen == "elevenlabs":
            return generate_with_elevenlabs(analysis, out_path, style)
        elif gen == "lyria":
            return generate_with_lyria(analysis, out_path, style)
        elif gen == "openrouter":
            return generate_with_openrouter(analysis, out_path, style)
        elif gen == "openrouter-dynamic":
            # TRUE dynamic: needs vocal_path
            if vocal_path is None:
                print("[generator] openrouter-dynamic needs vocal_path, falling back to openrouter prompt-based")
                return generate_with_openrouter(analysis, out_path, style)
            # Import dynamic module
            from .generator_openrouter_dynamic import generate_with_openrouter_dynamic
            return generate_with_openrouter_dynamic(vocal_path, analysis, out_path, style)
        elif gen in ("stable-audio-open", "stable_audio", "stable"):
            return generate_with_stable_audio(analysis, out_path, style)
        elif gen == "musicgen":
            raise NotImplementedError("MusicGen TODO")
        else:
            return gen_proc(analysis, out_path, style, duration_sec=analysis.get("duration_sec"))
    except Exception as e:
        print(f"[generator] {gen} failed ({e}), falling back to procedural (which now varies per song)")
        return gen_proc(analysis, out_path, style, duration_sec=analysis.get("duration_sec"))
