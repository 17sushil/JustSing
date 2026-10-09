# JustSing — VS Code Run Guide (Zero-Cost)

This guide is for running https://github.com/17sushil/JustSing locally in VS Code.

## 1) Prerequisites

- **Git**: https://git-scm.com/downloads
- **Python 3.10+**: https://www.python.org/downloads/ (check "Add to PATH" on Windows)
- **VS Code**: https://code.visualstudio.com/
- VS Code extensions: **Python** (ms-python.python) + **Pylance**

No Node.js needed (frontend is vanilla JS + Tailwind CDN). ffmpeg is bundled via `imageio-ffmpeg`.

## 2) Clone in VS Code

1. Open VS Code
2. `Ctrl+Shift+P` → `Git: Clone` → paste `https://github.com/17sushil/JustSing.git` → pick a folder → Open
3. Or terminal:
```bash
git clone https://github.com/17sushil/JustSing.git
cd JustSing
code .
```

## 3) Create virtual env & install

**In VS Code terminal (`Ctrl+``):**

Windows:
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Mac/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional for lyrics detection:
pip install -r requirements-optional.txt
```

VS Code will auto-detect `.venv` — select it when prompted (bottom-right Python version).

## 4) Run the app

### Option A — One command (recommended)
```bash
# Windows (venv active)
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Mac/Linux
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option B — VS Code Debug (F5)
- Press `F5` → select **"SingSmith API (procedural $0)"**
- It auto-sets `GENERATOR=procedural`
- Debug console shows logs

### Option C — VS Code Task
`Ctrl+Shift+P` → `Tasks: Run Task` → `Run SingSmith (procedural $0)`

You should see:
```
Uvicorn running on http://0.0.0.0:8000
```

## 5) Open the app

Open browser: **http://localhost:8000**

- Health check: http://localhost:8000/api/health → should return `{"status":"ok"}`
- Fallback upload (no JS): http://localhost:8000/test-upload

## 6) Use it

1. Choose vibe (warm-acoustic, lofi-chill, etc.)
2. Drop MP3/WAV/M4A/MP4/WebM or click Browse — OR Record (allow mic)
3. Click **Generate my song**
4. Watch progress: extracting → analyzing (key/BPM) → composing → mixing → mastering
5. Play final mix, download MP3/WAV + stems

**Sandbox tip:** If recording doesn't work, it's mic permission. Upload always works.

## 7) Upgrade to better quality (optional, still cheap)

Create `.env` file or set env var:

```bash
# ElevenLabs (10k free credits/month, $0.15/min after)
# Get key at https://elevenlabs.io → API keys
GENERATOR=elevenlabs ELEVENLABS_API_KEY=your_key python -m uvicorn api.main:app --port 8000 --reload

# Lyria 3.5 Google ($0.08/song, best cheap)
# Get key at https://ai.google.dev
GENERATOR=lyria GEMINI_API_KEY=your_key python -m uvicorn api.main:app --port 8000 --reload
```

One env var switches generator — no code change.

## 8) VS Code Debugging Tips

- **Breakpoints:** Open `api/pipeline/pipeline.py`, set breakpoint on `run_pipeline`, F5
- **Logs:** See `DEBUG CONSOLE` + `TERMINAL`
- **Hot reload:** `--reload` watches `api/` and `web/` — save file = auto restart
- **Test API without UI:**
```bash
# create test tone
python -c "import numpy as np, soundfile as sf; sr=44100; t=np.linspace(0,3,int(sr*3)); sf.write('test.wav', 0.5*np.sin(2*np.pi*261*t), sr)"
curl -F "file=@test.wav" -F "style=warm-acoustic" http://localhost:8000/api/upload
# then poll: curl http://localhost:8000/api/jobs/JOB_ID
```

## 9) Common Issues

**`ModuleNotFoundError: fastapi`**
→ venv not activated or deps not installed. Run `pip install -r requirements.txt`

**`ffmpeg not found`**
→ Shouldn't happen (bundled via imageio-ffmpeg). If it does: `pip install imageio-ffmpeg --force-reinstall`

**Port 8000 in use**
→ Change port: `uvicorn api.main:app --port 8001` and open http://localhost:8001

**Upload fails with 400**
→ File type not allowed. Use MP3/WAV/M4A/MP4/WebM

**Recording blocked**
→ Browser blocks mic on http (needs https) unless localhost. Use upload instead, or run via `https` tunnel, or allow mic in browser site settings.

**`storage/` permission error**
→ `mkdir -p storage && chmod 777 storage` (Mac/Linux) or run VS Code as admin once (Windows)

## 10) Project Structure in VS Code

```
JustSing/
  .vscode/           # launch.json, tasks.json (F5 ready)
  api/               # FastAPI backend
    main.py          # ← start here, serves frontend
    pipeline/        # extract → analyze → generate → mix → master
  web/               # frontend (index.html, app.js) — Tailwind CDN, no build
  storage/           # uploads/renders (gitignored)
  requirements.txt
  VSCODE_GUIDE.md    # this file
```

## 11) Deploy from VS Code (free)

- Frontend: drag `web/` to https://pages.cloudflare.com (free)
- API: Push to GitHub → connect to https://render.com free tier (750h/mo)
- Set env var `GENERATOR=procedural` on Render — still $0

---

**You now have a working studio in VS Code.** Sing anything — JustSing makes it a finished song.

Questions? Open an issue at https://github.com/17sushil/JustSing/issues

## 12) Free API Keys — OpenRouter YES it works!

See FREE_API_KEYS_GUIDE.md for full guide. Quick start:

1. Get free key: https://openrouter.ai/ → Sign up → https://openrouter.ai/settings/keys → Create Key (you get $1 free = 12 songs)

2. Set in VS Code terminal:
```powershell
# Windows
$env:OPENROUTER_API_KEY="sk-or-v1-..."
$env:GENERATOR="openrouter"
$env:OPENROUTER_MODEL="google/lyria-3-pro-preview"
python -m uvicorn api.main:app --port 8000 --reload

# Mac/Linux
OPENROUTER_API_KEY=sk-or-v1-... GENERATOR=openrouter python -m uvicorn api.main:app --port 8000 --reload
```

3. Or create .env file:
```
OPENROUTER_API_KEY=sk-or-v1-...
GENERATOR=openrouter
OPENROUTER_MODEL=google/lyria-3-pro-preview
```

Yes, OpenRouter key WILL work — we added support for google/lyria-3-pro-preview ($0.08) and google/lyria-3-clip-preview ($0.04).

