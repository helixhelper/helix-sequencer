# Helix Android MVP

**Audio in. Lights out. Helix Mobile.**

This folder is a first Android-friendly Helix control app. It is intentionally a thin mobile front end instead of a full phone port of the sequencing engine.

The MVP lets a user:

1. choose an audio file path,
2. choose a Helix profile,
3. choose a sequencing style,
4. submit a job to a Helix API endpoint, or run in offline mock mode,
5. view job status and expected artifact names.

## Why this shape

Helix's core engine is Python-heavy and can depend on audio analysis, xLights files, preview rendering, and filesystem outputs. Android should start as a controller/preview surface while the real engine runs on desktop, a LAN machine, or a small cloud box.

## Layout

```text
mobile/android_kivy/
  main.py            # Kivy UI entrypoint
  helix_client.py    # HTTP/mock job client
  buildozer.spec     # Android packaging config
  README.md          # this file
```

## Desktop test

From the repository root:

```bash
python -m pip install kivy requests
python mobile/android_kivy/main.py
```

Offline mock mode is enabled by default when no `HELIX_API_URL` is set.

## Point it at a real Helix API

```bash
export HELIX_API_URL=http://192.168.1.50:8765
python mobile/android_kivy/main.py
```

Expected API shape:

```http
POST /jobs
Content-Type: application/json

{
  "audio_path": "/path/or/android/content/ref/song.mp3",
  "profile": "master",
  "style": "vendor_like",
  "layout": "aaatest"
}
```

Response:

```json
{
  "job_id": "helix-20260614-123456",
  "status": "queued",
  "artifacts": ["sequence.xsq", "preview.mp4", "run_manifest.json"]
}
```

Status endpoint:

```http
GET /jobs/{job_id}
```

## Build APK/AAB with Buildozer

Buildozer is usually run on Linux or WSL:

```bash
cd mobile/android_kivy
python -m pip install buildozer
buildozer android debug
```

The generated APK appears under `bin/`.

## Next slices

- Add a tiny FastAPI job server that wraps `python main.py --profile ...`.
- Add Android file picker integration instead of manual path text entry.
- Add drummer model/submodel preview screen.
- Add artifacts download screen.
- Add run manifest viewer for `outputs/beta/.../run_manifest.json`.
