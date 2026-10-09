# ElevenLabs Free Key — 10,000 Credits/Month for JustSing

ElevenLabs gives **10,000 free credits every month** — no credit card needed. That's ~10-20 full songs.

## 1) Get Free Key

1. Go to https://elevenlabs.io/ → **Sign Up** (free)
2. Verify email
3. Go to https://elevenlabs.io/app/settings/api-keys
4. Click **Create API Key** → Copy key starting with `sk_...`
5. Check credits: https://elevenlabs.io/app/settings/usage → you should see 10,000 free

## 2) How JustSing Uses It

JustSing calls:
```
POST https://api.elevenlabs.io/v1/music
Headers: xi-api-key: YOUR_KEY
Body: {
  "prompt": "warm acoustic instrumental, C major, 90 BPM, major key, warm backing track...",
  "music_length_ms": 30000
}
```

- Exact duration control (perfect for matching your vocal length)
- Instrumental only (no AI vocals, just accompaniment)
- MP3 returned, saved as `accompaniment_raw.wav` → mixed with your voice

Cost: ~$0.15/min = ~150 credits/min. 10k credits = ~66 min of music/month = ~20 songs of 3 min each.

## 3) Set in VS Code (Local Laptop)

### Windows PowerShell:
```powershell
cd JustSing
.venv\Scripts\activate
$env:ELEVENLABS_API_KEY="sk_...your_key..."
$env:GENERATOR="elevenlabs"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Mac/Linux:
```bash
cd JustSing
source .venv/bin/activate
ELEVENLABS_API_KEY=sk_...your_key GENERATOR=elevenlabs python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### .env file (recommended, so you don't type every time):
Create file `.env` in JustSing folder:
```
ELEVENLABS_API_KEY=sk_...your_key...
GENERATOR=elevenlabs
```
Then just run:
```bash
python -m uvicorn api.main:app --port 8000 --reload
```

### VS Code F5:
Edit `.vscode/launch.json`:
```json
{
  "name": "SingSmith API (ElevenLabs Free 10k)",
  "type": "debugpy",
  "request": "launch",
  "module": "uvicorn",
  "args": ["api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
  "env": {
    "GENERATOR": "elevenlabs",
    "ELEVENLABS_API_KEY": "sk_...your_key...",
    "PYTHONPATH": "${workspaceFolder}"
  }
}
```
Press F5.

## 4) Test Your Key

```bash
# Test credits
curl -H "xi-api-key: YOUR_KEY" https://api.elevenlabs.io/v1/user

# Should return JSON with subscription and character limit

# Test music generation (costs credits)
curl -X POST https://api.elevenlabs.io/v1/music \
  -H "xi-api-key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"warm acoustic guitar instrumental, C major, 90 BPM","music_length_ms":10000}' \
  --output test.mp3
```

If you get `401` → key wrong
If `429` or `quota_exceeded` → free credits used up (wait next month or add $5)

## 5) Free Tier Tips

- **10k credits resets monthly** — set calendar reminder
- **Shorter songs = less credits** — 30 sec vocal = 30 sec music = ~75 credits
- **Procedural fallback** — if ElevenLabs fails (no credits), JustSing auto-falls back to procedural synth ($0), so app never crashes
- **Combine with OpenRouter** — Use OpenRouter $1 free for Lyria when ElevenLabs credits run out

## 6) Cost After Free

- Free: 10k/month
- Starter: $5/month → 30k credits
- Creator: $22/month → 100k credits
- Still cheap: $0.15/min vs hiring musicians $100+/song

## 7) Security

- Never commit `.env` to GitHub (it's in `.gitignore`)
- If you accidentally push key, delete it at https://elevenlabs.io/app/settings/api-keys and create new one
- For production (Render/Fly.io), set env var in dashboard, not in code

## 8) Which Generator to Choose?

| Generator | Free Amount | Quality | Best For |
|-----------|-------------|---------|----------|
| procedural | Infinite $0 | Good (synth) | MVP, offline, no signup |
| elevenlabs | 10k/mo free | Excellent | Best free realistic, exact duration |
| openrouter (Lyria) | $1 free = 12 songs | Excellent | Cheapest paid, $0.08/song |

**Recommendation:** Start with `procedural` (no key), then add `elevenlabs` free key for studio quality. Keep `openrouter` as backup.

---

**You now have studio-quality accompaniment for free every month.**
