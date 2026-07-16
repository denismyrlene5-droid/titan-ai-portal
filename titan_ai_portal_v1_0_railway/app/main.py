from __future__ import annotations
import json
import os
import shutil
import threading
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import SESSION_SECRET, is_logged_in, verify_password
from .db import create_job as db_create_job, get_job, init_db, list_jobs, update_job
from .vision import auto_detect_board, perspective_matrix, robust_hsv_color, warp_board
from .worker import create_calibration_frame, download_youtube, process_video

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE / "data"))
JOBS = DATA_DIR / "jobs"
JOBS.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = int(os.environ.get("MAX_UPLOAD_MB", "500")) * 1024 * 1024

app = FastAPI(title="Titan AI Portal")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=BASE / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "app" / "templates")
init_db()

def require_login(request: Request):
    if not is_logged_in(request):
        raise HTTPException(401, "Login required.")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, password: str = Form(...)):
    if not verify_password(password):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Wrong password."}, status_code=401
        )
    request.session["admin"] = True
    return RedirectResponse("/", status_code=303)

@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "jobs": list_jobs(12),
    })

@app.post("/api/jobs")
async def create_job(
    request: Request,
    video: UploadFile | None = File(None),
    youtube_url: str | None = Form(None),
):
    require_login(request)
    if not video and not youtube_url:
        raise HTTPException(400, "Upload a video or paste a YouTube URL.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS / job_id
    job_dir.mkdir()

    source_type = "upload" if video else "youtube"
    source_name = video.filename if video else youtube_url
    db_create_job(job_id, source_type, source_name or "")

    try:
        if video:
            suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
            video_path = job_dir / f"source{suffix}"
            total = 0
            with video_path.open("wb") as f:
                while chunk := await video.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD:
                        raise HTTPException(413, f"Upload is larger than {MAX_UPLOAD // 1024 // 1024} MB.")
                    f.write(chunk)
        else:
            update_job(job_id, "downloading", 0, "Downloading video")
            video_path = download_youtube(youtube_url, job_dir)

        (job_dir / "meta.json").write_text(json.dumps({
            "video_path": str(video_path),
            "youtube_url": youtube_url,
        }), encoding="utf-8")

        calibration_path = create_calibration_frame(video_path, job_dir)
        frame = cv2.imread(str(calibration_path))
        detected = auto_detect_board(frame) if frame is not None else None
        auto_points = detected.tolist() if detected is not None else None
        (job_dir / "auto_corners.json").write_text(json.dumps(auto_points), encoding="utf-8")

        update_job(
            job_id, "calibration", 0,
            "Board detected automatically. Confirm the corners and select both piece colours."
            if auto_points else
            "Select the board corners and both piece colours."
        )
        return {"job_id": job_id, "auto_corners": auto_points}
    except HTTPException:
        raise
    except Exception as exc:
        update_job(job_id, "error", 0, str(exc))
        raise HTTPException(500, str(exc))

@app.get("/api/jobs/{job_id}")
def job_status(request: Request, job_id: str):
    require_login(request)
    payload = get_job(job_id)
    if not payload:
        raise HTTPException(404, "Job not found.")
    return payload

@app.get("/api/jobs/{job_id}/calibration-frame")
def calibration_frame(request: Request, job_id: str):
    require_login(request)
    path = JOBS / job_id / "calibration.jpg"
    if not path.exists():
        raise HTTPException(404, "Calibration frame not found.")
    return FileResponse(path)

@app.get("/api/jobs/{job_id}/auto-corners")
def auto_corners(request: Request, job_id: str):
    require_login(request)
    path = JOBS / job_id / "auto_corners.json"
    if not path.exists():
        return {"corners": None}
    return {"corners": json.loads(path.read_text())}

@app.post("/api/jobs/{job_id}/calibrate")
async def calibrate(request: Request, job_id: str):
    require_login(request)
    job_dir = JOBS / job_id
    if not job_dir.exists():
        raise HTTPException(404, "Job not found.")

    data = await request.json()
    points = data.get("points", [])
    if len(points) != 6:
        raise HTTPException(400, "Exactly 6 points are required.")

    frame = cv2.imread(str(job_dir / "calibration.jpg"))
    if frame is None:
        raise HTTPException(500, "Could not load calibration frame.")

    corners = np.array(points[:4], dtype=np.float32)
    matrix = perspective_matrix(corners)
    warped = warp_board(frame, matrix)

    samples = np.array(points[4:6], dtype=np.float32).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(samples, matrix).reshape(-1, 2)

    colors = []
    for x, y in transformed:
        x, y = int(x), int(y)
        patch = warped[max(0,y-18):y+18, max(0,x-18):x+18]
        if patch.size == 0:
            raise HTTPException(400, "A colour sample was outside the board.")
        colors.append(robust_hsv_color(patch).tolist())

    calibration = {
        "corners": corners.tolist(),
        "color_a": colors[0],
        "color_b": colors[1],
    }
    (job_dir / "calibration.json").write_text(json.dumps(calibration), encoding="utf-8")
    update_job(job_id, "queued", 1, "Analysis queued.")

    def runner():
        try:
            process_video(job_dir, calibration)
        except Exception as exc:
            update_job(job_id, "error", 0, str(exc))

    threading.Thread(target=runner, daemon=True).start()
    return {"ok": True}

@app.get("/api/jobs/{job_id}/download")
def download_result(request: Request, job_id: str):
    require_login(request)
    path = JOBS / job_id / "titan_analysis.zip"
    if not path.exists():
        raise HTTPException(404, "Result is not ready.")
    return FileResponse(path, filename=f"titan_analysis_{job_id}.zip")

@app.delete("/api/jobs/{job_id}")
def delete_job(request: Request, job_id: str):
    require_login(request)
    job_dir = JOBS / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    return {"ok": True}

@app.get("/health")
def health():
    return {"status": "ok"}
