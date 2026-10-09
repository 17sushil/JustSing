"""
SingSmith Procedural Generator — zero-cost, pure numpy.
Generates an accompaniment that fits the singer's key, BPM, and duration.
No API keys, no GPU, works everywhere.

Design: 4 tracks mixed to stereo:
 - Drums (kick, snare, hi-hat) synthesized
 - Bass (sine + harmonics, root notes)
 - Chords (piano/guitar pad, triangle + sine)
 - Arp / extra

All tuned to detected key. Tempo matched exactly.
"""

import numpy as np
import soundfile as sf
from pathlib import Path
import math

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def note_to_freq(midi):
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))

def adsr_envelope(n_samples, sr, attack=0.01, decay=0.1, sustain=0.7, release=0.2):
    a = int(sr*attack)
    d = int(sr*decay)
    r = int(sr*release)
    s = n_samples - a - d - r
    if s < 0:
        # scale down
        total = attack+decay+release
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

def synth_kick(sr, duration=0.5):
    n = int(sr*duration)
    t = np.linspace(0, duration, n)
    # pitch drop 150 -> 50 Hz
    freq = 150 * np.exp(-t*20) + 50
    phase = 2*np.pi*np.cumsum(freq)/sr
    wave = np.sin(phase)
    env = np.exp(-t*8)
    return wave * env * 0.9

def synth_snare(sr, duration=0.3):
    n = int(sr*duration)
    t = np.linspace(0, duration, n)
    # noise + tone
    noise = np.random.randn(n) * 0.5
    tone = np.sin(2*np.pi*180*t) * np.exp(-t*10)
    env = np.exp(-t*12)
    return (noise + tone) * env * 0.6

def synth_hat(sr, duration=0.15, closed=True):
    n = int(sr*duration)
    noise = np.random.randn(n)
    # high-pass via simple diff
    # bandpass-ish
    env = np.exp(-np.linspace(0, duration, n)*(30 if closed else 10))
    return noise * env * (0.25 if closed else 0.18)

def synth_bass_note(midi, sr, duration, velocity=0.7):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    f0 = note_to_freq(midi)
    # sine + 2nd harmonic + slight saturation
    wave = np.sin(2*np.pi*f0*t) + 0.3*np.sin(2*np.pi*2*f0*t) + 0.1*np.sin(2*np.pi*3*f0*t)
    env = adsr_envelope(n, sr, attack=0.01, decay=0.1, sustain=0.8, release=0.15)
    return wave * env * velocity * 0.6

def synth_chord(midis, sr, duration, velocity=0.5, bright=False):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    wave = np.zeros(n)
    for midi in midis:
        f0 = note_to_freq(midi)
        # triangle-ish for piano: sum of odd harmonics decreasing
        # or warm pad: sine + triangle
        if bright:
            # brighter piano
            for h in range(1, 8):
                amp = 1.0/(h**1.5)
                wave += amp * np.sin(2*np.pi*f0*h*t)
        else:
            # warm pad
            wave += np.sin(2*np.pi*f0*t) + 0.4*np.sin(2*np.pi*2*f0*t) * 0.5
    env = adsr_envelope(n, sr, attack=0.08 if not bright else 0.01, decay=0.2, sustain=0.6, release=0.3)
    wave = wave / (len(midis) or 1)
    return wave * env * velocity * 0.4

def get_scale_notes(root_midi, is_major=True):
    """Return MIDI notes of scale in octave 4-5."""
    intervals_major = [0,2,4,5,7,9,11,12]
    intervals_minor = [0,2,3,5,7,8,10,12]
    intervals = intervals_major if is_major else intervals_minor
    return [root_midi + i for i in intervals]

def get_chord_progression(root_midi, is_major=True, style="warm-acoustic"):
    """
    Returns list of chords, each chord is list of MIDI notes.
    Simple but effective progressions tuned to style.
    """
    # Scale degrees -> root offsets
    if is_major:
        # I, V, vi, IV — classic feel-good
        # For warm-acoustic / indie-pop
        if style in ("warm-acoustic", "indie-pop", "piano-ballad"):
            degrees = [0, 7, 9, 5]  # I, V, vi, IV
        elif style == "lofi-chill":
            degrees = [0, 5, 9, 7]  # I, IV, vi, V — softer
        else:  # cinematic
            degrees = [0, 5, 3, 7]  # I, IV, iii, V
        scale_intervals = [0,2,4,5,7,9,11]
    else:
        # i, VI, III, VII — minor feel-good
        degrees = [0, 8, 3, 10]  # i, VI, III, VII
        scale_intervals = [0,2,3,5,7,8,10]

    # Build chords
    chords = []
    for deg_offset in degrees:
        # root of chord = root_midi + deg_offset
        chord_root = root_midi + deg_offset
        # triad: root, third, fifth
        # Determine third based on scale
        # Simplified: if is_major, use major triad except vi, ii, iii minor
        # For MVP, use major/minor based on degree
        if is_major:
            # major degrees: I, IV, V major, others minor
            if deg_offset in (0,5,7):
                third = chord_root + 4
            else:
                third = chord_root + 3
        else:
            # minor key: i, iv, v minor, others major
            if deg_offset in (0,5,10):
                third = chord_root + 3
            else:
                third = chord_root + 4
        fifth = chord_root + 7
        # voicing: put in mid range (C4=60)
        # keep around 60-72
        while chord_root < 60:
            chord_root += 12
            third += 12
            fifth += 12
        while chord_root > 67:
            chord_root -= 12
            third -= 12
            fifth -= 12
        # add octave for fullness
        chord_notes = [chord_root-12, chord_root, third, fifth, third+12]  # bass + triad + octave
        chords.append(chord_notes)
    return chords

def generate_accompaniment(analysis: dict, out_path: Path, style="warm-acoustic", duration_sec=None):
    sr = 44100
    bpm = analysis.get("bpm", 90.0) or 90.0
    # clamp BPM to sane range
    try:
        bpm = float(bpm)
    except:
        bpm = 90.0
    if bpm < 40:
        bpm = 90.0
    if bpm > 200:
        bpm = min(bpm, 180)
    key_str = analysis.get("key", "C major")
    is_major = analysis.get("is_major", True)
    # parse root
    try:
        root_name = key_str.split()[0]
        note_to_semi = {n:i for i,n in enumerate(NOTE_NAMES)}
        root_semi = note_to_semi.get(root_name, 0)
        root_midi = 60 + root_semi  # C4 = 60
        # Adjust octave for bass: if singer is high (mean > 250 Hz), put root lower, etc.
        f0_mean = analysis.get("f0_mean_hz", 180)
        if f0_mean > 260:  # high voice, keep accompaniment lower
            root_midi -= 12
    except:
        root_midi = 60

    total_duration = duration_sec or analysis.get("duration_sec", 30.0)
    # add 2 sec tail
    total_duration = float(total_duration) + 0.8

    n_total = int(sr * total_duration)
    # stereo mix
    mix_left = np.zeros(n_total, dtype=np.float32)
    mix_right = np.zeros(n_total, dtype=np.float32)

    # Timing
    beat_sec = 60.0 / bpm
    bar_sec = beat_sec * 4
    # 1 bar = 4 beats

    # Chord progression: each chord = 1 bar (or 2 bars for ballad)
    chords = get_chord_progression(root_midi, is_major, style)
    # How many bars needed?
    num_bars = int(math.ceil(total_duration / bar_sec))
    # Loop progression
    # Generate bass + chords + drums per bar

    # Pre-synthesize drum hits
    kick = synth_kick(sr)
    snare = synth_snare(sr)
    hat_closed = synth_hat(sr, 0.12, closed=True)
    hat_open = synth_hat(sr, 0.25, closed=False)

    for bar in range(num_bars):
        bar_start = int(bar * bar_sec * sr)
        chord = chords[bar % len(chords)]
        chord_duration = bar_sec
        # --- Bass: play root on each beat (or 1 and 3 for ballad)
        bass_root = chord[0]  # lowest note
        if style == "piano-ballad":
            # bass on beat 1 only, sustained
            note = synth_bass_note(bass_root, sr, chord_duration, velocity=0.7)
            s = bar_start
            e = min(s+len(note), n_total)
            mix_left[s:e] += note[:e-s] * 0.9
            mix_right[s:e] += note[:e-s] * 0.9
        else:
            # bass on 1 and 3, or every beat for pop
            beats_per_bar = 4
            for b in range(beats_per_bar):
                if style == "lofi-chill" and b % 2 == 1:
                    continue  # only 1 and 3
                dur = beat_sec * (1.8 if b==0 else 0.9)
                note = synth_bass_note(bass_root, sr, dur, velocity=0.65 if b==0 else 0.5)
                s = bar_start + int(b*beat_sec*sr)
                e = min(s+len(note), n_total)
                if s < n_total:
                    mix_left[s:e] += note[:e-s] * 0.85
                    mix_right[s:e] += note[:e-s] * 0.85

        # --- Chords / Pad
        # For acoustic: strum slightly arpeggiated, bright
        # For lofi: warm pad, slow attack
        is_bright = style in ("warm-acoustic", "indie-pop", "piano-ballad")
        # chord notes for harmony (upper part)
        upper_chord = chord[1:]  # without bass
        if style == "warm-acoustic":
            # strum: arpeggiate with 30ms delay per note
            for idx, midi_note in enumerate(upper_chord):
                delay = idx * 0.03
                note = synth_chord([midi_note], sr, chord_duration - delay, velocity=0.45, bright=True)
                s = bar_start + int(delay*sr)
                e = min(s+len(note), n_total)
                # slight stereo spread
                pan = (idx / max(len(upper_chord)-1,1)) * 0.6 - 0.3
                if s < n_total:
                    mix_left[s:e] += note[:e-s] * (0.5 - pan)
                    mix_right[s:e] += note[:e-s] * (0.5 + pan)
        else:
            # block chord pad
            chord_wave = synth_chord(upper_chord, sr, chord_duration, velocity=0.38, bright=is_bright)
            s = bar_start
            e = min(s+len(chord_wave), n_total)
            mix_left[s:e] += chord_wave[:e-s] * 0.7
            mix_right[s:e] += chord_wave[:e-s] * 0.7

        # --- Arp for indie-pop / cinematic
        if style in ("indie-pop", "cinematic", "lofi-chill"):
            # simple up arp every 8th note
            arp_notes = upper_chord[:3]  # 3 notes
            eighth = beat_sec / 2
            for step in range(8):
                midi_note = arp_notes[step % len(arp_notes)] + (12 if step>=4 else 0)
                note = synth_chord([midi_note], sr, eighth*0.9, velocity=0.25, bright=True)
                s = bar_start + int(step*eighth*sr)
                e = min(s+len(note), n_total)
                if s < n_total:
                    # ping-pong pan
                    pan = 0.3 if step%2==0 else -0.3
                    mix_left[s:e] += note[:e-s] * (0.5 - pan*0.3)
                    mix_right[s:e] += note[:e-s] * (0.5 + pan*0.3)

        # --- Drums
        for beat in range(4):
            beat_start = bar_start + int(beat*beat_sec*sr)
            # kick on 1 and 3 (or all for pop)
            if beat in (0,2) or (style=="indie-pop" and beat==1):
                s = beat_start
                e = min(s+len(kick), n_total)
                if s < n_total:
                    mix_left[s:e] += kick[:e-s] * 0.7
                    mix_right[s:e] += kick[:e-s] * 0.7
            # snare on 2 and 4
            if beat in (1,3):
                s = beat_start
                e = min(s+len(snare), n_total)
                if s < n_total:
                    mix_left[s:e] += snare[:e-s] * 0.55
                    mix_right[s:e] += snare[:e-s] * 0.55
            # hi-hats
            # 8th notes
            for eighth in range(2):
                hs = beat_start + int(eighth*beat_sec/2*sr)
                is_open = (beat==3 and eighth==1)  # open hat at end of bar
                hat = hat_open if is_open else hat_closed
                he = min(hs+len(hat), n_total)
                if hs < n_total:
                    mix_left[hs:he] += hat[:he-hs] * 0.5
                    mix_right[hs:he] += hat[:he-hs] * 0.5

    # --- Style-specific master EQ / effects (simple)
    # Apply gentle low-pass for lofi
    if style == "lofi-chill":
        # simple one-pole low-pass
        # y[n] = (1-a)*x[n] + a*y[n-1], a ~ 0.2 for mild
        a = 0.15
        for ch in (mix_left, mix_right):
            for i in range(1, len(ch)):
                ch[i] = (1-a)*ch[i] + a*ch[i-1]
        # add subtle vinyl crackle (noise)
        crackle = np.random.randn(n_total) * 0.015
        # gate crackle
        gate = (np.random.rand(n_total) > 0.995).astype(float)
        crackle = crackle * gate
        mix_left += crackle * 0.5
        mix_right += crackle * 0.5

    # Normalize to prevent clipping, leave headroom
    max_val = max(np.max(np.abs(mix_left)), np.max(np.abs(mix_right)), 1e-6)
    if max_val > 0.8:
        scale = 0.8 / max_val
        mix_left *= scale
        mix_right *= scale

    # Mix to stereo
    stereo = np.stack([mix_left, mix_right], axis=1)

    # Trim to original duration + tail already accounted, but ensure same as requested
    # Save
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), stereo, sr)
    return out_path
