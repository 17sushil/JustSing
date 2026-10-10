"""
SingSmith Pipeline Orchestrator — 9 stages from blueprint §3.
Zero-cost defaults: procedural generator, no separator, local analysis.
"""
import time
import traceback
from pathlib import Path
from ..config import STORAGE_DIR
from ..storage import write_status, read_status, job_dir, upload_path, render_dir
from .extract import extract_audio, encode_mp3, load_wav_mono
from .analysis import analyze_audio
from .generator_api import generate_accompaniment_auto
from .mix import mix_vocal_and_accompaniment
from .master import master_audio, loudnorm_ffmpeg
from .separator import extract_vocal_with_fallback

def run_pipeline(job_id: str, input_file: Path, style="warm-acoustic"):
    """
    Runs full pipeline for a job. Updates status.json at each stage.
    v1.2: Demucs separation like vocal.ai + phrase-following + per-beat changing
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

        # Stage 0: extract + separate (v1.2: Demucs like vocal.ai)
        # If SEPARATOR=demucs, isolates vocal from mixed song
        # If SEPARATOR=none, assumes input is already vocal
        wav_mono, wav_stereo = extract_vocal_with_fallback(input_file, jdir, sr=44100)
        # For analysis, use mono
        # For mix, use stereo

        update("analyzing", 15, "Analyzing your voice (key, tempo, range)...")

        # Stage 1-2: analysis (includes cleanup/isolation placeholder)
        analysis = analyze_audio(wav_mono)
        update("analyzing", 35, f"Detected {analysis['key']} at {analysis['bpm']} BPM", analysis=analysis)

        # Stage 3: generate accompaniment
        # v0.7: Always pass vocal for alignment — procedural uses it for beat tracking, dynamic uses it for AI listening
        from ..config import GENERATOR
        is_dynamic = "dynamic" in GENERATOR.lower()

        vocal_for_ai = wav_mono  # always pass for alignment

        if is_dynamic:
            update("generating", 40, f"OpenRouter is listening to your voice and composing {style} in {analysis['key']} at {analysis['bpm']} BPM, {len(analysis.get('beat_times',[]))} beats...")
        else:
            update("generating", 45, f"Composing {style} accompaniment in {analysis['key']} at {analysis['bpm']} BPM, locked to {len(analysis.get('beat_times',[]))} vocal beats...")

        acc_wav = rdir / "accompaniment_raw.wav"
        generate_accompaniment_auto(analysis, acc_wav, style=style, vocal_path=vocal_for_ai)

        if is_dynamic:
            update("generating", 65, "Dynamic accompaniment ready — composed around YOUR voice...")
        else:
            update("generating", 65, "Accompaniment ready, aligning to your voice...")

        # Stage 4: tune to singer (procedural already in key/tempo, so alignment is trivial)
        # For future: pitch-shift/time-stretch here if using API generator
        # For now, ensure same length handled in mix stage

        # Stage 5: mix
        update("mixing", 70, "Mixing vocal + accompaniment...")

        mix_raw = rdir / "mix_raw.wav"
        vocal_final, acc_final = None, None
        mix_raw, vocal_final, acc_final = mix_vocal_and_accompaniment(
            wav_stereo, acc_wav, mix_raw
        )

        # Stage 6: master
        update("mastering", 85, "Mastering to streaming loudness...")

        mix_mastered = rdir / "mix_mastered.wav"
        try:
            # Try ffmpeg loudnorm for better quality, fallback to RMS
            master_audio(mix_raw, mix_mastered)
        except Exception as e:
            print(f"[master] failed {e}, using raw mix")
            mix_mastered = mix_raw

        # Stage 7: encode MP3 + WAV
        update("encoding", 90, "Encoding MP3 and WAV...")

        mp3_out = rdir / "final.mp3"
        wav_out = rdir / "final.wav"
        # Copy mastered wav to final wav
        import shutil
        shutil.copy(str(mix_mastered), str(wav_out))
        encode_mp3(mix_mastered, mp3_out)

        # Also encode stems as MP3 for quick preview
        encode_mp3(vocal_final, rdir / "vocal.mp3")
        encode_mp3(acc_final, rdir / "accompaniment.mp3")

        # Stage 8: deliver
        update("completed", 100, "Song ready! 🎉", analysis=analysis, files={
            "mp3": f"/api/jobs/{job_id}/files/final.mp3",
            "wav": f"/api/jobs/{job_id}/files/final.wav",
            "vocal": f"/api/jobs/{job_id}/files/vocal.mp3",
            "accompaniment": f"/api/jobs/{job_id}/files/accompaniment.mp3",
            "stems": {
                "vocal_wav": f"/api/jobs/{job_id}/files/vocal_final.wav",
                "acc_wav": f"/api/jobs/{job_id}/files/accompaniment_final.wav",
                "mix_wav": f"/api/jobs/{job_id}/files/final.wav",
            }
        }, style=style)

        return True

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{job_id}] FAILED: {e}\n{tb}")
        update("failed", 0, f"Failed: {str(e)}", error=str(e), traceback=tb[-2000:])
        return False
