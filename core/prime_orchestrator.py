from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from core.prime_intent_adapters import (
    LyricIntentEvent,
    SpatialIntentEvent,
    StemIntentEvent,
    StyleDNAIntentEvent,
    build_multi_source_prime_intents,
)
from core.prime_logic import PrimeBlendConfig, PrimeBlendReport, PrimeIntent, PrimeRow, blend_prime_intents, emit_prime_rows


@dataclass(frozen=True)
class PrimeOrchestratorConfig:
    """Top-level guarded Prime conductor config."""

    enabled: bool = False
    blend: PrimeBlendConfig = PrimeBlendConfig()

    def with_runtime_enabled(self) -> "PrimeOrchestratorConfig":
        return PrimeOrchestratorConfig(
            enabled=True,
            blend=PrimeBlendConfig(
                enabled=True,
                max_intents_per_window=self.blend.max_intents_per_window,
                window_ms=self.blend.window_ms,
                max_models_per_intent=self.blend.max_models_per_intent,
                min_score=self.blend.min_score,
                allow_model_overlap=self.blend.allow_model_overlap,
                overlap_cooldown_ms=self.blend.overlap_cooldown_ms,
            ),
        )


@dataclass(frozen=True)
class PrimeOrchestrationInput:
    birdsong: tuple[PrimeIntent, ...] = ()
    stems: tuple[StemIntentEvent, ...] = ()
    lyrics: tuple[LyricIntentEvent, ...] = ()
    spatial: tuple[SpatialIntentEvent, ...] = ()
    style_dna: tuple[StyleDNAIntentEvent, ...] = ()
    legacy: tuple[PrimeIntent, ...] = ()


@dataclass(frozen=True)
class PrimeOrchestrationReport:
    schema: str
    enabled: bool
    input_intents: int
    prime_rows: int
    emitted_rows: int
    source_counts: Mapping[str, int]
    motif_counts: Mapping[str, int]
    blend_report: PrimeBlendReport


def gather_prime_intents(inputs: PrimeOrchestrationInput) -> list[PrimeIntent]:
    """Normalize all known source adapters into one PrimeIntent list."""

    intents: list[PrimeIntent] = []
    intents.extend(inputs.birdsong)
    intents.extend(inputs.legacy)
    intents.extend(
        build_multi_source_prime_intents(
            stems=inputs.stems,
            lyrics=inputs.lyrics,
            spatial=inputs.spatial,
            style_dna=inputs.style_dna,
        )
    )
    return intents


def run_prime_orchestrator(
    inputs: PrimeOrchestrationInput,
    add_model,
    *,
    config: PrimeOrchestratorConfig | None = None,
) -> tuple[list[PrimeRow], PrimeOrchestrationReport]:
    """Blend and emit every source through Prime.

    This remains default-off. When disabled, it still reports how many source
    intents would have been available, but emits no rows.
    """

    cfg = config or PrimeOrchestratorConfig()
    intents = gather_prime_intents(inputs)
    if not cfg.enabled:
        empty_blend = PrimeBlendReport(
            schema="helix.prime_intent.v1",
            enabled=False,
            accepted_intents=0,
            rejected_intents=0,
            emitted_rows=0,
            source_counts={},
            motif_counts={},
        )
        return [], _report(False, intents, [], 0, empty_blend)

    rows, blend_report = blend_prime_intents(intents, config=cfg.blend)
    emitted = emit_prime_rows(rows, add_model)
    return rows, _report(True, intents, rows, emitted, blend_report)


def _report(
    enabled: bool,
    intents: Sequence[PrimeIntent],
    rows: Sequence[PrimeRow],
    emitted_rows: int,
    blend_report: PrimeBlendReport,
) -> PrimeOrchestrationReport:
    source_counts: dict[str, int] = {}
    motif_counts: dict[str, int] = {}
    for intent in (intent.normalized() for intent in intents):
        source_counts[intent.source] = source_counts.get(intent.source, 0) + 1
        if intent.motif:
            motif_counts[intent.motif] = motif_counts.get(intent.motif, 0) + 1
    return PrimeOrchestrationReport(
        schema="helix.prime_orchestrator.v1",
        enabled=enabled,
        input_intents=len(intents),
        prime_rows=len(rows),
        emitted_rows=int(emitted_rows),
        source_counts=source_counts,
        motif_counts=motif_counts,
        blend_report=blend_report,
    )


__all__ = [
    "PrimeOrchestrationInput",
    "PrimeOrchestrationReport",
    "PrimeOrchestratorConfig",
    "gather_prime_intents",
    "run_prime_orchestrator",
]
