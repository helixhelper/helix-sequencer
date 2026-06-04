from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from core.prime_logic import PrimeIntent


@dataclass(frozen=True)
class StemIntentEvent:
    stem: str
    start_ms: int
    end_ms: int
    models: tuple[str, ...]
    cue: str = "hit"
    intensity: float = 1.0
    confidence: float = 0.90
    section: str = ""
    effect: str = "On"
    priority: float = 1.0


@dataclass(frozen=True)
class LyricIntentEvent:
    text: str
    start_ms: int
    end_ms: int
    models: tuple[str, ...]
    emotion: str = "neutral"
    intensity: float = 1.0
    confidence: float = 0.88
    section: str = ""
    effect: str = "On"
    priority: float = 1.0


@dataclass(frozen=True)
class SpatialIntentEvent:
    start_ms: int
    end_ms: int
    models: tuple[str, ...]
    motion: str = "flow"
    zone: str = ""
    intensity: float = 1.0
    confidence: float = 0.86
    section: str = ""
    effect: str = "Single Strand"
    priority: float = 1.0


@dataclass(frozen=True)
class StyleDNAIntentEvent:
    style_name: str
    start_ms: int
    end_ms: int
    models: tuple[str, ...]
    style_tags: tuple[str, ...] = ()
    motif: str = ""
    intensity: float = 0.75
    confidence: float = 0.82
    section: str = ""
    effect: str = "On"
    priority: float = 0.85
    metadata: Mapping[str, object] = field(default_factory=dict)


def stem_event_to_prime_intent(event: StemIntentEvent) -> PrimeIntent:
    return PrimeIntent(
        source="stems",
        start_ms=event.start_ms,
        end_ms=event.end_ms,
        models=event.models,
        label=f"stem_{event.stem}_{event.cue}",
        effect=event.effect,
        motif=_motif_for_stem(event.stem, event.cue),
        stem=event.stem,
        section=event.section,
        intensity=event.intensity,
        confidence=event.confidence,
        priority=event.priority,
        layer="rhythmic" if event.stem in {"drums", "kick", "snare", "bass"} else "accent",
        style_tags=(),
        metadata={"cue": event.cue},
    )


def lyric_event_to_prime_intent(event: LyricIntentEvent) -> PrimeIntent:
    return PrimeIntent(
        source="lyrics",
        start_ms=event.start_ms,
        end_ms=event.end_ms,
        models=event.models,
        label=f"lyric_{_safe_label(event.emotion)}",
        effect=event.effect,
        motif=_motif_for_emotion(event.emotion),
        stem="vocals",
        section=event.section,
        intensity=event.intensity,
        confidence=event.confidence,
        priority=event.priority * 1.06,
        layer="accent",
        style_tags=(),
        metadata={"text": event.text, "emotion": event.emotion},
    )


def spatial_event_to_prime_intent(event: SpatialIntentEvent) -> PrimeIntent:
    return PrimeIntent(
        source="spatial",
        start_ms=event.start_ms,
        end_ms=event.end_ms,
        models=event.models,
        label=f"spatial_{_safe_label(event.motion)}",
        effect=event.effect,
        motif=_motif_for_motion(event.motion),
        stem="other",
        section=event.section,
        intensity=event.intensity,
        confidence=event.confidence,
        priority=event.priority,
        layer="ambient" if event.motion in {"wash", "bed", "field"} else "accent",
        style_tags=(),
        metadata={"motion": event.motion, "zone": event.zone},
    )


def style_dna_event_to_prime_intent(event: StyleDNAIntentEvent) -> PrimeIntent:
    return PrimeIntent(
        source="style_dna",
        start_ms=event.start_ms,
        end_ms=event.end_ms,
        models=event.models,
        label=f"style_{_safe_label(event.style_name)}",
        effect=event.effect,
        motif=event.motif,
        stem="other",
        section=event.section,
        intensity=event.intensity,
        confidence=event.confidence,
        priority=event.priority,
        layer="ambient",
        style_tags=event.style_tags,
        metadata={"style_name": event.style_name, **dict(event.metadata)},
    )


def build_multi_source_prime_intents(
    *,
    stems: Sequence[StemIntentEvent] = (),
    lyrics: Sequence[LyricIntentEvent] = (),
    spatial: Sequence[SpatialIntentEvent] = (),
    style_dna: Sequence[StyleDNAIntentEvent] = (),
) -> list[PrimeIntent]:
    intents: list[PrimeIntent] = []
    intents.extend(stem_event_to_prime_intent(event) for event in stems)
    intents.extend(lyric_event_to_prime_intent(event) for event in lyrics)
    intents.extend(spatial_event_to_prime_intent(event) for event in spatial)
    intents.extend(style_dna_event_to_prime_intent(event) for event in style_dna)
    return intents


def _motif_for_stem(stem: str, cue: str) -> str:
    stem_key = stem.strip().lower()
    cue_key = cue.strip().lower()
    if stem_key in {"drums", "kick", "snare", "bass"}:
        return "pulse_cascade"
    if stem_key in {"piano", "keyboard"}:
        return "wave_sweep"
    if stem_key == "guitar":
        return "spiral" if cue_key in {"riff", "solo"} else "wave_sweep"
    if stem_key in {"vocals", "vocal"}:
        return "sparkle_field"
    return "wave_sweep"


def _motif_for_emotion(emotion: str) -> str:
    key = emotion.strip().lower()
    if key in {"joy", "happy", "bright", "wonder", "magic"}:
        return "sparkle_field"
    if key in {"anger", "drive", "power", "intense"}:
        return "pulse_cascade"
    if key in {"sad", "tender", "soft", "nostalgic"}:
        return "wave_sweep"
    if key in {"mystery", "dream", "ethereal"}:
        return "orbit"
    return "wave_sweep"


def _motif_for_motion(motion: str) -> str:
    key = motion.strip().lower()
    if key in {"orbit", "circle", "rotate"}:
        return "orbit"
    if key in {"spiral", "helix", "dna"}:
        return "spiral"
    if key in {"burst", "cascade", "impact"}:
        return "pulse_cascade"
    if key in {"sparkle", "glitter", "starfield"}:
        return "sparkle_field"
    return "wave_sweep"


def _safe_label(value: str) -> str:
    cleaned = "_".join(str(value).strip().lower().split())
    return cleaned or "cue"


__all__ = [
    "LyricIntentEvent",
    "SpatialIntentEvent",
    "StemIntentEvent",
    "StyleDNAIntentEvent",
    "build_multi_source_prime_intents",
    "lyric_event_to_prime_intent",
    "spatial_event_to_prime_intent",
    "stem_event_to_prime_intent",
    "style_dna_event_to_prime_intent",
]
