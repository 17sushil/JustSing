# 🎤 SingSmith — Full Product & Technical Blueprint
**"Sing anything, in any language. Get back a real song — your voice + a track built for it."**

> Prepared: 2026-10-09 · All prices/APIs verified against current (Sept–Oct 2026) sources.

---

## 1. The Core Idea (One Sentence)

A singer records themselves (any language, any skill level, no instruments, no music theory) → an AI pipeline extracts their clean voice, **detects the key, tempo, and their comfortable vocal range**, generates an accompaniment **in that key and tempo**, mixes and masters it → the user downloads a finished song.

The magic that makes it "feel so good": **the track adapts to the singer, not the other way around.** Nobody has to transpose, nobody fights a high scale, nobody learns guitar.

---

## 2. User Flow (The Happy Path)

```
1. Open app → optionally run "Find my range" (10-second vocal warm-up)
        ↓
2. Record in browser (mic) OR upload audio/video file — any language
        ↓  (live feedback while recording!)
   • Live pitch meter + "You're singing in G major"
   • Optional metronome / count-in / tap-tempo
        ↓
3. Upload → "Cooking your song…" (progress steps: Cleaning voice →
   Reading your melody → Writing the track → Tuning it to your voice → Mixing)
        ↓
4. Preview player: full mix + 2 alternate style variations
        ↓
5. Download: MP3 (free) · WAV + stems — vocals & instrumental (Pro)
   Share link · Lyrics transcript (in the sung language)
```

---

## 3. The Audio Pipeline (Heart of the App)

```
UPLOAD (audio | video | live recording)
   │
   ▼
[0] EXTRACT & PREP        ffmpeg → 48 kHz WAV, mono→dual-mono check, trim silence
   │
   ▼
[1] VOICE CLEANUP         Noise reduction (DeepFilterNet / RNNoise) +
   │                      light de-ess + gentle compression → clean dry vocal
   ▼
[2] VOCAL ISOLATION       Demucs (htdemucs_ft) → acapella
   │                      (matters if the user uploaded a video with music in it)
   ▼
[3] MUSIC ANALYSIS        librosa + Essentia + Whisper:
   │                      • BPM (onset envelope + tempo estimation)
   │                      • Key (chroma + Krumhansl–Schmuckler profiles)
   │                      • Vocal range (pYIN f0 stats → lowest/highest comfortable note)
   │                      • Loudness (LUFS), duration, energy/mood features
   │                      • Language + lyrics transcript (Whisper — any language)
   ▼
[4] TRACK GENERATION      Build a prompt from analysis + user style choice:
   │                      "acoustic guitar, warm drums, key of G, 92 BPM, Nepali
   │                       folk mood, instrumental, no vocals…"
   │                      Generate 3 variations via AI music API (see §5)
   ▼
[5] TUNE TO THE SINGER    ★ THE SECRET SAUCE ★
   │                      • Pick the generated key that best fits the singer's range
   │                        (or pitch-shift the instrumental by ±N semitones)
   │                      • Time-stretch the TRACK to the singer's detected tempo
   │                        (rubberband / ffmpeg atempo — never stretch the vocal!)
   │                      • Beat-grid align track start to first vocal onset
   ▼
[6] MIX                   Sidechain ducking (instruments dip 3–4 dB under the voice)
   │                      EQ carve (HPF instruments ~120 Hz, vocal presence pocket)
   │                      Vocal: light compression + short reverb send
   ▼
[7] MASTER                Matchering vs. a genre reference track (or ffmpeg
   │                      loudnorm 2-pass) → target −14 LUFS (streaming)
   ▼
[8] DELIVER               MP3 320 kbps + WAV + stems (vocals / instrumental)
                          + shareable player page + synced lyrics
```

**Why this works when "the melody is wrong / lyrics don't match":** we don't judge the performance. We extract the *center of gravity* of the voice (key, tempo, range, mood) and build the accompaniment around it. A wandering melody still gets a track that feels like it belongs to that voice. (Optional Pro feature: gentle, user-toggleable pitch correction on the vocal — "Studio mode".)

---

## 4. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | **Next.js (React) + Tailwind** | Fast, great recording UX, easy PWA later |
| Audio in browser | **MediaRecorder API + Web Audio API** | Native, no install |
| Live pitch detection | **Pitchy** or autocorrelate (Web Audio) | Real-time "you're in G" feedback |
| Waveforms | **wavesurfer.js** | Beautiful, battle-tested |
| Backend API | **Node/Express** or **FastAPI** | Your call; FastAPI is nicer for audio/ML glue |
| Job queue | **BullMQ + Redis** (or Celery) | Long audio jobs need async + retries |
| Database | **PostgreSQL** (Supabase or Railway) | Users, songs, jobs |
| File storage | **Cloudflare R2** (S3-compatible, ~free egress) | Audio files are big; R2 is cheapest |
| GPU worker | **Fly.io / Railway GPU** or **Replicate** | Demucs + analysis run here |
| Hosting (web) | **Vercel** | Zero-config Next.js |
| Payments | **Stripe** | Subscriptions + one-off credits |
| Auth | **Clerk** or Supabase Auth | Don't hand-roll auth |

---

## 5. APIs & Keys — The Complete Shopping List

### A. AI Music Generation (the accompaniment) — pick 1 primary + 1 backup

| Provider | What you get | Where to get the key | Price (2026) | Commercial use | Notes |
|---|---|---|---|---|---|
| **Google Lyria 3.5** (Gemini API, model `lyria-3.5`) | Full instrumental/vocal songs, 44.1 kHz, ~2 min, any style prompt | [ai.google.dev](https://ai.google.dev) → Gemini API key | **$0.08 / song** (no free tier) | Google claims no ownership; paid-tier data not used for training | ⭐ **Best price.** Cheapest official API. Output carries SynthID watermark. Duration is prompt-guided, not exact. |
| **ElevenLabs Music v2.5** | Songs with **exact duration control** (ms), WAV output, section plans | [elevenlabs.io](https://elevenlabs.io) | **$0.15 / minute** (~$0.30 per 2-min track) | Cleared on paid plans | ⭐ **Best control & licensing.** Best when you need the track to match the vocal's exact length. |
| **Mureka V9** | Top-ranked instrumental quality | Mureka developer portal | Paid API | Commercial authorization on paid output | Strong dark horse for instrumentals. |
| **Stability — Stable Audio 3** | Instrumental-only; **Small/Medium weights are open** → self-hostable | [platform.stability.ai](https://platform.stability.ai) | API credit-based; self-host free | Community License under $1M revenue | ⭐ **Best self-host option.** Run it on your own GPU, pay $0 per generation. |
| ~~Suno~~ | — | — | ~$0.10–0.55 via third parties | ❌ | **No official API.** Third-party wrappers (sunor.cc, apiframe) exist but are unofficial — industry advice: *don't build a product on them*. |
| ~~Udio~~ | — | — | — | ❌ | Downloads disabled; not usable for a product. |

**Recommendation:** Primary = **Lyria 3.5** (cheapest, official, watermark is actually a legal plus). Backup/precision = **ElevenLabs Music** (when exact duration matters). Long-term cost play = self-host **Stable Audio 3**.

### B. Vocal Separation & Audio Cleanup

| Tool | Type | Price | Notes |
|---|---|---|---|
| **Demucs (htdemucs_ft)** — self-hosted | Open source, GPU | Free (GPU time only) | ⭐ Best quality (top SDR benchmarks 2026), ~35 s per 4-min track on a decent GPU. Run on your own worker. |
| **LALAL.AI API** | REST API | ~$0.10–0.17 / min (packs from $15) | Easiest "just works" API if you don't want to run GPUs. Key at [lalal.ai](https://www.lalal.ai). |
| **StemSplit** | API | ~$0.10 / min, credits never expire | Demucs-class quality, good per-minute math. |
| **Ultimate Vocal Remover (UVR)** | Free local CLI | Free | Fallback for power users / batch. |
| **DeepFilterNet / RNNoise** | Open source | Free | Real-time noise suppression for the raw vocal (or ffmpeg `afftdn` as a cheap baseline). |

### C. Music Analysis (key / tempo / range) — all free, self-hosted

| Tool | Purpose |
|---|---|
| **librosa** (Python) | BPM (`beat_track`), key (chroma + Krumhansl–Schmuckler), onsets, MFCC/mood features. Industry standard — used by Spotify/YouTube tooling. |
| **Essentia** (C++/Python) | Richer MIR (loudness, danceability, key alternatives). Great as a second opinion. |
| **pYIN / torchcrepe** | Accurate vocal pitch tracking → singer's comfortable range (this powers "tune the track to YOUR voice"). |
| **rubberband / ffmpeg atempo** | Tempo alignment of the generated track (high-quality time-stretch). |
| **pytsmod / librosa.effects.pitch_shift** | Pitch-shift the *instrumental* into the singer's key. |

### D. Lyrics, Language & Transcription

| Tool | Purpose | Price |
|---|---|---|
| **Whisper (open-whisper / faster-whisper)** | Transcribe lyrics + auto-detect language (any language) → drives the generation prompt and the lyrics display | Free, self-hosted (tiny/base models are fast on CPU) |

### E. Mixing & Mastering

| Tool | Purpose | Price |
|---|---|---|
| **ffmpeg** (sidechain compress, EQ, loudnorm 2-pass, limiter) | The actual mix glue | Free |
| **Matchering** (Python, open source) | Reference-based mastering — matched spectral balance & loudness to a pro reference track. Won a blind test vs paid AI masters in 2026 | Free |
| **Masterchannel API** | If you ever want a hosted mastering API | from $1.50 / master |
| *(optional)* eMastered / iZotope Ozone | Reference benchmarks only | $39/mo · $219+ |

### F. Infra & Business Keys

| Service | Key from | Purpose |
|---|---|---|
| Cloudflare R2 (or AWS S3) | [dash.cloudflare.com](https://dash.cloudflare.com) | Store uploads, renders, stems |
| Stripe | [stripe.com](https://stripe.com) | Subscriptions & credits |
| Gemini API | [ai.google.dev](https://ai.google.dev) | Lyria 3.5 (also gives you Gemini for prompt-building helpers) |
| ElevenLabs | [elevenlabs.io](https://elevenlabs.io) | Music API (backup/precision) |
| Clerk / Supabase | respective dashboards | Auth + Postgres |
| Vercel + Fly.io/Railway | respective dashboards | Web hosting + GPU worker |

---

## 6. Cost Per Song (COGS) — Two Scenarios

**Scenario A — API-everything (fastest to launch):**

| Item | Cost |
|---|---|
| Lyria 3.5 (1–2 generations for variations) | $0.08–0.16 |
| LALAL.AI separation (~1 min of audio) | ~$0.10–0.17 |
| Whisper + librosa + mixing + mastering (self-hosted CPU) | ~$0.01 |
| GPU/CPU worker time + storage + bandwidth | ~$0.02 |
| **Total per finished song** | **≈ $0.20–0.35** |

**Scenario B — Self-hosted generation (scale play):**

| Item | Cost |
|---|---|
| Stable Audio 3 self-hosted generation | ~$0.02–0.05 GPU time |
| Demucs self-hosted separation | ~$0.02–0.05 GPU time |
| Everything else | ~$0.03 |
| **Total per finished song** | **≈ $0.07–0.13** |

**Pricing suggestion:** Free tier = 1 song/day, MP3 with 8 s audio watermark. Pro = $9/mo (unlimited renders, WAV + stems, no watermark, style library). At Pro usage, margin is ~10x. Even at $1/song one-off, margin is 3–5x. This business works.

---

## 7. "Make It Feel So Good" — UX Details That Matter

1. **Live feedback while recording** — pitch meter, live key readout ("You're singing in G major — nice"), waveform. Singing alone is scary; feedback makes it fun.
2. **"Find my range" onboarding** — 10-second warm-up; we learn their comfortable notes and *always* choose keys that fit. This is the killer feature for "some singers can't hit high scales."
3. **Zero music vocabulary required** — style picker is emoji/mood based: 🌸 warm acoustic · 🎸 band · 🎹 piano ballad · 🥁 beat-driven · 🕺 retro. No "chord progression" talk.
4. **Any language, truly** — Whisper detects the language; the UI, lyrics, and even the generation prompt adapt. Sing in Nepali, Hindi, Spanish, anything.
5. **Honest progress theatre** — "Cleaning your voice… Reading your melody… Writing the track… Tuning it to your voice… Mixing…" with a real progress bar. Rendering takes 60–120 s; make the wait feel like craftsmanship.
6. **Always give 3 variations** — one will feel "right." Let them A/B instantly in the player.
7. **One-click share page** — a beautiful public player (cover art, waveform, lyrics) they can send to friends.
8. **Stems download** — vocals and instrumental separately (Pro). Singers *love* this for karaoke, remixes, and practice.
9. **Optional "Studio mode"** — gentle, tasteful pitch correction + de-breath, toggleable. Never forced.
10. **Mobile-first PWA** — most users will record on their phone in a bedroom, not at a desk.

---

## 8. MVP Roadmap

| Phase | Duration | Scope |
|---|---|---|
| **0 — Validate** | 2 weeks | Landing page + waitlist + *concierge MVP*: users upload, YOU run the pipeline manually (scripts), deliver in 24 h. Proves demand before a line of app code. |
| **1 — Core pipeline** | 6–8 weeks | Upload (file) → automated pipeline (§3) → MP3 download. One style. No accounts. |
| **2 — The magic** | 4–6 weeks | In-browser recorder, live pitch/key feedback, range finder, 3 variations, style picker, accounts. |
| **3 — Delight** | 4 weeks | Stems, share pages, lyrics transcript, any-language UI, mobile PWA. |
| **4 — Monetize** | 2–3 weeks | Stripe, free tier limits, Pro plan, watermarking, basic analytics. |

**Suggested first milestone:** Phase 1. Everything else is polish on top of a working pipeline.

---

## 9. Legal & Trust (Don't Skip)

- **Licensing:** Prefer official APIs with clear commercial terms (Lyria via Gemini paid tier, ElevenLabs paid plans, Stability Community License < $1M revenue). Avoid unofficial Suno wrappers for a real product.
- **Watermarking:** Lyria output carries Google's **SynthID** watermark — good, disclose it. Consider **C2PA content credentials** on downloads.
- **Voice rights:** Users sing themselves — no voice cloning involved, so cloning consent issues don't arise. Still, add ToS: don't upload other people's recordings without rights.
- **Copyright:** The AI accompaniment is generated (no training-data issue on your side with official APIs); the user's vocal is theirs. State clearly who owns what in the ToS.
- **Privacy:** Audio is personal. Encrypt at rest, delete raw uploads after N days unless saved, GDPR-style deletion on request.

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Generated track doesn't match vocal tempo/key well | We control key (pitch-shift instrumental) and tempo (stretch track, never the vocal). This is deterministic DSP — reliable. |
| AI music quality varies | Generate 3 variations, let user pick; keep ElevenLabs as a "premium render" option. |
| Unofficial APIs rug-pull (Suno etc.) | Don't use them. Lyria/ElevenLabs/Stability are official. |
| GPU costs at scale | Start API-based; migrate generation to self-hosted Stable Audio 3 when volume justifies it. |
| Singer's recording is noisy/quiet | DeepFilterNet + normalization + compression in stage 1; show a "tip: get closer to the mic" hint based on LUFS. |
| "My melody was off and it sounds weird" | Optional gentle pitch correction (Studio mode); plus the accompaniment is key/tempo-centered on the *average* of the voice, so it's forgiving. |

---

## 11. Suggested Repo Skeleton (when we start building)

```
singsmith/
├── web/                    # Next.js app
│   ├── app/(marketing)/    # landing, pricing
│   ├── app/studio/         # recorder, live pitch, upload
│   └── app/song/[id]/      # player, share page, downloads
├── api/                    # FastAPI (or Express)
│   ├── routes/  (upload, songs, jobs, webhooks)
│   └── pipeline/           # stages 0–8 as composable steps
│       ├── extract.py  cleanup.py  separate.py
│       ├── analyze.py  generate.py  align.py
│       └── mix.py  master.py  deliver.py
├── worker/                 # GPU worker (Demucs, analysis, gen fallback)
├── infra/                  # docker-compose, fly.io, terraform-lite
└── docs/                   # this blueprint, API notes
```

---

## 12. Sources (verified Oct 2026)

- AI music model pricing & licensing (Sept 2026): [teamday.ai](https://www.teamday.ai/blog/best-ai-music-models-2026)
- Lyria 3.5 Gemini API — $0.08/song, SynthID: [cellcog.ai](https://cellcog.ai/blog/lyria-3-5/) · [aicybr.com](https://aicybr.com/blog/google-lyria-3-5-gemini-api-guide) · [mlq.ai](https://mlq.ai/news/google-releases-lyria-35-music-generation-in-gemini-and-its-api/)
- Suno/Udio API landscape (unofficial wrappers, warnings): [sunor.cc](https://sunor.cc/) · [apiframe.ai](https://apiframe.ai/models/suno) · [songcreator.pro](https://songcreator.pro/blog/ai-music-generator-pricing)
- Vocal separation benchmarks (Demucs top SDR, LALAL.AI API): [dev.to benchmark](https://dev.to/stevecase430/ai-vocal-remover-benchmark-2026-6-tools-tested-with-python-sdr-speed-hl9) · [stemsplit.io](https://stemsplit.io/blog/best-vocal-remover-tools) · [chartlex.com](https://www.chartlex.com/blog/marketing/ai-stem-separation-tools-2026)
- Key/BPM detection with librosa: [stemsplit.io](https://stemsplit.io/blog/bpm-key-detection-feature)
- Mastering (Matchering wins blind test, free): [futureproofmusicschool.com](https://futureproofmusicschool.com/blog/best-ai-tools-for-mixing-and-mastering) · [songmastr.com](https://www.songmastr.com/) · [masterchannel.ai](https://integrate.masterchannel.ai/)

---

*Next step: say the word and I'll scaffold the Phase-1 MVP — upload → pipeline → downloadable song.*

---

## 13. The Zero-Cost Edition — $0 to Build, $0 to Run an MVP

**Short answer: yes.** Every paid line item has a free replacement. The only thing money eventually buys is GPU time at scale — and by then, revenue covers it (see §6 margins).

### Free replacement for every paid item

| Paid item | $0 replacement | Trade-off |
|---|---|---|
| Lyria 3.5 ($0.08/song) | **Stable Audio Open (Small/Medium)** — Stability's open weights, self-hosted | Needs a GPU (or slow CPU); quality a notch below Lyria |
| ElevenLabs Music ($0.15/min) | **ElevenLabs free tier: 10,000 credits/month** (~tens of songs/mo) + **MusicGen / AudioLDM 2** self-hosted | Free credits are capped; MusicGen is CC-BY-NC (see caveats) |
| LALAL.AI separation (~$0.10/min) | **Demucs (htdemucs_ft)** self-hosted | Free; ~35 s/track on GPU, minutes on CPU |
| Whisper API | **faster-whisper** tiny/base, local CPU | Free; fast enough |
| librosa / pYIN / ffmpeg / Matchering | Already free | — |
| Vercel hosting | **Cloudflare Pages** (free, commercial-safe) | Edge/static hosting — fine for Next.js |
| API hosting | **Render free tier** (750 h/mo, sleeps when idle), **Fly.io free allowance**, or your own machine | Cold starts; fine for MVP |
| PostgreSQL + Auth | **Supabase free tier** (500 MB DB, 50k MAU, Auth included) — or plain SQLite | 500 MB is plenty to start |
| File storage | **Supabase Storage 1 GB free** or **Cloudflare R2 10 GB free** | — |
| Redis queue | **Upstash Redis free** (10k commands/day) — or simple DB-polled jobs | — |
| Stripe | **No monthly fee** — 2.9% + 30¢ per transaction only | $0 fixed cost even when monetizing |
| GPU for Demucs + generation | **Your own NVIDIA GPU**, **Google Colab free (T4)**, **Kaggle (~30 GPU-h/week)** | Borrowed time: Colab sessions die; not production-grade |
| Domain | Free subdomain (`*.pages.dev`, `*.onrender.com`) | Custom domain ≈ $10/yr later (optional) |

### The $0 architecture for the MVP

```
Browser (Next.js on Cloudflare Pages — free)
   │
   ▼
FastAPI (Render free tier / Fly free / your own box)
   │  jobs in DB or Upstash Redis (free)
   ▼
GPU worker (YOUR machine with an NVIDIA GPU, or a Colab/Kaggle notebook,
   exposed via a free cloudflared/ngrok tunnel)
   ├── Demucs (vocal isolation)            — free
   ├── faster-whisper (lyrics + language)  — free
   ├── librosa / pYIN (key, BPM, range)    — free
   ├── Stable Audio Open / MusicGen (track) — free
   └── ffmpeg + Matchering (mix + master)  — free
   │
   ▼
Supabase free (DB + auth + 1 GB storage)  ·  R2 free (10 GB files)
```

### Three honest caveats

1. **You need *some* GPU — borrowed is fine.** If you don't have an NVIDIA machine, use Colab/Kaggle free GPUs for the prototype, and ElevenLabs' 10k free credits/month as a quality bridge for the first real users. CPU-only generation works but takes minutes per song.
2. **Licenses:** MusicGen is **CC-BY-NC (non-commercial)** — fine for a personal MVP/demo, not for charging users. **Stable Audio Open** is free under **$1M annual revenue** (Stability AI Community License) — that's your commercial-safe zero-cost generator. Demucs (MIT), Whisper (MIT), librosa, ffmpeg, Matchering are permissively licensed. Verify each model card before launch.
3. **Quality:** self-hosted free generation is a notch below Lyria/ElevenLabs in 2026. Ship the MVP on free tooling to prove demand, then flip one config flag to paid APIs when revenue arrives.

### The path from $0 to funded

| Stage | Cost | What changes |
|---|---|---|
| Build & demo | **$0** | Everything local / free tiers |
| Soft launch (friends, ~10–50 songs/day) | **$0** | Free tiers + ElevenLabs free credits + borrowed GPU |
| First real users | ~$0–20/mo | Stripe has no fixed fee; optionally a spot GPU (~$0.20–0.40/hr) |
| Scale | revenue-funded | Paid API tier or dedicated GPU — 10x margins cover it |

**Rule: never spend a dollar before the product earns one.**

### Design rule for the zero-cost build

Write the pipeline **backend-agnostic from day one** — one config flag:

```bash
GENERATOR=stable-audio-open   # zero-cost default (self-hosted)
GENERATOR=musicgen            # zero-cost, non-commercial only
GENERATOR=elevenlabs          # paid, best duration control
GENERATOR=lyria               # paid, cheapest per song
SEPARATOR=demucs-local        # zero-cost default
SEPARATOR=lalal                # paid API
```

Upgrading from free to paid later = a one-line change, zero rewrites.
