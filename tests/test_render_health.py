from __future__ import annotations

from tools.render_health import evaluate_render_health


def _healthy_show() -> dict[str, object]:
    return {
        "model_effects": 2000,
        "models_with_effects": 200,
        "root_model_participation_ratio": 0.33,
        "general_effects_added": 0,
        "channel_overlap_count": 0,
        "drummer": {
            "timing_events": 100,
            "placed_effects": 100,
            "placed_by_type": {
                "kick": 30,
                "snare": 20,
                "hihat": 25,
                "tom": 15,
                "cymbal": 10,
            },
        },
    }


def _healthy_density() -> dict[str, object]:
    return {
        "sample_count": 4,
        "mean_bright_pixel_ratio": 0.012,
        "max_spread_ratio": 0.72,
    }


def test_render_health_accepts_realistic_native_preview() -> None:
    result = evaluate_render_health(
        _healthy_show(),
        _healthy_density(),
        require_drummer=True,
        require_native_choreography=True,
    )

    assert result["ok"] is True
    assert result["issues"] == []
    assert result["score"] >= 95.0
    assert result["metrics"]["drummer_placement_ratio"] == 1.0


def test_render_health_rejects_dark_sparse_output() -> None:
    density = _healthy_density()
    density["mean_bright_pixel_ratio"] = 0.0001
    density["max_spread_ratio"] = 0.05

    result = evaluate_render_health(_healthy_show(), density)

    assert result["ok"] is False
    assert any("too dark/sparse" in issue for issue in result["issues"])
    assert any("too spatially concentrated" in issue for issue in result["issues"])


def test_render_health_rejects_recovery_only_golden_preview() -> None:
    show = _healthy_show()
    show["general_effects_added"] = 42

    result = evaluate_render_health(
        show,
        _healthy_density(),
        require_native_choreography=True,
    )

    assert result["ok"] is False
    assert any("recovery choreography" in issue for issue in result["issues"])


def test_render_health_rejects_low_root_model_participation() -> None:
    show = _healthy_show()
    show["root_model_participation_ratio"] = 0.04

    result = evaluate_render_health(show, _healthy_density())

    assert result["ok"] is False
    assert any("root-model participation" in issue for issue in result["issues"])


def test_render_health_rejects_poor_drummer_coverage_and_missing_class() -> None:
    show = _healthy_show()
    show["drummer"] = {
        "timing_events": 100,
        "placed_effects": 60,
        "placed_by_type": {
            "kick": 20,
            "snare": 10,
            "hihat": 20,
            "tom": 10,
        },
    }

    result = evaluate_render_health(show, _healthy_density(), require_drummer=True)

    assert result["ok"] is False
    assert any("placement coverage is too low" in issue for issue in result["issues"])
    assert any("cymbal" in issue for issue in result["issues"])


def test_render_health_rejects_channel_overlap() -> None:
    show = _healthy_show()
    show["channel_overlap_count"] = 2

    result = evaluate_render_health(show, _healthy_density())

    assert result["ok"] is False
    assert any("channel overlap" in issue for issue in result["issues"])
