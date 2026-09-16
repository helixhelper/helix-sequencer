from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name = line
        for marker in ("==", ">=", "<=", "~=", "!=", ">", "<", "["):
            if marker in name:
                name = name.split(marker, 1)[0]
        names.add(name.strip().casefold())
    return names


def test_mutagen_is_not_redistributed_in_windows_beta_requirements() -> None:
    requirements = _requirement_names(ROOT / "requirements-beta.txt")
    notices = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")

    assert "mutagen" not in requirements
    assert "intentionally not declared in `requirements-beta.txt`" in notices


def test_windows_beta_requirements_exclude_heavy_optional_lyric_stack() -> None:
    requirements = _requirement_names(ROOT / "requirements-beta.txt")

    assert "openai-whisper" not in requirements
    assert "torch" not in requirements
