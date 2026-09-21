from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.lms_calibration import CalibrationApplication, load_lms_calibration
from core.multimodal_reference import (
    build_multimodal_reference,
    compare_candidate_video,
    load_section_specs,
)


LMS = """<?xml version="1.0" encoding="UTF-8"?>
<sequence>
  <channels>
    <channel id="one" deviceType="LOR" unit="1" circuit="1" centiseconds="200">
      <effect type="intensity" startCentisecond="0" endCentisecond="10" startIntensity="100" endIntensity="100" />
      <effect type="intensity" startCentisecond="100" endCentisecond="160" startIntensity="100" endIntensity="0" />
    </channel>
  </channels>
</sequence>
"""


class MultimodalReferenceTests(unittest.TestCase):
    def _sources(self, root: Path) -> tuple[Path, Path, Path, Path]:
        lms = root / "reference.lms"
        video = root / "reference.mp4"
        audio = root / "reference.wav"
        sections = root / "sections.json"
        lms.write_text(LMS, encoding="utf-8")
        video.write_bytes(b"video fixture")
        audio.write_bytes(b"audio fixture")
        sections.write_text(
            json.dumps(
                {
                    "sections": [
                        {"label": "intro", "start_seconds": 0.0, "end_seconds": 1.0},
                        {"label": "chorus", "start_seconds": 1.0, "end_seconds": 2.0},
                    ]
                }
            ),
            encoding="utf-8",
        )
        return lms, video, audio, sections

    def test_section_spec_rejects_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sections.json"
            path.write_text(
                json.dumps(
                    [
                        {"label": "a", "start_seconds": 0, "end_seconds": 2},
                        {"label": "b", "start_seconds": 1, "end_seconds": 3},
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_section_specs(path)

    def test_builder_requires_reference_rights_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lms, video, audio, sections = self._sources(Path(tmp))
            with self.assertRaises(PermissionError):
                build_multimodal_reference(
                    lms_path=lms,
                    video_path=video,
                    audio_path=audio,
                    section_spec_path=sections,
                )

    def test_bundle_is_aggregate_only_and_loadable_by_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lms, video, audio, sections = self._sources(root)
            visual = {
                "intro": {
                    "video_mean_luma": 0.1,
                    "video_contrast": 0.2,
                    "video_motion": 0.05,
                    "video_dark_fraction": 0.8,
                },
                "chorus": {
                    "video_mean_luma": 0.7,
                    "video_contrast": 0.4,
                    "video_motion": 0.3,
                    "video_dark_fraction": 0.1,
                },
            }
            with mock.patch("core.multimodal_reference._video_metrics", return_value=visual):
                bundle = build_multimodal_reference(
                    lms_path=lms,
                    video_path=video,
                    audio_path=audio,
                    section_spec_path=sections,
                    video_offset_seconds=0.25,
                    acknowledge_reference_rights=True,
                )
            output = root / "calibration.json"
            output.write_text(json.dumps(bundle), encoding="utf-8")
            profile = load_lms_calibration(output)

            serialized = json.dumps(bundle).lower()
            self.assertEqual(bundle["privacy_mode"], "aggregate_only")
            self.assertNotIn(str(lms).lower(), serialized)
            self.assertNotIn(str(video).lower(), serialized)
            self.assertNotIn(str(audio).lower(), serialized)
            self.assertEqual(len(profile.sections), 2)
            self.assertEqual(profile.sections[0].label, "intro")
            self.assertEqual(profile.sections[1].video_motion, 0.3)
            self.assertTrue(profile.audio_sha256)
            self.assertTrue(profile.video_sha256)

    def test_runtime_uses_section_specific_duration_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lms, video, audio, sections = self._sources(root)
            visual = {
                label: {
                    "video_mean_luma": 0.0,
                    "video_contrast": 0.0,
                    "video_motion": 0.0,
                    "video_dark_fraction": 0.0,
                }
                for label in ("intro", "chorus")
            }
            with mock.patch("core.multimodal_reference._video_metrics", return_value=visual):
                bundle = build_multimodal_reference(
                    lms_path=lms,
                    video_path=video,
                    audio_path=audio,
                    section_spec_path=sections,
                    acknowledge_reference_rights=True,
                )
            profile = load_lms_calibration(self._write_bundle(root, bundle))
            application = CalibrationApplication(profile=profile, strength=1.0)
            for index in range(80):
                application.tune_range(
                    1100,
                    1150,
                    stable_key=f"chorus-{index}",
                    min_duration_ms=10,
                )
            self.assertEqual(application.section_decisions["chorus"], 80)
            self.assertGreater(application.duration_adjusted, 0)

    def test_candidate_video_comparison_scores_each_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lms, video, audio, sections = self._sources(root)
            reference_metrics = {
                "intro": {
                    "video_mean_luma": 0.1,
                    "video_contrast": 0.2,
                    "video_motion": 0.05,
                    "video_dark_fraction": 0.8,
                },
                "chorus": {
                    "video_mean_luma": 0.7,
                    "video_contrast": 0.4,
                    "video_motion": 0.3,
                    "video_dark_fraction": 0.1,
                },
            }
            with mock.patch("core.multimodal_reference._video_metrics", return_value=reference_metrics):
                bundle = build_multimodal_reference(
                    lms_path=lms,
                    video_path=video,
                    audio_path=audio,
                    section_spec_path=sections,
                    acknowledge_reference_rights=True,
                )
            profile = load_lms_calibration(self._write_bundle(root, bundle))
            candidate = root / "candidate.mp4"
            candidate.write_bytes(b"candidate video")
            with mock.patch("core.multimodal_reference._video_metrics", return_value=reference_metrics):
                comparison = compare_candidate_video(
                    candidate_video_path=candidate,
                    profile=profile,
                )

            self.assertEqual(comparison["overall_score"], 100.0)
            self.assertEqual([item["label"] for item in comparison["sections"]], ["intro", "chorus"])
            self.assertNotIn(str(candidate), json.dumps(comparison))

    @staticmethod
    def _write_bundle(root: Path, bundle: dict[str, object]) -> Path:
        path = root / "bundle.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
