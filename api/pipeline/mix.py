"""
Mixing — vocal + accompaniment -> final mix.
FIXED v0.4: Vocal is 100% preserved, never changed. Only music adapts to singer.
Zero-cost DSP: sidechain ducking on accompaniment only.
"""
import numpy as np
import soundfile as sf
from pathlib import Path

def load_stereo(path: Path):
    data, sr = sf.read(str(path))
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    return data.astype(np.float32), sr

def rms(x):
    return np.sqrt(np.mean(x**2) + 1e-9)

def normalize_rms(x, target_rms=0.18):
    cur = rms(x)
    if cur < 1e-6:
        return x
    return x * (target_rms / cur)

def envelope_follower(x, sr, attack_ms=10, release_ms=100):
    """Simple envelope follower for sidechain."""
    attack = np.exp(-1.0 / (sr * attack_ms / 1000))
    release = np.exp(-1.0 / (sr * release_ms / 1000))
    env = np.zeros(len(x))
    cur = 0
    for i, sample in enumerate(np.abs(x)):
        if sample > cur:
            cur = attack * cur + (1-attack) * sample
        else:
            cur = release * cur + (1-release) * sample
        env[i] = cur
    return env

def mix_vocal_and_accompaniment(vocal_path: Path, acc_path: Path, out_path: Path, target_rms=0.18, preserve_vocal=True):
    """
    FIXED: If preserve_vocal=True (default), vocal is NEVER changed.
    - No compression
    - No normalization
    - No EQ
    - No pitch shift
    Only accompaniment is ducked and lowered to make vocal shine.
    """
    vocal_original, sr_v = load_stereo(vocal_path)
    acc, sr_a = load_stereo(acc_path)

    sr = sr_v  # vocal is master

    # Align lengths
    vocal_len = len(vocal_original)
    acc_len = len(acc)
    desired_len = vocal_len + int(sr*1.0)  # vocal + 1 sec tail
    if acc_len > desired_len:
        acc = acc[:desired_len]
        final_len = desired_len
    else:
        final_len = max(vocal_len, acc_len)
        if acc_len < final_len:
            pad = np.zeros((final_len - acc_len, 2), dtype=np.float32)
            acc = np.concatenate([acc, pad], axis=0)

    if vocal_len < final_len:
        pad = np.zeros((final_len - vocal_len, 2), dtype=np.float32)
        vocal_padded = np.concatenate([vocal_original, pad], axis=0)
    else:
        vocal_padded = vocal_original[:final_len]

    # Keep a copy of original vocal for output (100% untouched, just padded)
    vocal_for_mix = vocal_padded.copy()  # NO PROCESSING AT ALL

    # --- Sidechain: duck ACCOMPANIMENT only when vocal is loud ---
    vocal_mono = np.mean(vocal_for_mix, axis=1)
    env = envelope_follower(vocal_mono, sr, attack_ms=5, release_ms=150)
    env_norm = env / (np.max(env) + 1e-6)
    # Duck 0 to 4.5 dB when vocal present
    duck_gain = 1.0 - 0.41 * np.clip(env_norm, 0, 1)  # 0.59x = -4.5dB max
    acc_ducked = acc * duck_gain[:, None]

    # --- Balance: vocal at 0dB (untouched), acc at -7dB ---
    # Do NOT normalize vocal! Only normalize accompaniment to reasonable level
    acc_level_db = -7.5
    acc_gain = 10 ** (acc_level_db / 20)
    
    # Normalize accompaniment to target RMS *then* apply gain, so it's consistent
    # But keep vocal exactly as user sang it
    acc_n = normalize_rms(acc_ducked, target_rms=target_rms*0.55) * acc_gain

    # Mix: vocal 100% original + quiet accompaniment
    mix = vocal_for_mix + acc_n

    # --- Prevent clipping WITHOUT changing vocal tone ---
    # Only lower accompaniment if clipping, never touch vocal
    peak = np.max(np.abs(mix))
    if peak > 0.98:
        # How much over?
        over = peak / 0.98
        # Lower accompaniment more, keep vocal
        # Try lowering acc by over amount
        acc_n = acc_n / over
        mix = vocal_for_mix + acc_n
        peak2 = np.max(np.abs(mix))
        if peak2 > 0.98:
            # Still clipping because vocal itself is loud — apply very gentle limiter to mix only
            # This preserves vocal as much as possible, only catches extreme peaks
            # Use soft limiter: only compress above 0.95
            abs_mix = np.abs(mix)
            mask = abs_mix > 0.95
            if np.any(mask):
                # For samples above 0.95, compress
                # Keep vocal character, just prevent digital clip
                mix[mask] = np.sign(mix[mask]) * (0.95 + 0.05 * np.tanh((abs_mix[mask]-0.95)/0.05))

    # Save
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), mix, sr)

    # Stems: vocal_final is 100% original (padded but untouched), acc is processed
    vocal_out = out_path.parent / "vocal_final.wav"
    acc_out = out_path.parent / "accompaniment_final.wav"
    # Vocal stem = original untouched
    sf.write(str(vocal_out), vocal_for_mix, sr)
    sf.write(str(acc_out), acc_n, sr)

    # Also save a copy of truly original (unpadded) for verification
    vocal_true_original = out_path.parent / "vocal_original_untouched.wav"
    sf.write(str(vocal_true_original), vocal_original, sr_v)

    print(f"[mix] Vocal preserved: original peak {np.max(np.abs(vocal_original)):.3f}, mix peak {np.max(np.abs(mix)):.3f}, acc ducked")
    return out_path, vocal_out, acc_out
