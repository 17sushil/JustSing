"""
SingSmith Procedural Generator v0.4 — FIXED: Music varies per song, adapts to singer
Generates an accompaniment that fits the singer's key, BPM, and duration.
Now uses file hash + F0 + BPM to create UNIQUE music per upload, not same every time.

Design: 4 tracks mixed to stereo:
 - Drums (kick, snare, hi-hat) — pattern varies with BPM and hash
 - Bass — octave adapts to singer's range (high singer = low bass)
 - Chords — progression varies per style + hash + is_major
 - Arp / extra — varies

All tuned to detected key. Tempo matched exactly. Vocal NEVER changed (see mix.py).
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
    # Variation in kick pitch
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
    # Add slight detune based on variation for warmth
    detune = variation * 0.02
    wave = np.sin(2*np.pi*f0*t) + 0.3*np.sin(2*np.pi*2*f0*t*(1+detune)) + 0.1*np.sin(2*np.pi*3*f0*t)
    env = adsr_envelope(n, sr, attack=0.01, decay=0.1, sustain=0.8, release=0.15)
    return wave * env * velocity * 0.6

def synth_chord(midis, sr, duration, velocity=0.5, bright=False, variation=0):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    wave = np.zeros(n)
    for midi in midis:
        f0 = note_to_freq(midi + variation*0.05)  # tiny variation
        if bright:
            for h in range(1, 7):
                amp = 1.0/(h**1.4)
                wave += amp * np.sin(2*np.pi*f0*h*t)
        else:
            wave += np.sin(2*np.pi*f0*t) + 0.35*np.sin(2*np.pi*2*f0*t)
    env = adsr_envelope(n, sr, attack=0.08 if not bright else 0.015, decay=0.2, sustain=0.6, release=0.3)
    wave = wave / (len(midis) or 1)
    return wave * env * velocity * 0.4

def get_scale_notes(root_midi, is_major=True):
    intervals_major = [0,2,4,5,7,9,11,12]
    intervals_minor = [0,2,3,5,7,8,10,12]
    intervals = intervals_major if is_major else intervals_minor
    return [root_midi + i for i in intervals]

def get_chord_progressions_library():
    """Multiple progressions per style for variation"""
    return {
        "warm-acoustic": {
            "major": [
                [0, 7, 9, 5],  # I V vi IV
                [0, 5, 9, 7],  # I IV vi V
                [0, 9, 5, 7],  # I vi IV V
                [0, 5, 0, 7],  # I IV I V
            ],
            "minor": [
                [0, 8, 3, 10],
                [0, 3, 8, 10],
                [0, 8, 10, 3],
            ]
        },
        "lofi-chill": {
            "major": [
                [0, 5, 9, 7],
                [0, 9, 5, 0],
                [9, 5, 0, 7],
                [0, 3, 5, 7],
            ],
            "minor": [
                [0, 8, 10, 3],
                [0, 10, 8, 3],
            ]
        },
        "piano-ballad": {
            "major": [
                [0, 5, 9, 5],
                [0, 7, 9, 5],
                [0, 9, 7, 5],
            ],
            "minor": [
                [0, 5, 8, 10],
                [0, 8, 5, 10],
            ]
        },
        "indie-pop": {
            "major": [
                [0, 9, 5, 7],
                [0, 5, 9, 7],
                [5, 9, 0, 7],
                [0, 7, 5, 9],
            ],
            "minor": [
                [0, 3, 8, 10],
                [0, 8, 3, 10],
            ]
        },
        "cinematic": {
            "major": [
                [0, 5, 3, 7],
                [0, 3, 5, 7],
                [0, 5, 0, 3],
            ],
            "minor": [
                [0, 5, 8, 7],
                [0, 8, 5, 7],
            ]
        }
    }

def get_chord_progression(root_midi, is_major=True, style="warm-acoustic", seed=0):
    """Now picks progression based on seed for variation per song"""
    lib = get_chord_progressions_library()
    style_lib = lib.get(style, lib["warm-acoustic"])
    key_type = "major" if is_major else "minor"
    progressions = style_lib.get(key_type, style_lib["major"])
    
    # Pick progression based on seed
    prog_idx = seed % len(progressions)
    degrees = progressions[prog_idx]

    chords = []
    for deg_offset in degrees:
        chord_root = root_midi + deg_offset
        if is_major:
            if deg_offset in (0,5,7):
                third = chord_root + 4
            else:
                third = chord_root + 3
        else:
            if deg_offset in (0,5,10):
                third = chord_root + 3
            else:
                third = chord_root + 4
        fifth = chord_root + 7
        
        # Voicing: keep around 60-72, but vary inversion based on seed
        # Use seed to pick inversion
        inversion = (seed + deg_offset) % 3
        while chord_root < 60:
            chord_root += 12
            third += 12
            fifth += 12
        while chord_root > 68:
            chord_root -= 12
            third -= 12
            fifth -= 12
        
        if inversion == 1:
            # First inversion: third in bass
            chord_notes = [third-12, chord_root, fifth, third, fifth+12]
        elif inversion == 2:
            # Second inversion: fifth in bass
            chord_notes = [fifth-12, chord_root, third, fifth, third+12]
        else:
            chord_notes = [chord_root-12, chord_root, third, fifth, third+12]
        
        chords.append(chord_notes)
    
    print(f"[generator] Style {style} {'major' if is_major else 'minor'} prog {prog_idx} degrees {degrees} seed {seed}")
    return chords

def generate_accompaniment(analysis: dict, out_path: Path, style="warm-acoustic", duration_sec=None):
    sr = 44100
    bpm = analysis.get("bpm", 90.0) or 90.0
    try:
        bpm = float(bpm)
    except:
        bpm = 90.0
    if bpm < 45:
        bpm = 90.0
    if bpm > 200:
        bpm = min(bpm, 180)

    key_str = analysis.get("key", "C major")
    is_major = analysis.get("is_major", True)
    file_hash = analysis.get("file_hash", "00000000")
    
    # Seed random from file hash + bpm + key for UNIQUE music per upload
    try:
        seed = int(file_hash[:6], 16) % 10000
    except:
        seed = int(bpm*10 + hash(key_str) % 1000) % 10000
    
    # Use seed for all random variations
    np.random.seed(seed)
    random.seed(seed)
    
    print(f"[generator] Generating {style} in {key_str} at {bpm} BPM, seed {seed}, hash {file_hash}")

    # Parse root
    try:
        root_name = key_str.split()[0]
        note_to_semi = {n:i for i,n in enumerate(NOTE_NAMES)}
        root_semi = note_to_semi.get(root_name, 0)
        root_midi = 60 + root_semi
        f0_mean = analysis.get("f0_mean_hz", 180)
        f0_min = analysis.get("f0_min_hz", 110)
        # Adaptive octave: high singer = low accompaniment, low singer = mid accompaniment
        # This is the "tune to singer" feature — music adapts to voice, not vice versa
        if f0_mean > 300:  # soprano/high
            root_midi -= 12
            print(f"[generator] High voice {f0_mean:.0f}Hz, lowering accompaniment to {root_midi}")
        elif f0_mean > 220:  # mid-high
            root_midi -= 5
        elif f0_mean < 130:  # very low
            root_midi += 7
    except:
        root_midi = 60

    total_duration = duration_sec or analysis.get("duration_sec", 30.0)
    total_duration = float(total_duration) + 0.8
    n_total = int(sr * total_duration)
    mix_left = np.zeros(n_total, dtype=np.float32)
    mix_right = np.zeros(n_total, dtype=np.float32)

    beat_sec = 60.0 / bpm
    bar_sec = beat_sec * 4

    # Pick progression based on seed for variation
    chords = get_chord_progression(root_midi, is_major, style, seed=seed)
    num_bars = int(math.ceil(total_duration / bar_sec))

    # Drum pattern variation based on BPM and seed
    # If BPM > 120, more energetic; if < 80, more sparse
    drum_pattern_type = seed % 3  # 0,1,2 for variation
    if bpm > 125:
        drum_pattern_type = 0  # energetic
    elif bpm < 85:
        drum_pattern_type = 2  # sparse

    # Pre-synthesize with variation
    variation = (seed % 10) / 10.0
    kick = synth_kick(sr, variation=variation)
    snare = synth_snare(sr, variation=variation)
    hat_closed = synth_hat(sr, 0.12, closed=True, variation=variation)
    hat_open = synth_hat(sr, 0.25, closed=False, variation=variation)

    for bar in range(num_bars):
        bar_start = int(bar * bar_sec * sr)
        chord = chords[bar % len(chords)]
        chord_duration = bar_sec

        # --- Bass: adaptive to singer and BPM ---
        bass_root = chord[0]
        # Vary bass pattern based on style and seed
        bass_pattern = (seed + bar) % 2
        if style == "piano-ballad":
            note = synth_bass_note(bass_root, sr, chord_duration, velocity=0.68 + variation*0.1, variation=variation)
            s = bar_start
            e = min(s+len(note), n_total)
            mix_left[s:e] += note[:e-s] * 0.9
            mix_right[s:e] += note[:e-s] * 0.9
        else:
            beats_per_bar = 4
            for b in range(beats_per_bar):
                # Vary bass: sometimes only on 1 and 3, sometimes every beat
                if style == "lofi-chill" and b % 2 == 1 and bass_pattern == 0:
                    continue
                if drum_pattern_type == 2 and b in (1,3) and random.random() > 0.6:  # sparse
                    continue
                dur = beat_sec * (1.7 if b==0 else 0.85)
                vel = 0.65 if b==0 else 0.48 + random.random()*0.15
                note = synth_bass_note(bass_root, sr, dur, velocity=vel, variation=variation)
                s = bar_start + int(b*beat_sec*sr)
                e = min(s+len(note), n_total)
                if s < n_total:
                    mix_left[s:e] += note[:e-s] * 0.85
                    mix_right[s:e] += note[:e-s] * 0.85

        # --- Chords ---
        is_bright = style in ("warm-acoustic", "indie-pop", "piano-ballad")
        upper_chord = chord[1:]
        
        # Vary strum vs block based on seed
        use_strum = (style == "warm-acoustic" and (seed % 2 == 0)) or (seed % 3 == 0)
        
        if use_strum and style in ("warm-acoustic", "indie-pop"):
            for idx, midi_note in enumerate(upper_chord):
                delay = idx * (0.025 + random.random()*0.015)  # varied strum timing
                note = synth_chord([midi_note], sr, chord_duration - delay, velocity=0.42 + random.random()*0.1, bright=True, variation=variation)
                s = bar_start + int(delay*sr)
                e = min(s+len(note), n_total)
                pan = (idx / max(len(upper_chord)-1,1)) * 0.6 - 0.3 + random.random()*0.1
                if s < n_total:
                    mix_left[s:e] += note[:e-s] * (0.5 - pan)
                    mix_right[s:e] += note[:e-s] * (0.5 + pan)
        else:
            # Block chord, but vary velocity per bar for humanization
            vel = 0.35 + random.random()*0.1 + (0.05 if bar % 4 == 0 else 0)  # accent every 4 bars
            chord_wave = synth_chord(upper_chord, sr, chord_duration, velocity=vel, bright=is_bright, variation=variation)
            s = bar_start
            e = min(s+len(chord_wave), n_total)
            mix_left[s:e] += chord_wave[:e-s] * 0.7
            mix_right[s:e] += chord_wave[:e-s] * 0.7

        # --- Arp ---
        if style in ("indie-pop", "cinematic", "lofi-chill"):
            arp_notes = upper_chord[:3]
            eighth = beat_sec / 2
            # Vary arp pattern
            arp_pattern = (seed + bar) % 2
            for step in range(8):
                if arp_pattern == 0:
                    midi_note = arp_notes[step % len(arp_notes)] + (12 if step>=4 else 0)
                else:
                    # Down arp
                    midi_note = arp_notes[-(step % len(arp_notes))] + (12 if step<4 else 0)
                # Skip some steps for variation
                if random.random() > 0.85:
                    continue
                note = synth_chord([midi_note], sr, eighth*0.85, velocity=0.22 + random.random()*0.08, bright=True, variation=variation)
                s = bar_start + int(step*eighth*sr)
                e = min(s+len(note), n_total)
                if s < n_total:
                    pan = 0.3 if step%2==0 else -0.3
                    mix_left[s:e] += note[:e-s] * (0.5 - pan*0.3)
                    mix_right[s:e] += note[:e-s] * (0.5 + pan*0.3)

        # --- Drums with variation ---
        for beat in range(4):
            beat_start = bar_start + int(beat*beat_sec*sr)
            # Kick pattern varies
            kick_beats = [0,2]  # default
            if drum_pattern_type == 0:  # energetic
                kick_beats = [0,1,2] if style=="indie-pop" else [0,2]
                if bar % 2 == 1 and random.random() > 0.5:
                    kick_beats.append(3)
            elif drum_pattern_type == 1:  # standard
                kick_beats = [0,2]
            else:  # sparse
                kick_beats = [0]

            if beat in kick_beats:
                s = beat_start
                # Humanize timing slightly
                humanize = int((random.random()-0.5)*0.015*sr)  # ±15ms
                s = max(0, s+humanize)
                e = min(s+len(kick), n_total)
                if s < n_total:
                    mix_left[s:e] += kick[:e-s] * (0.68 + random.random()*0.1)
                    mix_right[s:e] += kick[:e-s] * (0.68 + random.random()*0.1)

            if beat in (1,3):
                # Snare, but vary velocity
                if drum_pattern_type == 2 and beat==1 and random.random()>0.7:
                    continue  # skip some snares in sparse
                s = beat_start
                humanize = int((random.random()-0.5)*0.012*sr)
                s = max(0, s+humanize)
                e = min(s+len(snare), n_total)
                if s < n_total:
                    vel = 0.52 + random.random()*0.15
                    mix_left[s:e] += snare[:e-s] * vel
                    mix_right[s:e] += snare[:e-s] * vel

            # Hats
            hat_div = 2
            if bpm < 90:
                hat_div = 2
            else:
                hat_div = 2 if random.random()>0.3 else 4  # sometimes 16th notes for faster

            for hi in range(hat_div):
                hs = beat_start + int(hi*beat_sec/hat_div*sr)
                is_open = (beat==3 and hi==hat_div-1 and random.random()>0.3)
                hat = hat_open if is_open else hat_closed
                he = min(hs+len(hat), n_total)
                if hs < n_total and random.random()>0.15:  # occasional skip for humanization
                    mix_left[hs:he] += hat[:he-hs] * (0.45 + random.random()*0.15)
                    mix_right[hs:he] += hat[:he-hs] * (0.45 + random.random()*0.15)

    # --- Effects ---
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
    print(f"[generator] Saved {out_path}, {total_duration:.1f}s, seed {seed}, varied music for hash {file_hash}")
    return out_path
