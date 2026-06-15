from __future__ import annotations

from dataclasses import replace

from core.birdsong_issue2_runtime import (
    BirdsongRuntimeConfig,
    emit_birdsong_rows,
    generate_birdsong_rows,
)
from core.feature_state import FeatureState


def _frames():
    state = FeatureState()
    return [
        state.update(
            0,
            energy=0.05,
            onset=0.0,
            centroid=1000.0,
            low=0.05,
            mid=0.02,
            high=0.01,
            beat_phase=0.0,
            time_s=0.0,
        ),
        state.update(
            1,
            energy=0.90,
            onset=1.0,
            centroid=7000.0,
            low=0.10,
            mid=0.20,
            high=0.90,
            beat_phase=0.50,
            time_s=0.5,
        ),
        state.update(
            2,
            energy=0.75,
            onset=0.70,
            centroid=900.0,
            low=0.80,
            mid=0.20,
            high=0.10,
            beat_phase=0.10,
            time_s=1.0,
        ),
    ]


def _enabled_config(**overrides):
    values = {"enabled": True}
    values.update(overrides)
    return BirdsongRuntimeConfig(**values)


def test_generate_birdsong_rows_defaults_off() -> None:
    rows = generate_birdsong_rows(_frames(), ["star", "arch"])

    assert rows == []


def test_generate_birdsong_rows_emits_deterministic_rows_when_enabled() -> None:
    frames = _frames()
    models = ["star", "arch", "ground", "mega"]
    config = _enabled_config(max_targets_per_frame=2, duration_ms=120)

    first = generate_birdsong_rows(frames, models, config=config)
    second = generate_birdsong_rows(frames, models, config=config)

    assert first == second
    assert len(first) == 4
    assert {row.label for row in first} == {"birdsong_issue2"}
    assert {row.motif for row in first} == {
        "sparkle_field",
        "pulse_cascade",
    }
    assert all(row.end_ms > row.start_ms for row in first)


def test_generate_birdsong_rows_dedupes_models_and_limits_targets() -> None:
    config = _enabled_config(max_targets_per_frame=1)

    rows = generate_birdsong_rows(
        _frames(),
        ["star", "STAR", "arch"],
        config=config,
    )

    assert len(rows) == 2
    assert all(row.model in {"star", "arch"} for row in rows)


def test_emit_birdsong_rows_uses_existing_add_model_contract() -> None:
    rows = generate_birdsong_rows(
        _frames(),
        ["star", "arch"],
        config=_enabled_config(max_targets_per_frame=1),
    )
    calls: list[tuple[str, int, int, str, str, str]] = []

    def add_model(
        model: str,
        st: int,
        en: int,
        label: str,
        eff: str = "On",
        stem: str = "other",
    ) -> None:
        calls.append((model, st, en, label, eff, stem))

    emitted = emit_birdsong_rows(rows, add_model)

    assert emitted == len(rows)
    assert emitted == len(calls)
    assert all(call[3] == "birdsong_issue2" for call in calls)
    assert all(call[5] == "other" for call in calls)


def _constant_callback(value):
    def callback(*_args, **_kwargs):
        return value

    return callback


def test_emit_birdsong_rows_counts_boolean_callback_results() -> None:
    rows = generate_birdsong_rows(
        _frames(),
        ["star"],
        config=_enabled_config(max_targets_per_frame=1),
    )[:1]

    assert emit_birdsong_rows(rows, _constant_callback(True)) == 1
    assert emit_birdsong_rows(rows, _constant_callback(False)) == 0


def test_emit_counts_int_and_unknown_callback_results() -> None:
    rows = generate_birdsong_rows(
        _frames(),
        ["star"],
        config=_enabled_config(max_targets_per_frame=1),
    )[:1]

    assert emit_birdsong_rows(rows, _constant_callback(3)) == 3
    assert emit_birdsong_rows(rows, _constant_callback(None)) == 1


def test_generate_birdsong_rows_sanitizes_invalid_config_values() -> None:
    rows = generate_birdsong_rows(
        _frames(),
        ["star", "arch", "ground", "mega"],
        config=_enabled_config(
            duration_ms="invalid",
            max_targets_per_frame="invalid",
        ),
    )

    assert len(rows) == 6
    assert all(row.end_ms > row.start_ms for row in rows)


def test_generate_birdsong_rows_skips_non_finite_frame_times() -> None:
    frames = _frames()
    bad_frames = [
        frames[0],
        replace(frames[1], time_s=float("nan")),
        replace(frames[2], time_s=float("inf")),
    ]

    rows = generate_birdsong_rows(
        bad_frames,
        ["star", "arch"],
        config=_enabled_config(max_targets_per_frame=1),
    )

    assert rows == []
