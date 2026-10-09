"""
SingSmith Procedural Generator v0.8 — TRUE melody-following like live band
FIXES melody_off bug: Chords now harmonize vocal notes, not fixed progression.

- Per-beat F0 detection via autocorrelation (not just per bar)
- For each bar, vocal note -> choose chord that CONTAINS vocal pitch (harmonization)
- Bass = root of chosen chord, ~19 semitones below vocal for support
- Diatonic chords in key, scored by: melody fit + progression + voice leading
- Drums on beat_times, onset accent, intro handling
- Seed from file_hash for uniqueness
"""

import numpy as np
import soundfile as sf
from pathlib import Path
import math
import hashlib
import random

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def note_to_freq(midi):
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))

def adsr_envelope(n_samples, sr, attack=0.01, decay=0.1, sustain=0.7, release=0.2):
    a = int(sr*attack)
    d = int(sr*decay)
    r = int(sr*release)
    s = n_samples - a - d - r
    if s < 0:
        total = attack+decay+release
        if total == 0:
            total = 1
        a = int(n_samples * attack/total)
        d = int(n_samples * decay/total)
        r = int(n_samples * release/total)
        s = 0
    env = np.concatenate([
        np.linspace(0, 1, a) if a>0 else np.array([]),
        np.linspace(1, sustain, d) if d>0 else np.array([]),
        np.ones(s)*sustain if s>0 else np.array([]),
        np.linspace(sustain, 0, r) if r>0 else np.array([])
    ])
    if len(env) < n_samples:
        env = np.pad(env, (0, n_samples-len(env)))
    else:
        env = env[:n_samples]
    return env

def synth_kick(sr, duration=0.5, variation=0):
    n = int(sr*duration)
    t = np.linspace(0, duration, n)
    base_pitch = 140 + variation*10
    freq = base_pitch * np.exp(-t*(18+variation)) + 45
    phase = 2*np.pi*np.cumsum(freq)/sr
    wave = np.sin(phase)
    env = np.exp(-t*(7+variation*0.5))
    return wave * env * 0.9

def synth_snare(sr, duration=0.3, variation=0):
    n = int(sr*duration)
    t = np.linspace(0, duration, n)
    noise = np.random.randn(n) * (0.5 + variation*0.1)
    tone_freq = 170 + variation*15
    tone = np.sin(2*np.pi*tone_freq*t) * np.exp(-t*(9+variation))
    env = np.exp(-t*(11+variation))
    return (noise + tone) * env * 0.6

def synth_hat(sr, duration=0.15, closed=True, variation=0):
    n = int(sr*duration)
    noise = np.random.randn(n)
    env = np.exp(-np.linspace(0, duration, n)*(28+variation*2 if closed else 9+variation))
    return noise * env * (0.25 if closed else 0.18)

def synth_bass_note(midi, sr, duration, velocity=0.7, variation=0):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    f0 = note_to_freq(midi)
    detune = variation * 0.02
    # Richer bass: sine + octave + 5th harmonic
    wave = np.sin(2*np.pi*f0*t) + 0.4*np.sin(2*np.pi*2*f0*t*(1+detune)) + 0.15*np.sin(2*np.pi*3*f0*t) + 0.08*np.sin(2*np.pi*1.5*f0*t)
    env = adsr_envelope(n, sr, attack=0.01, decay=0.1, sustain=0.8, release=0.15)
    return wave * env * velocity * 0.6

def synth_chord(midis, sr, duration, velocity=0.5, bright=False, variation=0):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    wave = np.zeros(n)
    for midi in midis:
        f0 = note_to_freq(midi + variation*0.05)
        if bright:
            for h in range(1, 7):
                amp = 1.0/(h**1.4)
                # Slight chorus
                wave += amp * np.sin(2*np.pi*f0*h*t + variation*0.1*h)
        else:
            wave += np.sin(2*np.pi*f0*t) + 0.35*np.sin(2*np.pi*2*f0*t) + 0.12*np.sin(2*np.pi*3*f0*t)
    env = adsr_envelope(n, sr, attack=0.08 if not bright else 0.015, decay=0.2, sustain=0.6, release=0.3)
    wave = wave / (len(midis) or 1)
    return wave * env * velocity * 0.4

def get_chord_progressions_library():
    return {
        "warm-acoustic": {
            "major": [[0, 7, 9, 5], [0, 5, 9, 7], [0, 9, 5, 7], [0, 5, 0, 7]],
            "minor": [[0, 8, 3, 10], [0, 3, 8, 10], [0, 8, 10, 3]]
        },
        "lofi-chill": {
            "major": [[0, 5, 9, 7], [0, 9, 5, 0], [9, 5, 0, 7], [0, 3, 5, 7]],
            "minor": [[0, 8, 10, 3], [0, 10, 8, 3]]
        },
        "piano-ballad": {
            "major": [[0, 5, 9, 5], [0, 7, 9, 5], [0, 9, 7, 5]],
            "minor": [[0, 5, 8, 10], [0, 8, 5, 10]]
        },
        "indie-pop": {
            "major": [[0, 9, 5, 7], [0, 5, 9, 7], [5, 9, 0, 7], [0, 7, 5, 9]],
            "minor": [[0, 3, 8, 10], [0, 8, 3, 10]]
        },
        "cinematic": {
            "major": [[0, 5, 3, 7], [0, 3, 5, 7], [0, 5, 0, 3]],
            "minor": [[0, 5, 8, 7], [0, 8, 5, 7]]
        }
    }

def get_diatonic_chords(root_midi, is_major):
    """
    Returns list of diatonic triads in key: each as (degree_offset, chord_type, notes_intervals)
    For major: I(0 maj), ii(2 min), iii(4 min), IV(5 maj), V(7 maj), vi(9 min), vii°(11 dim)
    For minor: i(0 min), ii°(2 dim), III(3 maj), iv(5 min), v(7 min), VI(8 maj), VII(10 maj)
    """
    if is_major:
        # degree, is_major, intervals from root
        chords = [
            (0, True, [0,4,7]),   # I
            (2, False, [0,3,7]),  # ii
            (4, False, [0,3,7]),  # iii
            (5, True, [0,4,7]),   # IV
            (7, True, [0,4,7]),   # V
            (9, False, [0,3,7]),  # vi
            (11, False, [0,3,6]), # vii°
        ]
    else:
        chords = [
            (0, False, [0,3,7]),  # i
            (2, False, [0,3,6]),  # ii°
            (3, True, [0,4,7]),   # III
            (5, False, [0,3,7]),  # iv
            (7, False, [0,3,7]),  # v (natural minor)
            (8, True, [0,4,7]),   # VI
            (10, True, [0,4,7]),  # VII
        ]
    result = []
    for deg, maj, intervals in chords:
        chord_root = root_midi + deg
        notes = [chord_root + iv for iv in intervals]
        # pitch classes
        pcs = [n % 12 for n in notes]
        result.append({
            "degree": deg,
            "is_major": maj,
            "root": chord_root,
            "notes": notes,
            "pcs": pcs,
            "intervals": intervals
        })
    return result

def detect_f0_in_segment(audio, sr):
    """
    Detect F0 in a short audio segment via autocorrelation.
    Returns Hz or None.
    """
    if len(audio) < sr*0.02:  # need at least 20ms
        return None
    if np.mean(np.abs(audio)) < 0.008:
        return None
    # Remove DC, window
    frame = audio - np.mean(audio)
    # Use 0.1 sec window max
    if len(frame) > int(sr*0.15):
        frame = frame[:int(sr*0.15)]
    # Autocorr
    corr = np.correlate(frame, frame, mode='full')[len(frame)-1:]
    # Find peak in vocal range 80-500Hz
    min_period = int(sr / 500)
    max_period = int(sr / 80)
    if max_period >= len(corr):
        max_period = len(corr)-1
    if min_period >= max_period:
        return None
    # Zero out below min_period
    corr[:min_period] = 0
    # Find max in range
    search = corr[min_period:max_period]
    if len(search) == 0:
        return None
    peak = np.argmax(search) + min_period
    if corr[peak] < 0.3 * corr[0]:
        return None
    f0 = sr / peak
    if 70 < f0 < 600:
        return float(f0)
    return None

def analyze_vocal_per_beat_and_bar(vocal_path: Path, beat_times, bar_times, analysis):
    """
    v0.8: Analyze F0 per beat AND per bar for true melody following.
    Returns:
      f0_per_beat: list per beat interval
      f0_per_bar: list per bar (avg of beats in bar)
      energy_per_beat, energy_per_bar
      midi_per_beat, midi_per_bar
    """
    f0_per_beat = []
    energy_per_beat = []
    midi_per_beat = []
    f0_per_bar = []
    energy_per_bar = []
    midi_per_bar = []

    try:
        y_vocal, sr_v = sf.read(str(vocal_path))
        if y_vocal.ndim > 1:
            y_vocal = np.mean(y_vocal, axis=1)
        
        # Per beat
        for i in range(len(beat_times)):
            start_t = beat_times[i]
            end_t = beat_times[i+1] if i+1 < len(beat_times) else start_t + 0.5
            start_s = int(start_t * sr_v)
            end_s = int(min(end_t * sr_v, len(y_vocal)))
            if end_s <= start_s:
                f0_per_beat.append(analysis.get("f0_mean_hz", 180))
                energy_per_beat.append(0.05)
                midi_per_beat.append(69 + 12*math.log2(analysis.get("f0_mean_hz",180)/440.0))
                continue
            seg = y_vocal[start_s:end_s]
            energy = float(np.mean(np.abs(seg)))
            energy_per_beat.append(energy)
            f0 = detect_f0_in_segment(seg, sr_v)
            if f0 is None:
                f0 = f0_per_beat[-1] if f0_per_beat else analysis.get("f0_mean_hz", 180)
            f0_per_beat.append(float(f0))
            midi = 69 + 12*math.log2(f0/440.0) if f0>0 else 60
            midi_per_beat.append(float(midi))

        # Per bar: average of beats in bar
        for bar_idx in range(len(bar_times)):
            bar_start = bar_times[bar_idx]
            bar_end = bar_times[bar_idx+1] if bar_idx+1 < len(bar_times) else bar_start + 2.0
            # Find beats in this bar
            beats_in_bar = [j for j, bt in enumerate(beat_times) if bar_start <= bt < bar_end]
            if beats_in_bar:
                # Average F0 of beats in bar that have energy
                f0s = [f0_per_beat[j] for j in beats_in_bar if energy_per_beat[j] > 0.015]
                energies = [energy_per_beat[j] for j in beats_in_bar]
                if f0s:
                    avg_f0 = float(np.mean(f0s))
                    avg_energy = float(np.mean(energies))
                    avg_midi = float(np.mean([midi_per_beat[j] for j in beats_in_bar if energy_per_beat[j] > 0.015] or [60]))
                else:
                    avg_f0 = f0_per_bar[-1] if f0_per_bar else analysis.get("f0_mean_hz", 180)
                    avg_energy = 0.02
                    avg_midi = 60
            else:
                # Fallback: analyze bar audio directly
                start_s = int(bar_start * sr_v)
                end_s = int(min(bar_end * sr_v, len(y_vocal)))
                if end_s > start_s:
                    seg = y_vocal[start_s:end_s]
                    avg_energy = float(np.mean(np.abs(seg)))
                    f0 = detect_f0_in_segment(seg, sr_v)
                    avg_f0 = f0 if f0 else (f0_per_bar[-1] if f0_per_bar else analysis.get("f0_mean_hz", 180))
                    avg_midi = 69 + 12*math.log2(avg_f0/440.0) if avg_f0>0 else 60
                else:
                    avg_f0 = analysis.get("f0_mean_hz", 180)
                    avg_energy = 0.05
                    avg_midi = 60
            f0_per_bar.append(avg_f0)
            energy_per_bar.append(avg_energy)
            midi_per_bar.append(avg_midi)

        print(f"[generator] Per-beat F0: {[f'{x:.0f}' for x in f0_per_beat[:12]]} midi {[f'{x:.0f}' for x in midi_per_beat[:12]]}")
        print(f"[generator] Per-bar F0: {[f'{x:.0f}' for x in f0_per_bar[:8]]} midi {[f'{x:.0f}' for x in midi_per_bar[:8]]} Energy: {[f'{x:.3f}' for x in energy_per_bar[:8]]}")

    except Exception as e:
        print(f"[generator] Per-beat analysis failed {e}")
        import traceback
        traceback.print_exc()
        num_beats = len(beat_times)
        num_bars = len(bar_times)
        f0_per_beat = [analysis.get("f0_mean_hz", 180)] * num_beats
        energy_per_beat = [0.1] * num_beats
        midi_per_beat = [60] * num_beats
        f0_per_bar = [analysis.get("f0_mean_hz", 180)] * num_bars
        energy_per_bar = [0.1] * num_bars
        midi_per_bar = [60] * num_bars

    return f0_per_beat, energy_per_beat, midi_per_beat, f0_per_bar, energy_per_bar, midi_per_bar

def choose_chord_for_vocal_note(vocal_midi, vocal_pc, diatonic_chords, expected_degree, prev_chord, seed):
    """
    Choose best chord that harmonizes vocal note.
    Scoring:
    - Melody fit: vocal is root (+10), 3rd (+7), 5th (+5), 7th (+3), tension (+1), non-chord (-5)
    - Progression: if degree matches expected from progression library (+4)
    - Voice leading: share notes with prev chord (+2 per shared pc)
    - Random small for variation
    """
    best_score = -1000
    best_chord = diatonic_chords[0]

    for chord in diatonic_chords:
        score = 0
        pcs = chord["pcs"]
        # Melody fit
        if vocal_pc in pcs:
            # Which interval is vocal?
            root_pc = chord["root"] % 12
            intervals = [(pc - root_pc) % 12 for pc in pcs]
            vocal_interval = (vocal_pc - root_pc) % 12
            if vocal_interval == 0:
                score += 10  # root
            elif vocal_interval in (3,4):  # minor/major 3rd
                score += 7
            elif vocal_interval == 7:  # 5th
                score += 5
            elif vocal_interval in (10,11):  # 7th
                score += 3
            else:
                score += 1
        else:
            # Check if vocal is 9th, 11th, 13th tension (allowed but less)
            root_pc = chord["root"] % 12
            vocal_interval = (vocal_pc - root_pc) % 12
            if vocal_interval in (1,2,5,9):  # 9th, 11th, 13th tensions
                score += 0.5
            else:
                score -= 5  # avoid strong dissonance

        # Progression match
        if expected_degree is not None and chord["degree"] == expected_degree:
            score += 4
        # Also bonus for I, V, vi which are common
        if chord["degree"] in (0,7,9):
            score += 1

        # Voice leading
        if prev_chord:
            shared = len(set(pcs) & set(prev_chord["pcs"]))
            score += shared * 1.5

        # Small random for variation per song
        score += (seed % 10) * 0.05 * (1 if chord["degree"] % 2 == 0 else -1)

        if score > best_score:
            best_score = score
            best_chord = chord

    return best_chord, best_score

def generate_accompaniment(analysis: dict, out_path: Path, style="warm-acoustic", duration_sec=None, vocal_path: Path = None):
    sr = 44100
    bpm = float(analysis.get("bpm", 90.0) or 90.0)
    bpm = float(np.clip(bpm, 45, 180))
    key_str = analysis.get("key", "C major")
    is_major = analysis.get("is_major", True)
    file_hash = analysis.get("file_hash", "00000000")
    beat_times = analysis.get("beat_times", [])
    onset_times = analysis.get("onset_times", [])
    first_vocal_time = analysis.get("first_vocal_time", 0.0)
    bar_times = analysis.get("bar_times", [])
    
    try:
        seed = int(file_hash[:6], 16) % 10000
    except:
        seed = int(bpm*10 + hash(key_str) % 1000) % 10000
    
    np.random.seed(seed)
    random.seed(seed)
    print(f"[generator] v0.8 MELODY-FOLLOWING {style} {key_str} {bpm} BPM seed {seed} hash {file_hash} beats {len(beat_times)} bars {len(bar_times)} first_vocal {first_vocal_time:.2f}s")

    try:
        root_name = key_str.split()[0]
        root_semi = {n:i for i,n in enumerate(NOTE_NAMES)}.get(root_name, 0)
        key_root_midi = 60 + root_semi  # keep original key for harmonization
        root_midi = key_root_midi
        f0_mean = analysis.get("f0_mean_hz", 180)
        # Adjust for bass range only, but keep key_root for chords
        if f0_mean > 300:
            root_midi = key_root_midi - 12
        elif f0_mean > 220:
            root_midi = key_root_midi - 5
        elif f0_mean < 130:
            root_midi = key_root_midi + 7
        else:
            root_midi = key_root_midi
    except:
        key_root_midi = 60
        root_midi = 60

    total_duration = float(duration_sec or analysis.get("duration_sec", 30.0)) + 1.2
    if not bar_times:
        beat_sec = 60.0 / bpm
        bar_sec = beat_sec * 4
        num_bars = int(math.ceil(total_duration / bar_sec)) + 1
        bar_times = [i*bar_sec for i in range(num_bars)]
    else:
        beat_sec = 60.0 / bpm
        bar_sec = beat_sec * 4
        while bar_times[-1] < total_duration:
            bar_times.append(bar_times[-1] + bar_sec)

    if not beat_times:
        beat_sec = 60.0 / bpm
        num_beats = int(math.ceil(total_duration / beat_sec)) + 4
        beat_times = [i*beat_sec for i in range(num_beats)]
    else:
        beat_sec = 60.0 / bpm
        while beat_times[-1] < total_duration:
            beat_times.append(beat_times[-1] + beat_sec)

    n_total = int(sr * total_duration)
    mix_left = np.zeros(n_total, dtype=np.float32)
    mix_right = np.zeros(n_total, dtype=np.float32)

    # Per-beat and per-bar analysis
    if vocal_path:
        f0_per_beat, energy_per_beat, midi_per_beat, f0_per_bar, energy_per_bar, midi_per_bar = analyze_vocal_per_beat_and_bar(vocal_path, beat_times, bar_times, analysis)
    else:
        f0_per_beat = [analysis.get("f0_mean_hz",180)]*len(beat_times)
        energy_per_beat = [0.1]*len(beat_times)
        midi_per_beat = [69+12*math.log2(analysis.get("f0_mean_hz",180)/440.0)]*len(beat_times)
        f0_per_bar = [analysis.get("f0_mean_hz",180)]*len(bar_times)
        energy_per_bar = [0.1]*len(bar_times)
        midi_per_bar = [60]*len(bar_times)

    # Diatonic chords in key
    diatonic_chords = get_diatonic_chords(key_root_midi, is_major)
    # Progression library for expected degrees
    prog_lib = get_chord_progressions_library()
    style_lib = prog_lib.get(style, prog_lib["warm-acoustic"])
    key_type = "major" if is_major else "minor"
    progressions = style_lib.get(key_type, style_lib["major"])
    prog_idx = seed % len(progressions)
    expected_degrees = progressions[prog_idx]  # e.g. [0,7,9,5]
    print(f"[generator] Style {style} {key_type} prog {prog_idx} degrees {expected_degrees} diatonic {len(diatonic_chords)} chords")

    # For each bar, choose chord that harmonizes vocal
    chosen_chords_per_bar = []
    prev_chord = None
    for bar_idx in range(len(bar_times)):
        vocal_midi = midi_per_bar[bar_idx] if bar_idx < len(midi_per_bar) else 60
        vocal_pc = int(round(vocal_midi)) % 12
        expected_deg = expected_degrees[bar_idx % len(expected_degrees)] if expected_degrees else None

        best_chord, score = choose_chord_for_vocal_note(vocal_midi, vocal_pc, diatonic_chords, expected_deg, prev_chord, seed+bar_idx)
        chosen_chords_per_bar.append(best_chord)
        prev_chord = best_chord
        print(f"[generator] Bar {bar_idx} vocal midi {vocal_midi:.0f} pc {NOTE_NAMES[vocal_pc]} -> chord deg {best_chord['degree']} root {NOTE_NAMES[best_chord['root']%12]} score {score:.1f} contains vocal? {vocal_pc in best_chord['pcs']}")

    num_bars = len(bar_times)
    drum_pattern_type = seed % 3
    if bpm > 125:
        drum_pattern_type = 0
    elif bpm < 85:
        drum_pattern_type = 2

    variation = (seed % 10) / 10.0
    kick = synth_kick(sr, variation=variation)
    snare = synth_snare(sr, variation=variation)
    hat_closed = synth_hat(sr, 0.12, closed=True, variation=variation)
    hat_open = synth_hat(sr, 0.25, closed=False, variation=variation)

    for bar_idx in range(num_bars):
        bar_start_t = bar_times[bar_idx]
        bar_end_t = bar_times[bar_idx+1] if bar_idx+1 < len(bar_times) else bar_start_t + (60.0/bpm*4)
        bar_duration = bar_end_t - bar_start_t
        if bar_duration <= 0:
            bar_duration = 60.0/bpm*4
        bar_start = int(bar_start_t * sr)
        if bar_start >= n_total:
            break

        bar_f0 = f0_per_bar[bar_idx] if bar_idx < len(f0_per_bar) else analysis.get("f0_mean_hz",180)
        bar_energy = energy_per_bar[bar_idx] if bar_idx < len(energy_per_bar) else 0.1
        bar_midi = midi_per_bar[bar_idx] if bar_idx < len(midi_per_bar) else 60
        
        is_intro = bar_start_t + bar_duration < first_vocal_time - 0.2
        is_silence_bar = bar_energy < 0.015

        # Chosen chord that harmonizes vocal
        chord_info = chosen_chords_per_bar[bar_idx] if bar_idx < len(chosen_chords_per_bar) else diatonic_chords[0]
        chord_root = chord_info["root"]
        # Build chord notes with voicing: root-12 for bass, plus upper notes
        # Upper chord: 3 notes in mid range
        upper_intervals = chord_info["intervals"]  # e.g. [0,4,7]
        # For voicing, put root in middle C area, not too low
        base = 60 + (chord_root % 12)  # C4 + degree
        while base < 60:
            base += 12
        while base > 67:
            base -= 12
        chord_notes_upper = [base + iv for iv in upper_intervals]
        # Add octave for richness
        chord_notes_full = [chord_root-12, base, base+upper_intervals[1], base+upper_intervals[2], base+upper_intervals[2]+12]

        # Bass root: root of chord, ~19 semitones below vocal for support, clamped to C2-C3
        bass_root = chord_root
        target_bass_midi = bar_midi - 19
        while bass_root > target_bass_midi + 7:
            bass_root -= 12
        while bass_root < target_bass_midi - 7:
            bass_root += 12
        while bass_root < 36:
            bass_root += 12
        while bass_root > 50:
            bass_root -= 12

        # Bass
        if style == "piano-ballad":
            vel = 0.68 + (bar_energy*0.5)
            if is_intro:
                vel *= 0.6
            if is_silence_bar:
                vel *= 0.3
            note = synth_bass_note(bass_root, sr, bar_duration*0.9, velocity=vel, variation=variation)
            s = bar_start
            e = min(s+len(note), n_total)
            if s < n_total:
                mix_left[s:e] += note[:e-s] * 0.9
                mix_right[s:e] += note[:e-s] * 0.9
        else:
            beats_in_bar = [bt for bt in beat_times if bar_start_t <= bt < bar_end_t]
            if not beats_in_bar:
                beats_in_bar = [bar_start_t + i*(bar_duration/4) for i in range(4)]
            for b_idx, beat_t in enumerate(beats_in_bar):
                if style == "lofi-chill" and b_idx % 2 == 1 and (seed+bar_idx)%2==0:
                    continue
                if drum_pattern_type == 2 and b_idx in (1,3) and random.random() > 0.6:
                    continue
                base_vel = 0.65 if b_idx==0 else 0.48
                vel = base_vel + bar_energy*0.3 + random.random()*0.1
                if is_intro:
                    vel *= 0.7
                if is_silence_bar:
                    vel *= 0.25
                dur = bar_duration/4 * (1.7 if b_idx==0 else 0.85)
                note = synth_bass_note(bass_root, sr, dur, velocity=vel, variation=variation)
                s = int(beat_t * sr)
                e = min(s+len(note), n_total)
                if 0 <= s < n_total:
                    mix_left[s:e] += note[:e-s] * 0.85
                    mix_right[s:e] += note[:e-s] * 0.85

        # Chords: at bar start, duration = bar_duration, velocity follows energy
        is_bright = style in ("warm-acoustic", "indie-pop", "piano-ballad")
        upper_chord = chord_notes_full[1:]  # without bass root duplicate
        use_strum = (style == "warm-acoustic" and (seed % 2 == 0)) or (seed % 3 == 0)
        chord_vel_base = 0.35 + bar_energy*0.4
        if is_intro:
            chord_vel_base *= 0.7
        if is_silence_bar:
            chord_vel_base *= 0.35
        
        if use_strum and style in ("warm-acoustic", "indie-pop"):
            for idx, midi_note in enumerate(upper_chord):
                delay = idx * (0.025 + random.random()*0.015)
                vel = chord_vel_base + random.random()*0.1
                note = synth_chord([midi_note], sr, bar_duration - delay, velocity=vel, bright=True, variation=variation)
                s = bar_start + int(delay*sr)
                e = min(s+len(note), n_total)
                pan = (idx / max(len(upper_chord)-1,1)) * 0.6 - 0.3 + random.random()*0.1
                if s < n_total:
                    mix_left[s:e] += note[:e-s] * (0.5 - pan)
                    mix_right[s:e] += note[:e-s] * (0.5 + pan)
        else:
            vel = chord_vel_base + random.random()*0.1 + (0.05 if bar_idx % 4 == 0 else 0)
            chord_wave = synth_chord(upper_chord, sr, bar_duration, velocity=vel, bright=is_bright, variation=variation)
            s = bar_start
            e = min(s+len(chord_wave), n_total)
            if s < n_total:
                mix_left[s:e] += chord_wave[:e-s] * 0.7
                mix_right[s:e] += chord_wave[:e-s] * 0.7

        # Arpeggio: follow vocal melody contour
        if style in ("indie-pop", "cinematic", "lofi-chill"):
            if not (is_silence_bar or (is_intro and random.random() > 0.5)):
                arp_notes = upper_chord[:3]
                beats_in_bar = [bt for bt in beat_times if bar_start_t <= bt < bar_end_t]
                if len(beats_in_bar) >= 2:
                    for beat_idx, beat_t in enumerate(beats_in_bar):
                        for sub in range(2):
                            t = beat_t + sub * (bar_duration/len(beats_in_bar)/2)
                            if random.random() > 0.85:
                                continue
                            # Arp follows vocal contour: if vocal high, arp high
                            octave = 12 if bar_midi > 70 else 0
                            midi_note = arp_notes[(beat_idx*2+sub) % len(arp_notes)] + octave
                            vel = 0.22 + bar_energy*0.2 + random.random()*0.08
                            if is_intro:
                                vel *= 0.5
                            note = synth_chord([midi_note], sr, (bar_duration/len(beats_in_bar)/2)*0.85, velocity=vel, bright=True, variation=variation)
                            s = int(t*sr)
                            e = min(s+len(note), n_total)
                            if 0 <= s < n_total:
                                pan = 0.3 if (beat_idx*2+sub)%2==0 else -0.3
                                mix_left[s:e] += note[:e-s] * (0.5 - pan*0.3)
                                mix_right[s:e] += note[:e-s] * (0.5 + pan*0.3)

        # Drums: on beat_times
        beats_in_bar = [bt for bt in beat_times if bar_start_t <= bt < bar_end_t]
        if not beats_in_bar:
            beats_in_bar = [bar_start_t + i*(bar_duration/4) for i in range(4)]

        for b_idx, beat_t in enumerate(beats_in_bar):
            beat_start = int(beat_t * sr)
            kick_beats = [0]
            if drum_pattern_type == 0:
                kick_beats = [0,2] if len(beats_in_bar)==4 else [0]
                if style=="indie-pop" and len(beats_in_bar)>2:
                    kick_beats = [0,1,2]
                if bar_idx % 2 == 1 and random.random() > 0.5 and len(beats_in_bar)>3:
                    kick_beats.append(3)
            elif drum_pattern_type == 1:
                kick_beats = [0,2]
            else:
                kick_beats = [0]

            if b_idx in kick_beats:
                if is_silence_bar and b_idx != 0:
                    continue
                if bar_energy > 0.08 or b_idx==0 or is_intro:
                    s = beat_start
                    humanize = int((random.random()-0.5)*0.008*sr)
                    s = max(0, s+humanize)
                    e = min(s+len(kick), n_total)
                    if s < n_total:
                        vel = 0.68 + bar_energy*0.2 + random.random()*0.1
                        if is_intro:
                            vel *= 0.7
                        mix_left[s:e] += kick[:e-s] * vel
                        mix_right[s:e] += kick[:e-s] * vel

            if b_idx in (1,3):
                if drum_pattern_type == 2 and b_idx==1 and random.random()>0.7:
                    continue
                if is_silence_bar and b_idx==1:
                    continue
                s = beat_start
                humanize = int((random.random()-0.5)*0.008*sr)
                s = max(0, s+humanize)
                e = min(s+len(snare), n_total)
                if s < n_total:
                    vel = 0.52 + bar_energy*0.2 + random.random()*0.15
                    if is_intro:
                        vel *= 0.6
                    if is_silence_bar:
                        vel *= 0.3
                    mix_left[s:e] += snare[:e-s] * vel
                    mix_right[s:e] += snare[:e-s] * vel

            hat_div = 2
            for hi in range(hat_div):
                hs_t = beat_t + hi*(bar_duration/len(beats_in_bar)/hat_div)
                hs = int(hs_t * sr)
                is_open = (b_idx==len(beats_in_bar)-1 and hi==hat_div-1 and random.random()>0.3)
                hat = hat_open if is_open else hat_closed
                he = min(hs+len(hat), n_total)
                if hs < n_total and random.random()>0.15:
                    hat_vel = 0.45 + bar_energy*0.1 + random.random()*0.15
                    if is_silence_bar:
                        hat_vel *= 0.4
                    if is_intro:
                        hat_vel *= 0.6
                    if bar_energy < 0.02:
                        hat_vel *= 0.5
                    mix_left[hs:he] += hat[:he-hs] * hat_vel
                    mix_right[hs:he] += hat[:he-hs] * hat_vel

        # Onset accent
        onsets_in_bar = [ot for ot in onset_times if bar_start_t <= ot < bar_end_t]
        for ot in onsets_in_bar:
            accent_t = max(bar_start_t, ot - 0.01)
            s = int(accent_t * sr)
            e = min(s+len(hat_closed), n_total)
            if s < n_total and not is_silence_bar:
                mix_left[s:e] += hat_closed[:e-s] * 0.25
                mix_right[s:e] += hat_closed[:e-s] * 0.25

    if style == "lofi-chill":
        a = 0.15
        for ch in (mix_left, mix_right):
            for i in range(1, len(ch)):
                ch[i] = (1-a)*ch[i] + a*ch[i-1]
        crackle = np.random.randn(n_total) * 0.015
        gate = (np.random.rand(n_total) > 0.995).astype(float)
        crackle = crackle * gate
        mix_left += crackle * 0.5
        mix_right += crackle * 0.5

    max_val = max(np.max(np.abs(mix_left)), np.max(np.abs(mix_right)), 1e-6)
    if max_val > 0.8:
        scale = 0.8 / max_val
        mix_left *= scale
        mix_right *= scale

    stereo = np.stack([mix_left, mix_right], axis=1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), stereo, sr)
    print(f"[generator] Saved {out_path}, {total_duration:.1f}s, {len(bar_times)} bars melody-following, seed {seed}, hash {file_hash}")
    return out_path
