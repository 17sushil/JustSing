import subprocess
import soundfile as sf
import numpy as np
from pathlib import Path
from ..config import FFMPEG_BIN

def run_ffmpeg(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:1000]}")
    return result

def extract_audio(input_path: Path, out_wav: Path, sr=44100):
    """
    Convert any audio/video to 44.1kHz WAV mono for analysis + stereo for mix.
    FIXED v0.4: Vocal is 100% preserved — stereo is created by duplicating mono in Python,
    not via ffmpeg -ac 2 which applies -3dB pan law (0.707) and changes voice.
    Returns paths to mono and stereo wavs.
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    mono_wav = out_wav.parent / "vocal_mono.wav"
    stereo_wav = out_wav.parent / "vocal_stereo.wav"

    # mono for analysis — ffmpeg
    run_ffmpeg([
        FFMPEG_BIN, "-y", "-i", str(input_path),
        "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le",
        str(mono_wav)
    ])

    # stereo for mixing — FIXED: create from mono in Python to preserve 100%
    # Load mono we just created (guaranteed 44.1k, mono, pcm_s16le)
    try:
        data, file_sr = sf.read(str(mono_wav))
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        # Duplicate to stereo WITHOUT attenuation (ffmpeg -ac 2 does -3dB)
        stereo = np.stack([data, data], axis=1)
        sf.write(str(stereo_wav), stereo, sr, subtype='PCM_16')
        print(f"[extract] Mono max {np.max(np.abs(data)):.4f} -> Stereo max {np.max(np.abs(stereo)):.4f} (preserved, no -3dB)")
    except Exception as e:
        print(f"[extract] Python stereo creation failed {e}, falling back to ffmpeg with pan filter")
        # Fallback: use pan filter to duplicate without -3dB
        run_ffmpeg([
            FFMPEG_BIN, "-y", "-i", str(mono_wav),
            "-af", "pan=stereo|c0=c0|c1=c0",
            "-ar", str(sr), "-c:a", "pcm_s16le",
            str(stereo_wav)
        ])

    return mono_wav, stereo_wav

def load_wav_mono(path: Path, sr=44100):
    data, file_sr = sf.read(str(path))
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    if file_sr != sr:
        duration = len(data) / file_sr
        new_len = int(duration * sr)
        x_old = np.linspace(0, duration, len(data))
        x_new = np.linspace(0, duration, new_len)
        data = np.interp(x_new, x_old, data)
    return data.astype(np.float32), sr

def encode_mp3(wav_path: Path, mp3_path: Path, bitrate="320k"):
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        FFMPEG_BIN, "-y", "-i", str(wav_path),
        "-c:a", "libmp3lame", "-b:a", bitrate,
        str(mp3_path)
    ])
    return mp3_path
