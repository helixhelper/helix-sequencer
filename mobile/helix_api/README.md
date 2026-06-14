# Helix Mobile Job API

This is a small LAN/desktop API that lets the Android app submit Helix sequencing jobs.

It is intentionally thin. It shells out to the existing repository CLI instead of duplicating orchestration logic.

## Install

From the repository root:

```bash
python -m pip install fastapi uvicorn pydantic
```

## Run

```bash
python mobile/helix_api/server.py
```

By default it listens on `0.0.0.0:8765`, so an Android phone on the same Wi-Fi can point to:

```text
http://YOUR_COMPUTER_LAN_IP:8765
```

Set that on Android as:

```bash
HELIX_API_URL=http://YOUR_COMPUTER_LAN_IP:8765
```

## Endpoints

```http
GET /health
POST /jobs
GET /jobs/{job_id}
```

## Safety behavior

- Only starts jobs for audio paths that exist on the runner machine.
- Uses a fixed output root under `outputs/mobile` by default.
- Keeps job state in memory for the MVP.
- Does not expose arbitrary shell command entry.
