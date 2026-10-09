"""
Mixing — vocal + accompaniment -> final mix.
Zero-cost DSP: sidechain ducking, EQ carve, compression, reverb send (simple).
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

def mix_vocal_and_accompaniment(vocal_path: Path, acc_path: Path, out_path: Path, target_rms=0.18):
    vocal, sr_v = load_stereo(vocal_path)
    acc, sr_a = load_stereo(acc_path)

    # Ensure same SR (assume 44.1k from pipeline, but resample if needed via simple interp)
    if sr_v != sr_a:
        # For MVP, assume same (both from our pipeline) — else trim
        sr = sr_v
    else:
        sr = sr_v

    # Align lengths: pad shorter with silence, trim longer to vocal length + 0.8s tail
    vocal_len = len(vocal)
    acc_len = len(acc)
    # We want final length = max(vocal, acc) but vocal is master
    final_len = max(vocal_len, acc_len)
    # If acc longer, trim to vocal + 1 sec tail
    desired_len = vocal_len + int(sr*1.0)
    if acc_len > desired_len:
        acc = acc[:desired_len]
        final_len = desired_len
    else:
        # pad acc if shorter
        if acc_len < final_len:
            pad = np.zeros((final_len - acc_len, 2), dtype=np.float32)
            acc = np.concatenate([acc, pad], axis=0)
    if vocal_len < final_len:
        pad = np.zeros((final_len - vocal_len, 2), dtype=np.float32)
        vocal = np.concatenate([vocal, pad], axis=0)

    # --- Vocal processing: light compression + high-pass via simple DC removal + de-ess-ish
    # Normalize vocal to target RMS first
    vocal_mono_for_env = np.mean(vocal, axis=1)
    # Simple compression: reduce peaks above threshold
    thresh = np.percentile(np.abs(vocal_mono_for_env), 85)
    ratio = 3.0
    # Apply soft compression
    vocal_compressed = vocal.copy()
    for ch in range(2):
        # simple: if abs > thresh, compress
        mask = np.abs(vocal[:, ch]) > thresh
        # compressed = thresh + (x - thresh)/ratio
        sign = np.sign(vocal[:, ch])
        over = np.abs(vocal[:, ch]) - thresh
        vocal_compressed[mask, ch] = sign[mask] * (thresh + over[mask]/ratio)

    vocal = vocal_compressed

    # --- Sidechain ducking: duck accompaniment when vocal is loud
    # Compute vocal envelope (mono)
    env = envelope_follower(vocal_mono_for_env, sr, attack_ms=5, release_ms=150)
    # Normalize env 0-1
    env_norm = env / (np.max(env) + 1e-6)
    # Ducking amount: up to 4 dB reduction when vocal present
    # gain = 1 - 0.4*env (when env high, gain ~0.6)
    duck_gain = 1.0 - 0.37 * np.clip(env_norm, 0, 1)
    # Smooth duck_gain
    # Apply to accompaniment
    acc_ducked = acc * duck_gain[:, None]

    # --- EQ carve: simple — reduce acc low-mids where vocal sits (300-3000 Hz)
    # For MVP, simple volume balance: vocal louder, acc quieter
    vocal_level = 0.0  # dB
    acc_level_db = -7.0  # accompaniment 7 dB below vocal
    acc_gain = 10 ** (acc_level_db / 20)

    # Normalize both to target RMS before mixing
    vocal_n = normalize_rms(vocal, target_rms=target_rms)
    acc_n = normalize_rms(acc_ducked, target_rms=target_rms*0.6) * acc_gain

    # Mix
    mix = vocal_n * (10 ** (vocal_level/20)) + acc_n

    # Prevent clipping: simple limiter
    peak = np.max(np.abs(mix))
    if peak > 0.95:
        mix = mix * (0.95 / peak)

    # Also create instrumental-only and vocal-only normalized versions for stems
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), mix, sr)

    # Save stems alongside
    vocal_out = out_path.parent / "vocal_final.wav"
    acc_out = out_path.parent / "accompaniment_final.wav"
    sf.write(str(vocal_out), vocal_n, sr)
    sf.write(str(acc_out), acc_n, sr)

    return out_path, vocal_out, acc_out
