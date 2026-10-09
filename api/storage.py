import json
import uuid
import time
from pathlib import Path
from .config import JOBS_DIR, UPLOADS_DIR, RENDERS_DIR

def new_job_id():
    return uuid.uuid4().hex[:12]

def job_dir(job_id: str) -> Path:
    p = JOBS_DIR / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p

def upload_path(job_id: str, filename: str) -> Path:
    d = UPLOADS_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d / filename

def render_dir(job_id: str) -> Path:
    d = RENDERS_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def write_status(job_id: str, data: dict):
    data["updated_at"] = time.time()
    (job_dir(job_id) / "status.json").write_text(json.dumps(data, indent=2))

def read_status(job_id: str) -> dict:
    f = job_dir(job_id) / "status.json"
    if not f.exists():
        return {"job_id": job_id, "status": "not_found"}
    return json.loads(f.read_text())

def list_jobs(limit=20):
    jobs = []
    for p in sorted(JOBS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        if p.is_dir():
            try:
                jobs.append(read_status(p.name))
            except:
                pass
    return jobs
