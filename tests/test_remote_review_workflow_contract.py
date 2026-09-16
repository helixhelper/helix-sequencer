from __future__ import annotations

from pathlib import Path


WORKFLOW = Path('.github/workflows/helix-remote-review-preview.yml')


def _workflow_text() -> str:
    assert WORKFLOW.exists(), f'Missing workflow: {WORKFLOW}'
    return WORKFLOW.read_text(encoding='utf-8')


def test_remote_review_workflow_exists_and_has_render_job() -> None:
    text = _workflow_text()

    assert 'name: Helix Remote Review Preview MP4' in text
    assert 'jobs:' in text
    assert 'render-winner-preview:' in text


def test_remote_review_workflow_uploads_mp4_artifacts() -> None:
    text = _workflow_text()

    assert 'uses: actions/upload-artifact@v4' in text
    assert 'id: upload-preview' in text
    assert 'name: helix-remote-review-preview-mp4' in text
    assert 'review_summary.md' in text
    assert '**/*.mp4' in text
    assert '**/*.xsq' in text
    assert '**/*.fseq' in text
    assert '**/*.json' in text
    assert 'if-no-files-found: error' in text


def test_remote_review_workflow_watches_outcome_affecting_paths() -> None:
    text = _workflow_text()

    assert 'pull_request:' in text
    assert 'push:' in text
    assert "'**/*.py'" in text
    assert "'**/*.json'" in text
    assert "'**/*.xml'" in text
    assert "'**/*.xsq'" in text
    assert "'**/*.lms'" in text
    assert 'cancel-in-progress: true' in text


def test_remote_review_workflow_renders_active_profile_from_deterministic_audio() -> None:
    text = _workflow_text()

    assert 'generate_structured_benchmark_audio.py' in text
    assert 'python -m tools.helixia_smoke_preview' in text
    assert '--profile master' in text
    assert 'PREVIEW_AUDIO_DIR: test_runs/outcome_preview_input' in text
    assert '--audio "$PREVIEW_AUDIO_DIR/helix-outcome-preview.wav"' in text
    assert '--output-dir "$PREVIEW_DIR"' in text
    assert 'python -m tools.build_outcome_preview_manifest' in text
    assert '--require-drummer' in text
    assert '--require-drum-classes' in text
    assert '--require-native-choreography' in text


def test_remote_review_workflow_uses_pinned_native_xlights_headless_render() -> None:
    text = _workflow_text()

    assert 'XLIGHTS_VERSION: "2026.17"' in text
    assert 'XLIGHTS_APPIMAGE_SHA256:' in text
    assert 'sha256sum -c -' in text
    assert 'Install xLights headless runtime libraries' in text
    assert 'libegl1' in text
    assert 'Native xLights headless acceptance render' in text
    assert '"$XLIGHTS_APPIMAGE" --headless' in text
    assert '--outputdir "$PREVIEW_DIR/native-xlights"' in text
    assert "-name '*.fseq'" in text


def test_remote_review_workflow_attaches_preview_link_to_pull_request() -> None:
    text = _workflow_text()

    assert 'pull-requests: write' in text
    assert 'steps.upload-preview.outputs.artifact-url' in text
    assert 'actions/github-script@v7' in text
    assert '<!-- helix-outcome-preview -->' in text
