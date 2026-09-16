from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core import effect_engine


@dataclass(frozen=True)
class EffectEngineFailure:
    """One per-song failure reported by the legacy effect engine."""

    message: str
    audio: str | None = None
    detail: str = ""

    def as_dict(self) -> dict[str, str | None]:
        return {
            "message": self.message,
            "audio": self.audio,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class EffectEngineRunResult:
    """Stable caller-facing result for an effect-engine invocation."""

    version: str
    failures: tuple[EffectEngineFailure, ...] = ()

    @property
    def succeeded(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "succeeded": self.succeeded,
            "failures": [failure.as_dict() for failure in self.failures],
        }


class EffectEngineRunError(RuntimeError):
    """Raised when the legacy engine reports one or more swallowed failures."""

    def __init__(self, result: EffectEngineRunResult):
        self.result = result
        messages = [failure.message for failure in result.failures]
        details = " | ".join(messages[:8])
        if len(messages) > 8:
            details += f" | ... and {len(messages) - 8} more"
        super().__init__(f"Effect engine reported generation failure(s): {details}")


def _parse_failure(message: str) -> EffectEngineFailure:
    text = str(message).strip()
    payload = text[len("FAILED:") :].strip() if text.startswith("FAILED:") else text
    audio: str | None = None
    detail = payload
    if ": " in payload:
        audio_part, detail = payload.split(": ", 1)
        audio = audio_part.strip() or None
    return EffectEngineFailure(message=text, audio=audio, detail=detail.strip())


def run_effect_engine(
    version: str,
    argv: Iterable[str],
    *,
    engine_module: Any | None = None,
) -> EffectEngineRunResult:
    """Run the legacy engine while converting its FAILED log contract into exceptions.

    `effect_engine.main_for` historically catches per-song exceptions, logs a line
    beginning with ``FAILED:``, and then returns normally. This adapter centralizes
    that legacy behavior behind a typed result/error contract so supported callers
    cannot mistake a partial batch for success. The engine's original logger is
    always restored, including when `main_for` raises directly.
    """

    engine = effect_engine if engine_module is None else engine_module
    failures: list[EffectEngineFailure] = []
    original_log = engine.log

    def capture_log(message: str) -> None:
        text = str(message)
        if text.lstrip().startswith("FAILED:"):
            failures.append(_parse_failure(text.lstrip()))
        original_log(message)

    engine.log = capture_log
    try:
        engine.main_for(version, list(argv))
    finally:
        engine.log = original_log

    result = EffectEngineRunResult(version=version, failures=tuple(failures))
    if failures:
        raise EffectEngineRunError(result)
    return result
