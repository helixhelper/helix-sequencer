from pathlib import Path

from helix.preview.canvas import Canvas
from helix.preview.export import PreviewExporter
from helix.preview.renderer import PreviewRenderer


def test_preview_renderer_and_canvas():
    frame = PreviewRenderer().render(100, {"tree": {"red": 1.0}})
    canvas = Canvas()
    canvas.draw_model("tree", frame.models["tree"])
    assert canvas.snapshot()["tree"]["red"] == 1.0


def test_preview_export(tmp_path: Path):
    output = tmp_path / "preview.txt"
    result = PreviewExporter().export_frames([], output)
    assert result.frame_count == 0
    assert output.exists()
