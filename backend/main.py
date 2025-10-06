import os
import shutil
import uuid
import argparse
import threading
from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import email_verifier

app = FastAPI(title="Email Verifier API", version="1.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "Uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

PROGRESS = {}

def run_verifier(job_id, input_path, output_path, premium, provider, api_key):
    try:
        args = argparse.Namespace(
            input=input_path,
            output=output_path,
            provider=provider,
            key=api_key,
            workers=5,
            premium=premium,
            job_id=job_id,
            progress_store=PROGRESS,
        )
        email_verifier.main(args)
        PROGRESS[job_id]["status"] = "done"
    except Exception as e:
        PROGRESS[job_id]["status"] = "error"
        PROGRESS[job_id]["error"] = str(e)
        with open(os.path.join(OUTPUT_DIR, f"{job_id}_error.log"), "w") as f:
            f.write(str(e))

@app.get("/")
async def root():
    return {"message": "Welcome to Email Verifier API! Go to /docs for interactive docs."}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    premium: bool = Query(False),
    provider: str = Query(None),
    key: str = Query(None),
):
    try:
        job_id = str(uuid.uuid4())
        job_upload_dir = os.path.join(UPLOAD_DIR, job_id)
        job_output_dir = os.path.join(OUTPUT_DIR, job_id)
        os.makedirs(job_upload_dir, exist_ok=True)
        os.makedirs(job_output_dir, exist_ok=True)
        input_path = os.path.join(job_upload_dir, file.filename)
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        PROGRESS[job_id] = {"done": 0, "total": 0, "status": "running", "error": None}
        thread = threading.Thread(
            target=run_verifier,
            args=(job_id, input_path, job_output_dir, premium, provider, key),
        )
        thread.start()
        return {"job_id": job_id, "status": "started"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/progress/{job_id}")
async def check_progress(job_id: str):
    if job_id not in PROGRESS:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    prog = PROGRESS[job_id]
    total = prog.get("total", 0)
    done = prog.get("done", 0)
    percent = round((done / total) * 100, 2) if total > 0 else 0
    return {
        "job_id": job_id,
        "done": done,
        "total": total,
        "percent": percent,
        "status": prog.get("status"),
        "error": prog.get("error")
    }

@app.get("/download/{job_id}")
async def download_result(job_id: str):
    job_output_dir = os.path.join(OUTPUT_DIR, job_id)
    if not os.path.exists(job_output_dir):
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    files = os.listdir(job_output_dir)
    if not files:
        return JSONResponse(status_code=404, content={"error": "No result file found"})
    result_file = os.path.join(job_output_dir, files[0])
    return FileResponse(result_file, filename=os.path.basename(result_file))