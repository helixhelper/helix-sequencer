# Helix Mobile Job API

This is a small LAN or desktop API that lets the Android app submit Helix sequencing jobs.

It is intentionally thin. It shells out to the existing repository CLI instead of duplicating orchestration logic.

## Install

From the repository root:

```bash
python -m pip install fastapi uvicorn pydantic python-multipart
```

`python-multipart` is required for `POST /jobs/upload`.

## Run

```bash
python mobile/helix_api/server.py
```

By default it listens on `0.0.0.0:8765`, so an Android phone on the same Wi-Fi can point to:

```text
http://YOUR_COMPUTER_LAN_IP:8765
```

## Endpoints

```http
GET /health
POST /jobs
POST /jobs/upload
GET /jobs/{job_id}
```

## Path mode

Use `POST /jobs` when the audio file already exists on the runner machine.

## Upload mode

Use `POST /jobs/upload` when the audio file is on the phone or app machine. Send `multipart/form-data` with:

```text
audio=<file>
profile=master
style=vendor_like
layout=aaatest
```

Uploaded songs are saved under:

```text
outputs/mobile/uploads/
```

The upload limit defaults to 250 MB and can be changed with the `HELIX_MOBILE_MAX_UPLOAD_BYTES` environment variable.

## Safety behavior

- Path mode only starts jobs for audio paths that exist on the runner machine.
- Upload mode only accepts common audio extensions: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`.
- Uses a fixed output root under `outputs/mobile` by default.
- Keeps job state in memory for the MVP.
- Does not expose arbitrary shell command entry.
