from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Iterable, Optional

from core import engine_profiles
from core.effects_orchestrator_bridge import EffectsOrchestrationRunReport, run_effects_orchestration
from core.run_config import RunConfig
from core.run_manager import RunManager

NO_EFFECTS_ORCHESTRATOR_FLAG = "--no-effects-orchestrator"
PROMOTE_ORCHESTRATOR_TEMPLATE_FLAG = "--promote-orchestrated-template"
NO_ORCHESTRATOR_TEMPLATE_PROMOTION_FLAG = "--no-orchestrator-template-promotion"
ORCHESTRATOR_ONLY_FLAGS = {
    NO_EFFECTS_ORCHESTRATOR_FLAG,
    PROMOTE_ORCHESTRATOR_TEMPLATE_FLAG,
    NO_ORCHESTRATOR_TEMPLATE_PROMOTION_FLAG,
}


def _effect_engine():
    from core import effect_engine

    return effect_engine


def available_profiles() -> list[engine_profiles.EngineProfile]:
    return engine_profiles.available_profiles()


def available_versions() -> list[str]:
    return [profile.version for profile in available_profiles()]


def _orchestration_enabled(engine_args: list[str] | None) -> bool:
    args = engine_args or []
    return NO_EFFECTS_ORCHESTRATOR_FLAG not in args


def _orchestrator_template_promotion_enabled(engine_args: list[str] | None) -> bool:
    args = engine_args or []
    if NO_EFFECTS_ORCHESTRATOR_FLAG in args or NO_ORCHESTRATOR_TEMPLATE_PROMOTION_FLAG in args:
        return False
    return PROMOTE_ORCHESTRATOR_TEMPLATE_FLAG in args


def _clean_engine_args(engine_args: list[str] | None) -> list[str] | None:
    if engine_args is None:
        return None
    return [arg for arg in engine_args if arg not in ORCHESTRATOR_ONLY_FLAGS]


def _set_or_replace_arg(args: list[str], flag: str, value: str) -> list[str]:
    out: list[str] = []
    replaced = False
    idx = 0
    while idx < len(args):
        item = args[idx]
        if item == flag:
            out.extend([flag, value])
            replaced = True
            idx += 2
            continue
        out.append(item)
        idx += 1
    if not replaced:
        out.extend([flag, value])
    return out


def _promote_orchestrated_template(
    engine_args: list[str] | None,
    report: EffectsOrchestrationRunReport | None,
) -> list[str] | None:
    """Optionally feed orchestrated planning back into the canonical renderer path.

    The orchestrator writes an inspected `*.orchestrated.xsq` from the user-provided
    template when possible. Promotion is intentionally explicit so the orchestrator
    can remain on by default for reports/contracts while broad test runs and normal
    sidecar users are not surprised by a generated template replacing their input.
    """
    cleaned = _clean_engine_args(engine_args)
    if not _orchestrator_template_promotion_enabled(engine_args):
        return cleaned
    if report is None or not report.invoked or not report.xsq_written or not report.orchestrated_xsq_path:
        return cleaned
    promoted_template = str(Path(report.orchestrated_xsq_path))
    return _set_or_replace_arg(list(cleaned or []), "--template", promoted_template)


def run_profile(profile_id: str | None, engine_args: list[str] | None = None) -> None:
    """Run a sequencing profile with integrated run tracking.
    
    Creates a RunConfig from engine_args, initializes a RunManager, and wraps
    the build logic with try/except to track success/failure.
    
    Args:
        profile_id: Profile identifier (e.g., "master", "v27.3").
        engine_args: CLI arguments to pass to the effect engine.
    
    Raises:
        SystemExit: On configuration or runtime errors after logging details.
    """
    try:
        profile = engine_profiles.resolve_profile(profile_id)
    except ValueError as e:
        print(f"ERROR: Invalid profile '{profile_id}': {e}", file=sys.stderr)
        raise SystemExit(1)
    
    # Create RunConfig from engine arguments
    try:
        config = RunConfig.from_engine_args(profile_id or "master", engine_args or [])
    except (ValueError, TypeError) as e:
        print(f"ERROR: Invalid arguments: {e}", file=sys.stderr)
        print("Use --help for usage information.", file=sys.stderr)
        raise SystemExit(1)
    
    # Initialize run manager
    try:
        manager = RunManager(config)
    except (OSError, IOError) as e:
        print(f"ERROR: Failed to initialize run directory: {e}", file=sys.stderr)
        raise SystemExit(1)
    
    try:
        report: EffectsOrchestrationRunReport | None = None
        if _orchestration_enabled(engine_args):
            report = run_effects_orchestration(engine_args)
            if report.invoked:
                print(f"effects_orchestrator: invoked passes={len(report.passes)} report={report.report_path}")
            else:
                print(f"effects_orchestrator: unavailable error={report.error}")
        
        effective_engine_args = _promote_orchestrated_template(engine_args, report)
        if report is not None and report.invoked and report.xsq_written and effective_engine_args != _clean_engine_args(engine_args):
            print(f"effects_orchestrator: promoted template={report.orchestrated_xsq_path}")
        
        # Run the effect engine
        _effect_engine().main_for(profile.version, effective_engine_args)
        
        # Finalize with success
        manager.finalize(success=True)
        print(f"SUCCESS: Run completed. Manifest: {manager.manifest_path}", file=sys.stderr)
        
    except KeyboardInterrupt:
        error_summary = "Run interrupted by user (Ctrl+C)"
        print(f"\nINTERRUPTED: {error_summary}", file=sys.stderr)
        manager.finalize(success=False, error_summary=error_summary)
        raise SystemExit(130)
        
    except Exception as e:
        error_summary = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        print(f"ERROR: {error_summary}", file=sys.stderr)
        print(f"Manifest saved to: {manager.manifest_path}", file=sys.stderr)
        manager.finalize(success=False, error_summary=error_summary)
        raise SystemExit(1)


def run_version(version: str, engine_args: list[str] | None = None) -> None:
    """Run a specific version profile."""
    run_profile(version, engine_args)


def build_sequence_set(profiles: Iterable[str | None], engine_args: list[str] | None = None) -> None:
    """Build sequences for multiple profiles."""
    for profile_id in profiles:
        run_profile(profile_id, engine_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Helix Sequencer: Automated audio-to-light sequencing for xLights.",
        epilog=(
            "Engine arguments (after --): Passed directly to the effect engine.\n"
            "  --no-effects-orchestrator: Skip orchestration pass.\n"
            "  --promote-orchestrated-template: Use orchestrator output as input template.\n"
            "  --no-orchestrator-template-promotion: Force sidecar-only behavior."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit.",
    )
    parser.add_argument(
        "--list-versions",
        action="store_true",
        help=argparse.SUPPRESS,  # Hidden for backwards compatibility
    )
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        help="Profile to run (can specify multiple times). Defaults to active master profile.",
    )
    parser.add_argument(
        "--version-id",
        action="append",
        dest="profiles",
        help=argparse.SUPPRESS,  # Hidden for backwards compatibility
    )
    parser.add_argument(
        "engine_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the effect engine (after --).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entrypoint with comprehensive error handling.
    
    Args:
        argv: CLI arguments (uses sys.argv if not provided).
    
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    try:
        parser = build_parser()
        args = parser.parse_args(argv)

        if args.list_profiles or args.list_versions:
            profiles = available_profiles()
            if not profiles:
                print("ERROR: No profiles available.", file=sys.stderr)
                return 1
            for profile in profiles:
                print(f"{profile.profile_id}: {profile.title} [{profile.version}]")
            return 0

        profiles = args.profiles or [engine_profiles.ACTIVE_PROFILE_ID]
        engine_args = list(args.engine_args)
        if engine_args[:1] == ["--"]:
            engine_args = engine_args[1:]
        
        build_sequence_set(profiles, engine_args)
        return 0
        
    except SystemExit as e:
        # Let SystemExit through (raised by run_profile or others)
        return e.code if isinstance(e.code, int) else (1 if e.code else 0)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"FATAL: {type(e).__name__}: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
