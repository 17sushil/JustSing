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

@app.post("/api/jobs/{job_id}/mix-custom")
async def mix_custom(
    job_id: str,
    vocal_gain: float = Form(1.0),
    acc_gain: float = Form(0.35),
    master_gain: float = Form(1.0),
):
    """v1.6: Mix with user-controlled gains, return new mixed file"""
    st = read_status(job_id)
    if st.get("status") == "not_found":
        raise HTTPException(404, "Job not found")
    if st.get("status") != "completed":
        raise HTTPException(400, f"Job not completed yet, status={st.get('status')}")

    # Clamp gains
    vocal_gain = float(max(0.0, min(3.0, vocal_gain)))
    acc_gain = float(max(0.0, min(3.0, acc_gain)))
    master_gain = float(max(0.0, min(3.0, master_gain)))

    rdir = render_dir(job_id)
    # Find vocal and acc files
    vocal_path = rdir / "vocal_final.wav"
    if not vocal_path.exists():
        vocal_path = rdir / "vocal_original_untouched.wav"
    acc_path = rdir / "accompaniment_final.wav"
    
    if not vocal_path.exists() or not acc_path.exists():
        # Try alternative locations
        jdir = job_dir(job_id)
        if not vocal_path.exists():
            vocal_path = jdir / "vocal_final.wav"
        if not acc_path.exists():
            acc_path = jdir / "accompaniment_final.wav"
    
    if not vocal_path.exists():
        raise HTTPException(404, f"Vocal file not found for job {job_id}")
    if not acc_path.exists():
        raise HTTPException(404, f"Accompaniment file not found for job {job_id}")

    # Output path with gains in name
    out_name = f"custom_mix_v{vocal_gain:.2f}_a{acc_gain:.2f}_m{master_gain:.2f}.wav"
    out_path = rdir / out_name

    try:
        from .pipeline.mix import mix_with_custom_gains
        mix_with_custom_gains(vocal_path, acc_path, out_path, vocal_gain=vocal_gain, acc_gain=acc_gain, master_gain=master_gain)
        
        # Also create mp3 version
        mp3_name = out_name.replace(".wav", ".mp3")
        mp3_path = rdir / mp3_name
        try:
            from .pipeline.master import master_audio
            # Use master to convert to mp3? Actually master does loudnorm, we can just use ffmpeg
            import subprocess
            from .config import FFMPEG_BIN
            subprocess.run([FFMPEG_BIN, "-y", "-i", str(out_path), "-b:a", "320k", str(mp3_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception as e:
            print(f"[mix-custom] mp3 conversion failed {e}, using wav only")
            mp3_path = out_path

        # Return file URLs
        base_url = f"/api/jobs/{job_id}/files"
        return {
            "job_id": job_id,
            "vocal_gain": vocal_gain,
            "acc_gain": acc_gain,
            "master_gain": master_gain,
            "files": {
                "wav": f"{base_url}/{out_name}",
                "mp3": f"{base_url}/{mp3_name}",
                "custom_wav": f"{base_url}/{out_name}",
                "custom_mp3": f"{base_url}/{mp3_name}",
            },
            "message": f"Mixed with vocal {vocal_gain:.2f}, acc {acc_gain:.2f}, master {master_gain:.2f}"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Mix failed: {e}")

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
