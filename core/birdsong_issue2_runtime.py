from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Iterable, Sequence

from core.feature_state import FeatureStateFrame


_ALLOWED_MOTIFS = ("wave_sweep", "spiral", "pulse_cascade", "orbit", "sparkle_field")


@dataclass(frozen=True)
class BirdsongRuntimeConfig:
    """Conservative, explicit gate for the Issue #2 generative path."""

    enabled: bool = False
    min_onset: float = 0.55
    min_energy: float = 0.25
    duration_ms: int = 180
    max_targets_per_frame: int = 3


@dataclass(frozen=True)
class BirdsongSequenceRow:
    model: str
    start_ms: int
    end_ms: int
    label: str
    effect: str
    motif: str
    intensity: float

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


@dataclass(frozen=True)
class BirdsongPhraseSnapshot:
    phrase_id: str
    frame_index: int
    start_ms: int
    motif: str
    effect: str
    intensity: float
    target_models: tuple[str, ...]

    def to_dict(self) -> dict[str, float | int | str | list[str]]:
        out = asdict(self)
        out["target_models"] = list(self.target_models)
        return out


@dataclass(frozen=True)
class BirdsongRuntimePlan:
    rows: tuple[BirdsongSequenceRow, ...]
    phrase_snapshots: tuple[BirdsongPhraseSnapshot, ...]

    def to_dict(self) -> dict[str, list[dict[str, object]]]:
        return {
            "rows": [row.to_dict() for row in self.rows],
            "phrase_snapshots": [snapshot.to_dict() for snapshot in self.phrase_snapshots],
        }


def generate_birdsong_rows(
    frames: Sequence[FeatureStateFrame],
    model_names: Sequence[str],
    *,
    config: BirdsongRuntimeConfig | None = None,
) -> list[BirdsongSequenceRow]:
    """Turn feature-state frames into deterministic placement rows.

    This is a guarded adapter for Issue #2. It intentionally does not touch the
    main effect engine by default. Callers must pass config.enabled=True before
    any rows are emitted, which lets the new generative path be tested without
    altering stable v27.3 output.
    """

    return list(plan_birdsong_runtime(frames, model_names, config=config).rows)


def plan_birdsong_runtime(
    frames: Sequence[FeatureStateFrame],
    model_names: Sequence[str],
    *,
    config: BirdsongRuntimeConfig | None = None,
) -> BirdsongRuntimePlan:
    """Build deterministic rows plus phrase snapshots for persistence."""

    cfg = config or BirdsongRuntimeConfig()
    if not _is_explicitly_enabled(cfg.enabled):
        return BirdsongRuntimePlan(rows=(), phrase_snapshots=())

    models = _clean_models(model_names)
    if not frames or not models:
        return BirdsongRuntimePlan(rows=(), phrase_snapshots=())

    duration_ms = _safe_positive_int(cfg.duration_ms, default=180, minimum=50)
    target_cap = _safe_positive_int(cfg.max_targets_per_frame, default=3, minimum=1)
    rows: list[BirdsongSequenceRow] = []
    phrases: list[BirdsongPhraseSnapshot] = []

    for index, frame in enumerate(frames):
        energy = _finite01(frame.energy_smooth if frame.energy_smooth > 0 else frame.energy)
        onset = _finite01(frame.onset)
        if energy < cfg.min_energy and onset < cfg.min_onset:
            continue

        start_ms = _frame_start_ms(frame.time_s)
        if start_ms is None:
            continue

        motif = _motif_for_frame(frame)
        effect = _effect_for_motif(motif, frame)
        intensity = _finite01(max(energy, onset))
        selected = _select_models(models, frame, index, limit=target_cap)
        phrases.append(
            BirdsongPhraseSnapshot(
                phrase_id=f"birdsong_issue2_{len(phrases) + 1:04d}",
                frame_index=int(frame.frame_index),
                start_ms=start_ms,
                motif=motif,
                effect=effect,
                intensity=intensity,
                target_models=tuple(selected),
            )
        )
        for step, model in enumerate(selected):
            st = start_ms + (step * 24)
            en = st + duration_ms + int(round(intensity * 80.0))
            rows.append(
                BirdsongSequenceRow(
                    model=model,
                    start_ms=st,
                    end_ms=max(st + 1, en),
                    label="birdsong_issue2",
                    effect=effect,
                    motif=motif,
                    intensity=intensity,
                )
            )
    return BirdsongRuntimePlan(rows=tuple(rows), phrase_snapshots=tuple(phrases))


def write_birdsong_runtime_manifest(
    path: str | Path,
    frames: Sequence[FeatureStateFrame],
    model_names: Sequence[str],
    *,
    config: BirdsongRuntimeConfig | None = None,
) -> Path:
    """Persist a repo-safe manifest of the guarded Birdsong runtime plan."""

    cfg = config or BirdsongRuntimeConfig()
    models = _clean_models(model_names)
    plan = plan_birdsong_runtime(frames, models, config=cfg)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "helix.birdsong_issue2.runtime_manifest.v1",
        "status": "repo_safe_synthetic_runtime_fixture",
        "config": _config_to_dict(cfg),
        "feature_frame_count": len(frames),
        "model_names": models,
        **plan.to_dict(),
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def emit_birdsong_rows(
    rows: Iterable[BirdsongSequenceRow],
    add_model,
    *,
    strict: bool = False,
) -> int:
    """Emit rows through the existing add_model callback contract.

    Callback results are interpreted when they can confirm placement: bools
    report success/failure, ints report a placement count, and other placement
    objects confirm one placement. Legacy callbacks commonly return ``None``;
    that result is unknown, so it still counts as one emitted row for backward
    compatibility with the original callback contract.

    Birdsong remains an experimental opt-in path, so callback failures are
    skipped by default instead of breaking stable sequence generation. Tests can
    pass ``strict=True`` when they need exception propagation.
    """

    count = 0
    for row in rows:
        try:
            result = add_model(
                row.model,
                int(row.start_ms),
                int(row.end_ms),
                row.label,
                eff=row.effect,
                stem="other",
            )
        except Exception:
            if strict:
                raise
            continue
        count += _emission_count(result)
    return count


def _is_explicitly_enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    if isinstance(value, int):
        return value == 1
    return False


def _clean_models(model_names: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in model_names:
        model = str(raw).strip()
        key = model.lower()
        if not model or key in seen:
            continue
        seen.add(key)
        out.append(model)
    return out


def _motif_for_frame(frame: FeatureStateFrame) -> str:
    low = _finite01(frame.low)
    mid = _finite01(frame.mid)
    high = _finite01(frame.high)
    onset = _finite01(frame.onset)
    beat_phase = _finite01(frame.beat_phase)
    if high >= max(low, mid) and high >= 0.35:
        return "sparkle_field"
    if low >= max(mid, high) and onset >= 0.45:
        return "pulse_cascade"
    if 0.35 <= beat_phase <= 0.65:
        return "orbit"
    if mid >= low and mid >= high:
        return "spiral"
    return "wave_sweep"


def _effect_for_motif(motif: str, frame: FeatureStateFrame) -> str:
    if motif == "sparkle_field":
        return "Twinkle"
    if motif == "pulse_cascade":
        return "On" if frame.onset >= 0.70 else "Ramp"
    if motif == "orbit":
        return "Spirals"
    if motif == "spiral":
        return "Wave"
    return "Single Strand"


def _select_models(
    models: Sequence[str],
    frame: FeatureStateFrame,
    frame_index: int,
    *,
    limit: int,
) -> list[str]:
    if not models:
        return []
    count = min(len(models), max(1, limit))
    if frame.high >= max(frame.low, frame.mid):
        start = (frame_index * 2) % len(models)
    elif frame.low >= max(frame.mid, frame.high):
        start = frame_index % len(models)
    else:
        start = (frame_index + int(round(frame.beat_phase * len(models)))) % len(models)
    return [models[(start + offset) % len(models)] for offset in range(count)]


def _finite01(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(out):
        return 0.0
    if out <= 0.0:
        return 0.0
    if out >= 1.0:
        return 1.0
    return out


def _safe_positive_int(value: object, *, default: int, minimum: int) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric):
        return default
    return max(minimum, int(numeric))


def _frame_start_ms(value: object) -> int | None:
    try:
        time_s = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(time_s):
        return None
    return max(0, int(round(time_s * 1000.0)))


def _emission_count(result: object) -> int:
    if isinstance(result, bool):
        return int(result)
    if isinstance(result, int):
        return max(0, result)
    return 1


def _config_to_dict(config: BirdsongRuntimeConfig) -> dict[str, object]:
    return asdict(config)


__all__ = [
    "BirdsongRuntimeConfig",
    "BirdsongRuntimePlan",
    "BirdsongPhraseSnapshot",
    "BirdsongSequenceRow",
    "emit_birdsong_rows",
    "generate_birdsong_rows",
    "plan_birdsong_runtime",
    "write_birdsong_runtime_manifest",
]
