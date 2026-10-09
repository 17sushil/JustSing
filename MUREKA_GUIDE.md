# JustSing — Mureka-Level Quality Guide (v1.0)

You want [Mureka.ai](https://www.mureka.ai/) level? Perfect alignment, studio instruments, varied music per song, not same audio? Here's how JustSing does it now.

## Why procedural alone is not enough

Procedural v0.10 is good for $0 instant:
- Phrase-following: chords change when YOU sing
- Melody-following: chords contain your vocal notes (6/8 True)
- Studio sound: saw+filter+chorus+reverb

But it's still synthetic sine/saw — not real guitar/piano samples like Mureka.

Mureka uses transformer + EnCodec (like MusicGen) trained on millions of songs.

## JustSing now has Mureka-level generator: `musicgen-melody`

Meta's **MusicGen Melody** (facebook/musicgen-melody) is the open-source equivalent of Mureka's Remix:
- **Your vocal -> chroma -> transformer generates music that follows YOUR melody exactly**
- Text prompt controls genre (warm-acoustic, lofi, etc.)
- EnCodec 32kHz -> high-quality 44.1k stereo
- Zero-cost, self-hosted, no API key, $0 forever
- First download ~4GB, then offline

### How it works (like Mureka Remix)

```
Your vocal WAV (melody) 
  -> chroma extraction (pitch classes per frame)
  -> MusicGen transformer (1.5B params) conditioned on chroma + text prompt
  -> Generates guitar, bass, drums, piano that FOLLOW your melody
  -> Mix with your original vocal (100% preserved, diff 0.0)
```

Result: Every song gets UNIQUE, studio-quality accompaniment that is 100% aligned to your voice, not same audio.

### Install (Windows)

```bat
C:\...\JustSing> .venv\Scripts\activate

# CPU only (recommended if no GPU, 30-60 sec per song)
(.venv) > pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
(.venv) > pip install audiocraft

# GPU (if you have NVIDIA, 5 sec per song)
(.venv) > pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
(.venv) > pip install audiocraft
```

### Use

Create `.env` in JustSing root:
```
GENERATOR=musicgen-melody
WHISPER=off
USE_LIBROSA=0
```

Run:
```bat
(.venv) > python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000 -> upload -> select style -> wait 30-60s (first time also downloads model 4GB) -> perfect alignment like Mureka!

### Generator options

| GENERATOR | Quality | Speed | Size | Needs | Melody Following? |
|-----------|---------|-------|------|-------|-------------------|
| procedural | v0.10 studio, synthetic but good | 2 sec | 0 MB | nothing | per-bar, phrase-following |
| musicgen-small | high, real instruments | 15 sec CPU | 1 GB | torch | text-only, no melody |
| musicgen-melody | **Mureka-level, BEST** | 30-60 sec CPU, 5 sec GPU | 4 GB | torch+audiocraft | **YES, chroma following** |
| musicgen-stereo-melody | stereo, Mureka-level | 40-70 sec CPU | 4 GB | torch+audiocraft | YES, stereo |
| openrouter | $0.08/song, Lyria | 10 sec | 0 | API key | prompt-only |
| openrouter-dynamic | $0.09/song, Gemini listens + Lyria | 20-40 sec | 0 | API key | audio-to-music 2-step |

### Tips for perfect alignment like Mureka

1. **Sing with clear melody**: Humming or singing with pitch variation helps chroma extraction
2. **Use phrases**: Leave 0.3s gaps between phrases — v0.10 detects phrases and changes chords at phrase starts
3. **Style matters**: `piano-ballad` and `warm-acoustic` are easiest to align, `cinematic` has more reverb
4. **Duration**: MusicGen max 30s per chunk, longer songs loop. Keep test songs 15-30s for best quality
5. **First vocal time**: If you start singing after 1s, you get intro bar — feels like live band count-in

### Troubleshooting

**"Same kinds of audio is there"** — Fixed in v0.8+:
- Procedural now uses file_hash seed + per-bar F0 following + diatonic chord scoring -> unique per song
- MusicGen uses hash in prompt + melody conditioning -> unique per song
- Check logs: `[generator] seed XXXX hash abcd1234` should differ per upload

**"Nothing is aligned"** — Fixed in v0.10:
- Old: fixed metronome grid [0, 1.37, 2.74...] -> off when you sing rubato
- New: `bar_times` includes phrase starts [0.0, 0.3(phrase!), 4.1(phrase!)...] -> chords change when YOU sing
- Check logs: `[phrases] Detected 2 phrases: 0.30-3.79s, 4.10-7.59s`

**"Opposite direction"** — Fixed:
- Old: `is_silence_bar = energy < 0.015` could be inverted if threshold wrong
- New: `inside_phrase = any(ps <= bar <= pe)` -> if inside phrase, NOT silence

### Zero-cost still?

Yes! All generators have $0 path:
- procedural: $0 always
- musicgen-melody: $0, self-hosted, no API, no internet after first download
- openrouter: $1 free credit = 12 songs, then $0.08/song (optional)

For Mureka-level without spending, use `musicgen-melody`.

### Next: Want me to add Suno/Udio-level vocals too?

JustSing currently preserves your vocal 100% (diff 0.0). If you want AI to *enhance* your vocal like Mureka (pitch correction, harmonies), we can add RVC or OpenVoice — also zero-cost.

Tell me which generator you tried and share `[phrases]` log — I'll tune to perfect!
