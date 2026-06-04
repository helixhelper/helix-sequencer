from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Mapping, Sequence


PRIME_INTENT_SCHEMA = "helix.prime_intent.v1"

_SOURCE_WEIGHTS: Mapping[str, float] = {
    "birdsong": 1.20,
    "stems": 1.10,
    "lyrics": 1.08,
    "spatial": 1.05,
    "style_dna": 1.00,
    "legacy": 0.92,
}

_SECTION_WEIGHTS: Mapping[str, float] = {
    "intro": 0.82,
    "verse": 0.92,
    "prechorus": 1.05,
    "chorus": 1.18,
    "drop": 1.22,
    "bridge": 1.08,
    "outro": 0.88,
}

_STEM_WEIGHTS: Mapping[str, float] = {
    "vocals": 1.16,
    "vocal": 1.16,
    "drums": 1.14,
    "kick": 1.12,
    "snare": 1.10,
    "bass": 1.10,
    "guitar": 1.04,
    "piano": 1.04,
    "keyboard": 1.04,
    "other": 1.00,
}

_MOTIF_STYLE_AFFINITY: Mapping[str, tuple[str, ...]] = {
    "sparkle_field": ("stars", "snowflakes", "matrix", "spinner"),
    "pulse_cascade": ("mega", "arch", "line", "canes_combo"),
    "orbit": ("spinner", "mega", "matrix", "circle"),
    "spiral": ("mega", "spiral", "spinner", "tree"),
    "wave_sweep": ("arch", "line", "roof", "canes_combo"),
}


@dataclass(frozen=True)
class PrimeIntent:
    """A source-neutral request for Helix to place a visual idea.

    Birdsong, stems, lyrics, spatial mapping, style DNA, and legacy cues can all
    submit this same shape. Prime Logic scores and resolves them before any xLights
    row is emitted.
    """

    source: str
    start_ms: int
    end_ms: int
    models: tuple[str, ...]
    label: str
    effect: str = "On"
    motif: str = ""
    stem: str = "other"
    section: str = ""
    intensity: float = 1.0
    confidence: float = 1.0
    priority: float = 1.0
    layer: str = "accent"
    style_tags: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def normalized(self) -> "PrimeIntent":
        start = max(0, int(self.start_ms))
        end = max(start + 1, int(self.end_ms))
        clean_models = tuple(_dedupe_text(self.models))
        return PrimeIntent(
            source=str(self.source or "legacy").strip().lower() or "legacy",
            start_ms=start,
            end_ms=end,
            models=clean_models,
            label=str(self.label or self.source or "prime_intent"),
            effect=str(self.effect or "On"),
            motif=str(self.motif or ""),
            stem=str(self.stem or "other").strip().lower() or "other",
            section=str(self.section or "").strip().lower(),
            intensity=_finite01(self.intensity),
            confidence=_finite01(self.confidence),
            priority=max(0.0, _finite(self.priority, 1.0)),
            layer=str(self.layer or "accent").strip().lower() or "accent",
            style_tags=tuple(_dedupe_text(self.style_tags)),
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class PrimeRow:
    model: str
    start_ms: int
    end_ms: int
    label: str
    effect: str
    source: str
    motif: str
    stem: str
    layer: str
    score: float


@dataclass(frozen=True)
class PrimeBlendConfig:
    """Controls how aggressive Prime is allowed to be."""

    enabled: bool = False
    max_intents_per_window: int = 4
    window_ms: int = 250
    max_models_per_intent: int = 4
    min_score: float = 0.05
    allow_model_overlap: bool = False
    overlap_cooldown_ms: int = 80


@dataclass(frozen=True)
class PrimeBlendReport:
    schema: str
    enabled: bool
    accepted_intents: int
    rejected_intents: int
    emitted_rows: int
    source_counts: Mapping[str, int]
    motif_counts: Mapping[str, int]


def blend_prime_intents(
    intents: Iterable[PrimeIntent],
    *,
    config: PrimeBlendConfig | None = None,
) -> tuple[list[PrimeRow], PrimeBlendReport]:
    """Blend source intents into deterministic Prime rows.

    The function is deliberately pure and default-off so it can be inserted ahead
    of xLights export without changing stable renderer behavior until explicitly
    enabled.
    """

    cfg = config or PrimeBlendConfig()
    if not cfg.enabled:
        return [], _report(False, [], 0)

    normalized = [intent.normalized() for intent in intents]
    normalized = [intent for intent in normalized if intent.models]
    scored = [(_intent_score(intent), index, intent) for index, intent in enumerate(normalized)]
    scored = [entry for entry in scored if entry[0] >= cfg.min_score]
    scored.sort(key=lambda entry: (-entry[0], entry[2].start_ms, entry[1]))

    accepted: list[tuple[float, int, PrimeIntent]] = []
    window_counts: dict[int, int] = {}
    model_busy_until: dict[str, int] = {}

    for score, index, intent in scored:
        window = intent.start_ms // max(1, int(cfg.window_ms))
        if window_counts.get(window, 0) >= max(1, int(cfg.max_intents_per_window)):
            continue
        if not cfg.allow_model_overlap and _models_are_busy(intent, model_busy_until):
            continue
        accepted.append((score, index, intent))
        window_counts[window] = window_counts.get(window, 0) + 1
        if not cfg.allow_model_overlap:
            until = intent.end_ms + max(0, int(cfg.overlap_cooldown_ms))
            for model in intent.models[: max(1, int(cfg.max_models_per_intent))]:
                model_busy_until[model] = max(model_busy_until.get(model, 0), until)

    accepted.sort(key=lambda entry: (entry[2].start_ms, -entry[0], entry[1]))
    rows: list[PrimeRow] = []
    for score, _index, intent in accepted:
        for model in intent.models[: max(1, int(cfg.max_models_per_intent))]:
            rows.append(
                PrimeRow(
                    model=model,
                    start_ms=int(intent.start_ms),
                    end_ms=int(intent.end_ms),
                    label=f"prime:{intent.source}:{intent.label}",
                    effect=intent.effect,
                    source=intent.source,
                    motif=intent.motif,
                    stem=intent.stem,
                    layer=intent.layer,
                    score=round(score, 6),
                )
            )

    return rows, _report(True, [entry[2] for entry in accepted], len(rows), rejected=len(normalized) - len(accepted))


def emit_prime_rows(rows: Iterable[PrimeRow], add_model) -> int:
    """Emit Prime rows through the existing add_model callback contract."""

    count = 0
    for row in rows:
        add_model(
            row.model,
            int(row.start_ms),
            int(row.end_ms),
            row.label,
            eff=row.effect,
            stem=row.stem,
        )
        count += 1
    return count


def prime_intent_from_birdsong_row(row: object, *, section: str = "", style_tags: Sequence[str] = ()) -> PrimeIntent:
    """Adapter for BirdsongSequenceRow-like objects without coupling imports."""

    return PrimeIntent(
        source="birdsong",
        start_ms=int(getattr(row, "start_ms")),
        end_ms=int(getattr(row, "end_ms")),
        models=(str(getattr(row, "model")),),
        label=str(getattr(row, "label", "birdsong")),
        effect=str(getattr(row, "effect", "On")),
        motif=str(getattr(row, "motif", "")),
        stem=str(getattr(row, "stem", "other")),
        section=section,
        intensity=float(getattr(row, "intensity", 1.0)),
        confidence=0.92,
        priority=1.12,
        layer="accent",
        style_tags=tuple(style_tags),
    )


def _intent_score(intent: PrimeIntent) -> float:
    source_weight = _SOURCE_WEIGHTS.get(intent.source, 1.0)
    section_weight = _SECTION_WEIGHTS.get(intent.section, 1.0)
    stem_weight = _STEM_WEIGHTS.get(intent.stem, 1.0)
    motif_weight = _motif_affinity(intent.motif, intent.style_tags)
    layer_weight = 1.08 if intent.layer == "accent" else 1.0 if intent.layer == "rhythmic" else 0.92
    return (
        max(0.0, intent.priority)
        * max(0.0, intent.intensity)
        * max(0.0, intent.confidence)
        * source_weight
        * section_weight
        * stem_weight
        * motif_weight
        * layer_weight
    )


def _motif_affinity(motif: str, style_tags: Sequence[str]) -> float:
    if not motif or not style_tags:
        return 1.0
    preferred = _MOTIF_STYLE_AFFINITY.get(motif, ())
    if not preferred:
        return 1.0
    tag_set = {tag.lower() for tag in style_tags}
    return 1.12 if any(tag in tag_set for tag in preferred) else 0.96


def _models_are_busy(intent: PrimeIntent, busy_until: Mapping[str, int]) -> bool:
    for model in intent.models:
        if intent.start_ms < busy_until.get(model, -1):
            return True
    return False


def _report(enabled: bool, accepted: Sequence[PrimeIntent], emitted_rows: int, rejected: int = 0) -> PrimeBlendReport:
    source_counts: dict[str, int] = {}
    motif_counts: dict[str, int] = {}
    for intent in accepted:
        source_counts[intent.source] = source_counts.get(intent.source, 0) + 1
        if intent.motif:
            motif_counts[intent.motif] = motif_counts.get(intent.motif, 0) + 1
    return PrimeBlendReport(
        schema=PRIME_INTENT_SCHEMA,
        enabled=enabled,
        accepted_intents=len(accepted),
        rejected_intents=max(0, int(rejected)),
        emitted_rows=int(emitted_rows),
        source_counts=source_counts,
        motif_counts=motif_counts,
    )


def _dedupe_text(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        key = value.lower()
        if not value or key in seen:
            continue
        out.append(value)
        seen.add(key)
    return out


def _finite01(value: object) -> float:
    out = _finite(value, 0.0)
    if out <= 0.0:
        return 0.0
    if out >= 1.0:
        return 1.0
    return out


def _finite(value: object, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


__all__ = [
    "PRIME_INTENT_SCHEMA",
    "PrimeBlendConfig",
    "PrimeBlendReport",
    "PrimeIntent",
    "PrimeRow",
    "blend_prime_intents",
    "emit_prime_rows",
    "prime_intent_from_birdsong_row",
]
