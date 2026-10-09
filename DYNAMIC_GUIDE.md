# JustSing Dynamic Mode — True Voice-Adaptive (Like Sora)

## Why same music before?

Old `GENERATOR=openrouter` only sent TEXT prompt (key, BPM) to Lyria. Same key/BPM = same music from Lyria (deterministic).

## New: `GENERATOR=openrouter-dynamic` — OpenRouter LISTENS to your voice

### How it works (2-step):

```
Your vocal WAV (actual audio)
   ↓ base64 encode
OpenRouter → google/gemini-2.5-flash (audio input model) — LISTENS
   ↓ analyzes: melody contour, rhythm, dynamics, emotion, phrasing
Detailed adaptive prompt (unique to YOUR voice)
   ↓
OpenRouter → google/lyria-3-pro-preview (Lyria) — generates music that FOLLOWS voice
   ↓
Accompaniment that truly fits your singing
   ↓
Mix with your 100% untouched vocal
```

### Cost:

- Step 1 (Gemini analysis): ~$0.002-0.01 per song (audio input)
- Step 2 (Lyria music): $0.08/song (pro) or $0.04/clip
- Total: ~$0.09/song
- Free: OpenRouter gives $1 free on signup = ~11 dynamic songs

### Setup in VS Code:

1. Get OpenRouter key: https://openrouter.ai/settings/keys → Create Key, set limit $1

2. Create `.env` file in JustSing root:

```
GENERATOR=openrouter-dynamic
OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY
OPENROUTER_MODEL=google/lyria-3-pro-preview
WHISPER=off
```

3. Run:

```bash
pip install -r requirements.txt
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Open http://localhost:8000 → upload → watch logs:

```
[openrouter-dynamic] Step 1: Analyzing voice with google/gemini-2.5-flash...
[openrouter-dynamic] Analysis result: ANALYSIS: This voice is intimate with rising melody...
[openrouter-dynamic] Generated adaptive prompt: warm acoustic... for mid-range voice...
[openrouter-dynamic] Step 2: Generating music with google/lyria-3-pro-preview...
```

Each upload now gets UNIQUE music that follows YOUR voice contour, not just key/BPM.

### Comparison:

| Mode | How it works | Cost | Truly dynamic? | Same prompt = same music? |
|------|--------------|------|----------------|---------------------------|
| procedural | Local synth, hash seed | $0 | Yes (varied per hash) | No (seed varies) |
| openrouter | Prompt (key/BPM) → Lyria | $0.08 | Partially (prompt varies) | Sometimes yes if same key/BPM |
| openrouter-dynamic | Audio → Gemini → Lyria | $0.09 | **YES — listens to voice** | No — audio different = music different |
| elevenlabs | Prompt → ElevenLabs Music | $0.15/min | Partially | Sometimes |

### If still same music with dynamic:

1. Check analysis: In UI, Key/BPM/file_hash should differ per song. If same, your singing may be too similar or too short (<3 sec).
2. Check logs: Prompt should be different per song. If same, file_hash may be same (same file uploaded twice).
3. Try longer recording (10+ sec) with varied melody — more for Gemini to analyze.
4. Try different style: warm-acoustic vs cinematic gives different mood.

### Fallback:

If OpenRouter dynamic fails (no credits, no audio chunks), JustSing auto-falls back to procedural which is guaranteed varied per hash (seeded).

---

**You wanted Sora-like — now you have it. OpenRouter actually listens.**
