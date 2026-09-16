from __future__ import annotations

from threading import Event, Thread
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


def test_runner_serializes_calls_that_share_legacy_global_logger_state() -> None:
    """A second strict run must not replace the logger while the first is active."""

    first_entered = Event()
    release_first = Event()
    second_started = Event()
    second_entered = Event()
    errors: list[BaseException] = []

    def first_main(_version: str, _argv: list[str]) -> None:
        first_entered.set()
        assert release_first.wait(timeout=2.0)

    def second_main(_version: str, _argv: list[str]) -> None:
        second_entered.set()

    first_engine = _fake_engine(first_main, [])
    second_engine = _fake_engine(second_main, [])

    def run_first() -> None:
        try:
            run_effect_engine("v27.3", [], engine_module=first_engine)
        except BaseException as exc:  # pragma: no cover - assertion aid
            errors.append(exc)

    def run_second() -> None:
        second_started.set()
        try:
            run_effect_engine("v27.3", [], engine_module=second_engine)
        except BaseException as exc:  # pragma: no cover - assertion aid
            errors.append(exc)

    first_thread = Thread(target=run_first)
    second_thread = Thread(target=run_second)
    first_thread.start()
    assert first_entered.wait(timeout=1.0)
    second_thread.start()
    assert second_started.wait(timeout=1.0)

    # The second thread has reached the runner but cannot enter its legacy
    # engine until the first invocation releases the adapter lock.
    assert second_entered.wait(timeout=0.05) is False
    release_first.set()

    first_thread.join(timeout=2.0)
    second_thread.join(timeout=2.0)
    assert first_thread.is_alive() is False
    assert second_thread.is_alive() is False
    assert second_entered.is_set() is True
    assert errors == []
