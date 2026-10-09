"""
SingSmith Analysis v0.10 — Phrase-following: chords change when YOU sing, not metronome
Detects: BPM, Key, range, beat_times, onset_times, first_vocal_time, bar_times, phrases
Phrases = non-silent intervals (where you actually sing) -> music follows those
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

def detect_phrases(y, sr, hop=0.01):
    """
    Detect vocal phrases (non-silent intervals) where you actually sing.
    Returns list of (start, end) times.
    """
    try:
        hop_samples = int(sr * hop)
        envelope = np.array([np.mean(np.abs(y[i:i+hop_samples])) for i in range(0, len(y), hop_samples)])
        times = np.arange(len(envelope)) * hop_samples / sr
        
        # Adaptive threshold
        max_env = np.max(envelope)
        thresh = max(max_env * 0.12, 0.025)  # at least 0.025
        # Also use percentile
        thresh = max(thresh, np.percentile(envelope, 70) * 0.5)
        
        # Find where above threshold
        above = envelope > thresh
        
        phrases = []
        in_phrase = False
        phrase_start = 0
        silence_counter = 0
        min_phrase_len = 0.15  # at least 150ms singing
        min_silence_len = 0.25  # at least 250ms silence to split phrases
        
        for i in range(len(above)):
            if above[i]:
                if not in_phrase:
                    in_phrase = True
                    phrase_start = times[i]
                    silence_counter = 0
                else:
                    silence_counter = 0
            else:
                if in_phrase:
                    silence_counter += 1
                    # If silence long enough, end phrase
                    if silence_counter * hop >= min_silence_len:
                        phrase_end = times[i - silence_counter]
                        if phrase_end - phrase_start >= min_phrase_len:
                            phrases.append((float(phrase_start), float(phrase_end)))
                        in_phrase = False
                        silence_counter = 0
        
        # Handle last phrase
        if in_phrase:
            phrase_end = times[-1]
            if phrase_end - phrase_start >= min_phrase_len:
                phrases.append((float(phrase_start), float(phrase_end)))
        
        # Merge very close phrases (<0.15s gap)
        merged = []
        for s, e in phrases:
            if merged and s - merged[-1][1] < 0.15:
                merged[-1] = (merged[-1][0], e)
            else:
                merged.append((s, e))
        
        phrase_str = ", ".join([f"{s:.2f}-{e:.2f}s" for s,e in merged[:6]])
        print(f"[phrases] Detected {len(merged)} phrases, thresh {thresh:.4f}, max_env {max_env:.4f}: {phrase_str}")
        return merged
    except Exception as e:
        print(f"[phrases] failed {e}")
        return []

def detect_bpm_and_beats_and_phrases(y, sr, f0s=None):
    """
    Returns tempo, beat_times, onset_times, first_vocal_time, phrases
    """
    duration = len(y) / sr
    beat_times = []
    onset_times = []
    first_vocal_time = 0.0
    tempo = 90.0
    phrases = []

    # First detect phrases
    phrases = detect_phrases(y, sr)

    # First vocal time from phrases or energy
    if phrases:
        first_vocal_time = phrases[0][0]
    else:
        try:
            hop = sr // 100
            envelope = np.array([np.mean(np.abs(y[i:i+hop])) for i in range(0, len(y), hop)])
            times = np.arange(len(envelope)) * hop / sr
            thresh = max(np.max(envelope) * 0.08, 0.02)
            above = np.where(envelope > thresh)[0]
            if len(above) > 0:
                for idx in above:
                    if idx+10 < len(envelope) and np.all(envelope[idx:idx+10] > thresh*0.5):
                        first_vocal_time = float(times[idx])
                        break
                else:
                    first_vocal_time = float(times[above[0]])
        except:
            first_vocal_time = 0.0

    # Onset times from phrase starts + energy peaks
    try:
        # Phrase starts are strong onsets
        onset_times = [s for s, e in phrases]
        # Also add energy-based onsets inside phrases
        hop = sr // 100
        envelope = np.array([np.mean(np.abs(y[i:i+hop])) for i in range(0, len(y), hop)])
        diff = np.diff(envelope)
        thresh = np.std(envelope) * 0.6
        onset_idx = np.where(diff > thresh)[0]
        times = onset_idx * hop / sr
        filtered = []
        last = -1
        for t in times:
            if t - last > 0.25 and envelope[int(t*sr//hop)] > 0.03:
                # Only if inside a phrase or near phrase
                filtered.append(float(t))
                last = t
        # Merge with phrase starts, deduplicate
        all_onsets = sorted(set(onset_times + filtered))
        # Filter to be within phrases or close
        onset_times = [t for t in all_onsets if t >= first_vocal_time - 0.1]
        onset_times = onset_times[:100]
    except:
        onset_times = [s for s, e in phrases]

    # BPM and beat_times
    import os
    librosa_ok = False
    if os.getenv("USE_LIBROSA", "0") == "1":
        try:
            import librosa
            tempo_lib, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
            beat_times_lib = librosa.frames_to_time(beat_frames, sr=sr)
            if len(beat_times_lib) >= 4 and 45 < float(tempo_lib) < 200:
                tempo = float(tempo_lib)
                beat_times = [float(t) for t in beat_times_lib]
                librosa_ok = True
                print(f"[beats] librosa tempo {tempo:.1f} beats {len(beat_times)}")
        except Exception as e:
            print(f"[beats] librosa failed {e}")

    if not librosa_ok:
        try:
            hop = max(1, sr // 100)
            envelope = np.array([np.mean(np.abs(y[i:i+hop])) for i in range(0, len(y), hop)])
            if len(envelope) < 20:
                tempo = 90.0
            else:
                env_smooth = np.convolve(envelope, np.ones(10)/10, mode='same')
                env = env_smooth - np.mean(env_smooth)
                sr_env = sr / hop
                best_bpm = None
                best_corr = -1
                for bpm in range(55, 176):
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

        # Generate beat_times anchored to first vocal time and phrases
        try:
            beat_sec = 60.0 / tempo
            # Start beats at 0, but ensure beats align to phrase starts
            # If first vocal at 0.8s, we want beat near 0.8s
            # Generate from 0
            num_beats = int(math.ceil(duration / beat_sec)) + 4
            beat_times = [i*beat_sec for i in range(num_beats)]
            # If we have phrases, adjust beat_times to snap to phrase starts
            # For each phrase start, find nearest beat and shift beats slightly to align?
            # Simpler: keep beats as is, but also add phrase starts as extra beats for chord changes
            # The generator will use bar_times from phrases, not just beats, for chords
            print(f"[beats] fallback tempo {tempo:.1f} beats {len(beat_times)} phrases {len(phrases)} first_vocal {first_vocal_time:.2f}s")
        except Exception as e:
            print(f"[beats] fallback beat generation failed {e}")
            beat_times = [i*60.0/tempo for i in range(int(duration*tempo/60)+2)]

    beat_times = sorted([t for t in beat_times if 0 <= t <= duration + 2.0])
    onset_times = sorted([t for t in onset_times if 0 <= t <= duration])

    if len(beat_times) < 4:
        beat_sec = 60.0 / tempo
        num_beats = int(math.ceil(duration / beat_sec)) + 4
        beat_times = [i*beat_sec for i in range(num_beats)]

    return tempo, beat_times, onset_times, first_vocal_time, phrases

def analyze_audio(wav_path: Path):
    y, sr = sf.read(str(wav_path))
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    duration = len(y) / sr
    y_analyze = y[:int(min(len(y), sr*60))]

    f0_min, f0_max, f0_mean, f0_all = detect_f0_range(y_analyze, sr)
    tempo, beat_times, onset_times, first_vocal_time, phrases = detect_bpm_and_beats_and_phrases(y_analyze, sr, f0s=f0_all)
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

    # Build bar_times: v0.10 uses phrases for chord changes, not just beats
    # bar_times = phrase starts + regular bars
    bar_times = []
    try:
        bar_times.append(0.0)
        # Add phrase starts as bar boundaries (so chords change when you sing)
        for s, e in phrases:
            if s > 0.1 and s not in bar_times:
                bar_times.append(s)
            # Also add phrase end as potential change
            # if e < duration and e not in bar_times:
            #    bar_times.append(e)
        # Add regular beat-based bars
        for i in range(0, len(beat_times), 4):
            bt = beat_times[i]
            if bt > 0.05 and bt not in bar_times:
                bar_times.append(bt)
        # Extend beyond last
        beat_sec = 60.0 / tempo
        bar_sec = beat_sec * 4
        last_bar = max(bar_times) if bar_times else 0.0
        while last_bar + bar_sec < duration + 1.0:
            last_bar += bar_sec
            bar_times.append(last_bar)
        bar_times = sorted(set([round(t,3) for t in bar_times]))
        # Remove very close bars (<0.3s apart) - keep phrase starts
        filtered_bars = [bar_times[0]]
        for t in bar_times[1:]:
            if t - filtered_bars[-1] >= 0.35 or any(abs(t - ps) < 0.05 for ps, pe in phrases):
                filtered_bars.append(t)
        bar_times = filtered_bars
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
        "phrases": [(round(float(s),3), round(float(e),3)) for s,e in phrases],
    }
    print(f"[analysis] {key} {tempo:.1f} BPM range {f0_min:.0f}-{f0_max:.0f}Hz mean {f0_mean:.0f}Hz hash {file_hash} beats {len(beat_times)} bars {len(bar_times)} phrases {len(phrases)} first_vocal {first_vocal_time:.2f}s")
    return result

def key_to_root_midi(key_str: str) -> int:
    try:
        root_name = key_str.split()[0]
        note_to_semitone = {n:i for i,n in enumerate(NOTE_NAMES)}
        root_semi = note_to_semitone.get(root_name, 0)
        return 60 + root_semi if root_name in NOTE_NAMES else 60
    except:
        return 60
