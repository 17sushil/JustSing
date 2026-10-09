"""
JustSing Dynamic Voice-Adaptive Generator v0.6
TRUE audio-to-music: OpenRouter actually LISTENS to your voice and composes around it.

How it works (like Sora but for music):
1. Send your actual vocal audio (base64) to Gemini 2.5 Flash via OpenRouter (audio input model)
2. Gemini analyzes: melody contour, rhythm, dynamics, emotion, key, BPM, range, language, phrasing
3. Gemini generates a DETAILED musical prompt that describes perfect accompaniment for YOUR specific voice
4. That detailed prompt is sent to Lyria (google/lyria-3-pro-preview) via OpenRouter to generate music

Result: Every song gets UNIQUE music that truly follows your voice, not same prompt = same music.

This is 2-step via OpenRouter, costs ~$0.01 for analysis + $0.08 for music = $0.09/song
Free tier: $1 free credit = ~11 dynamic songs
"""
import base64
import json
import os
from pathlib import Path
import requests

from ..config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_SITE_URL, OPENROUTER_APP_NAME

def encode_audio_base64(audio_path: Path, max_size_mb=10):
    """Encode audio file to base64, trim if too large for API"""
    data = audio_path.read_bytes()
    # If >10MB, trim to first 60 seconds (approx)
    # For WAV 44.1k stereo, 10MB ~ 30 sec, so we need to be careful
    # We'll use the mono file which is smaller, and limit to 30 sec for analysis
    if len(data) > max_size_mb * 1024 * 1024:
        # Rough trim: for 44.1k mono 16-bit, 1 sec ~ 88KB, so 10MB ~ 113 sec, safe
        # But for safety, just take first 8MB
        data = data[:max_size_mb * 1024 * 1024]
    
    return base64.b64encode(data).decode('utf-8')

def analyze_voice_with_openrouter(audio_path: Path, analysis: dict, style: str):
    """
    Step 1: Send vocal audio to Gemini via OpenRouter for deep analysis.
    Returns detailed musical description.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY missing")

    # Use a model that supports audio input
    analyzer_model = "google/gemini-2.5-flash"  # Supports audio input, cheap and fast
    # Alternative: openai/gpt-4o-audio-preview, google/gemini-2.0-flash

    b64_audio = encode_audio_base64(audio_path, max_size_mb=8)
    
    # Determine format from file extension
    ext = audio_path.suffix.lower().lstrip('.')
    if ext not in ('wav', 'mp3', 'mp4', 'webm', 'ogg', 'flac', 'm4a'):
        ext = 'wav'

    # Build analysis prompt for Gemini
    bpm = analysis.get("bpm", 90)
    key = analysis.get("key", "C major")
    f0_mean = analysis.get("f0_mean_hz", 180)
    f0_min = analysis.get("f0_min_hz", 100)
    f0_max = analysis.get("f0_max_hz", 300)
    duration = analysis.get("duration_sec", 30)
    language = analysis.get("language", "unknown")

    system_prompt = f"""You are a professional music producer and vocal coach. Analyze this singing voice recording deeply.

We already detected:
- Key: {key}
- BPM: {bpm}
- Vocal range: {f0_min:.0f}-{f0_max:.0f}Hz, mean {f0_mean:.0f}Hz
- Duration: {duration:.1f}s
- Language: {language}
- Style requested: {style}

Now listen to the actual audio and describe:
1. Melody contour: Is it rising, falling, stepwise, leaps? Happy, sad, energetic, intimate?
2. Rhythm: Is singing on beat, laid back, syncopated, rubato?
3. Dynamics: Soft/loud, where are emotional peaks?
4. Emotion and mood: What feeling does this voice convey?
5. Phrasing: Where are breaths, pauses, long notes?
6. What kind of accompaniment would make this singer sound AMAZING? Be specific about instruments, chords, groove.

Then output a SINGLE detailed prompt for a music generation model (Lyria) to create the perfect instrumental backing track that FOLLOWS this voice. The prompt should be 1-2 sentences, specific, and include key, BPM, instruments, and how it should follow the vocal.

Format:
ANALYSIS: [your detailed analysis]
PROMPT: [single detailed prompt for Lyria, instrumental only, no vocals, include key {key} and {bpm:.0f} BPM and duration {int(duration)}s]

Be specific and make it UNIQUE to this voice — not generic.
"""

    payload = {
        "model": analyzer_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": system_prompt},
                    {"type": "input_audio", "input_audio": {"data": b64_audio, "format": ext}}
                ]
            }
        ],
        "temperature": 0.7,
        "max_tokens": 800,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_SITE_URL,
        "X-Title": OPENROUTER_APP_NAME,
    }

    print(f"[openrouter-dynamic] Step 1: Analyzing voice with {analyzer_model}, audio {len(b64_audio)//1024}KB base64, {key} {bpm} BPM")

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=120,
    )

    if resp.status_code != 200:
        err = resp.text[:1000]
        print(f"[openrouter-dynamic] Analysis failed {resp.status_code}: {err[:300]}")
        # Fallback to simple prompt if analysis fails
        raise RuntimeError(f"Voice analysis failed {resp.status_code}: {err[:300]}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except:
        content = str(data)[:1000]

    print(f"[openrouter-dynamic] Analysis result: {content[:500]}...")

    # Extract PROMPT: line
    prompt = None
    if "PROMPT:" in content:
        prompt = content.split("PROMPT:")[-1].strip().split("\n")[0].strip()
        # Remove quotes if present
        prompt = prompt.strip('"').strip("'")
    else:
        # Use last line or whole content as prompt, but ensure instrumental
        # Take last 200 chars or last sentence
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        # Find most detailed line
        prompt = max(lines, key=len) if lines else content[:200]
        if "instrumental" not in prompt.lower():
            prompt += f", instrumental, {key}, {bpm:.0f} BPM, no vocals"

    # Ensure key and BPM and duration are in prompt for Lyria
    if key.lower() not in prompt.lower():
        prompt += f", {key}"
    if f"{bpm:.0f}" not in prompt and f"{int(bpm)}" not in prompt:
        prompt += f", {bpm:.0f} BPM"
    if "instrumental" not in prompt.lower():
        prompt += ", instrumental only, no vocals"

    # Add unique hash to prevent caching
    file_hash = analysis.get("file_hash", "0000")
    prompt += f", track {file_hash[:4]}"

    print(f"[openrouter-dynamic] Generated adaptive prompt: {prompt[:300]}...")

    return prompt, content  # return both prompt and full analysis

def generate_music_with_openrouter_from_prompt(prompt: str, analysis: dict, out_path: Path):
    """Step 2: Send detailed adaptive prompt to Lyria via OpenRouter"""
    import json

    model = OPENROUTER_MODEL or "google/lyria-3-pro-preview"
    file_hash = analysis.get("file_hash", "0000")
    try:
        seed = int(file_hash[:6], 16) % 100000
    except:
        seed = 0

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["text", "audio"],
        "audio": {"format": "mp3"},
        "stream": True,
        "temperature": 0.85 + (seed % 15)/100.0,
        "seed": seed,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_SITE_URL,
        "X-Title": OPENROUTER_APP_NAME,
    }

    print(f"[openrouter-dynamic] Step 2: Generating music with {model}, seed {seed}")

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        stream=True,
        timeout=180,
    )

    if resp.status_code != 200:
        err = resp.text[:1000]
        raise RuntimeError(f"OpenRouter music failed {resp.status_code}: {err}")

    audio_chunks = []
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
        except:
            continue

    if not audio_chunks:
        raise RuntimeError("No audio chunks from Lyria — try different prompt or model")

    binary_data = b"".join([base64.b64decode(c) for c in audio_chunks])
    if len(binary_data) < 1000:
        raise RuntimeError(f"Audio too short: {len(binary_data)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(binary_data)
    print(f"[openrouter-dynamic] Saved {len(binary_data)} bytes to {out_path}")
    return out_path

def generate_with_openrouter_dynamic(vocal_path: Path, analysis: dict, out_path: Path, style="warm-acoustic"):
    """
    Main entry: TRUE dynamic voice-adaptive generation.
    Sends actual vocal audio to OpenRouter for analysis, then generates matching music.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY missing")

    # Step 1: Analyze voice deeply via audio input model
    try:
        adaptive_prompt, full_analysis = analyze_voice_with_openrouter(vocal_path, analysis, style)
    except Exception as e:
        print(f"[openrouter-dynamic] Analysis failed ({e}), using fallback prompt")
        # Fallback to old prompt builder
        from .generator_api import _build_prompt
        adaptive_prompt, _ = _build_prompt(analysis, style)
        full_analysis = f"Fallback: {e}"

    # Step 2: Generate music from adaptive prompt
    out_path = generate_music_with_openrouter_from_prompt(adaptive_prompt, analysis, out_path)

    # Save analysis for debugging / UI
    try:
        analysis_path = out_path.parent / "voice_analysis.txt"
        analysis_path.write_text(f"File hash: {analysis.get('file_hash')}\nBPM: {analysis.get('bpm')} Key: {analysis.get('key')}\nF0: {analysis.get('f0_mean_hz')}Hz\nStyle: {style}\n\nFull AI Analysis:\n{full_analysis}\n\nFinal Prompt:\n{adaptive_prompt}\n")
    except:
        pass

    return out_path
