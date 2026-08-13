"""Compatibility entry point for the canonical effects orchestrator bridge.

The canonical implementation lives in :mod:`core.effects_orchestrator_bridge`.
This module exists so older sequencing code that imports the longer
``effects_orchestration_bridge`` name continues to delegate to the same active
implementation instead of growing a second orchestration path.
"""

from __future__ import annotations

from core.effects_orchestrator_bridge import (  # noqa: F401
    EffectsOrchestrationRunReport,
    effect_contract_path,
    orchestration_report_path,
    orchestrated_xsq_path,
    placement_report_path,
    run_effects_orchestration,
    xsq_render_report_path,
)

__all__ = [
    "EffectsOrchestrationRunReport",
    "effect_contract_path",
    "orchestration_report_path",
    "orchestrated_xsq_path",
    "placement_report_path",
    "run_effects_orchestration",
    "xsq_render_report_path",
]
