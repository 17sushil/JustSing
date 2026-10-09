"""
Mastering — loudness normalization + limiter.
Zero-cost: RMS target + peak limiting. Optionally uses ffmpeg loudnorm.
"""
import numpy as np
import soundfile as sf
from pathlib import Path
import subprocess
from ..config import FFMPEG_BIN, TARGET_RMS

def master_audio(input_wav: Path, output_wav: Path, target_rms=0.18):
    data, sr = sf.read(str(input_wav))
    if data.ndim == 1:
        data = data[:, None]

    # Loudness: RMS normalization to target (approx -14 LUFS)
    # Compute current RMS
    rms = np.sqrt(np.mean(data**2) + 1e-9)
    if rms > 1e-6:
        gain = target_rms / rms
        # limit gain to avoid extreme boosts
        gain = min(gain, 3.0)
        data = data * gain

    # Simple limiter: lookahead-ish by reducing peaks >0.95
    peak = np.max(np.abs(data))
    if peak > 0.95:
        # soft clip with tanh for peaks
        # For values >0.8, apply gentle compression
        # Use: y = sign(x) * (0.8 + 0.2*tanh((|x|-0.8)/0.2)) for |x|>0.8
        abs_data = np.abs(data)
        mask = abs_data > 0.8
        # compress
        compressed = 0.8 + 0.15 * np.tanh((abs_data[mask] - 0.8)/0.15)
        data[mask] = np.sign(data[mask]) * compressed[:, None] if data.ndim>1 else np.sign(data[mask])*compressed

        # final hard limit
        peak2 = np.max(np.abs(data))
        if peak2 > 0.98:
            data = data * (0.98 / peak2)

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_wav), data, sr)
    return output_wav

def loudnorm_ffmpeg(input_wav: Path, output_wav: Path):
    """
    Optional: use ffmpeg loudnorm filter for EBU R128 (-14 LUFS).
    If fails, fall back to simple RMS mastering.
    """
    try:
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(input_wav),
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-ar", "44100",
            str(output_wav)
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode()[:500])
        return output_wav
    except Exception as e:
        print(f"[master] ffmpeg loudnorm failed ({e}), using RMS master")
        return master_audio(input_wav, output_wav, TARGET_RMS)
