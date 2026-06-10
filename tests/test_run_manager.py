import json

from core.run_config import RunConfig
from core.run_manager import RunManager


def test_run_manager_writes_command_manifest_artifacts_and_finalize_success(tmp_path):
    audio = tmp_path / "song.wav"
    template = tmp_path / "template.xsq"
    layout = tmp_path / "xlights_rgbeffects.xml"
    for path in (audio, template, layout):
        path.write_text("source", encoding="utf-8")
    original_sources = {path: path.read_text(encoding="utf-8") for path in (audio, template, layout)}

    config = RunConfig(
        profile="master",
        output_root=tmp_path / "outputs",
        audio_path=audio,
        template_path=template,
        layout_path=layout,
    )

    manager = RunManager(config)

    assert manager.run_dir.exists()
    assert manager.run_dir.parent == config.output_root / "beta"
    assert manager.run_dir.name.endswith("-master")
    assert manager.command_path.exists()
    assert manager.manifest_path.exists()
    assert manager.log_path == manager.run_dir / "helix.log"
    assert "--audio" in manager.command_path.read_text(encoding="utf-8")

    started_manifest = json.loads(manager.manifest_path.read_text(encoding="utf-8"))
    assert started_manifest["schema"] == "helix.run_manifest.v1"
    assert started_manifest["app"] == "Helix Sequencer"
    assert started_manifest["status"] == "started"
    assert started_manifest["success"] is False
    assert started_manifest["profile"] == "master"
    assert started_manifest["audio_path"] == str(audio)
    assert started_manifest["template_path"] == str(template)
    assert started_manifest["layout_path"] == str(layout)
    assert started_manifest["run_dir"] == str(manager.run_dir)
    assert started_manifest["command"][0]
    assert started_manifest["warnings"] == []
    assert started_manifest["errors"] == []
    assert started_manifest["error_summary"] is None
    assert "git_commit" in started_manifest

    artifact_path = manager.run_dir / "placement.json"
    artifact_path.write_text("{}", encoding="utf-8")
    manager.record_artifact("effect_placement", artifact_path)
    manager.record_artifact("missing_report", manager.run_dir / "missing.json")

    artifact_manifest = json.loads(manager.manifest_path.read_text(encoding="utf-8"))
    assert artifact_manifest["artifacts"] == [
        {"kind": "effect_placement", "path": str(artifact_path), "exists": True},
        {"kind": "missing_report", "path": str(manager.run_dir / "missing.json"), "exists": False},
    ]

    manager.finalize(success=True)

    final_manifest = json.loads(manager.manifest_path.read_text(encoding="utf-8"))
    assert final_manifest["status"] == "completed"
    assert final_manifest["success"] is True
    assert final_manifest["finished_at"] is not None
    assert final_manifest["errors"] == []
    assert final_manifest["error_summary"] is None
    assert final_manifest["artifacts"][0]["kind"] == "effect_placement"
    assert {path: path.read_text(encoding="utf-8") for path in (audio, template, layout)} == original_sources


def test_run_manager_finalizes_failure_with_error_summary(tmp_path):
    config = RunConfig(profile="preview", output_root=tmp_path)

    manager = RunManager(config)
    manager.record_warning("non-fatal warning")
    manager.record_error("recoverable error")
    manager.finalize(success=False, error_summary="preview failed")

    manifest = json.loads(manager.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["success"] is False
    assert manifest["warnings"] == ["non-fatal warning"]
    assert manifest["errors"] == ["recoverable error", "preview failed"]
    assert manifest["error_summary"] == "preview failed"
