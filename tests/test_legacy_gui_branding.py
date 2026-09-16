from __future__ import annotations

import inspect
from pathlib import Path

from gui_launcher import HelixGui
from legacy_gui_branding import (
    AUTHOR_SUPPORT_URL,
    ICON_FILENAME,
    LEGAL_FILENAMES,
    LOGO_FILENAME,
    MASCOT_FILENAME,
    SUPPORT_DONATE_URL,
    instructions_text,
    legal_text,
    progress_stage_for_line,
)


ROOT = Path(__file__).resolve().parents[1]


def _resolver(root: Path):
    return lambda name: root / name


def test_legacy_support_destinations_are_preserved() -> None:
    assert AUTHOR_SUPPORT_URL == "https://paypal.me/ryankorkowski"
    assert SUPPORT_DONATE_URL == "https://www.paypal.com/donate/?hosted_button_id=BB6366BT755H6"


def test_first_version_brand_assets_remain_available() -> None:
    assert (ROOT / MASCOT_FILENAME).is_file()
    assert (ROOT / LOGO_FILENAME).is_file()
    assert (ROOT / ICON_FILENAME).is_file()


def test_instructions_button_uses_bundled_instructions(tmp_path: Path) -> None:
    instructions = tmp_path / "SEQUENCER_INSTRUCTIONS.txt"
    instructions.write_text("HELIX TEST INSTRUCTIONS", encoding="utf-8")

    assert instructions_text(_resolver(tmp_path)) == "HELIX TEST INSTRUCTIONS"


def test_legal_button_combines_bundled_project_notices(tmp_path: Path) -> None:
    for index, name in enumerate(LEGAL_FILENAMES, start=1):
        (tmp_path / name).write_text(f"legal section {index}", encoding="utf-8")

    text = legal_text(_resolver(tmp_path))

    for index, name in enumerate(LEGAL_FILENAMES, start=1):
        assert name in text
        assert f"legal section {index}" in text


def test_progress_report_turns_engine_output_into_readable_stages() -> None:
    assert progress_stage_for_line("Starting beta sequence build.") == "Starting sequence build"
    assert progress_stage_for_line("BeatGrid analysis: 128 BPM") == "Analyzing audio and musical structure"
    assert progress_stage_for_line("snare placement request accepted") == "Building the drummer performance"
    assert progress_stage_for_line("polish variant score 91.4") == "Evaluating and polishing variants"
    assert progress_stage_for_line("writing XSQ to show folder") == "Writing xLights show files"
    assert progress_stage_for_line("Beta run complete.") == "Completed"
    assert progress_stage_for_line("SUCCESS: Run completed. Manifest: C:/show/run_manifest.json") == "Completed"
    assert progress_stage_for_line("ERROR: output contract failed") == "Problem encountered"


def test_current_beta_gui_installs_legacy_branding_panel() -> None:
    source = inspect.getsource(HelixGui.__init__)
    assert "install_legacy_branding" in source


def test_packaged_beta_includes_help_legal_and_brand_assets() -> None:
    spec = (ROOT / "dream_sequence_weaver.spec").read_text(encoding="utf-8")
    for filename in (
        "SEQUENCER_INSTRUCTIONS.txt",
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_LICENSES.md",
        "app_icon.ico",
        "c82.png",
        "helixmascot.jpg",
    ):
        assert filename in spec
