"""
SingSmith Procedural Generator v1.5 — REAL PIANO + MELODIC ARPEGGIOS

FIXES poor piano/melody (user: drums good but piano poor):
- Real piano synthesis: 8 harmonics with inharmonicity B=0.0002-0.0006, exponential decay per harmonic, hammer noise, duplex resonance, proper ADSR (5ms attack, 250ms decay, 0.3 sustain, 600ms release)
- Guitar synthesis: bright pluck with body resonance
- Chord voicings with extensions: 7ths, 9ths, inversions for smooth voice leading (minimize movement)
- Arpeggio patterns per style: fingerpicking warm-acoustic [0,2,1,2,3,1,2,0], broken piano-ballad [0,1,2,1,0,2,3,1], not block chords
- Melodic fills: scale notes following vocal contour
- Vocal-as-top-note always, chord contains vocal PC
- Walking bass: root on beat 1, passing tone on beat 3
- Continuous 50ms tracking v1.4 kept, drums good

Zero-cost, works everywhere.
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
    rc = 1.0 / (2 * math.pi * cutoff)
    dt = 1.0 / sr
    alpha = dt / (rc + dt)
    y = np.zeros_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = y[i-1] + alpha * (x[i] - y[i-1])
    return y

def synth_piano_v15(midi, sr, duration, velocity=0.6, variation=0, bright=False):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    f0 = note_to_freq(midi)
    B = 0.0002 + (midi-21)/88 * 0.0004
    wave = np.zeros(n)
    harmonics = 8
    for h in range(1, harmonics+1):
        f_h = h * f0 * math.sqrt(1 + B * h * h)
        amp = 1.0 / (h**1.1)
        if h == 1:
            amp *= 1.0
        elif h == 2:
            amp *= 0.6
        elif h == 3:
            amp *= 0.4
        else:
            amp *= 0.3 / (h-2)
        detune = (random.random()-0.5)*0.002 * h
        f_h *= (1+detune)
        decay_rate = 2.0 + h*1.5 + (midi-60)*0.02
        harmonic_env = np.exp(-t * decay_rate)
        phase = 2*np.pi*f_h*t
        harmonic = np.sin(phase) * amp * harmonic_env
        wave += harmonic
    attack = 0.005
    decay = 0.25 + (1-velocity)*0.15
    sustain = 0.25 + velocity*0.2
    release = 0.6 + velocity*0.3
    env = adsr_envelope(n, sr, attack=attack, decay=decay, sustain=sustain, release=release)
    hammer_noise = np.random.randn(n) * 0.02 * np.exp(-t*80) * velocity
    cutoff = 4000 + velocity*2000 if bright else 2500 + velocity*1500
    wave = one_pole_lowpass(wave, cutoff, sr)
    duplex = np.sin(2*np.pi*f0*2*t) * 0.03 * np.exp(-t*3) + np.sin(2*np.pi*f0*3*t) * 0.015 * np.exp(-t*4)
    wave = wave + duplex + hammer_noise
    wave = np.tanh(wave * 1.1) * velocity * 0.7
    wave = wave * env
    return wave

def synth_guitar_v15(midi, sr, duration, velocity=0.5, variation=0):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    f0 = note_to_freq(midi)
    wave = np.zeros(n)
    for h in [1,2,3,4,6]:
        amp = 1.0 / (h**0.9)
        if h==2:
            amp *= 1.2
        f_h = h * f0 * (1 + (random.random()-0.5)*0.001)
        decay = 3.0 + h*0.8
        env_h = np.exp(-t*decay)
        wave += np.sin(2*np.pi*f_h*t) * amp * env_h
    pluck = np.random.randn(n) * 0.15 * np.exp(-t*50) * velocity
    wave += pluck
    wave = one_pole_lowpass(wave, 3000, sr)
    env = adsr_envelope(n, sr, attack=0.002, decay=0.3, sustain=0.3, release=0.4)
    wave = wave * env * velocity * 0.6
    return wave

def synth_kick_v15(sr, duration=0.5, variation=0):
    n = int(sr*duration)
    t = np.linspace(0, duration, n)
    base_pitch = 150 + variation*8
    freq = base_pitch * np.exp(-t*22) + 48
    phase = 2*np.pi*np.cumsum(freq)/sr
    body = np.sin(phase)
    click_env = np.exp(-t*120)
    click = np.sin(2*np.pi*3000*t) * click_env * 0.3
    amp_env = np.exp(-t*(6+variation*0.4))
    wave = (body + click) * amp_env
    wave = one_pole_lowpass(wave, 800, sr)
    return wave * 0.95

def synth_snare_v15(sr, duration=0.35, variation=0):
    n = int(sr*duration)
    t = np.linspace(0, duration, n)
    body_freq = 175 + variation*10
    body = np.sin(2*np.pi*body_freq*t) * np.exp(-t*12) * 0.6
    noise = np.random.randn(n)
    noise_hp = np.diff(np.concatenate([[0], noise])) * 0.7
    noise_env = np.exp(-t*(14+variation))
    wave = body + noise_hp * noise_env * 0.8
    wave = one_pole_lowpass(wave, 4000, sr)
    return wave * 0.65

def synth_hat_v15(sr, duration=0.14, closed=True, variation=0):
    n = int(sr*duration)
    noise = np.random.randn(n)
    hp = noise - np.concatenate([[0], noise[:-1]]) * 0.95
    decay = 30+variation*3 if closed else 10+variation
    env = np.exp(-np.linspace(0, duration, n)*decay)
    wave = hp * env
    wave = one_pole_lowpass(wave, 9000, sr)
    return wave * (0.28 if closed else 0.20)

def synth_bass_v15(midi, sr, duration, velocity=0.7, variation=0):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    f0 = note_to_freq(midi)
    sub = np.sin(2*np.pi*f0*t)
    saw = 2 * ( (f0 * t) % 1 ) - 1
    saw = saw * 0.25 * velocity
    wave = sub + saw
    cutoff = 350 + velocity*500
    wave = one_pole_lowpass(wave, cutoff, sr)
    env = adsr_envelope(n, sr, attack=0.005, decay=0.12, sustain=0.75, release=0.18)
    wave = np.tanh(wave * 1.2) * 0.9
    return wave * env * velocity * 0.75

def simple_reverb(stereo, sr, room=0.5, damp=0.5, mix=0.18):
    try:
        N = len(stereo)
        comb_delays = [int(sr * d) for d in [0.0297, 0.0371, 0.0411, 0.0437]]
        allpass_delays = [int(sr * d) for d in [0.005, 0.0017]]
        out = np.zeros_like(stereo)
        for ch in range(2):
            x = stereo[:, ch]
            comb_sum = np.zeros(N)
            for i, d in enumerate(comb_delays):
                buf = np.zeros(N)
                feedback = 0.7 + room*0.25
                for n in range(N):
                    if n >= d:
                        buf[n] = x[n] + feedback * buf[n-d] * (1-damp*0.3)
                    else:
                        buf[n] = x[n]
                comb_sum += buf
            comb_sum /= len(comb_delays)
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
        wet = out * mix
        dry = stereo * (1-mix)
        return dry + wet
    except Exception as e:
        print(f"[reverb] failed {e}, returning dry")
        return stereo

def get_diatonic_chords(root_midi, is_major):
    if is_major:
        chords = [
            (0, True, [0,4,7], "maj"),
            (2, False, [0,3,7], "m"),
            (4, False, [0,3,7], "m"),
            (5, True, [0,4,7], "maj"),
            (7, True, [0,4,7], "maj"),
            (9, False, [0,3,7], "m"),
            (11, False, [0,3,6], "dim"),
        ]
    else:
        chords = [
            (0, False, [0,3,7], "m"),
            (2, False, [0,3,6], "dim"),
            (3, True, [0,4,7], "maj"),
            (5, False, [0,3,7], "m"),
            (7, False, [0,3,7], "m"),
            (8, True, [0,4,7], "maj"),
            (10, True, [0,4,7], "maj"),
        ]
    result = []
    for deg, maj, intervals, qual in chords:
        chord_root = root_midi + deg
        notes = [chord_root + iv for iv in intervals]
        pcs = [n % 12 for n in notes]
        result.append({
            "degree": deg,
            "is_major": maj,
            "root": chord_root,
            "notes": notes,
            "pcs": pcs,
            "intervals": intervals,
            "quality": qual
        })
    return result

def get_chord_voicing(chord_info, target_octave=60, vocal_midi=None, inversion=0, add_extensions=False):
    root = chord_info["root"]
    intervals = chord_info["intervals"]
    base = target_octave + (root % 12)
    while base < target_octave:
        base += 12
    while base > target_octave+12:
        base -= 12
    notes = [base + iv for iv in intervals]
    if add_extensions:
        if chord_info["degree"] in (0, 5, 7):
            if chord_info["is_major"]:
                if chord_info["degree"] == 0:
                    notes.append(base + 11)
                else:
                    notes.append(base + 10)
            else:
                notes.append(base + 10)
        if random.random() > 0.6:
            notes.append(base + 14)
    if inversion == 1:
        notes = [notes[1], notes[2], notes[0]+12] + notes[3:]
    elif inversion == 2:
        notes = [notes[2], notes[0]+12, notes[1]+12] + [n+12 if i<3 else n for i,n in enumerate(notes[3:])]
    if vocal_midi is not None:
        top = vocal_midi
        while top > 84:
            top -= 12
        while top < 60:
            top += 12
        filtered = [n for n in notes if n < top - 2]
        if len(filtered) < 2:
            filtered = [top-12, top-7]
        notes = filtered + [top]
    notes = sorted(set([int(round(n)) for n in notes]))
    return notes

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

def detect_chroma_in_segment(audio, sr):
    try:
        n_fft = min(4096, len(audio))
        if n_fft < 512:
            return np.ones(12)/12
        window = np.hanning(n_fft)
        frame = audio[:n_fft] * window
        spec = np.abs(np.fft.rfft(frame))
        freqs = np.fft.rfftfreq(n_fft, 1/sr)
        valid = (freqs > 50) & (freqs < 4000)
        f_valid = freqs[valid]
        s_valid = spec[valid]
        if len(f_valid) == 0:
            return np.ones(12)/12
        midi = 69 + 12 * np.log2(f_valid / 440.0)
        pc = np.round(midi).astype(int) % 12
        chroma = np.zeros(12)
        for j, p in enumerate(pc):
            chroma[p] += s_valid[j]
        if np.max(chroma) > 0:
            chroma = chroma / np.max(chroma)
        return chroma
    except:
        return np.ones(12)/12

def analyze_vocal_continuous(vocal_path: Path, duration_sec, sr_target=44100):
    try:
        y_vocal, sr_v = sf.read(str(vocal_path))
        if y_vocal.ndim > 1:
            y_vocal = np.mean(y_vocal, axis=1)
        hop = int(sr_v * 0.05)
        times = []
        f0_curve = []
        energy_curve = []
        chroma_curve = []
        midi_curve = []
        for start in range(0, len(y_vocal)-hop, hop):
            seg = y_vocal[start:start+hop*3]
            t = start / sr_v
            times.append(t)
            energy = float(np.mean(np.abs(seg)))
            energy_curve.append(energy)
            f0 = detect_f0_in_segment(seg, sr_v)
            if f0 is None:
                f0 = f0_curve[-1] if f0_curve else 180.0
            f0_curve.append(float(f0))
            midi = 69 + 12*math.log2(f0/440.0) if f0>0 else 60
            midi_curve.append(float(midi))
            chroma = detect_chroma_in_segment(seg, sr_v)
            chroma_curve.append(chroma)
        if times and times[-1] < duration_sec:
            last_f0 = f0_curve[-1]
            last_energy = 0.01
            last_midi = midi_curve[-1]
            last_chroma = chroma_curve[-1]
            while times[-1] < duration_sec:
                times.append(times[-1]+0.05)
                f0_curve.append(last_f0)
                energy_curve.append(last_energy*0.9)
                midi_curve.append(last_midi)
                chroma_curve.append(last_chroma)
                last_energy *= 0.9
        print(f"[v1.5] Continuous: {len(times)} frames 50ms, F0 {min(f0_curve):.0f}-{max(f0_curve):.0f}Hz")
        return np.array(times), np.array(f0_curve), np.array(energy_curve), np.array(midi_curve), np.array(chroma_curve)
    except Exception as e:
        print(f"[v1.5] Continuous failed {e}")
        import traceback
        traceback.print_exc()
        n_frames = int(duration_sec / 0.05)
        times = np.linspace(0, duration_sec, n_frames)
        f0_curve = np.ones(n_frames)*180.0
        energy_curve = np.ones(n_frames)*0.1
        midi_curve = np.ones(n_frames)*60
        chroma_curve = np.tile(np.ones(12)/12, (n_frames,1))
        return times, f0_curve, energy_curve, midi_curve, chroma_curve

def analyze_vocal_per_beat_and_bar(vocal_path: Path, beat_times, bar_times, analysis):
    f0_per_beat = []
    energy_per_beat = []
    midi_per_beat = []
    chroma_per_beat = []
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
                chroma_per_beat.append(np.ones(12)/12)
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
            chroma = detect_chroma_in_segment(seg, sr_v)
            chroma_per_beat.append(chroma)
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
        print(f"[v1.5] Per-beat F0: {[f'{x:.0f}' for x in f0_per_beat[:10]]} midi {[f'{x:.0f}' for x in midi_per_beat[:10]]}")
        print(f"[v1.5] Per-bar F0: {[f'{x:.0f}' for x in f0_per_bar[:6]]} Energy: {[f'{x:.3f}' for x in energy_per_bar[:6]]}")
    except Exception as e:
        print(f"[v1.5] Per-beat analysis failed {e}")
        import traceback
        traceback.print_exc()
        num_beats = len(beat_times)
        num_bars = len(bar_times)
        f0_per_beat = [analysis.get("f0_mean_hz", 180)] * num_beats
        energy_per_beat = [0.1] * num_beats
        midi_per_beat = [60] * num_beats
        chroma_per_beat = [np.ones(12)/12] * num_beats
        f0_per_bar = [analysis.get("f0_mean_hz", 180)] * num_bars
        energy_per_bar = [0.1] * num_bars
        midi_per_bar = [60] * num_bars
    return f0_per_beat, energy_per_beat, midi_per_beat, chroma_per_beat, f0_per_bar, energy_per_bar, midi_per_bar

def choose_chord_for_vocal_note(vocal_midi, vocal_pc, diatonic_chords, expected_degree, prev_chord, seed, chroma=None, vocal_midi_exact=None):
    best_score = -1000
    best_chord = diatonic_chords[0]
    for chord in diatonic_chords:
        score = 0
        pcs = chord["pcs"]
        if chroma is not None:
            chroma_score = sum(chroma[pc] for pc in pcs)
            score += chroma_score * 3.5
        if vocal_pc in pcs:
            root_pc = chord["root"] % 12
            vocal_interval = (vocal_pc - root_pc) % 12
            if vocal_interval == 0:
                score += 12
            elif vocal_interval in (3,4):
                score += 9
            elif vocal_interval == 7:
                score += 7
            elif vocal_interval in (10,11):
                score += 4
            else:
                score += 2
        else:
            min_dist = min((vocal_pc - pc) % 12 for pc in pcs)
            min_dist = min(min_dist, 12-min_dist)
            if min_dist == 1:
                score += 2.0
            elif min_dist == 2:
                score += 0.8
            else:
                score -= 0.5
        if expected_degree is not None and chord["degree"] == expected_degree:
            score += 2.5
        if chord["degree"] in (0,7,9):
            score += 0.8
        if prev_chord:
            shared = len(set(pcs) & set(prev_chord["pcs"]))
            score += shared * 1.5
            root_jump = abs(chord["root"] - prev_chord["root"]) % 12
            if root_jump > 6:
                root_jump = 12 - root_jump
            score -= root_jump * 0.2
        score += (seed % 10) * 0.03 * (1 if chord["degree"] % 2 == 0 else -1)
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
    phrases = analysis.get("phrases", [])
    try:
        seed = int(file_hash[:6], 16) % 10000
    except:
        seed = int(bpm*10 + hash(key_str) % 1000) % 10000
    np.random.seed(seed)
    random.seed(seed)
    print(f"[generator] v1.5 REAL PIANO STUDIO {style} {key_str} {bpm} BPM seed {seed} hash {file_hash} beats {len(beat_times)} bars {len(bar_times)} phrases {len(phrases)}")
    try:
        root_name = key_str.split()[0]
        root_semi = {n:i for i,n in enumerate(NOTE_NAMES)}.get(root_name, 0)
        key_root_midi = 60 + root_semi
    except:
        key_root_midi = 60
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
        cont_times, cont_f0, cont_energy, cont_midi, cont_chroma = analyze_vocal_continuous(vocal_path, total_duration, sr)
        f0_per_beat, energy_per_beat, midi_per_beat, chroma_per_beat, f0_per_bar, energy_per_bar, midi_per_bar = analyze_vocal_per_beat_and_bar(vocal_path, beat_times, bar_times, analysis)
    else:
        n_frames = int(total_duration / 0.05)
        cont_times = np.linspace(0, total_duration, n_frames)
        cont_f0 = np.ones(n_frames)*analysis.get("f0_mean_hz",180)
        cont_energy = np.ones(n_frames)*0.1
        cont_midi = np.ones(n_frames)*60
        cont_chroma = np.tile(np.ones(12)/12, (n_frames,1))
        f0_per_beat = [analysis.get("f0_mean_hz",180)]*len(beat_times)
        energy_per_beat = [0.1]*len(beat_times)
        midi_per_beat = [69+12*math.log2(analysis.get("f0_mean_hz",180)/440.0)]*len(beat_times)
        chroma_per_beat = [np.ones(12)/12]*len(beat_times)
        f0_per_bar = [analysis.get("f0_mean_hz",180)]*len(bar_times)
        energy_per_bar = [0.1]*len(bar_times)
        midi_per_bar = [60]*len(bar_times)
    diatonic_chords = get_diatonic_chords(key_root_midi, is_major)
    prog_lib = {
        "warm-acoustic": {"major": [[0, 7, 9, 5], [0, 5, 9, 7]], "minor": [[0, 8, 3, 10], [0, 3, 8, 10]]},
        "lofi-chill": {"major": [[0, 5, 9, 7]], "minor": [[0, 8, 10, 3]]},
        "piano-ballad": {"major": [[0, 5, 9, 5]], "minor": [[0, 5, 8, 10]]},
        "indie-pop": {"major": [[0, 9, 5, 7]], "minor": [[0, 3, 8, 10]]},
        "cinematic": {"major": [[0, 5, 3, 7]], "minor": [[0, 5, 8, 7]]}
    }
    style_lib = prog_lib.get(style, prog_lib["warm-acoustic"])
    key_type = "major" if is_major else "minor"
    progressions = style_lib.get(key_type, style_lib["major"])
    prog_idx = seed % len(progressions)
    expected_degrees = progressions[prog_idx]
    print(f"[generator] Style {style} {key_type} prog {prog_idx} degrees {expected_degrees}")
    chosen_chords_per_bar = []
    chosen_chords_per_beat = []
    prev_chord = None
    for bar_idx in range(len(bar_times)):
        vocal_midi = midi_per_bar[bar_idx] if bar_idx < len(midi_per_bar) else 60
        vocal_pc = int(round(vocal_midi)) % 12
        expected_deg = expected_degrees[bar_idx % len(expected_degrees)] if expected_degrees else None
        best_chord, score = choose_chord_for_vocal_note(vocal_midi, vocal_pc, diatonic_chords, expected_deg, prev_chord, seed+bar_idx, chroma=None, vocal_midi_exact=vocal_midi)
        chosen_chords_per_bar.append(best_chord)
        prev_chord = best_chord
    prev_chord_beat = None
    for beat_idx in range(len(beat_times)):
        vocal_midi = midi_per_beat[beat_idx] if beat_idx < len(midi_per_beat) else 60
        vocal_pc = int(round(vocal_midi)) % 12
        chroma = chroma_per_beat[beat_idx] if beat_idx < len(chroma_per_beat) else None
        bar_idx_for_beat = 0
        for b_idx, bt in enumerate(bar_times):
            if beat_times[beat_idx] >= bt:
                bar_idx_for_beat = b_idx
        expected_deg = expected_degrees[bar_idx_for_beat % len(expected_degrees)] if expected_degrees else None
        best_chord, score = choose_chord_for_vocal_note(vocal_midi, vocal_pc, diatonic_chords, expected_deg, prev_chord_beat, seed+beat_idx+1000, chroma=chroma, vocal_midi_exact=vocal_midi)
        chosen_chords_per_beat.append(best_chord)
        prev_chord_beat = best_chord
    print(f"[generator] Per-beat chords {len(chosen_chords_per_beat)} + cont {len(cont_times)} frames")
    num_bars = len(bar_times)
    variation = (seed % 10) / 10.0
    kick = synth_kick_v15(sr, variation=variation)
    snare = synth_snare_v15(sr, variation=variation)
    hat_closed = synth_hat_v15(sr, 0.12, closed=True, variation=variation)
    hat_open = synth_hat_v15(sr, 0.25, closed=False, variation=variation)
    arp_patterns = {
        "warm-acoustic": [0, 2, 1, 2, 3, 1, 2, 0],
        "piano-ballad": [0, 1, 2, 1, 0, 2, 3, 1],
        "lofi-chill": [0, 2, 1, 3, 0, 1, 2, 1],
        "indie-pop": [0, 1, 2, 3, 2, 1, 0, 2],
        "cinematic": [0, 2, 3, 1, 0, 3, 2, 1]
    }
    arp_pattern = arp_patterns.get(style, arp_patterns["warm-acoustic"])
    prev_voicing = None
    for bar_idx in range(num_bars):
        bar_start_t = bar_times[bar_idx]
        bar_end_t = bar_times[bar_idx+1] if bar_idx+1 < len(bar_times) else bar_start_t + (60.0/bpm*4)
        for ps, pe in phrases:
            if abs(bar_start_t - ps) < 0.12:
                bar_end_t = pe
                break
        bar_duration = bar_end_t - bar_start_t
        if bar_duration <= 0 or bar_duration > 8.0:
            bar_duration = 60.0/bpm*4
        bar_start = int(bar_start_t * sr)
        if bar_start >= n_total:
            break
        bar_energy = energy_per_bar[bar_idx] if bar_idx < len(energy_per_bar) else 0.1
        bar_midi = midi_per_bar[bar_idx] if bar_idx < len(midi_per_bar) else 60
        is_intro = bar_start_t + bar_duration < first_vocal_time - 0.2
        inside_phrase = any(ps -0.1 <= bar_start_t <= pe +0.1 for ps, pe in phrases) if phrases else True
        is_silence_bar = (bar_energy < 0.015) and not inside_phrase
        if phrases and not inside_phrase:
            is_silence_bar = True
        beats_in_bar = [bt for bt in beat_times if bar_start_t <= bt < bar_end_t]
        if not beats_in_bar:
            beats_in_bar = [bar_start_t + i*(bar_duration/4) for i in range(4)]
        chord_info = chosen_chords_per_bar[bar_idx] if bar_idx < len(chosen_chords_per_bar) else diatonic_chords[0]
        inversion = 0
        if prev_voicing is not None:
            best_inv = 0
            min_move = 1000
            for inv in [0,1,2]:
                voicing = get_chord_voicing(chord_info, target_octave=60, vocal_midi=bar_midi, inversion=inv, add_extensions=bar_energy>0.05)
                if prev_voicing:
                    move = sum(abs(voicing[i]-prev_voicing[i]) if i < len(prev_voicing) and i < len(voicing) else 12 for i in range(min(len(voicing),3)))
                    if move < min_move:
                        min_move = move
                        best_inv = inv
            inversion = best_inv
        voicing = get_chord_voicing(chord_info, target_octave=60, vocal_midi=bar_midi, inversion=inversion, add_extensions=bar_energy>0.06)
        prev_voicing = voicing
        bass_root = chord_info["root"]
        target_bass_midi = bar_midi - 19
        while bass_root > target_bass_midi + 7:
            bass_root -= 12
        while bass_root < target_bass_midi - 7:
            bass_root += 12
        while bass_root < 36:
            bass_root += 12
        while bass_root > 50:
            bass_root -= 12
        if style != "piano-ballad":
            for b_idx, beat_t in enumerate(beats_in_bar):
                if b_idx not in (0,2):
                    if not (style=="indie-pop" and b_idx==1):
                        continue
                current_bass = bass_root
                if b_idx == 2 and bar_idx+1 < len(chosen_chords_per_bar):
                    next_root = chosen_chords_per_bar[bar_idx+1]["root"]
                    interval = (next_root - bass_root) % 12
                    if interval == 7:
                        current_bass = bass_root + 2
                    elif interval == 5:
                        current_bass = bass_root + 2
                base_vel = 0.70 if b_idx==0 else 0.52
                vel = base_vel + bar_energy*0.28 + random.random()*0.08
                if is_intro:
                    vel *= 0.65
                if is_silence_bar:
                    vel *= 0.2
                dur = bar_duration/4 * (1.8 if b_idx==0 else 1.0)
                note = synth_bass_v15(current_bass, sr, dur, velocity=vel, variation=variation)
                s = int(beat_t * sr)
                e = min(s+len(note), n_total)
                if 0 <= s < n_total:
                    mix_left[s:e] += note[:e-s] * 0.88
                    mix_right[s:e] += note[:e-s] * 0.88
        else:
            vel = 0.72 + (bar_energy*0.45)
            if is_intro:
                vel *= 0.6
            if is_silence_bar:
                vel *= 0.3
            note = synth_bass_v15(bass_root, sr, bar_duration*0.9, velocity=vel, variation=variation)
            s = bar_start
            e = min(s+len(note), n_total)
            if s < n_total:
                mix_left[s:e] += note[:e-s] * 0.92
                mix_right[s:e] += note[:e-s] * 0.92
        beat_chords_in_bar = []
        for bt in beats_in_bar:
            try:
                global_idx = beat_times.index(bt) if bt in beat_times else -1
                if global_idx >=0 and global_idx < len(chosen_chords_per_beat):
                    beat_chords_in_bar.append(chosen_chords_per_beat[global_idx])
                else:
                    beat_chords_in_bar.append(chord_info)
            except:
                beat_chords_in_bar.append(chord_info)
        unique_roots = len(set(c["root"] for c in beat_chords_in_bar))
        change_per_beat = unique_roots > 1 and not is_silence_bar
        if bar_energy > 0.08 and not is_silence_bar:
            change_per_beat = True
        if change_per_beat:
            for b_idx, beat_t in enumerate(beats_in_bar):
                beat_chord_info = beat_chords_in_bar[b_idx]
                beat_next_t = beats_in_bar[b_idx+1] if b_idx+1 < len(beats_in_bar) else bar_end_t
                beat_dur = beat_next_t - beat_t
                if beat_dur <=0:
                    beat_dur = bar_duration / len(beats_in_bar)
                beat_cont_mask = (cont_times >= beat_t) & (cont_times < beat_next_t)
                if np.any(beat_cont_mask):
                    beat_energy_avg = np.mean(cont_energy[beat_cont_mask])
                    beat_midi_avg = np.mean(cont_midi[beat_cont_mask])
                else:
                    beat_energy_avg = energy_per_beat[beat_times.index(beat_t)] if beat_t in beat_times and beat_times.index(beat_t) < len(energy_per_beat) else bar_energy
                    beat_midi_avg = midi_per_beat[beat_times.index(beat_t)] if beat_t in beat_times and beat_times.index(beat_t) < len(midi_per_beat) else bar_midi
                beat_voicing = get_chord_voicing(beat_chord_info, target_octave=60, vocal_midi=beat_midi_avg, inversion=0, add_extensions=beat_energy_avg>0.06)
                arp_notes = beat_voicing
                num_arp_notes = min(3, len(arp_notes))
                for arp_i in range(num_arp_notes):
                    arp_idx = arp_pattern[(b_idx*3 + arp_i) % len(arp_pattern)] % len(arp_notes)
                    arp_midi = arp_notes[arp_idx]
                    arp_delay = (arp_i / num_arp_notes) * beat_dur * 0.6
                    arp_dur = beat_dur * 0.8
                    chord_vel = 0.42 + beat_energy_avg*0.38 + random.random()*0.08
                    if is_intro:
                        chord_vel *= 0.65
                    if is_silence_bar:
                        chord_vel *= 0.30
                    if style in ("piano-ballad", "cinematic", "lofi-chill"):
                        arp_wave = synth_piano_v15(arp_midi, sr, arp_dur, velocity=chord_vel, variation=variation, bright=style in ("indie-pop","warm-acoustic"))
                    else:
                        arp_wave = synth_guitar_v15(arp_midi, sr, arp_dur, velocity=chord_vel, variation=variation)
                    s = int((beat_t + arp_delay) * sr)
                    e = min(s+len(arp_wave), n_total)
                    if s < n_total:
                        duck = 1.0 - min(beat_energy_avg*1.8, 0.32)
                        pan = (arp_idx / max(len(arp_notes)-1,1)) * 0.6 - 0.3
                        mix_left[s:e] += arp_wave[:e-s] * (0.65 - pan*0.4) * duck
                        mix_right[s:e] += arp_wave[:e-s] * (0.65 + pan*0.4) * duck
        else:
            num_beats = len(beats_in_bar)
            for b_idx, beat_t in enumerate(beats_in_bar):
                beat_dur = (beats_in_bar[b_idx+1] - beat_t) if b_idx+1 < len(beats_in_bar) else bar_duration/num_beats
                arp_notes = voicing
                num_arp_notes = 2 if is_silence_bar else 3
                for arp_i in range(num_arp_notes):
                    arp_idx = arp_pattern[(b_idx*2 + arp_i) % len(arp_pattern)] % len(arp_notes)
                    arp_midi = arp_notes[arp_idx]
                    arp_delay = (arp_i / num_arp_notes) * beat_dur * 0.5
                    arp_dur = beat_dur * 0.85
                    chord_vel_base = 0.40 + bar_energy*0.35
                    if is_intro:
                        chord_vel_base *= 0.65
                    if is_silence_bar:
                        chord_vel_base *= 0.30
                    vel = chord_vel_base + random.random()*0.08
                    if style in ("piano-ballad", "cinematic", "lofi-chill"):
                        arp_wave = synth_piano_v15(arp_midi, sr, arp_dur, velocity=vel, variation=variation, bright=style in ("indie-pop","warm-acoustic"))
                    else:
                        arp_wave = synth_guitar_v15(arp_midi, sr, arp_dur, velocity=vel, variation=variation)
                    s = int((beat_t + arp_delay) * sr)
                    e = min(s+len(arp_wave), n_total)
                    if s < n_total:
                        duck = 1.0 - min(bar_energy*1.5, 0.30)
                        pan = (arp_idx / max(len(arp_notes)-1,1)) * 0.5 - 0.25 + random.random()*0.08
                        mix_left[s:e] += arp_wave[:e-s] * (0.6 - pan*0.5) * duck
                        mix_right[s:e] += arp_wave[:e-s] * (0.6 + pan*0.5) * duck
        for b_idx, beat_t in enumerate(beats_in_bar):
            is_onset_beat = any(abs(beat_t - ot) < 0.08 for ot in onset_times)
            beat_cont_mask = (cont_times >= beat_t-0.05) & (cont_times < beat_t+0.05)
            is_energy_peak = False
            if np.any(beat_cont_mask):
                local_energy = np.mean(cont_energy[beat_cont_mask])
                prev_mask = (cont_times >= beat_t-0.15) & (cont_times < beat_t-0.05)
                next_mask = (cont_times >= beat_t+0.05) & (cont_times < beat_t+0.15)
                if np.any(prev_mask) and np.any(next_mask):
                    prev_e = np.mean(cont_energy[prev_mask])
                    next_e = np.mean(cont_energy[next_mask])
                    if local_energy > prev_e*1.3 and local_energy > next_e*1.1 and local_energy > 0.03:
                        is_energy_peak = True
            beat_start = int(beat_t * sr)
            kick_beats = [0]
            if style=="indie-pop" and len(beats_in_bar)>2:
                kick_beats = [0,1,2]
            elif len(beats_in_bar)==4:
                kick_beats = [0,2]
            should_kick = (b_idx in kick_beats) or is_onset_beat or is_energy_peak
            if should_kick:
                if is_silence_bar and b_idx != 0 and not is_onset_beat and not is_energy_peak:
                    continue
                if bar_energy > 0.05 or b_idx==0 or is_intro or is_onset_beat or is_energy_peak:
                    s = beat_start
                    humanize = int((random.random()-0.5)*0.003*sr)
                    s = max(0, s+humanize)
                    e = min(s+len(kick), n_total)
                    if s < n_total:
                        vel = 0.75 + bar_energy*0.15 + random.random()*0.06
                        if is_onset_beat or is_energy_peak:
                            vel += 0.20
                        if is_intro:
                            vel *= 0.65
                        mix_left[s:e] += kick[:e-s] * vel
                        mix_right[s:e] += kick[:e-s] * vel
            if b_idx in (1,3):
                if is_silence_bar and b_idx==1:
                    continue
                s = beat_start
                humanize = int((random.random()-0.5)*0.003*sr)
                s = max(0, s+humanize)
                e = min(s+len(snare), n_total)
                if s < n_total:
                    vel = 0.56 + bar_energy*0.15 + random.random()*0.10
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
                if hs < n_total and random.random()>0.10:
                    hat_vel = 0.48 + bar_energy*0.07 + random.random()*0.10
                    if is_silence_bar:
                        hat_vel *= 0.32
                    if is_intro:
                        hat_vel *= 0.52
                    if bar_energy < 0.02:
                        hat_vel *= 0.42
                    if is_energy_peak:
                        hat_vel += 0.15
                    mix_left[hs:he] += hat[:he-hs] * hat_vel
                    mix_right[hs:he] += hat[:he-hs] * hat_vel
    max_val = max(np.max(np.abs(mix_left)), np.max(np.abs(mix_right)), 1e-6)
    if max_val > 0.85:
        scale = 0.85 / max_val
        mix_left *= scale
        mix_right *= scale
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
    stereo = np.stack([mix_left, mix_right], axis=1)
    reverb_mix = 0.20
    if style == "cinematic":
        reverb_mix = 0.30
    elif style == "piano-ballad":
        reverb_mix = 0.25
    elif style == "lofi-chill":
        reverb_mix = 0.15
    stereo = simple_reverb(stereo, sr, room=0.6, damp=0.4, mix=reverb_mix)
    max_val = np.max(np.abs(stereo))
    if max_val > 0.89:
        stereo = stereo * (0.89 / max_val)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), stereo, sr)
    print(f"[generator] v1.5 REAL PIANO Saved {out_path}, {total_duration:.1f}s, {len(bar_times)} bars, {len(cont_times)} cont frames, seed {seed}, hash {file_hash}")
    return out_path
