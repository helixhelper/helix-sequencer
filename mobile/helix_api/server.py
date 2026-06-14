"""Small FastAPI job server for Helix Mobile.

Run from the repository root:

    python mobile/helix_api/server.py

Then point the Android app at:

    HELIX_API_URL=http://<desktop-lan-ip>:8765
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
import uvicorn


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "mobile"
DEFAULT_UPLOAD_ROOT = DEFAULT_OUTPUT_ROOT / "uploads"
ALLOWED_PROFILES = {"master", "v27.3", "v8.1", "beta", "drummer"}
ALLOWED_STYLES = {"vendor_like", "beat_heavy", "lyrics_heavy", "drummer_focused", "gentle_preview"}
ALLOWED_LAYOUTS = {"aaatest", "helixia", "gp_legacy", "snowman_band"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}
DEFAULT_ARTIFACTS = ["sequence.xsq", "preview.mp4", "run_manifest.json", "helix.log"]
MAX_UPLOAD_BYTES = int(os.environ.get("HELIX_MOBILE_MAX_UPLOAD_BYTES", str(250 * 1024 * 1024)))


class JobRequest(BaseModel):
    audio_path: str = Field(min_length=1)
    profile: str = "master"
    style: str = "vendor_like"
    layout: str = "aaatest"


class JobStatus(BaseModel):
    job_id: str
    status: str
    message: str = ""
    artifacts: List[str] = Field(default_factory=list)
    output_dir: Optional[str] = None


@dataclass
class JobRecord:
    job_id: str
    request: JobRequest
    status: str = "queued"
    message: str = ""
    artifacts: List[str] = field(default_factory=lambda: list(DEFAULT_ARTIFACTS))
    output_dir: Optional[str] = None
    return_code: Optional[int] = None

    def to_status(self) -> JobStatus:
        return JobStatus(
            job_id=self.job_id,
            status=self.status,
            message=self.message,
            artifacts=self.artifacts,
            output_dir=self.output_dir,
        )


app = FastAPI(title="Helix Mobile Job API", version="0.2.0")
_jobs: Dict[str, JobRecord] = {}
_lock = threading.Lock()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "repo_root": str(REPO_ROOT)}


@app.post("/jobs", response_model=JobStatus)
def create_job(request: JobRequest) -> JobStatus:
    _validate_request(request)
    return _enqueue_job(request, message="Queued by Helix Mobile.")


@app.post("/jobs/upload", response_model=JobStatus)
def create_uploaded_job(
    audio: UploadFile = File(...),
    profile: str = Form("master"),
    style: str = Form("vendor_like"),
    layout: str = Form("aaatest"),
) -> JobStatus:
    _validate_options(profile=profile, style=style, layout=layout)
    upload_path = _save_upload(audio)
    request = JobRequest(audio_path=str(upload_path), profile=profile, style=style, layout=layout)
    return _enqueue_job(request, message=f"Uploaded {upload_path.name} and queued Helix job.")


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str) -> JobStatus:
    with _lock:
        record = _jobs.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return record.to_status()


def _enqueue_job(request: JobRequest, *, message: str) -> JobStatus:
    job_id = f"helix-mobile-{time.strftime('%Y%m%d-%H%M%S')}"
    output_dir = DEFAULT_OUTPUT_ROOT / job_id
    record = JobRecord(
        job_id=job_id,
        request=request,
        output_dir=str(output_dir),
        message=message,
    )
    with _lock:
        _jobs[job_id] = record

    thread = threading.Thread(target=_run_job, args=(record,), daemon=True)
    thread.start()
    return record.to_status()


def _validate_request(request: JobRequest) -> None:
    audio = Path(request.audio_path).expanduser()
    if not audio.exists():
        raise HTTPException(status_code=400, detail=f"Audio path does not exist on runner: {audio}")
    _validate_options(profile=request.profile, style=request.style, layout=request.layout)


def _validate_options(*, profile: str, style: str, layout: str) -> None:
    if profile not in ALLOWED_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unsupported profile: {profile}")
    if style not in ALLOWED_STYLES:
        raise HTTPException(status_code=400, detail=f"Unsupported style: {style}")
    if layout not in ALLOWED_LAYOUTS:
        raise HTTPException(status_code=400, detail=f"Unsupported layout: {layout}")


def _save_upload(audio: UploadFile) -> Path:
    raw_name = Path(audio.filename or "audio.wav").name
    suffix = Path(raw_name).suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported audio extension: {suffix or '(none)'}")

    DEFAULT_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    upload_name = f"{time.strftime('%Y%m%d-%H%M%S')}-{raw_name}"
    upload_path = DEFAULT_UPLOAD_ROOT / upload_name

    bytes_written = 0
    with upload_path.open("wb") as out_file:
        while True:
            chunk = audio.file.read(1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                out_file.close()
                upload_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Audio upload is too large")
            out_file.write(chunk)

    if bytes_written == 0:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded audio file was empty")
    return upload_path


def _run_job(record: JobRecord) -> None:
    _set_record(record, status="running", message="Running Helix CLI...")
    output_dir = Path(record.output_dir or DEFAULT_OUTPUT_ROOT / record.job_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "main.py",
        "--profile",
        record.request.profile,
        "--",
        "--audio",
        str(Path(record.request.audio_path).expanduser()),
        "--output-root",
        str(output_dir),
    ]

    command_file = output_dir / "mobile_command.txt"
    command_file.write_text(" ".join(command) + "\n", encoding="utf-8")

    log_file = output_dir / "mobile_api.log"
    env = os.environ.copy()
    env["HELIX_MOBILE_STYLE"] = record.request.style
    env["HELIX_MOBILE_LAYOUT"] = record.request.layout

    try:
        with log_file.open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                env=env,
            )
        record.return_code = completed.returncode
        if completed.returncode == 0:
            _set_record(
                record,
                status="complete",
                message=f"Helix finished successfully. Log: {log_file}",
            )
        else:
            _set_record(
                record,
                status="failed",
                message=f"Helix exited with code {completed.returncode}. Log: {log_file}",
            )
    except Exception as exc:  # pragma: no cover - visible through API.
        _set_record(record, status="failed", message=f"Runner crashed: {exc}")


def _set_record(record: JobRecord, *, status: str, message: str) -> None:
    with _lock:
        record.status = status
        record.message = message
        _jobs[record.job_id] = record


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
