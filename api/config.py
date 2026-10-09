import os
from pathlib import Path

# Root dir = /home/user/singsmith
ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", ROOT / "storage")).resolve()
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
(UPLOADS_DIR := STORAGE_DIR / "uploads").mkdir(exist_ok=True)
(JOBS_DIR := STORAGE_DIR / "jobs").mkdir(exist_ok=True)
(RENDERS_DIR := STORAGE_DIR / "renders").mkdir(exist_ok=True)

GENERATOR = os.getenv("GENERATOR", "procedural").lower()  # procedural | elevenlabs | lyria | stable-audio-open | musicgen
SEPARATOR = os.getenv("SEPARATOR", "none").lower()  # none | demucs
WHISPER = os.getenv("WHISPER", "auto").lower()  # auto | off
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

TARGET_RMS = float(os.getenv("TARGET_RMS", "0.18"))
MP3_BITRATE = os.getenv("MP3_BITRATE", "320k")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/lyria-3-pro-preview")  # or google/lyria-3-clip-preview ($0.04) or minimax/music-2.6-free
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "https://github.com/17sushil/JustSing")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "JustSing")

# Procedural generator styles
STYLES = ["warm-acoustic", "lofi-chill", "piano-ballad", "indie-pop", "cinematic"]

# ffmpeg binary from imageio-ffmpeg (zero-cost bundled)
try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = "ffmpeg"  # fallback to system

print(f"[config] GENERATOR={GENERATOR} SEPARATOR={SEPARATOR} FFMPEG={FFMPEG_BIN} STORAGE={STORAGE_DIR}")
