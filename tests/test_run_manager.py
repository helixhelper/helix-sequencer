import json

from core.run_config import RunConfig
from core.run_manager import RunManager


def test_run_manager_writes_command_manifest_artifacts_and_finalize(tmp_path):
    config = RunConfig(profile="master", output_root=tmp_path, audio_path=tmp_path / "song.wav")

    manager = RunManager(config)

    assert manager.run_dir.exists()
    command_path = manager.run_dir / "command.txt"
    manifest_path = manager.run_dir / "run_manifest.json"
    assert command_path.exists()
    assert manifest_path.exists()
    assert "--audio" in command_path.read_text(encoding="utf-8")

    started_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert started_manifest["schema"] == "helix.run_manifest.v1"
    assert started_manifest["status"] == "started"
    assert started_manifest["success"] is None
    assert started_manifest["profile"] == "master"

    artifact_path = manager.run_dir / "placement.json"
    artifact_path.write_text("{}", encoding="utf-8")
    manager.record_artifact("effect_placement", artifact_path)

    artifact_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert artifact_manifest["artifacts"] == [
        {
            "kind": "effect_placement",
            "path": str(artifact_path),
            "recorded_at": artifact_manifest["artifacts"][0]["recorded_at"],
        }
    ]

    manager.finalize(success=False, error_summary="preview failed")

    final_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert final_manifest["status"] == "completed"
    assert final_manifest["success"] is False
    assert final_manifest["finished_at"] is not None
    assert final_manifest["errors"] == ["preview failed"]
    assert final_manifest["artifacts"][0]["kind"] == "effect_placement"
