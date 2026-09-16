from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.effect_engine_runner import EffectEngineRunError, run_effect_engine


def _fake_engine(main_for, messages: list[str]):
    def log(message: str) -> None:
        messages.append(str(message))

    return SimpleNamespace(main_for=main_for, log=log)


def test_runner_returns_typed_success_and_preserves_logger() -> None:
    messages: list[str] = []

    def main_for(_version: str, _argv: list[str]) -> None:
        engine.log("generated song.wav")

    engine = _fake_engine(main_for, messages)
    original_log = engine.log

    result = run_effect_engine("v27.3", ["--audio", "song.wav"], engine_module=engine)

    assert result.succeeded is True
    assert result.failures == ()
    assert result.as_dict()["succeeded"] is True
    assert messages == ["generated song.wav"]
    assert engine.log is original_log


def test_runner_promotes_one_swallowed_failure_with_structured_evidence() -> None:
    messages: list[str] = []

    def main_for(_version: str, _argv: list[str]) -> None:
        engine.log("FAILED: song.wav: RuntimeError('post-generation failure')")

    engine = _fake_engine(main_for, messages)
    original_log = engine.log

    with pytest.raises(EffectEngineRunError) as exc_info:
        run_effect_engine("v27.3", ["--audio", "song.wav"], engine_module=engine)

    result = exc_info.value.result
    assert result.succeeded is False
    assert len(result.failures) == 1
    assert result.failures[0].audio == "song.wav"
    assert result.failures[0].detail == "RuntimeError('post-generation failure')"
    assert "song.wav" in str(exc_info.value)
    assert messages == ["FAILED: song.wav: RuntimeError('post-generation failure')"]
    assert engine.log is original_log


def test_runner_aggregates_batch_failures_instead_of_stopping_after_first() -> None:
    messages: list[str] = []

    def main_for(_version: str, _argv: list[str]) -> None:
        engine.log("FAILED: one.wav: ValueError('bad one')")
        engine.log("continuing batch")
        engine.log("FAILED: two.wav: OSError('bad two')")

    engine = _fake_engine(main_for, messages)

    with pytest.raises(EffectEngineRunError) as exc_info:
        run_effect_engine("v27.3", ["--audio", "one.wav", "two.wav"], engine_module=engine)

    failures = exc_info.value.result.failures
    assert [failure.audio for failure in failures] == ["one.wav", "two.wav"]
    assert "bad one" in failures[0].detail
    assert "bad two" in failures[1].detail
    assert messages == [
        "FAILED: one.wav: ValueError('bad one')",
        "continuing batch",
        "FAILED: two.wav: OSError('bad two')",
    ]


def test_runner_restores_logger_when_engine_raises_directly() -> None:
    messages: list[str] = []

    def main_for(_version: str, _argv: list[str]) -> None:
        raise LookupError("direct failure")

    engine = _fake_engine(main_for, messages)
    original_log = engine.log

    with pytest.raises(LookupError, match="direct failure"):
        run_effect_engine("v27.3", [], engine_module=engine)

    assert engine.log is original_log
