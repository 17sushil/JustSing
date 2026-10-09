# JustSing — Free API Keys Guide

Yes, **OpenRouter API key WILL work** for JustSing! And you can get it for free.

## Quick Answer

| API | Free? | How much free? | Will it work for JustSing? | How to set |
|-----|-------|----------------|----------------------------|------------|
| **OpenRouter** | ✅ Yes | **$1 free credit** on signup + free models | ✅ **YES — fully supported now!** | `OPENROUTER_API_KEY=sk-or-...` + `GENERATOR=openrouter` |
| **ElevenLabs** | ✅ Yes | **10,000 credits/month** (~10-20 songs) | ✅ Yes | `ELEVENLABS_API_KEY=...` + `GENERATOR=elevenlabs` |
| **Google Gemini (Lyria direct)** | ✅ Partial | Free tier for Gemini, but Lyria $0.08/song | ✅ Yes, but needs paid | `GEMINI_API_KEY=...` + `GENERATOR=lyria` |
| **Procedural (default)** | ✅ Yes | **Infinite, $0 forever** | ✅ Yes (default) | `GENERATOR=procedural` (no key) |

## 1) OpenRouter — Recommended Free Path ($1 free)

**Why OpenRouter?**
- One key for 300+ models
- Supports Google Lyria music generation via `google/lyria-3-pro-preview` ($0.08/song) and `google/lyria-3-clip-preview` ($0.04/clip)
- $1 free credit = ~12 songs at $0.08 or 25 clips at $0.04
- Also has **completely free** music models like `minimax/music-2.6-free` (when available)

**How to get FREE key:**

1. Go to https://openrouter.ai/ → Sign Up (GitHub/Google)
2. Go to https://openrouter.ai/settings/keys → **Create Key**
3. Copy key starting with `sk-or-v1-...`
4. (Optional) Add $5 credit later if you want more — but start with free $1

**How to use in JustSing (VS Code):**

Option A — `.env` file:
```bash
# Create .env file in JustSing folder
echo "OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY_HERE" > .env
echo "GENERATOR=openrouter" >> .env
echo "OPENROUTER_MODEL=google/lyria-3-pro-preview" >> .env
```

Option B — Direct env var (Windows PowerShell):
```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-YOUR_KEY"
$env:GENERATOR="openrouter"
$env:OPENROUTER_MODEL="google/lyria-3-pro-preview"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Option B — Mac/Linux:
```bash
OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY GENERATOR=openrouter OPENROUTER_MODEL=google/lyria-3-pro-preview python -m uvicorn api.main:app --port 8000 --reload
```

Option C — VS Code launch.json:
Edit `.vscode/launch.json`, add to env:
```json
"OPENROUTER_API_KEY": "sk-or-v1-YOUR_KEY",
"GENERATOR": "openrouter",
"OPENROUTER_MODEL": "google/lyria-3-pro-preview"
```
Then press F5.

**Which OpenRouter model to pick?**

```bash
# Best quality, $0.08/song, 2 min max (recommended)
OPENROUTER_MODEL=google/lyria-3-pro-preview

# Cheaper, $0.04/clip, shorter (30s clips)
OPENROUTER_MODEL=google/lyria-3-clip-preview

# Try free music model (if available, check https://openrouter.ai/models?search=music)
OPENROUTER_MODEL=minimax/music-2.6-free
```

Check pricing live: https://openrouter.ai/google/lyria-3-pro-preview

## 2) ElevenLabs — 10k Free Credits/Month

1. Sign up at https://elevenlabs.io/
2. Go to https://elevenlabs.io/app/settings/api-keys → Create key
3. You get **10,000 credits free every month** — no card needed

Set:
```bash
GENERATOR=elevenlabs
ELEVENLABS_API_KEY=your_key
```

## 3) Procedural — $0 Forever (No Key)

Default. Works offline. No signup. Good for MVP, not as realistic as Lyria.

```bash
GENERATOR=procedural
# no keys needed
```

## How JustSing Uses Your Key

In `api/pipeline/generator_api.py`:

- If `GENERATOR=openrouter` and `OPENROUTER_API_KEY` set → calls `https://openrouter.ai/api/v1/chat/completions` with `model=google/lyria-3-pro-preview`, `modalities=["text","audio"]`, `stream=True`, collects base64 audio chunks, saves MP3
- If fails → automatically falls back to procedural (so your app never crashes)

## Test Your Key

```bash
# Test OpenRouter key directly
curl https://openrouter.ai/api/v1/models -H "Authorization: Bearer $OPENROUTER_API_KEY" | head -20

# Test music generation (will cost $0.04-$0.08)
curl -F "file=@test.wav" -F "style=warm-acoustic" http://localhost:8000/api/upload
# Check logs for "[openrouter] Calling model=..."
```

## FAQ

**Q: Will OpenRouter API key work?**
A: YES! We just added full support in v0.3. Set `GENERATOR=openrouter` + `OPENROUTER_API_KEY`.

**Q: Is it really free?**
A: OpenRouter gives $1 free on signup. Lyria costs $0.04-$0.08 per song, so free credit = 12-25 songs. After that, add $5.

**Q: What about completely free music (no cost ever)?**
A: Use `GENERATOR=procedural` (built-in) or try `OPENROUTER_MODEL=minimax/music-2.6-free` if available on OpenRouter free tier.

**Q: Which is best quality?**
A: Lyria via OpenRouter (`google/lyria-3-pro-preview`) > ElevenLabs > procedural.

**Q: I set key but still get procedural?**
A: Check logs. If you see `[generator] openrouter failed (...) falling back to procedural`, your key may be invalid or out of credits. Check https://openrouter.ai/settings/keys and https://openrouter.ai/activity

## Security

- Never commit `.env` to GitHub (it's in `.gitignore`)
- Use `.env.example` as template
- For production, set env vars on Render/Fly.io dashboard, not in code

---

**You now have 3 free paths. Start with procedural ($0), then upgrade to OpenRouter ($1 free) when you want studio quality.**

## 4) OpenRouter Dynamic — TRUE Audio-to-Music (NEW v0.6, Like Sora)

**Problem with old openrouter:** Prompt-only = same prompt = same music.

**Solution — openrouter-dynamic (2-step, truly dynamic):**

Step 1: Your actual vocal WAV (base64) → Gemini 2.5 Flash via OpenRouter (audio input model) → AI LISTENS and analyzes melody contour, rhythm, dynamics, emotion
Step 2: Detailed adaptive prompt → Lyria 3 Pro via OpenRouter → music that FOLLOWS your voice

Cost: ~$0.01 analysis + $0.08 music = $0.09/song. $1 free = ~11 dynamic songs.

**Set:**
```bash
GENERATOR=openrouter-dynamic
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=google/lyria-3-pro-preview
```

**How it differs:**
- `openrouter` = prompt-based: key/BPM/range + hash → Lyria (fast, $0.08, but same key/BPM can give similar music)
- `openrouter-dynamic` = audio-to-music: actual audio → Gemini analyzes → Lyria (slower ~20-40s, $0.09, truly unique per voice, like Sora)

**Use dynamic when:** You want music that truly follows your vocal melody and emotion, not just key/BPM.

