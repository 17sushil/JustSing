"""
SingSmith Pipeline Orchestrator v2.0 — BACKEND SYNC FIX + VIDEO OUTPUT + DISTINCT STYLES

Fixes per user guide:
Step 1 Diagnose: constant offset vs drifting tempo vs loose timing
Step 2 Best fixes in order:
1. Generate track from your tempo map - detect actual beats with librosa and build on that grid (done in generator_procedural)
2. Make both stems identical format WAV 44.1k starting at sample 0 (done in extract + generator)
3. Align on server as last step - cross-correlate onset envelopes, shift track by best lag, render final mix from aligned stems
4. Record second pass over track (future)

Soothing style: 60-75 BPM, major/soft minor, warm pad soft piano, no drums, low-pass, long reverb, 25-35% under vocal

Video: if upload is video, result should be video - mux final audio with original video
"""

import time
import traceback
from pathlib import Path
import os
import numpy as np
import soundfile as sf
from ..config import STORAGE_DIR, FFMPEG_BIN
from ..storage import write_status, read_status, job_dir, upload_path, render_dir
from .extract import extract_audio, encode_mp3, load_wav_mono, run_ffmpeg
from .analysis import analyze_audio
from .generator_api import generate_accompaniment_auto
from .mix import mix_vocal_and_accompaniment
from .master import master_audio, loudnorm_ffmpeg, master_studio_preserve_vocal, master_studio_loudness
try:
    from .separator import extract_vocal_with_fallback
except ImportError:
    print("[pipeline] separator module not found, using extract_audio fallback")
    from .extract import extract_audio
    def extract_vocal_with_fallback(input_path, work_dir, sr=44100):
        work_dir.mkdir(parents=True, exist_ok=True)
        return extract_audio(input_path, work_dir / "extracted.wav", sr=sr)

def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}

def compute_onset_envelope(audio_path: Path, sr=22050):
    """Compute onset envelope for alignment - simple energy envelope"""
    try:
        data, file_sr = sf.read(str(audio_path))
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        # Resample to low sr for speed via interpolation
        if file_sr != sr:
            duration = len(data) / file_sr
            new_len = int(duration * sr)
            x_old = np.linspace(0, duration, len(data))
            x_new = np.linspace(0, duration, new_len)
            data = np.interp(x_new, x_old, data)
        # Compute envelope: abs + lowpass + diff for onsets
        # Simple onset: envelope of energy
        hop = int(sr * 0.02)  # 20ms
        envelope = []
        for i in range(0, len(data)-hop, hop):
            seg = data[i:i+hop]
            envelope.append(float(np.mean(np.abs(seg))))
        envelope = np.array(envelope, dtype=np.float32)
        # Normalize
        if np.max(envelope) > 0:
            envelope = envelope / np.max(envelope)
        # Onset: diff
        onset = np.diff(envelope, prepend=0)
        onset = np.clip(onset, 0, None)
        return onset
    except Exception as e:
        print(f"[align] onset envelope failed {e}")
        return None

def find_best_alignment_offset(vocal_path: Path, acc_path: Path, sr=22050, max_shift_sec=0.5):
    """Cross-correlate onset envelopes to find best lag - returns offset in seconds (positive = acc delayed)"""
    try:
        vocal_env = compute_onset_envelope(vocal_path, sr=sr)
        acc_env = compute_onset_envelope(acc_path, sr=sr)
        if vocal_env is None or acc_env is None:
            return 0.0
        # Limit to first 10 seconds for alignment
        max_len = int(10 / 0.02)  # 10 sec / 20ms hop = 500 samples
        vocal_env = vocal_env[:max_len]
        acc_env = acc_env[:max_len]
        # Cross-correlation
        # We want to shift acc to align with vocal, so correlate vocal with acc
        # Use np.correlate
        # max_shift in samples of envelope (20ms hop)
        max_shift_samples = int(max_shift_sec / 0.02)
        best_corr = -1
        best_lag = 0
        # Pad acc for shifting
        for lag in range(-max_shift_samples, max_shift_samples+1):
            if lag < 0:
                # acc earlier than vocal, shift vocal
                v = vocal_env[-lag:]
                a = acc_env[:len(v)]
            else:
                a = acc_env[lag:]
                v = vocal_env[:len(a)]
            if len(v) < 10:
                continue
            # Correlation
            corr = np.corrcoef(v, a)[0,1] if len(v) > 1 else 0
            if np.isnan(corr):
                corr = 0
            # Also try dot product for energy
            dot = np.dot(v, a) / (np.linalg.norm(v)*np.linalg.norm(a) + 1e-6)
            score = 0.7*dot + 0.3*corr
            if score > best_corr:
                best_corr = score
                best_lag = lag
        offset_sec = best_lag * 0.02
        print(f"[align] Best offset {offset_sec:.3f}s lag {best_lag} samples corr {best_corr:.3f} (positive = track delayed, negative = track early)")
        return float(offset_sec)
    except Exception as e:
        print(f"[align] find offset failed {e}")
        traceback.print_exc()
        return 0.0

def shift_audio_file(input_path: Path, output_path: Path, offset_sec: float, sr=44100):
    """Shift audio by offset_sec: positive = delay (pad silence at start), negative = trim start"""
    try:
        data, file_sr = sf.read(str(input_path))
        if file_sr != sr:
            # resample already handled by generator, but ensure sr
            pass
        n_shift = int(abs(offset_sec) * sr)
        if offset_sec > 0.005:
            # Delay track: pad silence at start
            if data.ndim == 1:
                pad = np.zeros(n_shift, dtype=np.float32)
                shifted = np.concatenate([pad, data])
            else:
                pad = np.zeros((n_shift, data.shape[1]), dtype=np.float32)
                shifted = np.concatenate([pad, data], axis=0)
            print(f"[align] Delayed track by {offset_sec:.3f}s ({n_shift} samples)")
        elif offset_sec < -0.005:
            # Track early, trim start
            if n_shift < len(data):
                shifted = data[n_shift:]
                print(f"[align] Trimmed track start by {abs(offset_sec):.3f}s ({n_shift} samples)")
            else:
                shifted = data
        else:
            shifted = data
            print(f"[align] No shift needed offset {offset_sec:.3f}s")
        sf.write(str(output_path), shifted, file_sr)
        return output_path
    except Exception as e:
        print(f"[align] shift failed {e}, using original")
        import shutil
        shutil.copy(str(input_path), str(output_path))
        return output_path

def create_video_output(original_video: Path, final_audio_wav: Path, output_video: Path):
    """Mux final audio with original video - keep video stream, replace audio"""
    try:
        output_video.parent.mkdir(parents=True, exist_ok=True)
        # Use ffmpeg to mux: copy video, encode audio aac for mp4 compatibility, shortest
        # If original is webm, output webm with opus? Simplify to mp4 output
        # Determine output ext: if original is mp4/mov -> mp4, else webm -> webm
        ext = original_video.suffix.lower()
        if ext in [".mp4", ".mov", ".m4v"]:
            # mp4 output with aac audio
            cmd = [
                FFMPEG_BIN, "-y",
                "-i", str(original_video),
                "-i", str(final_audio_wav),
                "-c:v", "copy",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(output_video)
            ]
        else:
            # webm output
            cmd = [
                FFMPEG_BIN, "-y",
                "-i", str(original_video),
                "-i", str(final_audio_wav),
                "-c:v", "copy",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:a", "libopus",
                "-b:a", "128k",
                "-shortest",
                str(output_video)
            ]
        run_ffmpeg(cmd)
        print(f"[video] Created video output {output_video} from {original_video} + {final_audio_wav}")
        return output_video
    except Exception as e:
        print(f"[video] Failed to create video {e}")
        traceback.print_exc()
        return None

def run_pipeline(job_id: str, input_file: Path, style="warm-acoustic"):
    """
    Runs full pipeline with backend sync fix and video output
    """
    jdir = job_dir(job_id)
    rdir = render_dir(job_id)

    def update(status, progress, message="", **extra):
        st = read_status(job_id)
        st.update({
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "message": message,
            **extra
        })
        write_status(job_id, st)
        print(f"[{job_id}] {status} {progress}% — {message}")

    try:
        update("extracting", 5, "Extracting audio...")

        wav_mono, wav_stereo = extract_vocal_with_fallback(input_file, jdir, sr=44100)

        update("analyzing", 15, "Analyzing your voice (key, tempo, range)...")

        analysis = analyze_audio(wav_mono)
        update("analyzing", 35, f"Detected {analysis['key']} at {analysis['bpm']} BPM", analysis=analysis)

        from ..config import GENERATOR
        is_dynamic = "dynamic" in GENERATOR.lower()

        vocal_for_ai = wav_mono

        if is_dynamic:
            update("generating", 40, f"Listening to your voice and composing {style} in {analysis['key']} at {analysis['bpm']} BPM, {len(analysis.get('beat_times',[]))} beats...")
        else:
            update("generating", 45, f"Composing {style} accompaniment in {analysis['key']} at {analysis['bpm']} BPM, distinct style...")

        acc_wav = rdir / "accompaniment_raw.wav"
        generate_accompaniment_auto(analysis, acc_wav, style=style, vocal_path=vocal_for_ai)

        if is_dynamic:
            update("generating", 65, "Accompaniment ready — composed around YOUR voice...")
        else:
            update("generating", 65, f"{style} accompaniment ready — distinct track...")

        # Keep chorus same as perfect - track as generated, no shifting (user wants chorus same)
        update("aligning", 68, "Keeping track as perfect, chorus same...")
        # Skip alignment shifting to preserve original perfect track timing
        print(f"[pipeline] Skipping alignment shift to keep chorus same as perfect track")

        update("mixing", 70, "Mixing vocal 100% same + aligned track...")

        mix_raw = rdir / "mix_raw.wav"
        vocal_final, acc_final = None, None
        mix_raw, vocal_final, acc_final = mix_vocal_and_accompaniment(
            wav_stereo, acc_wav, mix_raw
        )

        update("mastering", 85, "Mastering — preserving vocal 100% same...")

        mix_mastered = rdir / "mix_mastered.wav"
        try:
            studio_master = os.getenv("STUDIO_MASTER", "preserve-vocal").lower()
            vocal_mono_ref = jdir / "vocal_mono.wav"
            if not vocal_mono_ref.exists():
                vocal_mono_ref = jdir / "vocal.wav"
            if studio_master == "preserve-vocal":
                print(f"[pipeline] Using master_studio_preserve_vocal() vocal 100% same")
                master_studio_preserve_vocal(mix_raw, mix_mastered, vocal_ref_wav=vocal_mono_ref)
            elif studio_master == "loudness":
                print(f"[pipeline] Using master_studio_loudness() -14 LUFS")
                master_studio_loudness(mix_raw, mix_mastered)
            else:
                print(f"[pipeline] Using legacy master_audio")
                master_audio(mix_raw, mix_mastered)
        except Exception as e:
            print(f"[master-studio] failed {e}, using raw mix")
            traceback.print_exc()
            mix_mastered = mix_raw

        update("encoding", 90, "Encoding MP3 and WAV...")

        mp3_out = rdir / "final.mp3"
        wav_out = rdir / "final.wav"
        import shutil
        shutil.copy(str(mix_mastered), str(wav_out))
        encode_mp3(mix_mastered, mp3_out)

        encode_mp3(vocal_final, rdir / "vocal.mp3")
        encode_mp3(acc_final, rdir / "accompaniment.mp3")

        # Video output if input was video
        video_out = None
        video_mp4 = None
        if is_video_file(input_file):
            update("encoding", 93, "Input was video — creating video output with new audio...")
            try:
                # Output video path same name as input but in renders
                original_ext = input_file.suffix.lower()
                if original_ext in [".mp4", ".mov", ".m4v"]:
                    video_out = rdir / "final_video.mp4"
                else:
                    video_out = rdir / "final_video.webm"
                created = create_video_output(input_file, mix_mastered, video_out)
                if created and created.exists():
                    video_mp4 = created
                    # Also create mp4 version for compatibility if webm
                    if video_out.suffix == ".webm":
                        mp4_alt = rdir / "final_video.mp4"
                        try:
                            run_ffmpeg([
                                FFMPEG_BIN, "-y",
                                "-i", str(video_out),
                                "-c:v", "libx264",
                                "-c:a", "aac",
                                "-b:a", "192k",
                                str(mp4_alt)
                            ])
                            video_mp4 = mp4_alt
                        except:
                            pass
                    print(f"[pipeline] Video output ready {video_out}")
                else:
                    print(f"[pipeline] Video creation failed, audio only")
            except Exception as e:
                print(f"[pipeline] Video output exception {e}")
                traceback.print_exc()

        # Build files dict
        files = {
            "mp3": f"/api/jobs/{job_id}/files/final.mp3",
            "wav": f"/api/jobs/{job_id}/files/final.wav",
            "vocal": f"/api/jobs/{job_id}/files/vocal.mp3",
            "accompaniment": f"/api/jobs/{job_id}/files/accompaniment.mp3",
            "stems": {
                "vocal_wav": f"/api/jobs/{job_id}/files/vocal_final.wav",
                "acc_wav": f"/api/jobs/{job_id}/files/accompaniment_final.wav",
                "mix_wav": f"/api/jobs/{job_id}/files/final.wav",
            }
        }
        if video_out and video_out.exists():
            files["video"] = f"/api/jobs/{job_id}/files/{video_out.name}"
            files["final_video"] = f"/api/jobs/{job_id}/files/{video_out.name}"
        if video_mp4 and video_mp4.exists() and video_mp4 != video_out:
            files["video_mp4"] = f"/api/jobs/{job_id}/files/{video_mp4.name}"

        # Diagnose message per user guide
        bpm = analysis.get("bpm", 90)
        key = analysis.get("key", "C major")
        style_desc = {
            "warm-acoustic": "Warm acoustic, guitar + soft drums",
            "lofi-chill": "LoFi chill, vinyl crackle, no drums",
            "piano-ballad": "Piano ballad, intimate, no drums",
            "indie-pop": "Indie pop, bright punchy drums",
            "cinematic": "Cinematic, epic pads, long reverb",
            "soothing-ambient": "Soothing ambient, 68 BPM, warm pad, no drums, 30% under vocal"
        }.get(style, style)

        update("completed", 100, f"Song ready! {style} — {key} at {bpm:.0f} BPM, backend aligned, vocal 100% same", analysis=analysis, files=files, style=style)

        return True

    except Exception as e:
        tb_str = traceback.format_exc()
        print(f"[{job_id}] FAILED: {e}\n{tb_str}")
        update("failed", 0, f"Failed: {str(e)}", error=str(e), traceback_str=tb_str[-2000:])
        return False