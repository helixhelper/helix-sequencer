# Helix Mobile

This directory contains the first mobile path for Helix.

## Pieces

- `android_kivy/` - Android-friendly Kivy app.
- `helix_api/` - LAN or desktop FastAPI runner that wraps the existing CLI.

## MVP flows

### Path mode

```text
Android phone
  -> Helix Kivy app
  -> POST /jobs on runner
  -> python main.py with selected profile and audio path
  -> outputs/mobile/job_id/
```

### Upload mode

```text
Android phone
  -> Helix Kivy app
  -> POST /jobs/upload with audio file
  -> runner saves upload under outputs/mobile/uploads/
  -> python main.py with selected profile and uploaded audio
  -> outputs/mobile/job_id/
```

## Current limitations

- The Android app still uses manual audio path entry for now.
- Upload mode works for a normal local file path; native Android file picker support is the next slice.
- Job state is in memory.
- Artifact download endpoints are not added yet.

## Recommended next slice

Add a native Android file picker in the Kivy app, then add artifact download endpoints for sequence files, preview videos, xModels, logs, and run manifests.
