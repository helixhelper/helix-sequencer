from __future__ import annotations

from dataclasses import dataclass

from core.prime_logic import (
    PrimeBlendConfig,
    PrimeIntent,
    blend_prime_intents,
    emit_prime_rows,
    prime_intent_from_birdsong_row,
)


def test_prime_logic_defaults_off() -> None:
    rows, report = blend_prime_intents(
        [
            PrimeIntent(
                source="birdsong",
                start_ms=100,
                end_ms=200,
                models=("star",),
                label="spark",
                motif="sparkle_field",
                intensity=1.0,
            )
        ]
    )

    assert rows == []
    assert report.enabled is False
    assert report.emitted_rows == 0


def test_prime_logic_scores_and_orders_source_intents() -> None:
    intents = [
        PrimeIntent(
            source="legacy",
            start_ms=1000,
            end_ms=1120,
            models=("mega",),
            label="legacy_hit",
            effect="On",
            section="verse",
            intensity=0.7,
            confidence=0.7,
            priority=0.7,
        ),
        PrimeIntent(
            source="birdsong",
            start_ms=1000,
            end_ms=1120,
            models=("star",),
            label="spark",
            effect="Twinkle",
            motif="sparkle_field",
            stem="vocals",
            section="chorus",
            intensity=0.9,
            confidence=0.95,
            priority=1.1,
            style_tags=("stars",),
        ),
    ]

    rows, report = blend_prime_intents(intents, config=PrimeBlendConfig(enabled=True))

    assert [row.model for row in rows] == ["star", "mega"]
    assert rows[0].label == "prime:birdsong:spark"
    assert rows[0].effect == "Twinkle"
    assert report.accepted_intents == 2
    assert report.source_counts["birdsong"] == 1
    assert report.motif_counts["sparkle_field"] == 1


def test_prime_logic_rejects_model_overlap_by_default() -> None:
    intents = [
        PrimeIntent(
            source="birdsong",
            start_ms=1000,
            end_ms=1200,
            models=("arch",),
            label="first",
            effect="Wave",
            intensity=1.0,
            confidence=1.0,
            priority=1.0,
        ),
        PrimeIntent(
            source="stems",
            start_ms=1040,
            end_ms=1150,
            models=("arch",),
            label="second",
            effect="On",
            intensity=1.0,
            confidence=1.0,
            priority=0.9,
        ),
    ]

    rows, report = blend_prime_intents(
        intents,
        config=PrimeBlendConfig(enabled=True, overlap_cooldown_ms=80),
    )

    assert len(rows) == 1
    assert rows[0].label == "prime:birdsong:first"
    assert report.rejected_intents == 1


def test_prime_logic_can_allow_overlap_when_requested() -> None:
    intents = [
        PrimeIntent(source="birdsong", start_ms=0, end_ms=100, models=("arch",), label="a", priority=1.0),
        PrimeIntent(source="stems", start_ms=10, end_ms=110, models=("arch",), label="b", priority=1.0),
    ]

    rows, report = blend_prime_intents(
        intents,
        config=PrimeBlendConfig(enabled=True, allow_model_overlap=True),
    )

    assert len(rows) == 2
    assert report.accepted_intents == 2


def test_prime_logic_limits_dense_windows() -> None:
    intents = [
        PrimeIntent(
            source="birdsong",
            start_ms=100 + index,
            end_ms=180 + index,
            models=(f"m{index}",),
            label=f"hit{index}",
            priority=1.0,
        )
        for index in range(5)
    ]

    rows, report = blend_prime_intents(
        intents,
        config=PrimeBlendConfig(enabled=True, max_intents_per_window=2, window_ms=250),
    )

    assert len(rows) == 2
    assert report.accepted_intents == 2
    assert report.rejected_intents == 3


def test_emit_prime_rows_uses_existing_add_model_contract() -> None:
    rows, _report = blend_prime_intents(
        [
            PrimeIntent(
                source="lyrics",
                start_ms=500,
                end_ms=700,
                models=("face",),
                label="vocal_word",
                effect="On",
                stem="vocals",
            )
        ],
        config=PrimeBlendConfig(enabled=True),
    )
    calls: list[tuple[str, int, int, str, str, str]] = []

    def add_model(model: str, st: int, en: int, label: str, eff: str = "On", stem: str = "other") -> None:
        calls.append((model, st, en, label, eff, stem))

    emitted = emit_prime_rows(rows, add_model)

    assert emitted == 1
    assert calls == [("face", 500, 700, "prime:lyrics:vocal_word", "On", "vocals")]


@dataclass(frozen=True)
class _BirdsongRow:
    model: str = "star"
    start_ms: int = 100
    end_ms: int = 240
    label: str = "birdsong_issue2"
    effect: str = "Twinkle"
    motif: str = "sparkle_field"
    intensity: float = 0.85


def test_prime_intent_from_birdsong_row_preserves_birdsong_context() -> None:
    intent = prime_intent_from_birdsong_row(_BirdsongRow(), section="chorus", style_tags=("stars",))

    assert intent.source == "birdsong"
    assert intent.models == ("star",)
    assert intent.motif == "sparkle_field"
    assert intent.section == "chorus"
    assert intent.style_tags == ("stars",)

    rows, report = blend_prime_intents([intent], config=PrimeBlendConfig(enabled=True))

    assert len(rows) == 1
    assert rows[0].label == "prime:birdsong:birdsong_issue2"
    assert rows[0].motif == "sparkle_field"
    assert report.motif_counts["sparkle_field"] == 1
