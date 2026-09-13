from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import effect_engine
from core.lms_calibration import (
    CalibrationApplication,
    ReferenceCalibrationProfile,
    calibration_from_report,
    inspect_lms,
    summarize_calibration_result,
)


LMS_WITH_ARCHIVE = """<?xml version="1.0" encoding="UTF-8"?>
<sequence>
  <channels>
    <channel id="one" name="Private channel name" deviceType="LOR" unit="1" circuit="1" centiseconds="100">
      <effect type="intensity" startCentisecond="0" endCentisecond="30" startIntensity="100" endIntensity="100" />
      <effect type="intensity" startCentisecond="50" endCentisecond="100" startIntensity="100" endIntensity="0" />
    </channel>
    <channel id="two" name="Another private name" deviceType="LOR" unit="1" circuit="2" centiseconds="100">
      <effect type="shimmer" startCentisecond="25" endCentisecond="75" startIntensity="100" endIntensity="0" />
    </channel>
    <channel id="meta" deviceType="Sequence" centiseconds="100" />
  </channels>
  <tracks>
    <track name="Archived copy">
      <channel savedIndex="0" />
      <channel savedIndex="1" />
    </track>
  </tracks>
</sequence>
"""


class LmsCalibrationTests(unittest.TestCase):
    def test_effect_engine_cli_accepts_calibration_options(self) -> None:
        args = effect_engine.parse_args(
            effect_engine.VARIANTS["v27.3"],
            [
                "--lms-calibration-file",
                "reference.lms",
                "--lms-calibration-strength",
                "0.7",
                "--acknowledge-reference-rights",
            ],
        )

        self.assertEqual(args.lms_calibration_file, "reference.lms")
        self.assertEqual(args.lms_calibration_strength, 0.7)
        self.assertTrue(args.acknowledge_reference_rights)

    def test_effect_engine_requires_rights_acknowledgement(self) -> None:
        with self.assertRaises(SystemExit):
            effect_engine.main_for(
                "v27.3",
                [
                    "--lms-calibration-file",
                    "reference.lms",
                    "--no-prompt",
                    "--no-save-settings",
                    "--quiet",
                ],
            )

    def test_inspection_excludes_metadata_and_archived_channel_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reference.lms"
            path.write_text(LMS_WITH_ARCHIVE, encoding="utf-8")
            report = inspect_lms(path)

        self.assertEqual(report.root_channel_count, 3)
        self.assertEqual(report.physical_channel_count, 2)
        self.assertEqual(report.active_effect_channel_count, 2)
        self.assertEqual(report.archived_channel_count, 2)
        self.assertEqual(report.physical_effect_count, 3)
        self.assertEqual(report.effect_type_counts, {"intensity": 2, "shimmer": 1})
        self.assertEqual(report.effect_shape_counts, {"fade_down": 2, "fixed": 1})
        self.assertEqual(report.effect_hints, {"fade": 2, "on": 1, "shimmer": 1})
        self.assertEqual(report.probable_duration_seconds, 1.0)

    def test_runtime_profile_is_aggregate_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "licensed_reference.lms"
            path.write_text(LMS_WITH_ARCHIVE, encoding="utf-8")
            profile = calibration_from_report(inspect_lms(path))

        payload = profile.to_dict()
        serialized = str(payload).lower()
        self.assertNotIn("source_path", payload)
        self.assertNotIn("private channel name", serialized)
        self.assertNotIn("licensed_reference", serialized)
        self.assertEqual(payload["physical_channel_count"], 2)
        self.assertEqual(payload["effect_count"], 3)

    def test_application_changes_effect_mix_duration_and_grid(self) -> None:
        profile = ReferenceCalibrationProfile(
            source_sha256="abc",
            effect_count=100,
            timing_grid_ms=50,
            timing_grid_alignment=1.0,
            median_effect_ms=300,
            p90_effect_ms=750,
            shimmer_share=0.0,
            fade_share=1.0,
            fixed_share=0.0,
            mean_active_fraction=1.0,
        )
        application = CalibrationApplication(profile=profile, strength=1.0)

        effect = application.tune_effect("Shimmer", stable_key="model|cue|123")
        tuned_ranges = [
            application.tune_range(
                123,
                200,
                stable_key=f"model|cue|{index}",
                min_duration_ms=50,
            )
            for index in range(20)
        ]
        start, end = next(item for item in tuned_ranges if item[1] - item[0] == 300)
        summary = summarize_calibration_result(application, [(start, end, effect)])

        self.assertEqual(effect, "Ramp")
        self.assertEqual((start, end), (100, 400))
        self.assertEqual(summary["application"]["shimmer_replaced"], 1)
        self.assertGreater(summary["application"]["duration_adjusted"], 0)
        self.assertLess(summary["application"]["duration_adjusted"], 20)
        self.assertEqual(summary["achieved"]["timing_grid_alignment"], 1.0)
        self.assertEqual(summary["achieved"]["median_effect_ms"], 300)


if __name__ == "__main__":
    unittest.main()
