"""
SingSmith Analysis — zero-cost, pure numpy/scipy.
Detects: BPM, Key (major/minor), vocal range (min/max F0), duration.
Optionally uses librosa / faster-whisper if installed.
"""
import numpy as np
import soundfile as sf
from pathlib import Path
import math

# Krumhansl-Schmuckler key profiles (major, minor) — classic music cognition
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def _stft_chroma(y, sr, n_fft=4096, hop=1024):
    """Very lightweight chromagram via FFT, mapped to 12 pitch classes."""
    # windowed STFT magnitude
    num_frames = 1 + (len(y) - n_fft) // hop
    chroma = np.zeros((12, num_frames))
    window = np.hanning(n_fft)
    for i in range(num_frames):
        frame = y[i*hop:i*hop+n_fft] * window
        if len(frame) < n_fft:
            break
        spec = np.abs(np.fft.rfft(frame))
        freqs = np.fft.rfftfreq(n_fft, 1/sr)
        # map each freq bin to pitch class
        # MIDI note = 69 + 12*log2(f/440)
        # avoid log(0)
        valid = freqs > 20
        f_valid = freqs[valid]
        s_valid = spec[valid]
        midi = 69 + 12 * np.log2(f_valid / 440.0)
        # pitch class = midi % 12
        pc = np.round(midi).astype(int) % 12
        # accumulate energy
        for j, p in enumerate(pc):
            chroma[p, i] += s_valid[j]
    # normalize per frame
    chroma = chroma / (np.max(chroma, axis=0, keepdims=True) + 1e-9)
    # mean across time
    mean_chroma = np.mean(chroma, axis=1)
    mean_chroma = mean_chroma / (np.max(mean_chroma) + 1e-9)
    return mean_chroma, chroma

def detect_key(y, sr):
    """Return key string like 'G major' and confidence."""
    try:
        mean_chroma, _ = _stft_chroma(y, sr)
        # correlate with all transpositions of profiles
        best_score = -1
        best_key = "C major"
        best_is_major = True
        for i in range(12):
            # rotate profile
            maj = np.roll(MAJOR_PROFILE, i)
            min_ = np.roll(MINOR_PROFILE, i)
            # correlation
            maj_corr = np.corrcoef(mean_chroma, maj)[0,1]
            min_corr = np.corrcoef(mean_chroma, min_)[0,1]
            if maj_corr > best_score:
                best_score = maj_corr
                best_key = f"{NOTE_NAMES[i]} major"
                best_is_major = True
            if min_corr > best_score:
                best_score = min_corr
                best_key = f"{NOTE_NAMES[i]} minor"
                best_is_major = False
        return best_key, float(best_score), best_is_major
    except Exception as e:
        return "C major", 0.0, True

def detect_bpm(y, sr):
    """Lightweight BPM via onset envelope + autocorrelation."""
    try:
        # Try librosa if available (better)
        try:
            import librosa
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            t = float(tempo)
            if t > 20:
                return t
        except Exception:
            pass

        # Fallback: energy envelope
        hop = max(1, sr // 100)  # 100 Hz envelope
        envelope = np.array([np.mean(np.abs(y[i:i+hop])) for i in range(0, len(y), hop)])
        if len(envelope) < 10:
            return 90.0
        envelope = np.convolve(envelope, np.ones(5)/5, mode='same')
        sr_env = sr / hop
        best_bpm = 90
        best_corr = -1
        env = envelope - np.mean(envelope)
        if np.std(env) < 1e-6:
            return 90.0
        for bpm in range(60, 181):
            lag = int(sr_env * 60 / bpm)
            if lag >= len(env) or lag < 2:
                continue
            try:
                corr = np.corrcoef(env[:-lag], env[lag:])[0,1]
            except:
                continue
            if not np.isnan(corr) and corr > best_corr:
                best_corr = corr
                best_bpm = bpm
        return float(best_bpm if best_bpm else 90)
    except Exception as e:
        print(f"[bpm] fallback due to {e}")
        return 90.0

def detect_f0_range(y, sr):
    """Estimate vocal F0 min/max via autocorrelation per frame. Returns min/max Hz and MIDI."""
    try:
        # Try torchcrepe / librosa pyin if available
        try:
            import librosa
            f0, voiced_flag, _ = librosa.pyin(y, fmin=50, fmax=800, sr=sr, hop_length=1024)
            f0 = f0[~np.isnan(f0)]
            if len(f0) > 10:
                f0_sorted = np.sort(f0)
                # use 5th and 95th percentile to avoid outliers
                lo = float(np.percentile(f0_sorted, 5))
                hi = float(np.percentile(f0_sorted, 95))
                mean = float(np.mean(f0_sorted))
                return lo, hi, mean
        except:
            pass

        # Fallback: simple autocorrelation pitch tracker
        # process 100ms windows
        win = int(sr * 0.1)
        hop = int(sr * 0.05)
        f0s = []
        for i in range(0, len(y)-win, hop):
            frame = y[i:i+win]
            if np.max(np.abs(frame)) < 0.02:  # silence
                continue
            # autocorrelation
            frame = frame - np.mean(frame)
            corr = np.correlate(frame, frame, mode='full')[len(frame)-1:]
            # find peak in 50-800 Hz range
            min_period = int(sr / 800)
            max_period = int(sr / 50)
            if max_period >= len(corr):
                max_period = len(corr)-1
            # ignore zero lag
            corr[:min_period] = 0
            peak = np.argmax(corr[min_period:max_period]) + min_period
            if corr[peak] > 0.3 * corr[0]:  # voiced
                f0 = sr / peak
                if 50 < f0 < 800:
                    f0s.append(f0)
        if len(f0s) < 5:
            return 110.0, 330.0, 180.0
        f0s = np.array(f0s)
        lo = float(np.percentile(f0s, 5))
        hi = float(np.percentile(f0s, 95))
        mean = float(np.mean(f0s))
        return lo, hi, mean
    except Exception as e:
        return 110.0, 330.0, 180.0

def analyze_audio(wav_path: Path):
    y, sr = sf.read(str(wav_path))
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    duration = len(y) / sr

    # If too long, analyze first 60s for speed, but keep full duration
    y_analyze = y[:int(min(len(y), sr*60))]

    bpm = detect_bpm(y_analyze, sr)
    key, key_conf, is_major = detect_key(y_analyze, sr)
    f0_min, f0_max, f0_mean = detect_f0_range(y_analyze, sr)

    # Comfortable range: MIDI notes
    def hz_to_midi(hz):
        return 69 + 12 * math.log2(hz / 440.0) if hz>0 else 60
    midi_min = hz_to_midi(f0_min)
    midi_max = hz_to_midi(f0_max)

    # Language detection via faster-whisper if available
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
    except Exception as e:
        # whisper not installed or failed — fine
        pass

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
    }
    return result

def key_to_root_midi(key_str: str) -> int:
    """Convert 'G major' -> MIDI root (C4=60)."""
    try:
        root_name = key_str.split()[0]
        # map
        note_to_semitone = {n:i for i,n in enumerate(NOTE_NAMES)}
        # handle flats? Simplify: convert Db->C#, etc.
        # For MVP, assume sharps only
        root_semi = note_to_semitone.get(root_name, 0)
        # put root in octave 3 (C3=48) for bass, 4 for mid
        return 60 + root_semi if root_name in NOTE_NAMES else 60
    except:
        return 60
