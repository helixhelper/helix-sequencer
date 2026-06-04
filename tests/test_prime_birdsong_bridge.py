from __future__ import annotations

from core.birdsong_issue2_runtime import BirdsongRuntimeConfig, generate_birdsong_rows
from core.feature_state import FeatureState
from core.prime_birdsong_bridge import (
    PrimeBirdsongBridgeConfig,
    build_prime_birdsong_intents,
    run_prime_birdsong_bridge,
)
from core.prime_logic import PrimeBlendConfig


def _frames():
    state = FeatureState()
    return [
        state.update(0, energy=0.10, onset=0.0, centroid=900.0, low=0.10, mid=0.05, high=0.02, beat_phase=0.0, time_s=0.0),
        state.update(1, energy=0.95, onset=0.9, centroid=6500.0, low=0.10, mid=0.20, high=0.90, beat_phase=0.50, time_s=0.5),
        state.update(2, energy=0.82, onset=0.75, centroid=800.0, low=0.85, mid=0.20, high=0.10, beat_phase=0.10, time_s=1.0),
    ]


def test_prime_birdsong_bridge_defaults_off() -> None:
    calls: list[tuple[str, int, int, str, str, str]] = []

    def add_model(model: str, st: int, en: int, label: str, eff: str = "On", stem: str = "other") -> None:
        calls.append((model, st, en, label, eff, stem))

    report = run_prime_birdsong_bridge(_frames(), ["star", "arch"], add_model)

    assert report.enabled is False
    assert report.birdsong_rows == 0
    assert report.prime_intents == 0
    assert report.prime_rows == 0
    assert report.emitted_rows == 0
    assert calls == []


def test_prime_birdsong_bridge_emits_prime_rows_when_enabled() -> None:
    calls: list[tuple[str, int, int, str, str, str]] = []

    def add_model(model: str, st: int, en: int, label: str, eff: str = "On", stem: str = "other") -> None:
        calls.append((model, st, en, label, eff, stem))

    config = PrimeBirdsongBridgeConfig(
        enabled=True,
        section="chorus",
        style_tags=("stars", "arch"),
        birdsong=BirdsongRuntimeConfig(enabled=True, max_targets_per_frame=1, duration_ms=120),
        prime=PrimeBlendConfig(enabled=True, allow_model_overlap=True),
    )

    report = run_prime_birdsong_bridge(_frames(), ["star", "arch", "mega"], add_model, config=config)

    assert report.enabled is True
    assert report.birdsong_rows == 2
    assert report.prime_intents == 2
    assert report.prime_rows == 2
    assert report.emitted_rows == 2
    assert len(calls) == 2
    assert all(call[3].startswith("prime:birdsong:") for call in calls)
    assert report.source_counts["birdsong"] == 2
    assert set(report.motif_counts) == {"sparkle_field", "pulse_cascade"}


def test_prime_birdsong_bridge_requires_birdsong_rows() -> None:
    calls: list[tuple[str, int, int, str, str, str]] = []

    def add_model(model: str, st: int, en: int, label: str, eff: str = "On", stem: str = "other") -> None:
        calls.append((model, st, en, label, eff, stem))

    config = PrimeBirdsongBridgeConfig(
        enabled=True,
        birdsong=BirdsongRuntimeConfig(enabled=False),
        prime=PrimeBlendConfig(enabled=True),
    )

    report = run_prime_birdsong_bridge(_frames(), ["star", "arch"], add_model, config=config)

    assert report.enabled is True
    assert report.birdsong_rows == 0
    assert report.prime_rows == 0
    assert report.emitted_rows == 0
    assert calls == []


def test_build_prime_birdsong_intents_preserves_context() -> None:
    birdsong_rows = generate_birdsong_rows(
        _frames(),
        ["star", "arch"],
        config=BirdsongRuntimeConfig(enabled=True, max_targets_per_frame=1),
    )
    intents = build_prime_birdsong_intents(birdsong_rows, section="bridge", style_tags=("mega",))

    assert intents
    assert all(intent.section == "bridge" for intent in intents)
    assert all(intent.style_tags == ("mega",) for intent in intents)
    assert all(intent.source == "birdsong" for intent in intents)
