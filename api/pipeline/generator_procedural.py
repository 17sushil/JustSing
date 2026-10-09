"""
SingSmith Procedural Generator v0.9 — Studio karaoke: rich instruments + reverb
FIXES poor results: cheap sine -> saw + filter + chorus + reverb, tight groove

- Same melody-following harmony as v0.8 (chords contain vocal notes)
- Richer synth: saw + lowpass + chorus for chords, warm sub for bass
- Better drums: kick with click, snare with body+noise, hats with HP filter
- Simple Freeverb-like reverb, master glue
- Groove: bass on 1 and 3, not every beat, leaves space
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

def one_pole_lowpass(x, cutoff, sr):
    # Simple one-pole LPF
    rc = 1.0 / (2 * math.pi * cutoff)
    dt = 1.0 / sr
    alpha = dt / (rc + dt)
    y = np.zeros_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = y[i-1] + alpha * (x[i] - y[i-1])
    return y

def saw_wave(freq, t, sr):
    # Bandlimited-ish saw via sum of sines up to Nyquist
    # For simplicity, use naive saw but filter later
    phase = 2 * math.pi * freq * t
    # naive saw: 2*(phase/(2pi) %1)-1
    saw = 2 * ( (freq * t) % 1 ) - 1
    return saw

def synth_kick_v09(sr, duration=0.5, variation=0):
    n = int(sr*duration)
    t = np.linspace(0, duration, n)
    # Body: sine sweep 150->50 Hz
    base_pitch = 150 + variation*8
    freq = base_pitch * np.exp(-t*22) + 48
    phase = 2*np.pi*np.cumsum(freq)/sr
    body = np.sin(phase)
    # Click: short high freq burst at start
    click_env = np.exp(-t*120)
    click = np.sin(2*np.pi*3000*t) * click_env * 0.3
    # Envelope
    amp_env = np.exp(-t*(6+variation*0.4))
    wave = (body + click) * amp_env
    # Lowpass to keep warm
    wave = one_pole_lowpass(wave, 800, sr)
    return wave * 0.95

def synth_snare_v09(sr, duration=0.35, variation=0):
    n = int(sr*duration)
    t = np.linspace(0, duration, n)
    # Body: sine at 180Hz
    body_freq = 175 + variation*10
    body = np.sin(2*np.pi*body_freq*t) * np.exp(-t*12) * 0.6
    # Noise: bandpassed
    noise = np.random.randn(n)
    # Highpass noise via simple diff
    noise_hp = np.diff(np.concatenate([[0], noise])) * 0.7
    # Envelopes
    noise_env = np.exp(-t*(14+variation))
    # Mix
    wave = body + noise_hp * noise_env * 0.8
    # Slight lowpass
    wave = one_pole_lowpass(wave, 4000, sr)
    return wave * 0.65

def synth_hat_v09(sr, duration=0.14, closed=True, variation=0):
    n = int(sr*duration)
    # White noise -> highpass
    noise = np.random.randn(n)
    # Highpass: simple
    b = [1, -1]
    # Use lfilter-like via diff for speed
    hp = noise - np.concatenate([[0], noise[:-1]]) * 0.95
    # Envelope
    decay = 30+variation*3 if closed else 10+variation
    env = np.exp(-np.linspace(0, duration, n)*decay)
    wave = hp * env
    # Bandpass-ish around 8k
    wave = one_pole_lowpass(wave, 9000, sr)
    return wave * (0.28 if closed else 0.20)

def synth_bass_v09(midi, sr, duration, velocity=0.7, variation=0):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    f0 = note_to_freq(midi)
    # Warm bass: sine + saw + sub
    # Sub: sine at f0
    sub = np.sin(2*np.pi*f0*t)
    # Saw with lowpass for warmth
    saw = saw_wave(f0, t, sr) * 0.35
    saw2 = saw_wave(f0*2, t, sr) * 0.15
    # Mix
    wave = sub + saw + saw2
    # Lowpass at ~800Hz for warmth, varies with velocity
    cutoff = 300 + velocity*500
    wave = one_pole_lowpass(wave, cutoff, sr)
    # ADSR: punchy attack
    env = adsr_envelope(n, sr, attack=0.005, decay=0.12, sustain=0.75, release=0.18)
    # Slight saturation
    wave = np.tanh(wave * 1.2) * 0.9
    return wave * env * velocity * 0.7

def synth_chord_v09(midis, sr, duration, velocity=0.5, bright=False, variation=0, style="warm-acoustic"):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    wave = np.zeros(n)
    # For each note, use saw + sine mix with detune for chorus
    for idx, midi in enumerate(midis):
        f0 = note_to_freq(midi + variation*0.03)
        # Detune for chorus
        detune = (random.random()-0.5)*0.008  # ~0.8% detune
        f0_d = f0 * (1+detune)
        if bright or style in ("warm-acoustic","indie-pop"):
            # Bright: saw + octave
            saw = saw_wave(f0, t, sr) * 0.5
            saw_d = saw_wave(f0_d, t, sr) * 0.35
            # Add sine for body
            sine = np.sin(2*np.pi*f0*t) * 0.3
            note_wave = saw + saw_d + sine
            # Lowpass at 3-5k for warmth
            note_wave = one_pole_lowpass(note_wave, 3500 if bright else 2500, sr)
        else:
            # Warm pad: sine + soft saw
            sine = np.sin(2*np.pi*f0*t) + 0.4*np.sin(2*np.pi*2*f0*t)
            saw = saw_wave(f0, t, sr) * 0.25
            note_wave = sine + saw
            note_wave = one_pole_lowpass(note_wave, 1800, sr)
        # Pan slightly via amplitude already handled outside, just sum
        wave += note_wave

    wave = wave / (len(midis) or 1)
    # ADSR
    if bright:
        env = adsr_envelope(n, sr, attack=0.012, decay=0.18, sustain=0.65, release=0.35)
    else:
        env = adsr_envelope(n, sr, attack=0.08, decay=0.25, sustain=0.6, release=0.4)
    # Soft saturation for warmth
    wave = np.tanh(wave * 0.9) 
    return wave * env * velocity * 0.45

def simple_reverb(stereo, sr, room=0.5, damp=0.5, mix=0.18):
    """
    Very simple Freeverb-like: comb filters + allpass
    stereo: (N,2)
    """
    try:
        N = len(stereo)
        # Comb filter delays (ms) from freeverb
        comb_delays = [int(sr * d) for d in [0.0297, 0.0371, 0.0411, 0.0437]]
        allpass_delays = [int(sr * d) for d in [0.005, 0.0017]]
        
        # Process each channel
        out = np.zeros_like(stereo)
        for ch in range(2):
            x = stereo[:, ch]
            # Combs in parallel
            comb_sum = np.zeros(N)
            for i, d in enumerate(comb_delays):
                buf = np.zeros(N)
                feedback = 0.7 + room*0.25
                # Simple comb: y[n] = x[n] + feedback * y[n-d]
                for n in range(N):
                    if n >= d:
                        buf[n] = x[n] + feedback * buf[n-d] * (1-damp*0.3)
                    else:
                        buf[n] = x[n]
                comb_sum += buf
            comb_sum /= len(comb_delays)
            # Allpass chain (simplified)
            y = comb_sum
            for d in allpass_delays:
                buf = np.zeros(N)
                for n in range(N):
                    if n >= d:
                        buf[n] = -0.5*y[n] + y[n-d] + 0.5*buf[n-d]
                    else:
                        buf[n] = y[n]
                y = buf
            out[:, ch] = y
        
        # Mix dry/wet
        wet = out * mix
        dry = stereo * (1-mix)
        return dry + wet
    except Exception as e:
        print(f"[reverb] failed {e}, returning dry")
        return stereo

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
    if is_major:
        chords = [
            (0, True, [0,4,7]),
            (2, False, [0,3,7]),
            (4, False, [0,3,7]),
            (5, True, [0,4,7]),
            (7, True, [0,4,7]),
            (9, False, [0,3,7]),
            (11, False, [0,3,6]),
        ]
    else:
        chords = [
            (0, False, [0,3,7]),
            (2, False, [0,3,6]),
            (3, True, [0,4,7]),
            (5, False, [0,3,7]),
            (7, False, [0,3,7]),
            (8, True, [0,4,7]),
            (10, True, [0,4,7]),
        ]
    result = []
    for deg, maj, intervals in chords:
        chord_root = root_midi + deg
        notes = [chord_root + iv for iv in intervals]
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
    if len(audio) < sr*0.02:
        return None
    if np.mean(np.abs(audio)) < 0.008:
        return None
    frame = audio - np.mean(audio)
    if len(frame) > int(sr*0.15):
        frame = frame[:int(sr*0.15)]
    corr = np.correlate(frame, frame, mode='full')[len(frame)-1:]
    min_period = int(sr / 500)
    max_period = int(sr / 80)
    if max_period >= len(corr):
        max_period = len(corr)-1
    if min_period >= max_period:
        return None
    corr[:min_period] = 0
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

        for bar_idx in range(len(bar_times)):
            bar_start = bar_times[bar_idx]
            bar_end = bar_times[bar_idx+1] if bar_idx+1 < len(bar_times) else bar_start + 2.0
            beats_in_bar = [j for j, bt in enumerate(beat_times) if bar_start <= bt < bar_end]
            if beats_in_bar:
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
    best_score = -1000
    best_chord = diatonic_chords[0]

    for chord in diatonic_chords:
        score = 0
        pcs = chord["pcs"]
        if vocal_pc in pcs:
            root_pc = chord["root"] % 12
            vocal_interval = (vocal_pc - root_pc) % 12
            if vocal_interval == 0:
                score += 10
            elif vocal_interval in (3,4):
                score += 7
            elif vocal_interval == 7:
                score += 5
            elif vocal_interval in (10,11):
                score += 3
            else:
                score += 1
        else:
            root_pc = chord["root"] % 12
            vocal_interval = (vocal_pc - root_pc) % 12
            if vocal_interval in (1,2,5,9):
                score += 0.5
            else:
                score -= 5

        if expected_degree is not None and chord["degree"] == expected_degree:
            score += 4
        if chord["degree"] in (0,7,9):
            score += 1

        if prev_chord:
            shared = len(set(pcs) & set(prev_chord["pcs"]))
            score += shared * 1.5

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
    print(f"[generator] v0.9 STUDIO {style} {key_str} {bpm} BPM seed {seed} hash {file_hash} beats {len(beat_times)} bars {len(bar_times)} first_vocal {first_vocal_time:.2f}s")

    try:
        root_name = key_str.split()[0]
        root_semi = {n:i for i,n in enumerate(NOTE_NAMES)}.get(root_name, 0)
        key_root_midi = 60 + root_semi
        root_midi = key_root_midi
        f0_mean = analysis.get("f0_mean_hz", 180)
        if f0_mean > 300:
            root_midi = key_root_midi - 12
        elif f0_mean > 220:
            root_midi = key_root_midi - 5
        elif f0_mean < 130:
            root_midi = key_root_midi + 7
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

    if vocal_path:
        f0_per_beat, energy_per_beat, midi_per_beat, f0_per_bar, energy_per_bar, midi_per_bar = analyze_vocal_per_beat_and_bar(vocal_path, beat_times, bar_times, analysis)
    else:
        f0_per_beat = [analysis.get("f0_mean_hz",180)]*len(beat_times)
        energy_per_beat = [0.1]*len(beat_times)
        midi_per_beat = [69+12*math.log2(analysis.get("f0_mean_hz",180)/440.0)]*len(beat_times)
        f0_per_bar = [analysis.get("f0_mean_hz",180)]*len(bar_times)
        energy_per_bar = [0.1]*len(bar_times)
        midi_per_bar = [60]*len(bar_times)

    diatonic_chords = get_diatonic_chords(key_root_midi, is_major)
    prog_lib = get_chord_progressions_library()
    style_lib = prog_lib.get(style, prog_lib["warm-acoustic"])
    key_type = "major" if is_major else "minor"
    progressions = style_lib.get(key_type, style_lib["major"])
    prog_idx = seed % len(progressions)
    expected_degrees = progressions[prog_idx]
    print(f"[generator] Style {style} {key_type} prog {prog_idx} degrees {expected_degrees}")

    chosen_chords_per_bar = []
    prev_chord = None
    for bar_idx in range(len(bar_times)):
        vocal_midi = midi_per_bar[bar_idx] if bar_idx < len(midi_per_bar) else 60
        vocal_pc = int(round(vocal_midi)) % 12
        expected_deg = expected_degrees[bar_idx % len(expected_degrees)] if expected_degrees else None
        best_chord, score = choose_chord_for_vocal_note(vocal_midi, vocal_pc, diatonic_chords, expected_deg, prev_chord, seed+bar_idx)
        chosen_chords_per_bar.append(best_chord)
        prev_chord = best_chord
        print(f"[generator] Bar {bar_idx} vocal {vocal_midi:.0f} {NOTE_NAMES[vocal_pc]} -> chord deg {best_chord['degree']} root {NOTE_NAMES[best_chord['root']%12]} score {score:.1f} contains? {vocal_pc in best_chord['pcs']}")

    num_bars = len(bar_times)
    drum_pattern_type = seed % 3
    if bpm > 125:
        drum_pattern_type = 0
    elif bpm < 85:
        drum_pattern_type = 2

    variation = (seed % 10) / 10.0
    kick = synth_kick_v09(sr, variation=variation)
    snare = synth_snare_v09(sr, variation=variation)
    hat_closed = synth_hat_v09(sr, 0.12, closed=True, variation=variation)
    hat_open = synth_hat_v09(sr, 0.25, closed=False, variation=variation)

    for bar_idx in range(num_bars):
        bar_start_t = bar_times[bar_idx]
        bar_end_t = bar_times[bar_idx+1] if bar_idx+1 < len(bar_times) else bar_start_t + (60.0/bpm*4)
        bar_duration = bar_end_t - bar_start_t
        if bar_duration <= 0:
            bar_duration = 60.0/bpm*4
        bar_start = int(bar_start_t * sr)
        if bar_start >= n_total:
            break

        bar_energy = energy_per_bar[bar_idx] if bar_idx < len(energy_per_bar) else 0.1
        bar_midi = midi_per_bar[bar_idx] if bar_idx < len(midi_per_bar) else 60
        
        is_intro = bar_start_t + bar_duration < first_vocal_time - 0.2
        is_silence_bar = bar_energy < 0.015

        chord_info = chosen_chords_per_bar[bar_idx] if bar_idx < len(chosen_chords_per_bar) else diatonic_chords[0]
        chord_root = chord_info["root"]
        upper_intervals = chord_info["intervals"]
        base = 60 + (chord_root % 12)
        while base < 60:
            base += 12
        while base > 67:
            base -= 12
        chord_notes_full = [chord_root-12, base, base+upper_intervals[1], base+upper_intervals[2], base+upper_intervals[2]+12]

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

        # Bass: play on 1 and 3 for groove, not every beat
        if style == "piano-ballad":
            vel = 0.72 + (bar_energy*0.45)
            if is_intro:
                vel *= 0.6
            if is_silence_bar:
                vel *= 0.3
            note = synth_bass_v09(bass_root, sr, bar_duration*0.9, velocity=vel, variation=variation)
            s = bar_start
            e = min(s+len(note), n_total)
            if s < n_total:
                mix_left[s:e] += note[:e-s] * 0.92
                mix_right[s:e] += note[:e-s] * 0.92
        else:
            beats_in_bar = [bt for bt in beat_times if bar_start_t <= bt < bar_end_t]
            if not beats_in_bar:
                beats_in_bar = [bar_start_t + i*(bar_duration/4) for i in range(4)]
            # Bass groove: only on 0 and 2 (1 and 3), with occasional 2nd beat
            for b_idx, beat_t in enumerate(beats_in_bar):
                # Play bass on downbeats
                if b_idx not in (0,2):
                    if not (style=="indie-pop" and b_idx==1 and random.random()>0.6):
                        continue
                base_vel = 0.70 if b_idx==0 else 0.52
                vel = base_vel + bar_energy*0.28 + random.random()*0.08
                if is_intro:
                    vel *= 0.65
                if is_silence_bar:
                    vel *= 0.2
                dur = bar_duration/4 * (1.8 if b_idx==0 else 1.0)
                note = synth_bass_v09(bass_root, sr, dur, velocity=vel, variation=variation)
                s = int(beat_t * sr)
                e = min(s+len(note), n_total)
                if 0 <= s < n_total:
                    mix_left[s:e] += note[:e-s] * 0.88
                    mix_right[s:e] += note[:e-s] * 0.88

        # Chords
        is_bright = style in ("warm-acoustic", "indie-pop", "piano-ballad")
        upper_chord = chord_notes_full[1:]
        use_strum = (style == "warm-acoustic" and (seed % 2 == 0)) or (seed % 3 == 0)
        chord_vel_base = 0.38 + bar_energy*0.38
        if is_intro:
            chord_vel_base *= 0.65
        if is_silence_bar:
            chord_vel_base *= 0.30
        
        if use_strum and style in ("warm-acoustic", "indie-pop"):
            for idx, midi_note in enumerate(upper_chord):
                delay = idx * (0.028 + random.random()*0.012)
                vel = chord_vel_base + random.random()*0.09
                note = synth_chord_v09([midi_note], sr, bar_duration - delay, velocity=vel, bright=True, variation=variation, style=style)
                s = bar_start + int(delay*sr)
                e = min(s+len(note), n_total)
                pan = (idx / max(len(upper_chord)-1,1)) * 0.7 - 0.35 + random.random()*0.08
                if s < n_total:
                    mix_left[s:e] += note[:e-s] * (0.55 - pan*0.6)
                    mix_right[s:e] += note[:e-s] * (0.55 + pan*0.6)
        else:
            vel = chord_vel_base + random.random()*0.09 + (0.06 if bar_idx % 4 == 0 else 0)
            chord_wave = synth_chord_v09(upper_chord, sr, bar_duration, velocity=vel, bright=is_bright, variation=variation, style=style)
            s = bar_start
            e = min(s+len(chord_wave), n_total)
            if s < n_total:
                # Slight stereo spread
                mix_left[s:e] += chord_wave[:e-s] * 0.72
                mix_right[s:e] += chord_wave[:e-s] * 0.72

        # Arpeggio
        if style in ("indie-pop", "cinematic", "lofi-chill"):
            if not (is_silence_bar or (is_intro and random.random() > 0.5)):
                arp_notes = upper_chord[:3]
                beats_in_bar = [bt for bt in beat_times if bar_start_t <= bt < bar_end_t]
                if len(beats_in_bar) >= 2:
                    for beat_idx, beat_t in enumerate(beats_in_bar):
                        for sub in range(2):
                            t = beat_t + sub * (bar_duration/len(beats_in_bar)/2)
                            if random.random() > 0.82:
                                continue
                            octave = 12 if bar_midi > 70 else 0
                            midi_note = arp_notes[(beat_idx*2+sub) % len(arp_notes)] + octave
                            vel = 0.24 + bar_energy*0.18 + random.random()*0.07
                            if is_intro:
                                vel *= 0.5
                            note = synth_chord_v09([midi_note], sr, (bar_duration/len(beats_in_bar)/2)*0.85, velocity=vel, bright=True, variation=variation, style=style)
                            s = int(t*sr)
                            e = min(s+len(note), n_total)
                            if 0 <= s < n_total:
                                pan = 0.35 if (beat_idx*2+sub)%2==0 else -0.35
                                mix_left[s:e] += note[:e-s] * (0.5 - pan*0.28)
                                mix_right[s:e] += note[:e-s] * (0.5 + pan*0.28)

        # Drums on beat_times
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
                if bar_energy > 0.07 or b_idx==0 or is_intro:
                    s = beat_start
                    humanize = int((random.random()-0.5)*0.006*sr)
                    s = max(0, s+humanize)
                    e = min(s+len(kick), n_total)
                    if s < n_total:
                        vel = 0.72 + bar_energy*0.18 + random.random()*0.08
                        if is_intro:
                            vel *= 0.65
                        mix_left[s:e] += kick[:e-s] * vel
                        mix_right[s:e] += kick[:e-s] * vel

            if b_idx in (1,3):
                if drum_pattern_type == 2 and b_idx==1 and random.random()>0.7:
                    continue
                if is_silence_bar and b_idx==1:
                    continue
                s = beat_start
                humanize = int((random.random()-0.5)*0.006*sr)
                s = max(0, s+humanize)
                e = min(s+len(snare), n_total)
                if s < n_total:
                    vel = 0.56 + bar_energy*0.18 + random.random()*0.12
                    if is_intro:
                        vel *= 0.55
                    if is_silence_bar:
                        vel *= 0.28
                    mix_left[s:e] += snare[:e-s] * vel
                    mix_right[s:e] += snare[:e-s] * vel

            hat_div = 2
            for hi in range(hat_div):
                hs_t = beat_t + hi*(bar_duration/len(beats_in_bar)/hat_div)
                hs = int(hs_t * sr)
                is_open = (b_idx==len(beats_in_bar)-1 and hi==hat_div-1 and random.random()>0.3)
                hat = hat_open if is_open else hat_closed
                he = min(hs+len(hat), n_total)
                if hs < n_total and random.random()>0.12:
                    hat_vel = 0.48 + bar_energy*0.09 + random.random()*0.12
                    if is_silence_bar:
                        hat_vel *= 0.35
                    if is_intro:
                        hat_vel *= 0.55
                    if bar_energy < 0.02:
                        hat_vel *= 0.45
                    mix_left[hs:he] += hat[:he-hs] * hat_vel
                    mix_right[hs:he] += hat[:he-hs] * hat_vel

        onsets_in_bar = [ot for ot in onset_times if bar_start_t <= ot < bar_end_t]
        for ot in onsets_in_bar:
            accent_t = max(bar_start_t, ot - 0.008)
            s = int(accent_t * sr)
            e = min(s+len(hat_closed), n_total)
            if s < n_total and not is_silence_bar:
                mix_left[s:e] += hat_closed[:e-s] * 0.22
                mix_right[s:e] += hat_closed[:e-s] * 0.22

    # Master: slight glue + reverb
    # Normalize first
    max_val = max(np.max(np.abs(mix_left)), np.max(np.abs(mix_right)), 1e-6)
    if max_val > 0.85:
        scale = 0.85 / max_val
        mix_left *= scale
        mix_right *= scale

    # Lofi vinyl
    if style == "lofi-chill":
        a = 0.18
        for ch in (mix_left, mix_right):
            for i in range(1, len(ch)):
                ch[i] = (1-a)*ch[i] + a*ch[i-1]
        crackle = np.random.randn(n_total) * 0.012
        gate = (np.random.rand(n_total) > 0.996).astype(float)
        crackle = crackle * gate
        mix_left += crackle * 0.5
        mix_right += crackle * 0.5

    # Reverb: 18% wet for spacious studio feel
    stereo = np.stack([mix_left, mix_right], axis=1)
    # Apply reverb based on style
    reverb_mix = 0.18
    if style == "cinematic":
        reverb_mix = 0.28
    elif style == "piano-ballad":
        reverb_mix = 0.22
    elif style == "lofi-chill":
        reverb_mix = 0.15

    stereo = simple_reverb(stereo, sr, room=0.6, damp=0.4, mix=reverb_mix)

    # Final limit
    max_val = np.max(np.abs(stereo))
    if max_val > 0.89:
        stereo = stereo * (0.89 / max_val)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), stereo, sr)
    print(f"[generator] v0.9 Saved {out_path}, {total_duration:.1f}s, {len(bar_times)} bars studio, seed {seed}, hash {file_hash}")
    return out_path
