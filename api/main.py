"""
SingSmith API — FastAPI backend for zero-cost MVP.
Fixed routing for sandbox preview: explicit static serving, no mount conflicts.
"""
import shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import mimetypes

from .config import ROOT, STORAGE_DIR, STYLES, GENERATOR
from .storage import new_job_id, job_dir, upload_path, render_dir, write_status, read_status, list_jobs
from .pipeline.pipeline import run_pipeline

app = FastAPI(title="SingSmith MVP", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR = ROOT / "web"

# --- API ---
@app.get("/api/health")
def health():
    return {"status": "ok", "generator": GENERATOR, "styles": STYLES, "storage": str(STORAGE_DIR)}

@app.get("/api/styles")
def get_styles():
    return {"styles": STYLES, "generator": GENERATOR}

@app.post("/api/upload")
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    style: str = Form("warm-acoustic"),
):
    if style not in STYLES:
        style = "warm-acoustic"
    if not file or not file.filename:
        raise HTTPException(400, "No file uploaded")

    job_id = new_job_id()
    ext = Path(file.filename).suffix or ".webm"
    if len(ext) > 10 or not ext.startswith("."):
        ext = ".webm"
    ext = ext.lower()
    # allow common audio/video
    allowed = {".mp3",".wav",".m4a",".mp4",".webm",".ogg",".flac",".mov",".aac",".wma",".opus"}
    if ext not in allowed:
        ext = ".webm"

    upath = upload_path(job_id, f"original{ext}")
    upath.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(upath, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(500, f"Failed to save upload: {e}")

    write_status(job_id, {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "message": "Queued...",
        "style": style,
        "original_filename": file.filename,
        "files": {}
    })

    background_tasks.add_task(run_pipeline, job_id, upath, style)
    return {"job_id": job_id, "status": "queued", "style": style}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    st = read_status(job_id)
    if st.get("status") == "not_found":
        raise HTTPException(404, "Job not found")
    return st

@app.get("/api/jobs")
def get_jobs(limit: int = 20):
    return {"jobs": list_jobs(limit)}

@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    from .config import JOBS_DIR, UPLOADS_DIR, RENDERS_DIR
    import shutil
    jdir = JOBS_DIR / job_id
    udir = UPLOADS_DIR / job_id
    rdir = RENDERS_DIR / job_id
    found = False
    for d in [jdir, udir, rdir]:
        if d.exists():
            try:
                shutil.rmtree(str(d))
                found = True
            except Exception as e:
                print(f"[delete] failed to delete {d}: {e}")
    if not found:
        raise HTTPException(404, "Job not found")
    return {"status": "deleted", "job_id": job_id}

@app.post("/api/jobs/{job_id}/mix-custom")
async def mix_custom(
    job_id: str,
    vocal_gain: float = Form(1.0),
    acc_gain: float = Form(0.35),
    master_gain: float = Form(1.0),
):
    from .config import RENDERS_DIR
    import soundfile as sf
    import numpy as np
    rdir = RENDERS_DIR / job_id
    if not rdir.exists():
        raise HTTPException(404, "Job not found")
    # Find vocal and acc wavs - prefer final stems
    vocal_candidates = [rdir / "vocal_final.wav", rdir / "vocal.mp3", rdir / "final.wav"]
    acc_candidates = [rdir / "accompaniment_final.wav", rdir / "accompaniment.mp3"]
    vocal_path = None
    acc_path = None
    for p in vocal_candidates:
        if p.exists():
            vocal_path = p
            break
    for p in acc_candidates:
        if p.exists():
            acc_path = p
            break
    if not vocal_path or not acc_path:
        # try job dir
        from .config import JOBS_DIR
        jdir = JOBS_DIR / job_id
        for p in [jdir / "vocal.wav", jdir / "vocal_mono.wav", jdir / "vocal_stereo.wav"]:
            if p.exists():
                vocal_path = p
                break
    if not vocal_path or not acc_path:
        raise HTTPException(404, "Stems not found for custom mix")

    try:
        # Load
        def load_any(path):
            data, sr = sf.read(str(path))
            if data.ndim == 1:
                data = np.stack([data, data], axis=1)
            return data.astype(np.float32), sr
        vocal, sr_v = load_any(vocal_path)
        acc, sr_a = load_any(acc_path)
        sr = sr_v
        # Align lengths
        final_len = max(len(vocal), len(acc))
        if len(vocal) < final_len:
            pad = np.zeros((final_len - len(vocal), 2), dtype=np.float32)
            vocal = np.concatenate([vocal, pad], axis=0)
        if len(acc) < final_len:
            pad = np.zeros((final_len - len(acc), 2), dtype=np.float32)
            acc = np.concatenate([acc, pad], axis=0)
        # Apply gains
        vocal = vocal * float(vocal_gain)
        acc = acc * float(acc_gain)
        mix = (vocal + acc) * float(master_gain)
        # Prevent clipping
        peak = np.max(np.abs(mix))
        if peak > 0.98:
            mix = mix * (0.98 / peak)
        out_wav = rdir / f"custom_mix_{int(vocal_gain*100)}_{int(acc_gain*100)}_{int(master_gain*100)}.wav"
        sf.write(str(out_wav), mix, sr)
        # Encode mp3
        from .pipeline.extract import encode_mp3
        out_mp3 = out_wav.with_suffix(".mp3")
        try:
            encode_mp3(out_wav, out_mp3)
        except:
            out_mp3 = out_wav
        return {
            "status": "ok",
            "job_id": job_id,
            "gains": {"vocal": vocal_gain, "acc": acc_gain, "master": master_gain},
            "files": {
                "wav": f"/api/jobs/{job_id}/files/{out_wav.name}",
                "mp3": f"/api/jobs/{job_id}/files/{out_mp3.name}" if out_mp3.exists() else f"/api/jobs/{job_id}/files/{out_wav.name}",
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Custom mix failed: {e}")

@app.get("/api/jobs/{job_id}/files/{filename}")
def get_file(job_id: str, filename: str):
    rdir = render_dir(job_id)
    fpath = (rdir / filename).resolve()
    try:
        if not str(fpath).startswith(str(rdir.resolve())):
            raise HTTPException(403, "Forbidden")
    except:
        raise HTTPException(403, "Forbidden")

    if not fpath.exists():
        jdir = job_dir(job_id)
        alt = (jdir / filename).resolve()
        if alt.exists() and str(alt).startswith(str(jdir.resolve())):
            fpath = alt
        else:
            raise HTTPException(404, f"File not found: {filename}")

    mime, _ = mimetypes.guess_type(str(fpath))
    if not mime:
        if fpath.suffix == ".mp3":
            mime = "audio/mpeg"
        elif fpath.suffix == ".wav":
            mime = "audio/wav"
        else:
            mime = "application/octet-stream"
    return FileResponse(str(fpath), media_type=mime, filename=f"{job_id}_{filename}")

@app.get("/test-upload")
def test_upload_page():
    """Simple HTML form upload without JS — works even if JS broken."""
    return HTMLResponse("""
    <html><body style="font-family:sans-serif; max-width:600px; margin:40px auto;">
    <h2>SingSmith Test Upload (no JS)</h2>
    <form action="/api/upload" method="post" enctype="multipart/form-data">
      <input type="file" name="file" accept="audio/*,video/*" required><br><br>
      <label>Style: <select name="style">
        <option>warm-acoustic</option>
        <option>lofi-chill</option>
        <option>piano-ballad</option>
        <option>indie-pop</option>
        <option>cinematic</option>
      </select></label><br><br>
      <button type="submit">Upload</button>
    </form>
    <p>After upload, you get a job_id JSON. Then check <a href="/api/jobs">/api/jobs</a> and /api/jobs/{id}</p>
    </body></html>
    """)

# --- Frontend serving (must be AFTER api routes) ---
def serve_file(path: Path):
    if not path.exists() or not path.is_file():
        return None
    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(str(path), media_type=mime or "application/octet-stream")

@app.get("/")
async def serve_root():
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index), media_type="text/html")
    return {"message": "SingSmith API — frontend not found", "health": "/api/health"}

@app.get("/web/{filename:path}")
async def serve_web_assets(filename: str):
    fpath = WEB_DIR / filename
    # security: prevent traversal
    try:
        fpath = fpath.resolve()
        if not str(fpath).startswith(str(WEB_DIR.resolve())):
            raise HTTPException(403)
    except:
        raise HTTPException(403)
    if fpath.exists() and fpath.is_file():
        return FileResponse(str(fpath))
    raise HTTPException(404, f"Asset not found: {filename}")

@app.get("/{full_path:path}")
async def serve_spa_fallback(full_path: str, request: Request):
    # Don't intercept API
    if full_path.startswith("api/"):
        raise HTTPException(404, "API not found")
    if full_path.startswith("web/"):
        # try web subpath
        sub = full_path[4:]
        fpath = WEB_DIR / sub
        try:
            fpath = fpath.resolve()
            if str(fpath).startswith(str(WEB_DIR.resolve())) and fpath.exists():
                return FileResponse(str(fpath))
        except:
            pass
        raise HTTPException(404)
    # Try to serve as file from web dir (e.g. app.js at root)
    fpath = WEB_DIR / full_path
    try:
        if fpath.exists() and fpath.is_file() and str(fpath.resolve()).startswith(str(WEB_DIR.resolve())):
            return FileResponse(str(fpath))
    except:
        pass
    # Fallback to index.html for SPA
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index), media_type="text/html")
    raise HTTPException(404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
