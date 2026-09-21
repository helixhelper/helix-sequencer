# LMS + real-life video calibration

Helix can use a licensed Light-O-Rama LMS sequence and synchronized footage of
the physical display as one aggregate calibration source. The LMS supplies exact
structural measurements; the video supplies audience-visible brightness,
contrast, motion, and darkness measurements.

The generated JSON stores hashes and section aggregates only. It does not store
source paths, channel names, LMS events, video frames, or event-level timing.

Create a section file:

```json
{
  "sections": [
    {"label": "intro", "start_seconds": 0.0, "end_seconds": 18.5},
    {"label": "verse", "start_seconds": 18.5, "end_seconds": 43.0},
    {"label": "chorus", "start_seconds": 43.0, "end_seconds": 68.0}
  ]
}
```

Build the aggregate profile:

```bash
python -m tools.build_multimodal_reference \
  --lms reference.lms \
  --video physical-show.mp4 \
  --audio song.wav \
  --sections sections.json \
  --video-offset-seconds 0.0 \
  --output nutrocker-reference.json \
  --acknowledge-reference-rights
```

`--video-offset-seconds` is the video time at which audio time zero occurs. A
positive value means the soundtrack begins after the video begins.

Use the bundle through the existing calibrated engine path:

```bash
python main.py --audio song.wav \
  --lms-calibration-file nutrocker-reference.json \
  --acknowledge-reference-rights
```

Runtime calibration chooses the section containing each placement and uses that
section's LMS timing alignment, median duration, and activity target. Video
metrics are used to compare a rendered Helix candidate with the physical show:

```bash
python -m tools.compare_multimodal_reference \
  --calibration nutrocker-reference.json \
  --candidate-video helix-preview.mp4 \
  --output nutrocker-comparison.json
```

The comparison reports section-level brightness, contrast, movement, darkness,
and an overall perceptual-match score. These measurements do not copy reference
choreography into the generated sequence.

The profile also records `video_covered` and `video_coverage_fraction` for each
section. This allows an excerpted physical-show recording to remain useful:
covered sections contribute video targets, partially covered sections disclose
their observed fraction, and unrecorded sections are excluded from visual
comparison instead of being mistaken for black frames.
