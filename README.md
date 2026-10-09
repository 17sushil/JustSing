# JustSing — Sing Anything, Get a Finished Song 🎤

**Sing in any language. No instruments. No music theory. Get back a studio-quality song where the track adapts to YOUR voice.**

> Built for people who love singing but can't afford music production or don't have time to learn instruments.

![Zero-Cost](https://img.shields.io/badge/cost-%240%20to%20build-brightgreen) ![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green) ![License](https://img.shields.io/badge/license-MIT-purple)

### ✨ Demo (Zero-Cost MVP v0.2)

- **Upload** audio/video (MP3, WAV, M4A, MP4, WebM) **or Record** in browser
- **Any language** — Nepali, Hindi, English, Spanish, etc.
- **We detect:** Key (Krumhansl-Schmuckler chroma), BPM (autocorrelation), Vocal Range (F0 tracking), Language (Whisper optional)
- **We compose:** Accompaniment *in your key & tempo* — you never fight a scale you can't reach
- **We mix & master:** Sidechain ducking, -14 LUFS loudness, MP3 320k + WAV + stems

### 🎧 Styles (Procedural Synth — $0)

- 🎸 **Warm Acoustic** — Guitar + soft drums
- 🌙 **LoFi Chill** — Mellow, vinyl crackle
- 🎹 **Piano Ballad** — Intimate piano
- ✨ **Indie Pop** — Bright, upbeat
- 🎬 **Cinematic** — Epic, spacious

All generated locally with pure `numpy/scipy` — no API keys, no GPU needed.

### 🚀 Quick Start (Zero Cost)

```bash
git clone https://github.com/17sushil/JustSing.git
cd JustSing

pip install -r requirements.txt
# optional: pip install -r requirements-optional.txt  # for Whisper lyrics

GENERATOR=procedural uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# open http://localhost:8000
```

Upload a singing clip → watch progress → download finished song.

### 🔌 Upgrade Path (One Env Var)

The pipeline is backend-agnostic. Flip one flag for higher quality:

```bash
# Free (default)
GENERATOR=procedural

# Paid, studio quality
GENERATOR=elevenlabs ELEVENLABS_API_KEY=...  # $0.15/min, 10k free credits/month
GENERATOR=lyria GEMINI_API_KEY=...           # $0.08/song via ai.google.dev
GENERATOR=stable-audio-open                  # self-hosted, free < $1M revenue
```

| Generator | Cost | Quality | API Key From |
|---|---|---|---|
| procedural | $0 | Good (synth) | None |
| stable-audio-open | $0 self-hosted | Very Good | platform.stability.ai |
| Lyria 3.5 (Google) | $0.08/song | Excellent | ai.google.dev |
| ElevenLabs Music v2.5 | $0.15/min | Excellent | elevenlabs.io |

### 🏗️ Architecture

```
Browser (Tailwind UI + MediaRecorder)
  ↓
FastAPI (api/main.py) — /api/upload, /api/jobs/{id}
  ↓
Pipeline (9 stages):
  1. extract (ffmpeg via imageio-ffmpeg)
  2. analyze (librosa optional, else numpy fallback)
  3. generate accompaniment (procedural OR API)
  4. tune track to singer (pitch-shift/time-stretch instrumental)
  5. mix (sidechain ducking 3-4dB, EQ carve, compression)
  6. master (RMS -14 LUFS + limiter OR ffmpeg loudnorm)
  7. encode MP3 320k + WAV + stems
  ↓
storage/renders/{job_id}/final.mp3
```

See [`singsmith-blueprint.md`](./singsmith-blueprint.md) for full product & technical blueprint (COGS, API pricing, 5-phase roadmap).

### 📁 Project Structure

```
JustSing/
  api/
    main.py              # FastAPI + frontend serving (fixed v0.2)
    config.py            # env + ffmpeg binary
    storage.py           # job management
    pipeline/
      extract.py         # ffmpeg extract + MP3 encode
      analysis.py        # key/BPM/range detection
      generator_procedural.py  # $0 synth: drums, bass, chords, arp
      generator_api.py   # wrappers for Lyria/ElevenLabs with fallback
      mix.py             # sidechain + balance
      master.py          # RMS + limiter
      pipeline.py        # orchestrator
  web/
    index.html           # polished UI v0.2 (fixed sandbox routing)
    app.js               # vanilla JS, drag-drop, recorder, polling
  requirements.txt       # core deps (all free)
  .env.example           # config template
```

### 🌐 Deploy Free

- **Frontend:** Cloudflare Pages (free) — drag `web/` folder
- **API:** Render free tier (750h/mo) or Fly.io free allowance
- **DB/Auth/Storage:** Supabase free (500MB DB, 1GB storage)
- **Queue:** Upstash Redis free (10k cmds/day) or DB polling
- **Total:** $0/month to start, Stripe has no monthly fee (2.9% + 30¢ only when you earn)

### 🧪 Tested

```
✅ warm-acoustic — 8s vocal → 8s song (C major, 177 BPM, 255-402 Hz)
✅ lofi-chill, piano-ballad, indie-pop, cinematic — all MP3+WAV+stems
```

### 📜 License

MIT — Procedural generator is free forever. See licenses for optional generators:
- Stable Audio Open: Community License (free < $1M revenue)
- MusicGen: CC-BY-NC (non-commercial, demo only)
- Lyria/ElevenLabs: Paid API, commercial-safe on paid tiers

### 🙏 For Singers

You don't need to be perfect. Off-key is okay. We tune the *track* to you, never your voice. Sing in any language, any melody — JustSing makes it a finished song.

---

**Built in Kathmandu with ❤️ for singers who can't afford a studio.**

Want to contribute? Open an issue or PR.
