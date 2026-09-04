from __future__ import annotations

import tempfile
from pathlib import Path

from tools.run_helix_e2e import _next_run_dir


def test_next_run_dir_does_not_reuse_existing_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        (output_dir / "song").mkdir()
        (output_dir / "song-1").mkdir()

        run_dir = _next_run_dir(output_dir, "song")

        assert run_dir == output_dir.resolve() / "song-2"
        assert (output_dir / "song").exists()
        assert (output_dir / "song-1").exists()
