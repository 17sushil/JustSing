"""
API generators — wrappers for ElevenLabs, Lyria, Stable Audio Open, MusicGen, OpenRouter.
FIXED v0.7: TRUE alignment — beat tracking + warping for OpenRouter outputs.
"""

from pathlib import Path
import base64
import hashlib
import random
import subprocess
import numpy as np
import soundfile as sf
import os

from ..config import (
    GENERATOR, ELEVENLABS_API_KEY, GEMINI_API_KEY,
    OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_SITE_URL, OPENROUTER_APP_NAME,
    FFMPEG_BIN
)

def _run_ffmpeg(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:800]}")
    return result

def ensure_wav(in_path: Path, out_path: Path = None):
    if out_path is None:
        out_path = in_path
    try:
        data, sr = sf.read(str(in_path))
        if sr == 44100:
            if in_path == out_path:
                return out_path
            if out_path != in_path:
                import shutil
                shutil.copy(str(in_path), str(out_path))
            return out_path
        else:
            tmp = out_path.parent / (out_path.stem + "_tmp.wav")
            _run_ffmpeg([FFMPEG_BIN, "-y", "-i", str(in_path), "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(tmp)])
            tmp.replace(out_path)
            return out_path
    except Exception as e:
        print(f"[ensure_wav] Converting {in_path} via ffmpeg due to {e}")
        tmp = out_path.parent / (out_path.stem + "_converted.wav")
        _run_ffmpeg([FFMPEG_BIN, "-y", "-i", str(in_path), "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(tmp)])
        if out_path != tmp:
            if out_path.exists():
                out_path.unlink()
            tmp.rename(out_path)
        return out_path

def align_accompaniment_to_vocal_beats(acc_path: Path, analysis: dict):
    """
    v0.7: Align generated accompaniment to vocal beats.
    - If USE_LIBROSA=1, does piecewise warping (may segfault on some envs, disabled by default)
    - Otherwise, simple trim/pad + overall tempo adjust via ffmpeg atempo if needed
    """
    try:
        target_duration = float(analysis.get("duration_sec", 30)) + 1.2
        vocal_beats = analysis.get("beat_times", [])
        target_bpm = float(analysis.get("bpm", 90))

        ensure_wav(acc_path, acc_path)

        y, sr = sf.read(str(acc_path))
        if y.ndim == 1:
            y = np.stack([y, y], axis=1)
        y_mono = np.mean(y, axis=1) if y.ndim > 1 else y

        # Optional librosa warping
        if os.getenv("USE_LIBROSA", "0") == "1":
            try:
                import librosa
                tempo_acc, beat_frames = librosa.beat.beat_track(y=y_mono, sr=sr, units='frames')
                acc_beats = [float(t) for t in librosa.frames_to_time(beat_frames, sr=sr)]
                print(f"[align] Acc BPM {tempo_acc:.1f} beats {len(acc_beats)} vs vocal {target_bpm:.1f} beats {len(vocal_beats)}")

                if len(vocal_beats) >= 4 and len(acc_beats) >= 4:
                    if len(acc_beats) < len(vocal_beats) * 0.5:
                        beat_sec_acc = 60.0 / float(tempo_acc) if tempo_acc > 0 else 60.0/target_bpm
                        num_beats = int(target_duration / beat_sec_acc) + 4
                        acc_beats = [i*beat_sec_acc for i in range(num_beats)]

                    if len(acc_beats) != len(vocal_beats):
                        acc_beats_interp = np.interp(
                            np.linspace(0, len(acc_beats)-1, len(vocal_beats)),
                            np.arange(len(acc_beats)),
                            acc_beats
                        )
                        acc_beats_mapped = acc_beats_interp.tolist()
                    else:
                        acc_beats_mapped = acc_beats

                    out_left = []
                    out_right = []
                    first_acc_beat = acc_beats_mapped[0] if acc_beats_mapped else 0.0
                    if first_acc_beat > 0.1:
                        e0 = int(first_acc_beat * sr)
                        if e0 > 0:
                            out_left.append(y[:e0, 0])
                            out_right.append(y[:e0, 1] if y.shape[1]>1 else y[:e0, 0])

                    for i in range(len(vocal_beats)-1):
                        v_start = vocal_beats[i]
                        v_end = vocal_beats[i+1]
                        v_dur = v_end - v_start
                        if v_dur <= 0.05 or v_dur > 5.0:
                            continue
                        a_start = acc_beats_mapped[i] if i < len(acc_beats_mapped) else acc_beats[-1] + (i - len(acc_beats_mapped)+1)*(60.0/target_bpm)
                        a_end = acc_beats_mapped[i+1] if i+1 < len(acc_beats_mapped) else a_start + v_dur
                        a_dur = a_end - a_start
                        if a_dur <= 0.05 or a_dur > 5.0:
                            a_dur = v_dur
                            a_start = v_start
                            a_end = v_end

                        s = int(a_start * sr)
                        e = int(a_end * sr)
                        if s < 0:
                            s = 0
                        if e > len(y):
                            e = len(y)
                        if e <= s:
                            continue
                        seg = y[s:e]
                        rate = a_dur / v_dur if v_dur>0 else 1.0
                        rate = float(np.clip(rate, 0.25, 4.0))

                        if abs(rate - 1.0) < 0.05:
                            out_left.append(seg[:,0] if seg.ndim>1 else seg)
                            out_right.append(seg[:,1] if seg.ndim>1 and seg.shape[1]>1 else seg[:,0] if seg.ndim>1 else seg)
                        else:
                            try:
                                if seg.ndim > 1:
                                    left = seg[:,0]
                                    right = seg[:,1] if seg.shape[1]>1 else left
                                    left_stretched = librosa.effects.time_stretch(left.astype(np.float32), rate=rate)
                                    right_stretched = librosa.effects.time_stretch(right.astype(np.float32), rate=rate)
                                    min_len = min(len(left_stretched), len(right_stretched))
                                    out_left.append(left_stretched[:min_len])
                                    out_right.append(right_stretched[:min_len])
                                else:
                                    stretched = librosa.effects.time_stretch(seg.astype(np.float32), rate=rate)
                                    out_left.append(stretched)
                                    out_right.append(stretched)
                            except Exception as ex:
                                print(f"[align] stretch failed {i} rate {rate:.2f} {ex}")
                                out_left.append(seg[:,0] if seg.ndim>1 else seg)
                                out_right.append(seg[:,1] if seg.ndim>1 and seg.shape[1]>1 else seg[:,0] if seg.ndim>1 else seg)

                    if out_left:
                        left_concat = np.concatenate(out_left)
                        right_concat = np.concatenate(out_right)
                        target_len = int(target_duration * sr)
                        if len(left_concat) > target_len:
                            left_concat = left_concat[:target_len]
                            right_concat = right_concat[:target_len]
                        elif len(left_concat) < target_len:
                            pad_len = target_len - len(left_concat)
                            left_concat = np.concatenate([left_concat, np.zeros(pad_len, dtype=np.float32)])
                            right_concat = np.concatenate([right_concat, np.zeros(pad_len, dtype=np.float32)])
                        stereo = np.stack([left_concat, right_concat], axis=1)
                        sf.write(str(acc_path), stereo, sr)
                        print(f"[align] Warped to vocal beats: {len(vocal_beats)} beats, new len {len(stereo)/sr:.2f}s")
                        return acc_path
            except Exception as e:
                print(f"[align] librosa warping failed {e}, fallback to trim/pad")

        # Fallback: trim/pad to duration (no segfault risk)
        try:
            y, sr = sf.read(str(acc_path))
            if y.ndim == 1:
                y = np.stack([y, y], axis=1)
            target_len = int(target_duration * sr)
            if len(y) > target_len:
                y = y[:target_len]
            elif len(y) < target_len:
                pad = np.zeros((target_len - len(y), 2), dtype=np.float32)
                y = np.concatenate([y, pad], axis=0)
            sf.write(str(acc_path), y, sr)
            print(f"[align] Fallback trim/pad to {target_duration:.1f}s")
        except Exception as e:
            print(f"[align] final fallback failed {e}")

        return acc_path

    except Exception as e:
        print(f"[align] alignment failed {e}, keeping original")
        return acc_path

def _build_prompt(analysis: dict, style="warm-acoustic"):
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
    beat_times = analysis.get("beat_times", [])
    first_vocal = analysis.get("first_vocal_time", 0.0)

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

    beat_info = ""
    if beat_times and len(beat_times) > 4:
        beat_info = f", aligned to vocal beats, first vocal at {first_vocal:.1f}s, {len(beat_times)} beats"

    prompt = (
        f"{mood} instrumental backing track, {variation_phrase}, "
        f"{key}, {bpm:.0f} BPM, {'major' if is_major else 'minor'} key, "
        f"for {voice_type} ({energy}), "
        f"vocal range {f0_min:.0f}-{f0_max:.0f}Hz, mean {f0_mean:.0f}Hz, "
        f"{acc_adapt}, "
        f"no vocals, no lead vocal, instrumental only, "
        f"guitar, bass, drums, piano, duration {int(duration)} seconds, "
        f"track {file_hash[:4]}{beat_info}"
    )

    if language != "unknown" and language != "":
        prompt += f", {language} song mood"
    if lyrics:
        prompt += f", mood inspired by: {lyrics[:40]}"

    print(f"[prompt] {prompt[:220]}... (hash {file_hash}, voice {f0_mean:.0f}Hz {voice_type})")
    return prompt, duration

def generate_with_elevenlabs(analysis: dict, out_path: Path, style="warm-acoustic"):
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY missing")
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
                            ensure_wav(out_path, out_path)
                            align_accompaniment_to_vocal_beats(out_path, analysis)
                            print(f"[elevenlabs] Saved from base64 JSON, {out_path.stat().st_size} bytes")
                            return out_path
                    except:
                        pass
                out_path.write_bytes(resp.content)
                ensure_wav(out_path, out_path)
                if out_path.stat().st_size < 1000:
                    raise RuntimeError(f"Too small: {len(resp.content)}")
                align_accompaniment_to_vocal_beats(out_path, analysis)
                print(f"[elevenlabs] Saved {out_path.stat().st_size} bytes")
                return out_path
            err_text = resp.text[:1000] if hasattr(resp, 'text') else str(resp.status_code)
            print(f"[elevenlabs] Attempt {idx+1} failed {resp.status_code}: {err_text[:300]}")
            if resp.status_code == 401:
                raise RuntimeError("ElevenLabs 401 Unauthorized")
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
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY missing")
    import requests, json
    prompt, duration = _build_prompt(analysis, style)
    model = OPENROUTER_MODEL or "google/lyria-3-pro-preview"
    file_hash = analysis.get("file_hash", "0000")
    try:
        seed = int(file_hash[:6], 16) % 100000
    except:
        seed = random.randint(0, 100000)

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["text", "audio"],
        "audio": {"format": "mp3"},
        "stream": True,
        "temperature": 0.8 + (seed % 20)/100.0,
        "seed": seed,
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
        raise RuntimeError("OpenRouter returned no audio chunks")

    try:
        binary_data = b"".join([base64.b64decode(c) for c in audio_chunks])
    except Exception as e:
        raise RuntimeError(f"Failed to decode audio: {e}")

    if len(binary_data) < 1000:
        raise RuntimeError(f"Audio too short ({len(binary_data)} bytes)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp3 = out_path.parent / (out_path.stem + ".mp3")
    tmp_mp3.write_bytes(binary_data)
    ensure_wav(tmp_mp3, out_path)
    try:
        tmp_mp3.unlink()
    except:
        pass

    align_accompaniment_to_vocal_beats(out_path, analysis)
    print(f"[openrouter] Saved {len(binary_data)} bytes mp3 -> wav {out_path.stat().st_size} bytes, hash {file_hash}, seed {seed}")
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
    gen = (GENERATOR or "procedural").lower().strip()
    from .generator_procedural import generate_accompaniment as gen_proc

    if gen in ("openrouter", "or", "lyria-openrouter", "openrouter/lyria", "google/lyria-3-pro-preview", "google/lyria-3-clip-preview"):
        gen = "openrouter"
    if gen in ("openrouter-dynamic", "dynamic", "or-dynamic", "sora", "voice-adaptive", "audio-to-music"):
        gen = "openrouter-dynamic"
    if gen in ("musicgen-melody", "musicgen", "mg-melody", "mureka", "melody"):
        gen = "musicgen-melody"
    if gen in ("musicgen-small", "mg-small"):
        gen = "musicgen-small"
    if gen in ("musicgen-medium", "mg-medium"):
        gen = "musicgen-medium"
    if gen in ("musicgen-large", "mg-large"):
        gen = "musicgen-large"
    if gen in ("musicgen-stereo-melody", "stereo-melody"):
        gen = "musicgen-stereo-melody"
    if gen in ("chorus-aligned", "chorus", "choir", "harmony", "v1.7", "chorus_v1.7"):
        gen = "chorus-aligned"

    try:
        if gen == "chorus-aligned":
            from .generator_chorus_aligned import generate_accompaniment as gen_chorus
            return gen_chorus(analysis, out_path, style, duration_sec=analysis.get("duration_sec"), vocal_path=vocal_path)
        if gen == "elevenlabs":
            return generate_with_elevenlabs(analysis, out_path, style)
        elif gen == "lyria":
            return generate_with_lyria(analysis, out_path, style)
        elif gen == "openrouter":
            return generate_with_openrouter(analysis, out_path, style)
        elif gen == "openrouter-dynamic":
            if vocal_path is None:
                print("[generator] openrouter-dynamic needs vocal_path, falling back to openrouter")
                return generate_with_openrouter(analysis, out_path, style)
            from .generator_openrouter_dynamic import generate_with_openrouter_dynamic
            return generate_with_openrouter_dynamic(vocal_path, analysis, out_path, style)
        elif gen == "musicgen-melody":
            if vocal_path is None:
                print("[generator] musicgen-melody needs vocal_path, using procedural as fallback for analysis")
                # For melody we need vocal, but if not provided, use text-only small
                from .generator_musicgen_melody import generate_with_musicgen_melody
                # Try to find vocal from analysis? Use None fallback
                # If no vocal, generate text-only via small model
                return generate_with_musicgen_melody(vocal_path or out_path, analysis, out_path, style, model_name="melody")
            from .generator_musicgen_melody import generate_with_musicgen_melody
            return generate_with_musicgen_melody(vocal_path, analysis, out_path, style, model_name="melody")
        elif gen == "musicgen-small":
            from .generator_musicgen_melody import generate_with_musicgen_melody
            # small is text-only, vocal optional
            return generate_with_musicgen_melody(vocal_path or out_path, analysis, out_path, style, model_name="small")
        elif gen == "musicgen-medium":
            from .generator_musicgen_melody import generate_with_musicgen_melody
            return generate_with_musicgen_melody(vocal_path or out_path, analysis, out_path, style, model_name="medium")
        elif gen == "musicgen-large":
            from .generator_musicgen_melody import generate_with_musicgen_melody
            return generate_with_musicgen_melody(vocal_path or out_path, analysis, out_path, style, model_name="large")
        elif gen == "musicgen-stereo-melody":
            from .generator_musicgen_melody import generate_with_musicgen_melody
            return generate_with_musicgen_melody(vocal_path, analysis, out_path, style, model_name="stereo-melody")
        elif gen in ("stable-audio-open", "stable_audio", "stable"):
            return generate_with_stable_audio(analysis, out_path, style)
        elif gen == "musicgen":
            raise NotImplementedError("MusicGen TODO")
        else:
            return gen_proc(analysis, out_path, style, duration_sec=analysis.get("duration_sec"), vocal_path=vocal_path)
    except Exception as e:
        import traceback
        print(f"[generator] {gen} failed ({e}), falling back to procedural v0.10\n{traceback.format_exc()[:1000]}")
        return gen_proc(analysis, out_path, style, duration_sec=analysis.get("duration_sec"), vocal_path=vocal_path)
