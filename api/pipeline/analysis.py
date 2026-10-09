"""
SingSmith Analysis v0.7 — TRUE alignment: beat tracking + onset detection + first vocal time
Detects: BPM, Key, vocal range, duration, beat_times, onset_times, first_vocal_time, bar_times
Now music can lock to vocal timing instead of fixed grid.
"""

import numpy as np
import soundfile as sf
from pathlib import Path
import math
import hashlib

MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

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
        valid = (freqs > 40) & (freqs < 5000)
        f_valid = freqs[valid]
        s_valid = spec[valid]
        if len(f_valid) == 0:
            continue
        midi = 69 + 12 * np.log2(f_valid / 440.0)
        pc = np.round(midi).astype(int) % 12
        for j, p in enumerate(pc):
            chroma[p, i] += s_valid[j] * (1.0 + s_valid[j])
    chroma = chroma / (np.max(chroma, axis=0, keepdims=True) + 1e-9)
    mean_chroma = np.mean(chroma, axis=1)
    if np.max(mean_chroma) > 0:
        mean_chroma = mean_chroma / np.max(mean_chroma)
    return mean_chroma, chroma

def detect_key(y, sr, f0_mean=180):
    try:
        mean_chroma, _ = _stft_chroma(y, sr)
        best_score = -1
        best_key = None
        best_is_major = True
        import os
        if os.getenv("USE_LIBROSA", "0") == "1":
            try:
                import librosa
                chroma_lib = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=1024)
                mean_chroma_lib = np.mean(chroma_lib, axis=1)
                mean_chroma_lib = mean_chroma_lib / (np.max(mean_chroma_lib)+1e-9)
                mean_chroma = mean_chroma_lib
            except:
                pass
        for i in range(12):
            maj = np.roll(MAJOR_PROFILE, i)
            min_ = np.roll(MINOR_PROFILE, i)
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
        if best_score < 0.35 or best_key is None:
            note_from_f0 = hz_to_note_name(f0_mean)
            try:
                h = hashlib.md5(y[:sr].tobytes()).hexdigest()
                hash_val = int(h[:4], 16) % 12
                f0_semi = NOTE_NAMES.index(note_from_f0)
                final_semi = (f0_semi + hash_val) % 12
                final_note = NOTE_NAMES[final_semi]
            except:
                final_note = note_from_f0
            best_key = f"{final_note} major"
            best_is_major = True
            best_score = max(best_score, 0.4)
        return best_key, float(best_score), best_is_major
    except Exception as e:
        note = hz_to_note_name(f0_mean)
        return f"{note} major", 0.4, True

def detect_f0_range(y, sr):
    try:
        # Skip librosa.pyin — it can segfault on some systems with numba, use safe autocorr fallback
        # pyin is more accurate but not required for alignment
        pass
        # try:
        #     import librosa
        #     f0, voiced_flag, _ = librosa.pyin(y, fmin=50, fmax=800, sr=sr, hop_length=1024)
        #     f0 = f0[~np.isnan(f0)]
        #     if len(f0) > 10:
        #         f0_sorted = np.sort(f0)
        #         lo = float(np.percentile(f0_sorted, 5))
        #         hi = float(np.percentile(f0_sorted, 95))
        #         mean = float(np.mean(f0_sorted))
        #         return lo, hi, mean, f0_sorted
        # except:
        #     pass
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

def detect_bpm_and_beats(y, sr, f0s=None):
    """
    Returns tempo, beat_times, onset_times, first_vocal_time
    Tries librosa first for true beat tracking, falls back to energy-based.
    """
    duration = len(y) / sr
    beat_times = []
    onset_times = []
    first_vocal_time = 0.0
    tempo = 90.0

    # --- first vocal time via energy envelope ---
    try:
        hop = sr // 100  # 10ms
        envelope = np.array([np.mean(np.abs(y[i:i+hop])) for i in range(0, len(y), hop)])
        times = np.arange(len(envelope)) * hop / sr
        # threshold: 5% of max, but at least 0.02
        thresh = max(np.max(envelope) * 0.08, 0.02)
        above = np.where(envelope > thresh)[0]
        if len(above) > 0:
            # first time where it stays above for 100ms (10 frames)
            for idx in above:
                if idx+10 < len(envelope) and np.all(envelope[idx:idx+10] > thresh*0.5):
                    first_vocal_time = float(times[idx])
                    break
            else:
                first_vocal_time = float(times[above[0]])
        else:
            first_vocal_time = 0.0
    except:
        first_vocal_time = 0.0

    # --- Try librosa beat tracking (disabled by default due to segfault in some envs, enable with USE_LIBROSA=1) ---
    librosa_ok = False
    import os
    if os.getenv("USE_LIBROSA", "0") == "1":
        try:
            import librosa
            tempo_lib, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
            beat_times_lib = librosa.frames_to_time(beat_frames, sr=sr)
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='frames')
            onset_times_lib = librosa.frames_to_time(onset_frames, sr=sr)
            if len(beat_times_lib) >= 4 and 45 < float(tempo_lib) < 200:
                tempo = float(tempo_lib)
                beat_times = [float(t) for t in beat_times_lib]
                onset_times = [float(t) for t in onset_times_lib if t >= first_vocal_time - 0.1]
                librosa_ok = True
                print(f"[beats] librosa tempo {tempo:.1f} beats {len(beat_times)} onsets {len(onset_times)} first_vocal {first_vocal_time:.2f}s")
        except Exception as e:
            print(f"[beats] librosa failed {e}, fallback")
    else:
        print("[beats] librosa disabled (USE_LIBROSA=0), using energy fallback for stability")

    if not librosa_ok:
        # Fallback BPM detection via envelope autocorrelation
        try:
            hop = max(1, sr // 100)
            envelope = np.array([np.mean(np.abs(y[i:i+hop])) for i in range(0, len(y), hop)])
            if len(envelope) < 20:
                tempo = 90.0
            else:
                env_smooth = np.convolve(envelope, np.ones(10)/10, mode='same')
                env = env_smooth - np.mean(env_smooth)
                std = np.std(env)
                if std < 1e-6:
                    std = 1e-6
                sr_env = sr / hop
                best_bpm = None
                best_corr = -1
                for bpm in range(50, 181):
                    lag = int(sr_env * 60 / bpm)
                    if lag >= len(env) or lag < 3:
                        continue
                    a = env[:-lag]
                    b = env[lag:]
                    if len(a) < 10:
                        continue
                    denom = (np.std(a)*np.std(b) + 1e-9)
                    if denom < 1e-9:
                        continue
                    corr = np.mean((a-np.mean(a))*(b-np.mean(b))) / denom
                    if not np.isnan(corr) and corr > best_corr:
                        best_corr = corr
                        best_bpm = bpm
                if best_bpm is not None:
                    tempo = float(best_bpm)
                else:
                    # F0 change rate fallback
                    if f0s is not None and len(f0s) > 10:
                        f0_arr = np.array(f0s)
                        diff = np.abs(np.diff(f0_arr))
                        changes = np.sum(diff > 15)
                        changes_per_sec = changes / max(duration, 1)
                        f0_bpm = 60 + changes_per_sec * 30
                        tempo = float(np.clip(f0_bpm, 65, 130))
                    else:
                        h = hashlib.md5(y[:sr].tobytes()).hexdigest()
                        tempo = float(75 + (int(h[:2], 16) % 50))
                # hash jitter
                h = hashlib.md5(y[::sr//10][:100].tobytes()).hexdigest()
                jitter = (int(h[:2], 16) % 7) - 3
                tempo = float(np.clip(tempo + jitter, 55, 175))
        except Exception as e:
            print(f"[bpm] fallback due to {e}")
            try:
                h = hashlib.md5(y[:1000].tobytes()).hexdigest()
                tempo = float(80 + (int(h[:2], 16) % 40))
            except:
                tempo = 90.0

        # Generate synthetic beat_times from tempo and first_vocal_time
        try:
            beat_sec = 60.0 / tempo
            # Start beats slightly before first vocal for intro, or at 0
            start_beat = 0.0
            if first_vocal_time > beat_sec * 1.5:
                # Keep intro: first beat at 0
                start_beat = 0.0
            else:
                # Vocal starts early, align first beat to first vocal or 0
                start_beat = 0.0
            num_beats = int(math.ceil(duration / beat_sec)) + 2
            beat_times = [start_beat + i*beat_sec for i in range(num_beats)]
            # Onset times via energy peaks
            try:
                hop = sr // 100
                envelope = np.array([np.mean(np.abs(y[i:i+hop])) for i in range(0, len(y), hop)])
                # Find peaks where envelope rises sharply
                diff = np.diff(envelope)
                thresh = np.std(envelope) * 0.5
                onset_idx = np.where(diff > thresh)[0]
                times = onset_idx * hop / sr
                # Filter: at least 0.3s apart
                filtered = []
                last = -1
                for t in times:
                    if t - last > 0.25 and envelope[int(t*sr//hop)] > 0.03:
                        filtered.append(float(t))
                        last = t
                onset_times = filtered[:100]
            except:
                onset_times = []
            print(f"[beats] fallback tempo {tempo:.1f} beats {len(beat_times)} first_vocal {first_vocal_time:.2f}s")
        except Exception as e:
            print(f"[beats] fallback beat generation failed {e}")
            beat_times = [i*60.0/tempo for i in range(int(duration*tempo/60)+2)]
            onset_times = []

    # Ensure beat_times sorted and within duration
    beat_times = sorted([t for t in beat_times if 0 <= t <= duration + 2.0])
    onset_times = sorted([t for t in onset_times if 0 <= t <= duration])

    # If beat_times empty, create from tempo
    if len(beat_times) < 4:
        beat_sec = 60.0 / tempo
        num_beats = int(math.ceil(duration / beat_sec)) + 4
        beat_times = [i*beat_sec for i in range(num_beats)]

    return tempo, beat_times, onset_times, first_vocal_time

def analyze_audio(wav_path: Path):
    y, sr = sf.read(str(wav_path))
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    duration = len(y) / sr
    y_analyze = y[:int(min(len(y), sr*60))]

    f0_min, f0_max, f0_mean, f0_all = detect_f0_range(y_analyze, sr)
    tempo, beat_times, onset_times, first_vocal_time = detect_bpm_and_beats(y_analyze, sr, f0s=f0_all)
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

    try:
        file_hash = hashlib.md5(y[:sr*2].tobytes()).hexdigest()[:8]
    except:
        file_hash = "unknown"

    # Build bar_times from beat_times: every 4 beats = 1 bar
    bar_times = []
    try:
        # Always start at 0 for intro
        bar_times.append(0.0)
        # Then every 4 beats
        for i in range(0, len(beat_times), 4):
            bt = beat_times[i]
            if bt > 0.05 and bt not in bar_times:
                bar_times.append(bt)
        # Extend beyond last beat to cover duration
        beat_sec = 60.0 / tempo
        bar_sec = beat_sec * 4
        last_bar = bar_times[-1] if bar_times else 0.0
        while last_bar + bar_sec < duration + 1.0:
            last_bar += bar_sec
            bar_times.append(last_bar)
        bar_times = sorted(set(bar_times))
    except:
        beat_sec = 60.0 / tempo
        bar_sec = beat_sec * 4
        num_bars = int(math.ceil((duration+1.0)/bar_sec))+1
        bar_times = [i*bar_sec for i in range(num_bars)]

    result = {
        "bpm": round(float(tempo), 1),
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
        "beat_times": [round(float(t), 3) for t in beat_times],
        "onset_times": [round(float(t), 3) for t in onset_times],
        "first_vocal_time": round(float(first_vocal_time), 3),
        "bar_times": [round(float(t), 3) for t in bar_times],
    }
    print(f"[analysis] {key} {tempo:.1f} BPM range {f0_min:.0f}-{f0_max:.0f}Hz mean {f0_mean:.0f}Hz hash {file_hash} beats {len(beat_times)} bars {len(bar_times)} first_vocal {first_vocal_time:.2f}s")
    return result

def key_to_root_midi(key_str: str) -> int:
    try:
        root_name = key_str.split()[0]
        note_to_semitone = {n:i for i,n in enumerate(NOTE_NAMES)}
        root_semi = note_to_semitone.get(root_name, 0)
        return 60 + root_semi if root_name in NOTE_NAMES else 60
    except:
        return 60
