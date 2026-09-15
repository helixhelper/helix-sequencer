from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import engine_profiles
from tools import build_outcome_preview_manifest as preview_manifest


class BuildOutcomePreviewManifestTests(unittest.TestCase):
    def _write_bundle(self, root: Path) -> tuple[Path, Path, Path]:
        version = engine_profiles.active_profile().version
        stem = "helix-outcome-preview"
        mp4 = root / f"{stem},{version}.mp4"
        xsq = root / f"{stem},{version}.xsq"
        report = root / f"{stem},{version}.report.json"
        mp4.write_bytes(b"mp4" * 500)
        xsq.write_bytes(b"xsq" * 500)
        report.write_text(
            json.dumps(
                {
                    "quality": {
                        "score": 95.0,
                        "grade": "A",
                        "top_show_benchmark": {"score": 92.8, "grade": "A-"},
                    }
                }
            ).ljust(1500),
            encoding="utf-8",
        )
        return mp4, xsq, report

    def test_build_manifest_validates_active_profile_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp4, xsq, _ = self._write_bundle(root)
            expected_mp4_hash = preview_manifest.sha256_file(mp4)
            expected_xsq_hash = preview_manifest.sha256_file(xsq)
            with mock.patch.object(
                preview_manifest,
                "_read_video_metadata",
                return_value={"duration": 30.0, "fps": 10.0},
            ), mock.patch.object(preview_manifest, "_validate_audio_stream"):
                manifest = preview_manifest.build_manifest(
                    root,
                    benchmark_duration_seconds=30,
                    event="pull_request",
                    commit="abc123",
                )

        self.assertEqual(manifest["profile_id"], engine_profiles.ACTIVE_PROFILE_ID)
        self.assertEqual(manifest["profile_version"], engine_profiles.ACTIVE_STYLE_VERSION)
        self.assertEqual(manifest["quality_score"], 95.0)
        self.assertEqual(manifest["top_show_grade"], "A-")
        self.assertTrue(manifest["audio_stream_validated"])
        self.assertEqual(manifest["preview_mp4_sha256"], expected_mp4_hash)
        self.assertEqual(manifest["sequence_xsq_sha256"], expected_xsq_hash)

    def test_render_summary_includes_downloadable_artifact_identity(self) -> None:
        manifest = {
            "commit": "abc123",
            "profile_id": "master",
            "profile_version": "v27.3",
            "benchmark_duration_seconds": 30.0,
            "preview_mp4": "out/helix-outcome-preview,v27.3.mp4",
            "quality_score": 95.0,
            "quality_grade": "A",
            "top_show_score": 92.8,
            "top_show_grade": "A-",
            "preview_mp4_sha256": "f" * 64,
        }

        summary = preview_manifest.render_summary(manifest)

        self.assertIn("helix-outcome-preview,v27.3.mp4", summary)
        self.assertIn("`master` (`v27.3`)", summary)
        self.assertIn("MP4 SHA-256", summary)

    def test_missing_preview_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(preview_manifest.PreviewArtifactError):
                preview_manifest.build_manifest(
                    Path(tmp),
                    benchmark_duration_seconds=30,
                    event="local",
                    commit="local",
                )


if __name__ == "__main__":
    unittest.main()
