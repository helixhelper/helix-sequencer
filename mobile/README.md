# Helix Mobile

This directory contains the first mobile path for Helix.

## Pieces

- `android_kivy/` - Android-friendly Kivy app.
- `helix_api/` - LAN/desktop FastAPI runner that wraps the existing CLI.

## MVP flow

```text
Android phone
  -> Helix Kivy app
  -> POST /jobs on desktop/cloud runner
  -> python main.py --profile ... -- --audio ...
  -> outputs/mobile/<job_id>/
```

## Current limitations

- The Android app uses manual audio path entry for now.
- The server expects the audio path to exist on the runner machine.
- Job state is in memory.
- Artifact download endpoints are not added yet.

## Recommended next slice

Add an upload endpoint so Android can send an audio file directly to the runner:

```http
POST /jobs/upload
multipart/form-data: audio file + profile + style + layout
```

Then add a native Android file picker in the Kivy app.
