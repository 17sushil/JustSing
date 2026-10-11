"""
SingSmith Generator v1.7.4 SAME VOL AS INPUT + LOW DRUMS + FLUTE

User: "I need default low drum sound and piano and flute like sound as of same volume level as input audio"

- Drums low by default: DRUM_BOOST=0.5 -> kick 0.35*0.5=0.175, snare 0.28*0.5=0.14, hat 0.20*0.5=0.10
- Flute/piano same vol as input: CHORUS_BOOST=1.0 default, vols 0.55,0.45,0.42,0.32 * boost = same RMS as vocal
- Flute timbre: pure sine 0.9 + 2nd 0.08 + 3rd 0.03 + breath noise, vibrato 5.5Hz ±12 cents
"""

import numpy as np
import soundfile as sf
from pathlib import Path
import math
import hashlib
import random
import os

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

def synth_choir_voice(f0_curve, sr, duration, semitone_shift, velocity_curve, pan=0.0, variation=0, base_vol=0.5):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0), np.zeros(0)
    t = np.linspace(0, duration, n)
    if len(f0_curve) != n:
        x_old = np.linspace(0, duration, len(f0_curve))
        f0_interp = np.interp(t, x_old, f0_curve)
    else:
        f0_interp = f0_curve
    f0_shifted = f0_interp * (2 ** (semitone_shift/12.0))
    window = int(sr * 0.03)
    if window > 1:
        f0_shifted = np.convolve(f0_shifted, np.ones(window)/window, mode='same')
    f0_shifted = np.clip(f0_shifted, 60, 800)
    if len(velocity_curve) != n:
        x_old = np.linspace(0, duration, len(velocity_curve))
        vel_interp = np.interp(t, x_old, velocity_curve)
    else:
        vel_interp = velocity_curve
    timbre = os.getenv("CHORUS_TIMBRE", "flute").lower()
    vibrato_rate = 5.5
    vibrato_depth = 0.007
    vibrato = 1.0 + vibrato_depth * np.sin(2*np.pi*vibrato_rate*t + variation*0.1)
    f0_vib = f0_shifted * vibrato
    phase = 2*np.pi*np.cumsum(f0_vib)/sr
    if timbre == "flute":
        sine = np.sin(phase) * 0.9
        second = np.sin(2*phase) * 0.08
        third = np.sin(3*phase) * 0.03
        wave = sine + second + third
        breath = np.random.randn(n) * 0.015
        breath = breath - np.convolve(breath, np.ones(int(sr*0.002))/int(sr*0.002), mode='same')
        wave = wave + breath * 0.12
        cutoff = 2600 if semitone_shift <= -7 else 3400
        wave = one_pole_lowpass(wave, cutoff, sr)
    else:
        sine = np.sin(phase)
        saw_phase = 2 * ( (np.cumsum(f0_shifted)/sr) % 1 ) - 1
        saw = saw_phase * 0.25
        third = np.sin(2*phase) * 0.12
        wave = sine * 0.7 + saw * 0.3 + third * 0.15
        cutoff = 1800 if semitone_shift <= -7 else 2200 if semitone_shift <= -3 else 3000
        wave = one_pole_lowpass(wave, cutoff, sr)
    env_window = int(sr*0.05)
    if env_window > 1:
        vel_smooth = np.convolve(vel_interp, np.ones(env_window)/env_window, mode='same')
    else:
        vel_smooth = vel_interp
    vel_max = np.max(vel_smooth) + 1e-6
    vel_norm = vel_smooth / vel_max
    gate = (vel_norm > 0.008).astype(float)
    gate_len = max(1, int(sr*0.02))
    gate = np.convolve(gate, np.ones(gate_len)/gate_len, mode='same')
    wave = wave * vel_norm * gate * base_vol * 1.2
    left_gain = 0.5 - pan*0.4
    right_gain = 0.5 + pan*0.4
    left = wave * left_gain
    right = wave * right_gain
    return left, right

def synth_soft_pad(midi, sr, duration, velocity=0.2, variation=0):
    n = int(sr*duration)
    if n<=0:
        return np.zeros(0)
    t = np.linspace(0, duration, n)
    f0 = note_to_freq(midi)
    sine = np.sin(2*np.pi*f0*t) * 0.6
    sine2 = np.sin(2*np.pi*f0*2*t) * 0.2
    sine3 = np.sin(2*np.pi*f0*0.5*t) * 0.15
    wave = sine + sine2 + sine3
    env = adsr_envelope(n, sr, attack=0.4, decay=0.3, sustain=0.5, release=0.8)
    wave = one_pole_lowpass(wave, 1200, sr)
    wave = wave * env * velocity * 0.35
    return wave

def synth_kick(sr, duration=0.5, variation=0):
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

def synth_snare(sr, duration=0.35, variation=0):
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

def synth_hat(sr, duration=0.14, closed=True, variation=0):
    n = int(sr*duration)
    noise = np.random.randn(n)
    hp = noise - np.concatenate([[0], noise[:-1]]) * 0.95
    decay = 30+variation*3 if closed else 10+variation
    env = np.exp(-np.linspace(0, duration, n)*decay)
    wave = hp * env
    wave = one_pole_lowpass(wave, 9000, sr)
    return wave * (0.28 if closed else 0.20)

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

def analyze_vocal_continuous(vocal_path: Path, duration_sec):
    try:
        y_vocal, sr_v = sf.read(str(vocal_path))
        if y_vocal.ndim > 1:
            y_vocal = np.mean(y_vocal, axis=1)
        hop = int(sr_v * 0.05)
        times = []
        f0_curve = []
        energy_curve = []
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
        if times and times[-1] < duration_sec:
            last_f0 = f0_curve[-1]
            last_energy = 0.01
            while times[-1] < duration_sec:
                times.append(times[-1]+0.05)
                f0_curve.append(last_f0)
                energy_curve.append(last_energy*0.9)
                last_energy *= 0.9
        print(f"[chorus] Continuous: {len(times)} frames 50ms, F0 {min(f0_curve):.0f}-{max(f0_curve):.0f}Hz")
        return np.array(times), np.array(f0_curve), np.array(energy_curve), sr_v
    except Exception as e:
        print(f"[chorus] Continuous failed {e}")
        import traceback
        traceback.print_exc()
        n_frames = int(duration_sec / 0.05)
        times = np.linspace(0, duration_sec, n_frames)
        f0_curve = np.ones(n_frames)*180.0
        energy_curve = np.ones(n_frames)*0.1
        return times, f0_curve, energy_curve, 44100

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
    print(f"[generator] v1.7.4 SAME VOL + LOW DRUMS + FLUTE STUDIO {style} {key_str} {bpm} BPM seed {seed} hash {file_hash} beats {len(beat_times)} bars {len(bar_times)} phrases {len(phrases)}")
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
    if vocal_path and vocal_path.exists():
        cont_times, cont_f0, cont_energy, sr_v = analyze_vocal_continuous(vocal_path, total_duration)
    else:
        n_frames = int(total_duration / 0.05)
        cont_times = np.linspace(0, total_duration, n_frames)
        cont_f0 = np.ones(n_frames)*analysis.get("f0_mean_hz",180)
        cont_energy = np.ones(n_frames)*0.1
        print(f"[chorus] No vocal path, using dummy F0")
    third_shift = -4 if is_major else -3
    try:
        chorus_boost = float(os.getenv("CHORUS_BOOST", "1.0"))
        chorus_boost = max(0.3, min(3.0, chorus_boost))
    except:
        chorus_boost = 1.0
    try:
        drum_boost = float(os.getenv("DRUM_BOOST", "0.5"))
        drum_boost = max(0.0, min(2.0, drum_boost))
    except:
        drum_boost = 0.5
    chorus_voices = [
        {"shift": -12, "vol": 0.55 * chorus_boost, "pan": -0.20, "name": "octave_down"},
        {"shift": -7, "vol": 0.45 * chorus_boost, "pan": 0.20, "name": "fifth"},
        {"shift": third_shift, "vol": 0.42 * chorus_boost, "pan": -0.10, "name": "third"},
        {"shift": 12, "vol": 0.32 * chorus_boost, "pan": 0.10, "name": "octave_up"},
    ]
    print(f"[chorus] v1.7.4 SAME VOL AS INPUT + LOW DRUMS — chorus boost {chorus_boost:.1f}x drum boost {drum_boost:.1f}x — {len(chorus_voices)} voices")
    for voice in chorus_voices:
        shift = voice["shift"]
        base_vol = voice["vol"]
        pan = voice["pan"]
        vel_curve = cont_energy * base_vol * 4.5
        left, right = synth_choir_voice(cont_f0, sr, total_duration, shift, vel_curve, pan=pan, variation=seed, base_vol=base_vol)
        mix_left += left
        mix_right += right
        print(f"[chorus] Voice {voice['name']} shift {shift} vol {base_vol:.2f} peak {np.max(np.abs(left)):.3f}")
    try:
        root_name = key_str.split()[0]
        root_semi = {n:i for i,n in enumerate(NOTE_NAMES)}.get(root_name, 0)
        key_root_midi = 60 + root_semi
    except:
        key_root_midi = 60
    if is_major:
        prog_degrees = [0, 7, 9, 5]
    else:
        prog_degrees = [0, 10, 8, 10]
    num_bars = len(bar_times)
    for bar_idx in range(num_bars):
        bar_start_t = bar_times[bar_idx]
        bar_end_t = bar_times[bar_idx+1] if bar_idx+1 < len(bar_times) else bar_start_t + (60.0/bpm*4)
        bar_duration = bar_end_t - bar_start_t
        if bar_duration <=0 or bar_duration > 8.0:
            bar_duration = 60.0/bpm*4
        bar_start = int(bar_start_t * sr)
        if bar_start >= n_total:
            break
        bar_mask = (cont_times >= bar_start_t) & (cont_times < bar_end_t)
        bar_energy = np.mean(cont_energy[bar_mask]) if np.any(bar_mask) else 0.05
        is_intro = bar_start_t + bar_duration < first_vocal_time - 0.2
        inside_phrase = any(ps -0.1 <= bar_start_t <= pe +0.1 for ps, pe in phrases) if phrases else True
        is_silence_bar = (bar_energy < 0.015) and not inside_phrase
        degree = prog_degrees[bar_idx % len(prog_degrees)]
        chord_root = key_root_midi + degree
        pad_root = chord_root - 12
        while pad_root < 48:
            pad_root += 12
        while pad_root > 60:
            pad_root -= 12
        pad_notes = [pad_root, pad_root+7]
        for pad_midi in pad_notes:
            vel = (0.50 + bar_energy*0.30) * chorus_boost
            if is_intro:
                vel *= 0.5
            if is_silence_bar:
                vel *= 0.15
            pad_wave = synth_soft_pad(pad_midi, sr, bar_duration*1.1, velocity=vel, variation=seed)
            s = bar_start
            e = min(s+len(pad_wave), n_total)
            if s < n_total:
                duck = 1.0 - min(bar_energy*1.2, 0.25)
                mix_left[s:e] += pad_wave[:e-s] * 1.0 * duck
                mix_right[s:e] += pad_wave[:e-s] * 1.0 * duck
    variation = (seed % 10) / 10.0
    kick = synth_kick(sr, variation=variation)
    snare = synth_snare(sr, variation=variation)
    hat_closed = synth_hat(sr, 0.12, closed=True, variation=variation)
    hat_open = synth_hat(sr, 0.25, closed=False, variation=variation)
    for bar_idx in range(num_bars):
        bar_start_t = bar_times[bar_idx]
        bar_end_t = bar_times[bar_idx+1] if bar_idx+1 < len(bar_times) else bar_start_t + (60.0/bpm*4)
        bar_duration = bar_end_t - bar_start_t
        if bar_duration <=0 or bar_duration > 8.0:
            bar_duration = 60.0/bpm*4
        beats_in_bar = [bt for bt in beat_times if bar_start_t <= bt < bar_end_t]
        if not beats_in_bar:
            beats_in_bar = [bar_start_t + i*(bar_duration/4) for i in range(4)]
        bar_mask = (cont_times >= bar_start_t) & (cont_times < bar_end_t)
        bar_energy = np.mean(cont_energy[bar_mask]) if np.any(bar_mask) else 0.05
        is_intro = bar_start_t + bar_duration < first_vocal_time - 0.2
        is_silence_bar = (bar_energy < 0.015)
        for b_idx, beat_t in enumerate(beats_in_bar):
            is_onset_beat = any(abs(beat_t - ot) < 0.08 for ot in onset_times)
            beat_mask = (cont_times >= beat_t-0.05) & (cont_times < beat_t+0.05)
            is_energy_peak = False
            if np.any(beat_mask):
                local_energy = np.mean(cont_energy[beat_mask])
                prev_mask = (cont_times >= beat_t-0.15) & (cont_times < beat_t-0.05)
                next_mask = (cont_times >= beat_t+0.05) & (cont_times < beat_t+0.15)
                if np.any(prev_mask) and np.any(next_mask):
                    prev_e = np.mean(cont_energy[prev_mask])
                    next_e = np.mean(cont_energy[next_mask])
                    if local_energy > prev_e*1.3 and local_energy > next_e*1.1 and local_energy > 0.03:
                        is_energy_peak = True
            beat_start = int(beat_t * sr)
            kick_beats = [0,2] if len(beats_in_bar)==4 else [0]
            should_kick = (b_idx in kick_beats) or is_onset_beat or is_energy_peak
            if should_kick:
                if is_silence_bar and b_idx != 0 and not is_onset_beat:
                    continue
                s = beat_start
                humanize = int((random.random()-0.5)*0.003*sr)
                s = max(0, s+humanize)
                e = min(s+len(kick), n_total)
                if s < n_total:
                    vel = (0.35 + bar_energy*0.08 + random.random()*0.03) * drum_boost
                    if is_onset_beat or is_energy_peak:
                        vel += 0.10 * drum_boost
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
                    vel = (0.28 + bar_energy*0.08 + random.random()*0.04) * drum_boost
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
                    hat_vel = (0.20 + bar_energy*0.04 + random.random()*0.04) * drum_boost
                    if is_silence_bar:
                        hat_vel *= 0.32
                    if is_intro:
                        hat_vel *= 0.52
                    if is_energy_peak:
                        hat_vel += 0.08 * drum_boost
                    mix_left[hs:he] += hat[:he-hs] * hat_vel
                    mix_right[hs:he] += hat[:he-hs] * hat_vel
    max_val = max(np.max(np.abs(mix_left)), np.max(np.abs(mix_right)), 1e-6)
    if max_val > 0.85:
        scale = 0.85 / max_val
        mix_left *= scale
        mix_right *= scale
    stereo = np.stack([mix_left, mix_right], axis=1)
    reverb_mix = 0.22
    if style == "cinematic":
        reverb_mix = 0.30
    elif style == "piano-ballad":
        reverb_mix = 0.25
    stereo = simple_reverb(stereo, sr, room=0.6, damp=0.4, mix=reverb_mix)
    max_val = np.max(np.abs(stereo))
    if max_val > 0.89:
        stereo = stereo * (0.89 / max_val)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), stereo, sr)
    print(f"[generator] v1.7.4 SAME VOL + LOW DRUMS + FLUTE Saved {out_path}, {total_duration:.1f}s, {len(bar_times)} bars, {len(cont_times)} cont frames, seed {seed}, hash {file_hash}")
    return out_path
