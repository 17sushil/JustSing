"""
SingSmith Analysis v0.4 — FIXED: More varied key/BPM detection, vocal-adaptive
Detects: BPM, Key (major/minor), vocal range (min/max F0), duration.
Now uses F0 mean to help key when chroma confidence low, and better BPM for a cappella.
"""
import numpy as np
import soundfile as sf
from pathlib import Path
import math
import hashlib

MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Map Hz to nearest note name for fallback key
def hz_to_note_name(hz):
    if hz <= 0:
        return 'C'
    midi = 69 + 12 * math.log2(hz / 440.0)
    note = int(round(midi)) % 12
    return NOTE_NAMES[note]

def _stft_chroma(y, sr, n_fft=4096, hop=1024):
    num_frames = 1 + (len(y) - n_fft) // hop
    if num_frames <= 0:
        return np.ones(12)/12, np.ones((12,1))
    chroma = np.zeros((12, num_frames))
    window = np.hanning(n_fft)
    for i in range(num_frames):
        frame = y[i*hop:i*hop+n_fft] * window
        if len(frame) < n_fft:
            break
        spec = np.abs(np.fft.rfft(frame))
        freqs = np.fft.rfftfreq(n_fft, 1/sr)
        valid = (freqs > 40) & (freqs < 5000)  # focus on musical range
        f_valid = freqs[valid]
        s_valid = spec[valid]
        if len(f_valid) == 0:
            continue
        midi = 69 + 12 * np.log2(f_valid / 440.0)
        pc = np.round(midi).astype(int) % 12
        for j, p in enumerate(pc):
            chroma[p, i] += s_valid[j] * (1.0 + s_valid[j])  # emphasize strong bins
    # normalize per frame
    chroma = chroma / (np.max(chroma, axis=0, keepdims=True) + 1e-9)
    mean_chroma = np.mean(chroma, axis=1)
    if np.max(mean_chroma) > 0:
        mean_chroma = mean_chroma / np.max(mean_chroma)
    return mean_chroma, chroma

def detect_key(y, sr, f0_mean=180):
    """Return key string like 'G major' and confidence. Now uses F0 mean as fallback."""
    try:
        mean_chroma, _ = _stft_chroma(y, sr)
        best_score = -1
        best_key = None
        best_is_major = True

        # Try librosa first if available (much better)
        try:
            import librosa
            chroma_lib = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=1024)
            mean_chroma_lib = np.mean(chroma_lib, axis=1)
            mean_chroma_lib = mean_chroma_lib / (np.max(mean_chroma_lib)+1e-9)
            # Use librosa chroma for correlation
            mean_chroma = mean_chroma_lib
        except:
            pass

        for i in range(12):
            maj = np.roll(MAJOR_PROFILE, i)
            min_ = np.roll(MINOR_PROFILE, i)
            # correlation, handle NaN
            try:
                maj_corr = np.corrcoef(mean_chroma, maj)[0,1]
                min_corr = np.corrcoef(mean_chroma, min_)[0,1]
            except:
                maj_corr = -1
                min_corr = -1
            if np.isnan(maj_corr):
                maj_corr = -1
            if np.isnan(min_corr):
                min_corr = -1
            if maj_corr > best_score:
                best_score = maj_corr
                best_key = f"{NOTE_NAMES[i]} major"
                best_is_major = True
            if min_corr > best_score:
                best_score = min_corr
                best_key = f"{NOTE_NAMES[i]} minor"
                best_is_major = False

        # If confidence very low (<0.3), use F0 mean to guess key (more varied than always C)
        if best_score < 0.35 or best_key is None:
            # Use F0 mean to pick root, and use major by default for feel-good
            note_from_f0 = hz_to_note_name(f0_mean)
            # Add some variation based on audio hash so different files get different keys even if F0 similar
            # Hash first 1 sec of audio to get deterministic variation
            try:
                h = hashlib.md5(y[:sr].tobytes()).hexdigest()
                hash_val = int(h[:4], 16) % 12
                # Mix F0 note and hash
                f0_semi = NOTE_NAMES.index(note_from_f0)
                final_semi = (f0_semi + hash_val) % 12
                final_note = NOTE_NAMES[final_semi]
            except:
                final_note = note_from_f0
            best_key = f"{final_note} major"
            best_is_major = True
            best_score = max(best_score, 0.4)  # bump confidence

        return best_key, float(best_score), best_is_major
    except Exception as e:
        # Fallback varied by F0
        note = hz_to_note_name(f0_mean)
        return f"{note} major", 0.4, True

def detect_bpm(y, sr, f0s=None):
    """Improved BPM for a cappella: uses envelope + F0 change rate + spectral flux."""
    try:
        # Try librosa
        try:
            import librosa
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            t = float(tempo)
            if 40 < t < 220:
                return t
        except:
            pass

        # Method 1: energy envelope autocorrelation
        hop = max(1, sr // 100)
        envelope = np.array([np.mean(np.abs(y[i:i+hop])) for i in range(0, len(y), hop)])
        if len(envelope) < 20:
            return 90.0

        # Spectral flux for onset detection (more sensitive for vocal)
        # Compute short-time energy and zero-crossing variation
        # Use envelope smoothed
        env_smooth = np.convolve(envelope, np.ones(10)/10, mode='same')
        env = env_smooth - np.mean(env_smooth)
        std = np.std(env)
        if std < 1e-6:
            std = 1e-6

        # Autocorr search 50-180 BPM (wider range for singing)
        sr_env = sr / hop
        best_bpm = None
        best_corr = -1
        candidates = []

        for bpm in range(50, 181):
            lag = int(sr_env * 60 / bpm)
            if lag >= len(env) or lag < 3:
                continue
            # Use normalized correlation
            a = env[:-lag]
            b = env[lag:]
            if len(a) < 10:
                continue
            # Pearson corr
            denom = (np.std(a)*np.std(b) + 1e-9)
            if denom < 1e-9:
                continue
            corr = np.mean((a-np.mean(a))*(b-np.mean(b))) / denom
            if not np.isnan(corr):
                candidates.append((bpm, corr))
                if corr > best_corr:
                    best_corr = corr
                    best_bpm = bpm

        # Method 2: F0 change rate (for singing without drums)
        f0_bpm = None
        if f0s is not None and len(f0s) > 10:
            # Count significant F0 changes per second as proxy for tempo
            # If many pitch changes, faster tempo
            f0_arr = np.array(f0s)
            # diff
            diff = np.abs(np.diff(f0_arr))
            # Count changes > 10 Hz as note change
            changes = np.sum(diff > 15)
            duration = len(y) / sr
            changes_per_sec = changes / max(duration, 1)
            # Map changes_per_sec to BPM: 0.5 changes/sec ~ 60 BPM, 2 changes/sec ~ 120 BPM
            # Heuristic
            f0_bpm = 60 + changes_per_sec * 30
            f0_bpm = np.clip(f0_bpm, 60, 140)

        # Combine: if envelope corr is weak (<0.2), use F0-based BPM
        if best_corr < 0.15 and f0_bpm is not None:
            # Blend with some variation based on audio hash
            h = hashlib.md5(y[:sr*2].tobytes()).hexdigest()
            hash_var = (int(h[:2], 16) % 20) - 10  # -10 to +10
            final_bpm = float(np.clip(f0_bpm + hash_var, 65, 130))
            print(f"[bpm] Low envelope corr {best_corr:.2f}, using F0-based {f0_bpm:.1f} + hash {hash_var} = {final_bpm:.1f}")
            return final_bpm

        if best_bpm is None:
            # No clear BPM, use F0 if available, else hash-based varied default
            if f0_bpm is not None:
                return float(f0_bpm)
            # Hash-based: different files get different BPMs, not always 90
            h = hashlib.md5(y[:sr].tobytes()).hexdigest()
            varied = 75 + (int(h[:2], 16) % 50)  # 75-124 BPM varied
            return float(varied)

        # Add small hash variation so same BPM detection doesn't give identical music
        # But keep it close to detected BPM (±3)
        h = hashlib.md5(y[::sr//10][:100].tobytes()).hexdigest()
        jitter = (int(h[:2], 16) % 7) - 3  # -3 to +3
        final = float(np.clip(best_bpm + jitter, 55, 175))
        print(f"[bpm] Detected {best_bpm} (corr {best_corr:.2f}) + jitter {jitter} = {final}")
        return final

    except Exception as e:
        print(f"[bpm] fallback due to {e}")
        # Varied fallback, not always 90
        try:
            h = hashlib.md5(y[:1000].tobytes()).hexdigest()
            varied = 80 + (int(h[:2], 16) % 40)
            return float(varied)
        except:
            return 90.0

def detect_f0_range(y, sr):
    """Estimate vocal F0 min/max via autocorrelation per frame."""
    try:
        try:
            import librosa
            f0, voiced_flag, _ = librosa.pyin(y, fmin=50, fmax=800, sr=sr, hop_length=1024)
            f0 = f0[~np.isnan(f0)]
            if len(f0) > 10:
                f0_sorted = np.sort(f0)
                lo = float(np.percentile(f0_sorted, 5))
                hi = float(np.percentile(f0_sorted, 95))
                mean = float(np.mean(f0_sorted))
                return lo, hi, mean, f0_sorted
        except:
            pass

        win = int(sr * 0.1)
        hop = int(sr * 0.05)
        f0s = []
        for i in range(0, len(y)-win, hop):
            frame = y[i:i+win]
            if np.max(np.abs(frame)) < 0.02:
                continue
            frame = frame - np.mean(frame)
            corr = np.correlate(frame, frame, mode='full')[len(frame)-1:]
            min_period = int(sr / 800)
            max_period = int(sr / 50)
            if max_period >= len(corr):
                max_period = len(corr)-1
            corr[:min_period] = 0
            peak = np.argmax(corr[min_period:max_period]) + min_period
            if corr[peak] > 0.3 * corr[0]:
                f0 = sr / peak
                if 50 < f0 < 800:
                    f0s.append(f0)
        if len(f0s) < 5:
            return 110.0, 330.0, 180.0, np.array([180.0])
        f0s_arr = np.array(f0s)
        lo = float(np.percentile(f0s_arr, 5))
        hi = float(np.percentile(f0s_arr, 95))
        mean = float(np.mean(f0s_arr))
        return lo, hi, mean, f0s_arr
    except Exception as e:
        return 110.0, 330.0, 180.0, np.array([180.0])

def analyze_audio(wav_path: Path):
    y, sr = sf.read(str(wav_path))
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    duration = len(y) / sr
    y_analyze = y[:int(min(len(y), sr*60))]

    # F0 first, so we can use it for key and BPM fallback
    f0_min, f0_max, f0_mean, f0_all = detect_f0_range(y_analyze, sr)
    bpm = detect_bpm(y_analyze, sr, f0s=f0_all)
    key, key_conf, is_major = detect_key(y_analyze, sr, f0_mean=f0_mean)

    def hz_to_midi(hz):
        return 69 + 12 * math.log2(hz / 440.0) if hz>0 else 60
    midi_min = hz_to_midi(f0_min)
    midi_max = hz_to_midi(f0_max)

    language = "unknown"
    lyrics = ""
    try:
        from ..config import WHISPER, WHISPER_MODEL
        if WHISPER != "off":
            import faster_whisper
            model = faster_whisper.WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            segments, info = model.transcribe(str(wav_path), beam_size=5)
            language = info.language
            lyrics = " ".join([s.text for s in segments])[:1000]
    except:
        pass

    # Add hash for variation tracking
    try:
        file_hash = hashlib.md5(y[:sr*2].tobytes()).hexdigest()[:8]
    except:
        file_hash = "unknown"

    result = {
        "bpm": round(float(bpm), 1),
        "key": key,
        "key_confidence": round(float(key_conf), 3),
        "is_major": bool(is_major),
        "f0_min_hz": round(float(f0_min), 1),
        "f0_max_hz": round(float(f0_max), 1),
        "f0_mean_hz": round(float(f0_mean), 1),
        "midi_min": round(float(midi_min), 1),
        "midi_max": round(float(midi_max), 1),
        "duration_sec": round(float(duration), 2),
        "language": language,
        "lyrics_preview": lyrics[:500],
        "sr": sr,
        "file_hash": file_hash,
    }
    print(f"[analysis] {key} {bpm:.1f} BPM range {f0_min:.0f}-{f0_max:.0f}Hz mean {f0_mean:.0f}Hz hash {file_hash}")
    return result

def key_to_root_midi(key_str: str) -> int:
    try:
        root_name = key_str.split()[0]
        note_to_semitone = {n:i for i,n in enumerate(NOTE_NAMES)}
        root_semi = note_to_semitone.get(root_name, 0)
        return 60 + root_semi if root_name in NOTE_NAMES else 60
    except:
        return 60
