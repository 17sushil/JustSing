# Contributing to JustSing

## Zero-Cost Principle
Never add a paid dependency without a free fallback. The app must run with $0.

## Dev Setup
```bash
pip install -r requirements.txt
GENERATOR=procedural uvicorn api.main:app --reload --port 8000
```

## Adding a Generator
Edit `api/pipeline/generator_api.py`, add function, register in `GENERATOR` env switch. Always fallback to procedural if key missing.

## Code Style
- Python: black, ruff
- Keep analysis pure numpy/scipy where possible
- Frontend: vanilla JS + Tailwind CDN (no build step for MVP)

## Testing
```bash
# generate test vocal
python - << 'PY'
import numpy as np, soundfile as sf
sr=44100; dur=5; t=np.linspace(0,dur,int(sr*dur))
f0=261.63; vocal=np.sin(2*np.pi*f0*t)*0.6
sf.write('/tmp/test.wav', vocal, sr)
PY

curl -F "file=@/tmp/test.wav" -F "style=warm-acoustic" http://localhost:8000/api/upload
```
