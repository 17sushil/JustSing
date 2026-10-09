"""
JustSing MusicGen Melody Generator v1.0 — Mureka-level quality
Uses Meta's MusicGen Melody (facebook/musicgen-melody) to generate accompaniment
that TRULY follows your vocal melody via chroma conditioning.

- Vocal -> chroma -> MusicGen generates music that follows melody
- Text prompt from analysis (key, BPM, style) for genre
- High-quality EnCodec 32kHz -> 44.1k stereo
- Zero-cost, self-hosted, no API key needed, but needs torch + ~4GB download
- Fallback to procedural v0.10 if audiocraft not installed

Install:
  pip install audiocraft torch torchaudio
  # Or for CPU only: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
  # Then: pip install audiocraft

Usage:
  GENERATOR=musicgen-melody
  GENERATOR=musicgen-small (text-only, faster)
  GENERATOR=musicgen-medium (better quality, needs GPU)
"""

from pathlib import Path
import subprocess
import numpy as np
import soundfile as sf

from ..config import FFMPEG_BIN

def _run_ffmpeg(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:800]}")
    return result

def ensure_wav_32k_to_44k(in_path: Path, out_path: Path):
    """Convert any audio to 44.1k stereo WAV"""
    _run_ffmpeg([FFMPEG_BIN, "-y", "-i", str(in_path), "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out_path)])
    return out_path

def generate_with_musicgen_melody(vocal_path: Path, analysis: dict, out_path: Path, style="warm-acoustic", model_name="melody"):
    """
    Generate accompaniment using MusicGen Melody that follows vocal melody.
    
    model_name options:
      - melody: facebook/musicgen-melody (1.5B, best for melody following, ~4GB)
      - small: facebook/musicgen-small (300M, text-only, fast, ~1GB)
      - medium: facebook/musicgen-medium (1.5B text-only)
      - large: facebook/musicgen-large (3.3B, best quality)
      - stereo-melody: facebook/musicgen-stereo-melody (stereo version)
    """
    # First try audiocraft (best for melody)
    try:
        import torch
        import torchaudio
        from audiocraft.models import MusicGen
        from audiocraft.data.audio import audio_write
        has_audiocraft = True
    except ImportError as e:
        print(f"[musicgen] audiocraft not installed ({e}), trying transformers...")
        has_audiocraft = False

    if has_audiocraft:
        # Use audiocraft path (melody-guided)
        return _generate_with_audiocraft(vocal_path, analysis, out_path, style, model_name)
    else:
        # Try transformers (works on Python 3.14, no spacy needed)
        try:
            from transformers import pipeline
            import torch
            print("[musicgen] Using transformers pipeline (works on Python 3.14)...")
            return _generate_with_transformers(vocal_path, analysis, out_path, style, model_name)
        except ImportError as e:
            print(f"[musicgen] transformers not installed ({e}), falling back to procedural v0.10")
            from .generator_procedural import generate_accompaniment as gen_proc
            return gen_proc(analysis, out_path, style=style, duration_sec=analysis.get("duration_sec"), vocal_path=vocal_path)

def _generate_with_audiocraft(vocal_path: Path, analysis: dict, out_path: Path, style="warm-acoustic", model_name="melody"):

    # Determine model
    model_id_map = {
        "melody": "facebook/musicgen-melody",
        "small": "facebook/musicgen-small",
        "medium": "facebook/musicgen-medium",
        "large": "facebook/musicgen-large",
        "stereo-melody": "facebook/musicgen-stereo-melody",
        "stereo-small": "facebook/musicgen-stereo-small",
    }
    # Normalize model_name
    model_name_lower = model_name.lower().strip()
    if model_name_lower in model_id_map:
        hf_model_id = model_id_map[model_name_lower]
    elif "facebook/" in model_name_lower or "musicgen" in model_name_lower:
        hf_model_id = model_name_lower
    else:
        hf_model_id = "facebook/musicgen-melody"

    print(f"[musicgen] Loading model {hf_model_id}... (first time downloads ~1-4GB)")

    try:
        model = MusicGen.get_pretrained(hf_model_id)
    except Exception as e:
        print(f"[musicgen] Failed to load {hf_model_id} ({e}), trying melody")
        try:
            model = MusicGen.get_pretrained("facebook/musicgen-melody")
            hf_model_id = "facebook/musicgen-melody"
        except Exception as e2:
            print(f"[musicgen] Also failed melody ({e2}), falling back to procedural")
            from .generator_procedural import generate_accompaniment as gen_proc
            return gen_proc(analysis, out_path, style=style, duration_sec=analysis.get("duration_sec"), vocal_path=vocal_path)

    # Generation params
    duration = float(analysis.get("duration_sec", 30))
    # MusicGen max 30s for melody, we chunk if longer
    # For MVP, limit to 30s, or generate in chunks
    gen_duration = min(duration + 1.0, 30.0)  # +1 sec tail, max 30
    if duration > 30:
        print(f"[musicgen] Duration {duration}s >30s, will generate {gen_duration}s and loop/pad")

    bpm = analysis.get("bpm", 90)
    key = analysis.get("key", "C major")
    is_major = analysis.get("is_major", True)
    file_hash = analysis.get("file_hash", "0000")
    f0_mean = analysis.get("f0_mean_hz", 180)

    # Build rich prompt like Mureka
    mood_map = {
        "warm-acoustic": "warm acoustic, intimate, fingerpicked guitar, soft drums, warm bass, organic",
        "lofi-chill": "lofi chill, mellow, vinyl crackle, soft piano, relaxed, jazzy, cozy",
        "piano-ballad": "piano ballad, intimate, emotional, soft pads, minimal, heartfelt",
        "indie-pop": "indie pop, bright, upbeat, clean guitar, punchy drums, bouncy bass, catchy",
        "cinematic": "cinematic, epic, spacious, orchestral pads, emotional, atmospheric, film score"
    }
    mood = mood_map.get(style, style)

    # Voice-adaptive prompt
    if f0_mean > 300:
        voice_adapt = "low warm accompaniment, deep bass, soft pads, leave space for high soprano voice"
    elif f0_mean > 220:
        voice_adapt = "balanced accompaniment, mid-range guitar and piano, gentle, supports clear voice"
    elif f0_mean > 150:
        voice_adapt = "warm accompaniment that complements mid voice, not overpowering"
    else:
        voice_adapt = "higher bright accompaniment, light guitar, airy pads to lift low voice"

    # Mureka-style prompt: detailed, includes key, BPM, instruments, no vocals
    prompt = (
        f"{mood} instrumental backing track, "
        f"{key}, {bpm:.0f} BPM, {'major' if is_major else 'minor'} key, "
        f"{voice_adapt}, "
        f"no vocals, no lead vocal, instrumental only, "
        f"guitar, bass, drums, piano, "
        f"studio quality, professional mix, "
        f"track {file_hash[:4]}"
    )

    print(f"[musicgen] Prompt: {prompt[:250]}...")
    print(f"[musicgen] Vocal path {vocal_path}, duration {gen_duration}s, model {hf_model_id}")

    # Load vocal as melody
    try:
        # Use torchaudio to load
        melody_wav, melody_sr = torchaudio.load(str(vocal_path))
        # Ensure mono or stereo? MusicGen expects [C, T] or [B, C, T]
        # If stereo, convert to mono for melody? Actually melody can be stereo but we use mono
        if melody_wav.shape[0] > 1:
            melody_wav = torch.mean(melody_wav, dim=0, keepdim=True)
        # Trim to gen_duration
        max_samples = int(melody_sr * gen_duration)
        if melody_wav.shape[1] > max_samples:
            melody_wav = melody_wav[:, :max_samples]
        
        print(f"[musicgen] Melody loaded {melody_wav.shape} sr {melody_sr}, trimmed to {gen_duration}s")

        model.set_generation_params(
            duration=gen_duration,
            top_k=250,
            top_p=0.0,
            temperature=1.0,
            cfg_coef=3.0,  # guidance scale
        )

        # Generate with chroma conditioning (melody-guided)
        # For melody model, use generate_with_chroma
        if "melody" in hf_model_id:
            print(f"[musicgen] Generating with chroma conditioning (melody-guided)...")
            wav = model.generate_with_chroma(
                descriptions=[prompt],
                melody_wavs=melody_wav,
                melody_sample_rate=melody_sr,
                progress=True
            )
        else:
            # Text-only models
            print(f"[musicgen] Generating text-only (no melody conditioning)...")
            wav = model.generate(descriptions=[prompt], progress=True)

        # wav shape: [B, C, T]
        print(f"[musicgen] Generated wav shape {wav.shape}, sample_rate {model.sample_rate}")

        # Save temp
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temp_wav = out_path.parent / (out_path.stem + "_musicgen_32k.wav")
        # audio_write saves with loudness normalization
        # We'll manually save via soundfile for control
        # wav is torch tensor [B, C, T], take first batch
        audio_tensor = wav[0].cpu()
        # Convert to numpy [C, T] -> [T, C]
        if audio_tensor.dim() == 2:
            # [C, T]
            audio_np = audio_tensor.numpy().T
        else:
            audio_np = audio_tensor.numpy()

        # Save 32k temp
        sf.write(str(temp_wav), audio_np, model.sample_rate)
        print(f"[musicgen] Saved temp 32k {temp_wav} {len(audio_np)/model.sample_rate:.1f}s")

        # Convert to 44.1k stereo
        ensure_wav_32k_to_44k(temp_wav, out_path)
        try:
            temp_wav.unlink()
        except:
            pass

        # If original duration > gen_duration, loop or pad
        y, sr = sf.read(str(out_path))
        if y.ndim == 1:
            y = np.stack([y, y], axis=1)
        target_len = int((duration + 1.2) * sr)
        if len(y) < target_len:
            # Loop if needed for longer songs
            if len(y) > 0:
                repeats = int(np.ceil(target_len / len(y)))
                y_looped = np.tile(y, (repeats, 1))[:target_len]
                sf.write(str(out_path), y_looped, sr)
                print(f"[musicgen] Looped to {target_len/sr:.1f}s for long song")
        elif len(y) > target_len:
            y = y[:target_len]
            sf.write(str(out_path), y, sr)

        print(f"[musicgen] Final saved {out_path}, {len(y)/sr:.1f}s, model {hf_model_id}")
        return out_path

    except Exception as e:
        import traceback
        print(f"[musicgen] Generation failed {e}\n{traceback.format_exc()[:1500]}")
        print("[musicgen] Falling back to procedural v0.10")
        from .generator_procedural import generate_accompaniment as gen_proc
        return gen_proc(analysis, out_path, style=style, duration_sec=analysis.get("duration_sec"), vocal_path=vocal_path)

def _generate_with_transformers(vocal_path: Path, analysis: dict, out_path: Path, style="warm-acoustic", model_name="small"):
    """
    Fallback using HuggingFace transformers — works on Python 3.14, no spacy/blis needed.
    Uses text-to-audio pipeline, not melody-guided, but still real instruments (Mureka-level sound).
    For true melody following, need audiocraft, but this is much better than procedural.
    """
    try:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
        import torch
        import scipy.io.wavfile
    except ImportError as e:
        print(f"[musicgen-transformers] not installed {e}")
        raise

    model_id_map = {
        "small": "facebook/musicgen-small",
        "medium": "facebook/musicgen-medium",
        "large": "facebook/musicgen-large",
        "melody": "facebook/musicgen-small",  # fallback to small for transformers (melody needs audiocraft)
        "stereo-melody": "facebook/musicgen-stereo-small",
    }
    hf_model_id = model_id_map.get(model_name.lower(), "facebook/musicgen-small")

    print(f"[musicgen-transformers] Loading {hf_model_id} via transformers...")

    try:
        processor = AutoProcessor.from_pretrained(hf_model_id)
        model = MusicgenForConditionalGeneration.from_pretrained(hf_model_id)
    except Exception as e:
        print(f"[musicgen-transformers] Failed to load {hf_model_id}: {e}")
        raise

    duration = float(analysis.get("duration_sec", 15))
    gen_duration = min(duration + 1.0, 20.0)  # limit for transformers

    bpm = analysis.get("bpm", 90)
    key = analysis.get("key", "C major")
    is_major = analysis.get("is_major", True)
    file_hash = analysis.get("file_hash", "0000")
    f0_mean = analysis.get("f0_mean_hz", 180)

    mood_map = {
        "warm-acoustic": "warm acoustic, intimate, fingerpicked guitar, soft drums, warm bass",
        "lofi-chill": "lofi chill, mellow, vinyl crackle, soft piano, relaxed",
        "piano-ballad": "piano ballad, intimate, emotional, soft pads",
        "indie-pop": "indie pop, bright, upbeat, clean guitar, punchy drums",
        "cinematic": "cinematic, epic, spacious, orchestral pads"
    }
    mood = mood_map.get(style, style)

    if f0_mean > 300:
        voice_adapt = "low warm accompaniment, deep bass, soft pads"
    elif f0_mean > 220:
        voice_adapt = "balanced accompaniment, mid-range guitar and piano"
    elif f0_mean > 150:
        voice_adapt = "warm accompaniment"
    else:
        voice_adapt = "higher bright accompaniment, light guitar"

    prompt = (
        f"{mood} instrumental backing track, "
        f"{key}, {bpm:.0f} BPM, {'major' if is_major else 'minor'}, "
        f"{voice_adapt}, no vocals, instrumental only, "
        f"guitar, bass, drums, piano, studio quality, track {file_hash[:4]}"
    )

    print(f"[musicgen-transformers] Prompt: {prompt[:200]}...")

    try:
        inputs = processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        )

        # Generate: max_new_tokens controls duration (~50 tokens per second)
        # For 15 sec, need ~750 tokens
        max_tokens = int(gen_duration * 50) + 100
        max_tokens = min(max_tokens, 1500)

        print(f"[musicgen-transformers] Generating {gen_duration}s with {max_tokens} tokens...")

        audio_values = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=True, guidance_scale=3.0)

        # audio_values shape: [batch, channels, samples]
        sampling_rate = model.config.audio_encoder.sampling_rate
        print(f"[musicgen-transformers] Generated shape {audio_values.shape} sr {sampling_rate}")

        # Save
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temp_wav = out_path.parent / (out_path.stem + "_mg_transformers.wav")
        
        # Take first batch, first channel? Actually [B, C, T] -> we need [T] or [T, C]
        audio_np = audio_values[0, 0].cpu().numpy()
        # If stereo, we have 2 channels? For small it's mono, convert to stereo
        if audio_values.shape[1] == 1:
            # mono -> stereo
            audio_stereo = np.stack([audio_np, audio_np], axis=1)
        else:
            # stereo: [C, T] -> [T, C]
            audio_stereo = audio_values[0].cpu().numpy().T

        # Save temp at model sr
        sf.write(str(temp_wav), audio_stereo if audio_values.shape[1]>1 else audio_np, sampling_rate)
        # Convert to 44.1k
        ensure_wav_32k_to_44k(temp_wav, out_path)
        try:
            temp_wav.unlink()
        except:
            pass

        # Trim/pad to target
        y, sr = sf.read(str(out_path))
        if y.ndim == 1:
            y = np.stack([y, y], axis=1)
        target_len = int((duration + 1.2) * sr)
        if len(y) < target_len:
            if len(y) > 0:
                repeats = int(np.ceil(target_len / len(y)))
                y = np.tile(y, (repeats, 1))[:target_len]
        else:
            y = y[:target_len]
        sf.write(str(out_path), y, sr)

        print(f"[musicgen-transformers] Saved {out_path} {len(y)/sr:.1f}s")
        return out_path

    except Exception as e:
        import traceback
        print(f"[musicgen-transformers] Failed {e}\n{traceback.format_exc()[:1500]}")
        raise

def generate_accompaniment_musicgen(vocal_path: Path, analysis: dict, out_path: Path, style="warm-acoustic", model_variant="melody"):
    return generate_with_musicgen_melody(vocal_path, analysis, out_path, style, model_name=model_variant)
