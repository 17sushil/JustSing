"""
JustSing Separator v1.2 — vocal.ai level separation via Demucs
Uses Facebook Demucs v4 (htdemucs) — SOTA, free, works CPU/GPU

- Input: any audio/video (song with vocals + instruments)
- Output: isolated vocal (like vocal.ai / remove-vocal.ai)
- Zero-cost, self-hosted, no API key
- Fallback to no separation if demucs not installed

Install:
  pip install demucs
  # For GPU: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

Usage:
  SEPARATOR=demucs in .env
  Or: SEPARATOR=none (default, no separation, assumes input is already vocal)
"""

from pathlib import Path
import subprocess
import shutil
import numpy as np
import soundfile as sf

from ..config import FFMPEG_BIN, SEPARATOR

def separate_with_demucs_cli(input_path: Path, out_dir: Path, model="htdemucs"):
    """
    Use demucs CLI via subprocess: python -m demucs --two-stems=vocals
    Returns path to vocals.wav
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Demucs output structure: out_dir / model / track_name / vocals.wav
    cmd = [
        "python", "-m", "demucs",
        "--two-stems=vocals",
        "-n", model,
        "-o", str(out_dir),
        str(input_path)
    ]
    
    print(f"[separator] Running Demucs {model} on {input_path}...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        print(f"[separator] Demucs CLI failed: {result.stderr[:1000]}")
        raise RuntimeError(f"Demucs failed: {result.stderr[:500]}")
    
    # Find vocals.wav
    track_name = input_path.stem
    # Demucs creates out_dir / model / track_name / vocals.wav
    vocals_path = out_dir / model / track_name / "vocals.wav"
    
    # Also try with different structure
    if not vocals_path.exists():
        # Search recursively
        candidates = list(out_dir.rglob("vocals.wav"))
        if candidates:
            vocals_path = candidates[0]
        else:
            raise RuntimeError(f"Demucs output not found, searched {out_dir}")

    print(f"[separator] Demucs separated vocal: {vocals_path} ({vocals_path.stat().st_size} bytes)")
    return vocals_path

def separate_with_demucs_api(input_path: Path, out_dir: Path, model_name="htdemucs"):
    """
    Use Demucs Python API (faster, no subprocess)
    """
    try:
        import torch
        import torchaudio
        from demucs.pretrained import get_model
        from demucs.apply import apply_model
        from demucs.audio import AudioFile
    except ImportError as e:
        print(f"[separator] demucs/torch not installed ({e}), trying CLI")
        return separate_with_demucs_cli(input_path, out_dir, model=model_name)

    print(f"[separator] Using Demucs API {model_name}...")

    # Load model
    model = get_model(model_name)
    model.cpu()
    model.eval()

    # Load audio
    wav, sr = torchaudio.load(str(input_path))
    # Convert to stereo if needed
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    
    # Apply model
    # Demucs expects [batch, channels, samples]
    wav = wav.unsqueeze(0)  # [1, 2, T]
    
    # For long audio, chunk
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / ref.std()

    with torch.no_grad():
        sources = apply_model(model, wav, device="cpu", split=True, overlap=0.25, progress=True)

    # sources: [batch, 4, channels, samples] or [batch, 2, channels, samples] for two-stems
    # For two-stems=vocals, we have 2 sources: vocals and no_vocals
    # Actually apply_model returns [batch, sources, channels, samples]
    # For htdemucs 4 stems: drums, bass, other, vocals
    # For two-stems, we need to handle

    # Get vocals (last source for 4-stem, or 0 for two-stems?)
    # For htdemucs, vocals is index 3
    if sources.shape[1] == 4:
        vocals = sources[0, 3]  # [channels, samples]
    elif sources.shape[1] == 2:
        vocals = sources[0, 0]  # vocals is first for two-stems?
    else:
        vocals = sources[0, -1]

    # Save
    out_dir.mkdir(parents=True, exist_ok=True)
    vocals_path = out_dir / f"{input_path.stem}_vocals.wav"
    
    # Convert to numpy and save
    vocals_np = vocals.cpu().numpy().T  # [samples, channels]
    sf.write(str(vocals_path), vocals_np, model.samplerate)

    print(f"[separator] Demucs API separated: {vocals_path}")
    return vocals_path

def separate_vocal(input_path: Path, out_dir: Path):
    """
    Main entry: separate vocal from mixed audio like vocal.ai
    Returns path to isolated vocal wav
    """
    # Check if demucs is available
    try:
        import demucs
        has_demucs = True
    except ImportError:
        has_demucs = False

    if not has_demucs:
        print("[separator] demucs not installed, skipping separation (assuming input is already vocal)")
        print("[separator] Install: pip install demucs")
        return None

    try:
        # Try API first (faster), fallback to CLI
        try:
            return separate_with_demucs_api(input_path, out_dir)
        except Exception as e:
            print(f"[separator] API failed {e}, trying CLI...")
            return separate_with_demucs_cli(input_path, out_dir)
    except Exception as e:
        print(f"[separator] Separation failed {e}, using original as vocal")
        return None

def extract_vocal_with_fallback(input_path: Path, work_dir: Path, sr=44100):
    """
    Used by pipeline: if SEPARATOR=demucs, separate vocal, else just convert
    Returns mono and stereo vocal paths
    """
    from .extract import extract_audio, run_ffmpeg
    import soundfile as sf

    work_dir.mkdir(parents=True, exist_ok=True)

    # If separator is demucs, try to separate
    if SEPARATOR == "demucs":
        try:
            separated_dir = work_dir / "separated"
            vocals_path = separate_vocal(input_path, separated_dir)
            if vocals_path and vocals_path.exists():
                # Now extract mono/stereo from separated vocals
                # Use same logic as extract_audio but from vocals_path
                mono_wav = work_dir / "vocal_mono.wav"
                stereo_wav = work_dir / "vocal_stereo.wav"

                # Convert to 44.1k mono
                run_ffmpeg([
                    FFMPEG_BIN, "-y", "-i", str(vocals_path),
                    "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le",
                    str(mono_wav)
                ])

                # Stereo from mono in Python (no -3dB)
                try:
                    data, file_sr = sf.read(str(mono_wav))
                    if data.ndim > 1:
                        data = np.mean(data, axis=1)
                    stereo = np.stack([data, data], axis=1)
                    sf.write(str(stereo_wav), stereo, sr, subtype='PCM_16')
                    print(f"[separator] Mono max {np.max(np.abs(data)):.4f} -> Stereo preserved")
                except Exception as e:
                    print(f"[separator] Python stereo failed {e}, using pan filter")
                    run_ffmpeg([
                        FFMPEG_BIN, "-y", "-i", str(mono_wav),
                        "-af", "pan=stereo|c0=c0|c1=c0",
                        "-ar", str(sr), "-c:a", "pcm_s16le",
                        str(stereo_wav)
                    ])

                return mono_wav, stereo_wav
        except Exception as e:
            print(f"[separator] Demucs separation failed {e}, falling back to simple extract")

    # Fallback: simple extract (no separation)
    return extract_audio(input_path, work_dir / "extracted.wav", sr=sr)
