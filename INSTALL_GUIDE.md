# Install Guide — Fix pip errors

## Problem: `pip install -r requirements-optional.txt` gave lots of errors

**Root cause:** Old `requirements-optional.txt` tried to install `torch + audiocraft + transformers + demucs + faster-whisper` all at once.
- `audiocraft` fails on Python 3.14 (needs Cython <3.0, blis error)
- `torch` is 2GB, slow, may fail on some systems
- You DON'T need any optional deps for chorus-aligned to work!

## Solution: Zero-Error Install (Recommended)

### Option 1: No optional deps — works 100% (chorus-aligned + procedural + volume mixer)

```bash
pip install -r requirements.txt
# That's it! No optional needed
# .env:
GENERATOR=chorus-aligned
SEPARATOR=none
WHISPER=off
USE_LIBROSA=0
```

`chorus-aligned` and `procedural` work with ZERO optional deps — pure numpy + soundfile.

### Option 2: Add vocal separation (like vocal.ai) — needs torch but step-by-step

If you upload songs WITH background music and want to extract vocal:

```bash
# Step 1: torch CPU (2GB, may take 5 min)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Step 2: demucs (needs torch already installed)
pip install demucs

# .env:
SEPARATOR=demucs
GENERATOR=chorus-aligned
```

If `pip install demucs` still fails:
```bash
pip install demucs --no-deps
pip install julius  # demucs dependency
```

### Option 3: Real instruments (Mureka-level) — fixes poor piano

If piano still poor, use real AI instruments (not synth):

**For Python 3.14 (your version, works):**
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install transformers scipy sentencepiece

# .env:
GENERATOR=musicgen-small  # 300M model ~1GB, real guitar/piano/drums
SEPARATOR=none
WHISPER=off
```

**For Python 3.11 with melody following (BEST, follows YOUR exact melody):**
```bash
# Use Python 3.11 venv
python3.11 -m venv venv311
source venv311/bin/activate  # or venv311\Scripts\activate on Windows
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install audiocraft

# .env:
GENERATOR=musicgen-melody  # follows YOUR melody via chroma, like Mureka Remix
```

### Option 4: Lyrics transcription

```bash
pip install faster-whisper

# .env:
WHISPER=auto
```

## Why you heard only drums, no chorus?

**Fixed in v1.7.1:**
- Old chorus volumes: 0.18, 0.14, 0.12, 0.08 = too quiet vs drums 0.75 → drums drowned chorus
- Old gate threshold: 0.03 = too strict, quiet vocals got gated out → no chorus
- Old pad: 0.18 vol = too quiet

**New v1.7.1:**
- Chorus volumes: 0.45, 0.35, 0.32, 0.22 = 2.5x louder
- Gate threshold: 0.008 (was 0.03) = sings even with quiet voice
- Pad: 0.35+0.25*energy = 2x louder, 0.8 mix
- Drums reduced: kick 0.55 (was 0.75), snare 0.42 (was 0.56), hat 0.32 (was 0.48)

Now chorus should be clearly audible, not just drums.

## Quick Test

```bash
git pull origin main

# No optional install needed!
pip install -r requirements.txt

# .env:
GENERATOR=chorus-aligned
SEPARATOR=none
WHISPER=off
USE_LIBROSA=0

python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# Open http://localhost:8000
# Upload your voice
# You should hear: your voice + 4 harmony voices (octave down, fifth, third, octave up) + soft pad + drums
# All perfectly aligned because chorus uses YOUR pitch curve
```

If you still hear only drums, check backend logs:
```
[chorus] Continuous: 185 frames 50ms, F0 80-501Hz
[chorus] Generating 4 harmony voices from YOUR F0: shifts [-12, -7, -3, 12]
[chorus] Voice octave_down shift -12 vol 0.45 added, peak 0.XXX
```
If you see `peak 0.000`, energy gate too high — share log and I'll fix.

## For Real Instruments (Fix Poor Music)

If chorus-aligned still not enough, use `musicgen-small`:

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install transformers scipy sentencepiece

# .env:
GENERATOR=musicgen-small
```

This gives real guitar/piano/drums (not synth) — Mureka-level quality, $0 self-hosted.
