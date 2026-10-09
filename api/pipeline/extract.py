import subprocess
import soundfile as sf
import numpy as np
from pathlib import Path
from ..config import FFMPEG_BIN

def run_ffmpeg(cmd):
    # print cmd for debugging
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:1000]}")
    return result

def extract_audio(input_path: Path, out_wav: Path, sr=44100):
    """
    Convert any audio/video to 44.1kHz WAV mono for analysis + stereo for mix.
    Returns paths to mono and stereo wavs.
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    mono_wav = out_wav.parent / "vocal_mono.wav"
    stereo_wav = out_wav.parent / "vocal_stereo.wav"

    # mono for analysis
    run_ffmpeg([
        FFMPEG_BIN, "-y", "-i", str(input_path),
        "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le",
        str(mono_wav)
    ])
    # stereo for mixing (keep stereo if exists, else mono->stereo)
    run_ffmpeg([
        FFMPEG_BIN, "-y", "-i", str(input_path),
        "-vn", "-ac", "2", "-ar", str(sr), "-c:a", "pcm_s16le",
        str(stereo_wav)
    ])

    return mono_wav, stereo_wav

def load_wav_mono(path: Path, sr=44100):
    data, file_sr = sf.read(str(path))
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    # resample if needed (simple linear if file_sr != sr - for MVP assume 44.1k from ffmpeg)
    if file_sr != sr:
        # quick resample via interpolation
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
