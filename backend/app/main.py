# main.py
import os
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import uuid
from pathlib import Path
from rq import Queue
from redis import Redis

# Local import (verify_lib in same folder)
from verify_lib import find_emails_in_text, classify_email

app = FastAPI()

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_conn = Redis.from_url(REDIS_URL)
q = Queue(connection=redis_conn)

UPLOAD_DIR = Path('uploads')
UPLOAD_DIR.mkdir(exist_ok=True)

@app.post('/upload')
async def upload_file(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    out_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    with open(out_path, 'wb') as f:
        content = await file.read()
        f.write(content)
    # enqueue by function name; worker will import worker.process_file
    q.enqueue('worker.process_file', str(out_path), job_id)
    return JSONResponse({'job_id': job_id, 'filename': file.filename})

@app.get('/status/{job_id}')
def status(job_id: str):
    # Simple placeholder: extend later with DB tracking
    return {'job_id': job_id, 'status': 'queued_or_running'}
