from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from core.birdsong_issue2_runtime import BirdsongRuntimeConfig, generate_birdsong_rows
from core.prime_logic import (
    PRIME_INTENT_SCHEMA,
    PrimeBlendConfig,
    PrimeBlendReport,
    PrimeIntent,
    blend_prime_intents,
    emit_prime_rows,
    prime_intent_from_birdsong_row,
)


@dataclass(frozen=True)
class PrimeBirdsongBridgeConfig:
    """Guarded runtime bridge from Birdsong Issue #2 rows into Prime Logic."""

    enabled: bool = False
    section: str = ""
    style_tags: tuple[str, ...] = ()
    birdsong: BirdsongRuntimeConfig = BirdsongRuntimeConfig()
    prime: PrimeBlendConfig = PrimeBlendConfig()

    def with_runtime_enabled(self) -> "PrimeBirdsongBridgeConfig":
        """Return a config with both Birdsong and Prime explicitly enabled."""

        return PrimeBirdsongBridgeConfig(
            enabled=True,
            section=self.section,
            style_tags=self.style_tags,
            birdsong=BirdsongRuntimeConfig(
                enabled=True,
                min_onset=self.birdsong.min_onset,
                min_energy=self.birdsong.min_energy,
                duration_ms=self.birdsong.duration_ms,
                max_targets_per_frame=self.birdsong.max_targets_per_frame,
            ),
            prime=PrimeBlendConfig(
                enabled=True,
                max_intents_per_window=self.prime.max_intents_per_window,
                window_ms=self.prime.window_ms,
                max_models_per_intent=self.prime.max_models_per_intent,
                min_score=self.prime.min_score,
                allow_model_overlap=self.prime.allow_model_overlap,
                overlap_cooldown_ms=self.prime.overlap_cooldown_ms,
            ),
        )


@dataclass(frozen=True)
class PrimeBirdsongBridgeReport:
    schema: str
    enabled: bool
    birdsong_rows: int
    prime_intents: int
    prime_rows: int
    emitted_rows: int
    prime_report: PrimeBlendReport
    motif_counts: Mapping[str, int]
    source_counts: Mapping[str, int]


def build_prime_birdsong_intents(
    birdsong_rows: Iterable[object],
    *,
    section: str = "",
    style_tags: Sequence[str] = (),
) -> list[PrimeIntent]:
    """Convert Birdsong row-like objects into Prime intents."""

    return [
        prime_intent_from_birdsong_row(row, section=section, style_tags=style_tags)
        for row in birdsong_rows
    ]


def run_prime_birdsong_bridge(
    frames: Sequence[object],
    model_names: Sequence[str],
    add_model,
    *,
    config: PrimeBirdsongBridgeConfig | None = None,
) -> PrimeBirdsongBridgeReport:
    """Generate Birdsong rows, blend through Prime, and optionally emit rows.

    This bridge is intentionally default-off. It returns a complete report even
    when disabled so SequenceBuilder/RunManager can record zero-row side effects
    without changing stable output.
    """

    cfg = config or PrimeBirdsongBridgeConfig()
    if not cfg.enabled:
        return _bridge_report(False, [], [], [], emitted_rows=0)

    birdsong_rows = generate_birdsong_rows(frames, model_names, config=cfg.birdsong)
    prime_intents = build_prime_birdsong_intents(
        birdsong_rows,
        section=cfg.section,
        style_tags=cfg.style_tags,
    )
    prime_rows, prime_report = blend_prime_intents(prime_intents, config=cfg.prime)
    emitted = emit_prime_rows(prime_rows, add_model)
    return _bridge_report(True, birdsong_rows, prime_intents, prime_rows, emitted_rows=emitted, prime_report=prime_report)


def _bridge_report(
    enabled: bool,
    birdsong_rows: Sequence[object],
    prime_intents: Sequence[PrimeIntent],
    prime_rows: Sequence[object],
    *,
    emitted_rows: int,
    prime_report: PrimeBlendReport | None = None,
) -> PrimeBirdsongBridgeReport:
    report = prime_report or PrimeBlendReport(
        schema=PRIME_INTENT_SCHEMA,
        enabled=False,
        accepted_intents=0,
        rejected_intents=0,
        emitted_rows=0,
        source_counts={},
        motif_counts={},
    )
    motif_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for intent in prime_intents:
        source_counts[intent.source] = source_counts.get(intent.source, 0) + 1
        if intent.motif:
            motif_counts[intent.motif] = motif_counts.get(intent.motif, 0) + 1
    return PrimeBirdsongBridgeReport(
        schema="helix.prime_birdsong_bridge.v1",
        enabled=enabled,
        birdsong_rows=len(birdsong_rows),
        prime_intents=len(prime_intents),
        prime_rows=len(prime_rows),
        emitted_rows=int(emitted_rows),
        prime_report=report,
        motif_counts=motif_counts,
        source_counts=source_counts,
    )


__all__ = [
    "PrimeBirdsongBridgeConfig",
    "PrimeBirdsongBridgeReport",
    "build_prime_birdsong_intents",
    "run_prime_birdsong_bridge",
]
