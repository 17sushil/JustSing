"""
JustSing Dynamic Voice-Adaptive Generator v0.7 — TRUE alignment
- Step 1: Gemini listens to actual vocal audio via OpenRouter
- Step 2: Lyria generates music from adaptive prompt
- Step 3: Beat-warp alignment to vocal beats (librosa if available)
"""

import base64
import json
from pathlib import Path
import requests

from ..config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_SITE_URL, OPENROUTER_APP_NAME

def encode_audio_base64(audio_path: Path, max_size_mb=8):
    data = audio_path.read_bytes()
    if len(data) > max_size_mb * 1024 * 1024:
        data = data[:max_size_mb * 1024 * 1024]
    return base64.b64encode(data).decode('utf-8')

def analyze_voice_with_openrouter(audio_path: Path, analysis: dict, style: str):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY missing")

    analyzer_model = "google/gemini-2.5-flash"
    b64_audio = encode_audio_base64(audio_path, max_size_mb=8)
    ext = audio_path.suffix.lower().lstrip('.')
    if ext not in ('wav', 'mp3', 'mp4', 'webm', 'ogg', 'flac', 'm4a'):
        ext = 'wav'

    bpm = analysis.get("bpm", 90)
    key = analysis.get("key", "C major")
    f0_mean = analysis.get("f0_mean_hz", 180)
    f0_min = analysis.get("f0_min_hz", 100)
    f0_max = analysis.get("f0_max_hz", 300)
    duration = analysis.get("duration_sec", 30)
    language = analysis.get("language", "unknown")
    beat_times = analysis.get("beat_times", [])
    onset_times = analysis.get("onset_times", [])
    first_vocal = analysis.get("first_vocal_time", 0.0)

    beat_info = f"{len(beat_times)} beats detected, first vocal at {first_vocal:.1f}s" if beat_times else "no beat info"
    onset_info = f"{len(onset_times)} onsets" if onset_times else ""

    system_prompt = f"""You are a professional music producer and vocal coach. Analyze this singing voice recording deeply.

We already detected:
- Key: {key}
- BPM: {bpm}
- Vocal range: {f0_min:.0f}-{f0_max:.0f}Hz, mean {f0_mean:.0f}Hz
- Duration: {duration:.1f}s
- Language: {language}
- Style requested: {style}
- Timing: {beat_info}, {onset_info}

Now listen to the actual audio and describe:
1. Melody contour: Is it rising, falling, stepwise, leaps? Happy, sad, energetic, intimate?
2. Rhythm: Is singing on beat, laid back, syncopated, rubato? Where are strong beats?
3. Dynamics: Soft/loud, where are emotional peaks?
4. Emotion and mood: What feeling does this voice convey?
5. Phrasing: Where are breaths, pauses, long notes?
6. What kind of accompaniment would make this singer sound AMAZING? Be specific about instruments, chords, groove that LOCKS to their timing.

Then output a SINGLE detailed prompt for a music generation model (Lyria) to create the perfect instrumental backing track that FOLLOWS this voice RHYTHMICALLY. The prompt must include key, BPM, instruments, and emphasize rhythmic alignment to vocal.

Format:
ANALYSIS: [your detailed analysis]
PROMPT: [single detailed prompt for Lyria, instrumental only, no vocals, include key {key} and {bpm:.0f} BPM and duration {int(duration)}s, mention it should follow vocal timing]

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

    print(f"[openrouter-dynamic] Step 1: Analyzing voice with {analyzer_model}, audio {len(b64_audio)//1024}KB base64, {key} {bpm} BPM, {beat_info}")

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=120,
    )

    if resp.status_code != 200:
        err = resp.text[:1000]
        print(f"[openrouter-dynamic] Analysis failed {resp.status_code}: {err[:300]}")
        raise RuntimeError(f"Voice analysis failed {resp.status_code}: {err[:300]}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except:
        content = str(data)[:1000]

    print(f"[openrouter-dynamic] Analysis result: {content[:500]}...")

    prompt = None
    if "PROMPT:" in content:
        prompt = content.split("PROMPT:")[-1].strip().split("\n")[0].strip()
        prompt = prompt.strip('"').strip("'")
    else:
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        prompt = max(lines, key=len) if lines else content[:200]
        if "instrumental" not in prompt.lower():
            prompt += f", instrumental, {key}, {bpm:.0f} BPM, no vocals"

    if key.lower() not in prompt.lower():
        prompt += f", {key}"
    if f"{bpm:.0f}" not in prompt and f"{int(bpm)}" not in prompt:
        prompt += f", {bpm:.0f} BPM"
    if "instrumental" not in prompt.lower():
        prompt += ", instrumental only, no vocals"

    file_hash = analysis.get("file_hash", "0000")
    prompt += f", track {file_hash[:4]}, locked to vocal rhythm"

    print(f"[openrouter-dynamic] Generated adaptive prompt: {prompt[:300]}...")

    return prompt, content

def generate_music_with_openrouter_from_prompt(prompt: str, analysis: dict, out_path: Path):
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
    # Write mp3 temp then convert to wav
    tmp_mp3 = out_path.parent / (out_path.stem + ".mp3")
    tmp_mp3.write_bytes(binary_data)
    
    # Convert to wav via ffmpeg (ensure_wav from generator_api)
    try:
        from .generator_api import ensure_wav, align_accompaniment_to_vocal_beats
        ensure_wav(tmp_mp3, out_path)
        try:
            tmp_mp3.unlink()
        except:
            pass
        # Align to vocal beats
        align_accompaniment_to_vocal_beats(out_path, analysis)
    except Exception as e:
        print(f"[openrouter-dynamic] Conversion/alignment failed {e}, saving mp3 as wav path")
        # Fallback: just write binary as is (will be converted later)
        out_path.write_bytes(binary_data)
    
    print(f"[openrouter-dynamic] Saved {len(binary_data)} bytes to {out_path}")
    return out_path

def generate_with_openrouter_dynamic(vocal_path: Path, analysis: dict, out_path: Path, style="warm-acoustic"):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY missing")

    try:
        adaptive_prompt, full_analysis = analyze_voice_with_openrouter(vocal_path, analysis, style)
    except Exception as e:
        print(f"[openrouter-dynamic] Analysis failed ({e}), using fallback prompt")
        from .generator_api import _build_prompt
        adaptive_prompt, _ = _build_prompt(analysis, style)
        full_analysis = f"Fallback: {e}"

    out_path = generate_music_with_openrouter_from_prompt(adaptive_prompt, analysis, out_path)

    try:
        analysis_path = out_path.parent / "voice_analysis.txt"
        analysis_path.write_text(f"File hash: {analysis.get('file_hash')}\nBPM: {analysis.get('bpm')} Key: {analysis.get('key')}\nF0: {analysis.get('f0_mean_hz')}Hz\nBeats: {len(analysis.get('beat_times', []))} First vocal: {analysis.get('first_vocal_time')}s\nStyle: {style}\n\nFull AI Analysis:\n{full_analysis}\n\nFinal Prompt:\n{adaptive_prompt}\n")
    except:
        pass

    return out_path
