from __future__ import annotations

import contextlib
import io
import json
import os
import queue
import subprocess
import sys
import threading
import traceback
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from drummer_review_gui import DrummerReviewWindow
from legacy_gui_branding import install_legacy_branding


APP_TITLE = "Helix Sequence Weaver"
BETA_LABEL = "Working Beta • Drummer X + V3"
LATEST_PRESET = "Helixville4 + Drummer V3"


def resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    return Path(frozen_root).resolve() if frozen_root else Path(__file__).resolve().parent


def workspace_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


RESOURCE_ROOT = resource_root()
WORKSPACE_ROOT = workspace_root()
BETA_WORKSPACE = WORKSPACE_ROOT / "beta_workspace"
LATEST_LAYOUT_DIR = BETA_WORKSPACE / "helixville4_latest"
LATEST_LAYOUT = LATEST_LAYOUT_DIR / "xlights_rgbeffects.xml"
DEFAULT_OUTPUT = BETA_WORKSPACE / "outputs"


def _external_or_resource(relative_path: str) -> Path:
    external = WORKSPACE_ROOT / relative_path
    return external if external.exists() else RESOURCE_ROOT / relative_path


def _best_layout_file(folder: Path) -> Path:
    backup = folder / "xlights_rgbeffects.xbkp"
    return backup if backup.exists() else folder / "xlights_rgbeffects.xml"


@dataclass(frozen=True)
class BetaRunOptions:
    profile: str
    template: Path
    audio: Path
    layout: Path
    output_dir: Path
    variants: int = 3
    vendor_bar: bool = False
    matrix_intelligence: bool = True
    polish: bool = True
    auto_shortlist: bool = True
    learning_memory: bool = True
    sync_lyrics: bool = False
    birdsong: bool = False
    birdsong_auto: bool = True
    birdsong_profile: str = "canopy"
    birdsong_intensity: float = 1.2
    birdsong_min_confidence: float = 0.45


def build_engine_argv(options: BetaRunOptions) -> list[str]:
    args = [
        "--profile",
        options.profile or "master",
        "--",
        "--template",
        str(options.template),
        "--audio",
        str(options.audio),
        "--layout-file",
        str(options.layout),
        "--output-dir",
        str(options.output_dir),
        "--variants",
        str(max(1, int(options.variants))),
        "--no-prompt",
        "--auto-timing-tracks",
        "--matrix-intelligence" if options.matrix_intelligence else "--no-matrix-intelligence",
        "--polish" if options.polish else "--no-polish",
        "--learning-memory" if options.learning_memory else "--no-learning-memory",
    ]
    if options.auto_shortlist:
        args.append("--auto-shortlist")
    if options.vendor_bar:
        args.append("--vendor-bar")
    if options.sync_lyrics:
        args.append("--sync-lyrics-heads")
    if options.birdsong:
        args.extend(
            [
                "--birdsong",
                "--birdsong-profile",
                options.birdsong_profile or "wild",
                "--birdsong-intensity",
                f"{float(options.birdsong_intensity):.2f}",
                "--birdsong-min-confidence",
                f"{float(options.birdsong_min_confidence):.2f}",
                "--birdsong-auto" if options.birdsong_auto else "--no-birdsong-auto",
            ]
        )
    else:
        args.extend(["--no-birdsong", "--no-birdsong-auto"])
    return args


def inspect_drummer_layout(layout_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ready": False,
        "state": "layout_missing",
        "submodel_count": 0,
        "pose_count": 0,
        "node_count": 0,
        "path": str(layout_path),
    }
    if not layout_path.exists():
        return result
    try:
        root = ET.parse(layout_path).getroot()
        drummer = root.find(".//models/model[@name='HX_SNOWMAN_DRUMMER']")
        if drummer is None:
            result["state"] = "drummer_missing"
            return result
        submodels = drummer.findall("./subModel")
        pose_names = [
            str(item.attrib.get("name", ""))
            for item in submodels
            if "_HIT_" in str(item.attrib.get("name", ""))
            or str(item.attrib.get("name", "")).endswith("_DOWNBEAT_IMPACT")
        ]
        result.update(
            {
                "ready": bool(drummer.attrib.get("CustomModel")) and len(pose_names) >= 8,
                "state": drummer.attrib.get("HelixImplementationState", "unknown"),
                "submodel_count": len(submodels),
                "pose_count": len(pose_names),
                "node_count": int(drummer.attrib.get("HelixNodeCount", "0") or 0),
            }
        )
    except (OSError, ValueError, ET.ParseError) as exc:
        result["state"] = f"invalid_layout: {exc}"
    return result


def latest_drummer_summary(output_dir: Path) -> dict[str, Any] | None:
    if not output_dir.exists():
        return None
    reports = sorted(
        output_dir.rglob("*.report.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for report_path in reports:
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        drummer = dict(payload.get("drummer", {}) or {})
        review = dict(drummer.get("review", {}) or {})
        quality = dict(payload.get("quality", {}) or {})
        output_contract = dict(payload.get("output_contract", {}) or {})
        return {
            "show_folder": str(output_contract.get("show_folder") or report_path.parent),
            "report_path": str(report_path),
            "fallback_mode": str(drummer.get("fallback_mode", "") or "unknown"),
            "analyzed_cues": int(drummer.get("analyzed_cues", 0) or 0),
            "placement_requests": int(drummer.get("placement_requests", 0) or 0),
            "placed_effects": int(drummer.get("placed_effects", 0) or 0),
            "timing_track_events": int(drummer.get("timing_track_events", 0) or 0),
            "analysis_profile": str(review.get("analysis_profile", "legacy_report") or "legacy_report"),
            "events": list(review.get("events", []) or []),
            "counts_by_type": dict(review.get("counts_by_type", {}) or {}),
            "average_confidence": float(review.get("average_confidence", 0.0) or 0.0),
            "average_velocity": float(review.get("average_velocity", 0.0) or 0.0),
            "low_confidence_events": int(review.get("low_confidence_events", 0) or 0),
            "placed_cues": int(review.get("placed_cues", 0) or 0),
            "unplaced_cues": int(review.get("unplaced_cues", 0) or 0),
            "cue_placement_ratio": float(review.get("cue_placement_ratio", 0.0) or 0.0),
            "duration_ms": int(review.get("duration_ms", 0) or 0),
            "quality_score": quality.get("score", ""),
            "quality_grade": quality.get("grade", ""),
        }
    return None


def self_check() -> int:
    checks: dict[str, bool] = {
        "template": (RESOURCE_ROOT / "template.xsq").exists(),
        "helixville4_layout": (RESOURCE_ROOT / "helixville4" / "xlights_rgbeffects.xml").exists(),
        "helixville4_manifest": (RESOURCE_ROOT / "helixville4" / "helixia_manifest.json").exists(),
        "drummer_v3_xmodel": (
            RESOURCE_ROOT
            / "fixtures"
            / "band_geometry"
            / "models"
            / "HX_SNOWMAN_DRUMMER_V3.xmodel"
        ).exists(),
    }
    try:
        from core import sequence_builder  # noqa: F401
        from tools.build_helixville4_finished_drummer_layout import (
            build_finished_drummer_layout,  # noqa: F401
        )

        checks["engine_import"] = True
        checks["layout_builder_import"] = True
    except Exception:
        checks["engine_import"] = False
        checks["layout_builder_import"] = False
        traceback.print_exc()
    payload = {
        "ok": all(checks.values()),
        "frozen": bool(getattr(sys, "frozen", False)),
        "resource_root": str(RESOURCE_ROOT),
        "workspace_root": str(WORKSPACE_ROOT),
        "checks": checks,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


class QueueWriter(io.TextIOBase):
    def __init__(self, emit: Callable[[tuple[str, Any]], None]) -> None:
        super().__init__()
        self.emit = emit
        self.buffer = ""

    def write(self, value: str) -> int:
        self.buffer += str(value)
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.emit(("log", line.rstrip()))
        return len(value)

    def flush(self) -> None:
        if self.buffer:
            self.emit(("log", self.buffer.rstrip()))
            self.buffer = ""


class HelixGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} — {BETA_LABEL}")
        self.geometry("1120x830")
        self.minsize(980, 720)
        self.configure(bg="#0a0a0b")
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._running = False
        self._latest_summary: dict[str, Any] | None = None

        self.layout_presets = self._layout_presets()
        self.profile_var = tk.StringVar(value="master")
        self.layout_preset_var = tk.StringVar(value=LATEST_PRESET)
        self.template_var = tk.StringVar(value=str(_external_or_resource("template.xsq")))
        self.audio_var = tk.StringVar(value="")
        self.layout_var = tk.StringVar(value=str(LATEST_LAYOUT))
        self.output_var = tk.StringVar(value=str(DEFAULT_OUTPUT))

        self.vendor_bar_var = tk.BooleanVar(value=False)
        self.matrix_var = tk.BooleanVar(value=True)
        self.polish_var = tk.BooleanVar(value=True)
        self.shortlist_var = tk.BooleanVar(value=True)
        self.learning_memory_var = tk.BooleanVar(value=True)
        self.sync_lyrics_var = tk.BooleanVar(value=False)
        self.birdsong_var = tk.BooleanVar(value=False)
        self.birdsong_auto_var = tk.BooleanVar(value=True)
        self.birdsong_profile_var = tk.StringVar(value="canopy")
        self.birdsong_intensity_var = tk.DoubleVar(value=1.2)
        self.birdsong_min_conf_var = tk.DoubleVar(value=0.45)
        self.variants_var = tk.IntVar(value=3)
        self.drummer_status_var = tk.StringVar(value="Preparing Drummer V3 layout…")
        self.run_summary_var = tk.StringVar(value="No beta run assessed yet.")

        self._configure_style()
        self._build_ui()
        install_legacy_branding(self, _external_or_resource)
        self.after(80, self._drain_events)
        self.after(140, self._prepare_latest_layout_on_startup)
        self.after(260, self._load_last_review)

    def _layout_presets(self) -> dict[str, Path]:
        presets = {LATEST_PRESET: LATEST_LAYOUT}
        candidates = [
            ("GP's House", _best_layout_file(RESOURCE_ROOT)),
            ("allmodels", _best_layout_file(RESOURCE_ROOT / "allmodels")),
            ("helixville", _best_layout_file(RESOURCE_ROOT / "helixville")),
        ]
        for label, path in candidates:
            if path.exists():
                presets[label] = path
        presets["Custom"] = Path("")
        return presets

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background="#121214", foreground="#f2f1ee", fieldbackground="#1a1a1e")
        style.configure("TFrame", background="#0a0a0b")
        style.configure("TLabelframe", background="#121214", foreground="#c4b48a")
        style.configure("TLabelframe.Label", background="#121214", foreground="#c4b48a")
        style.configure("TLabel", background="#121214", foreground="#f2f1ee")
        style.configure(
            "Header.TLabel",
            background="#0a0a0b",
            foreground="#f2f1ee",
            font=("Segoe UI", 21, "bold"),
        )
        style.configure(
            "Beta.TLabel",
            background="#0a0a0b",
            foreground="#d4785a",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background="#121214",
            foreground="#7aada4",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure("TButton", padding=(10, 7))
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 10, "bold"),
            foreground="#0a0a0b",
            background="#d4785a",
        )
        style.map("Primary.TButton", background=[("active", "#e08b70"), ("disabled", "#62463d")])
        style.configure("Review.TButton", foreground="#f2f1ee", background="#2a2523")
        style.map("Review.TButton", background=[("active", "#3a302c"), ("disabled", "#202024")])
        style.configure("TCheckbutton", background="#121214", foreground="#e4e1db")
        style.configure("TCombobox", fieldbackground="#1a1a1e", foreground="#f2f1ee")
        style.configure("Horizontal.TProgressbar", background="#d4785a", troughcolor="#29292d")

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 5}
        shell = ttk.Frame(self)
        shell.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        header = ttk.Frame(shell)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, text=APP_TITLE, style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text=BETA_LABEL, style="Beta.TLabel").pack(
            side=tk.LEFT,
            padx=14,
            pady=(9, 0),
        )

        context = ttk.LabelFrame(shell, text="1  Show files")
        context.pack(fill=tk.X, **pad)
        context.columnconfigure(1, weight=1)
        ttk.Label(context, text="Layout preset").grid(row=0, column=0, sticky="w", **pad)
        preset = ttk.Combobox(
            context,
            textvariable=self.layout_preset_var,
            values=list(self.layout_presets),
            state="readonly",
            width=28,
        )
        preset.grid(row=0, column=1, sticky="w", **pad)
        preset.bind("<<ComboboxSelected>>", lambda _event: self._apply_layout_preset())
        ttk.Button(
            context,
            text="Prepare Latest Layout",
            command=self._prepare_latest_layout,
        ).grid(row=0, column=2, sticky="w", **pad)

        self._path_row(context, 1, "Template XSQ", self.template_var, "file", [("XSQ", "*.xsq")])
        self._path_row(
            context,
            2,
            "Audio file",
            self.audio_var,
            "file",
            [("Audio", "*.wav *.mp3 *.flac *.ogg *.m4a *.aiff *.aif")],
        )
        self._path_row(
            context,
            3,
            "Layout file",
            self.layout_var,
            "file",
            [("xLights Layout", "*.xml *.xbkp")],
        )
        self._path_row(context, 4, "Output folder", self.output_var, "folder")

        drummer = ttk.LabelFrame(shell, text="2  Drummer readiness")
        drummer.pack(fill=tk.X, **pad)
        ttk.Label(drummer, textvariable=self.drummer_status_var, style="Status.TLabel").pack(
            side=tk.LEFT,
            padx=10,
            pady=7,
        )
        ttk.Label(drummer, textvariable=self.run_summary_var).pack(side=tk.LEFT, padx=18, pady=7)
        self.review_button = ttk.Button(
            drummer,
            text="Open Drummer X Review",
            style="Review.TButton",
            command=self._open_drummer_review,
            state=tk.DISABLED,
        )
        self.review_button.pack(side=tk.RIGHT, padx=10, pady=7)

        controls = ttk.LabelFrame(shell, text="3  Build options")
        controls.pack(fill=tk.X, **pad)
        ttk.Label(controls, text="Profile").grid(row=0, column=0, sticky="w", **pad)
        ttk.Combobox(
            controls,
            textvariable=self.profile_var,
            values=["master"],
            width=12,
            state="readonly",
        ).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(controls, text="Variants").grid(row=0, column=2, sticky="w", **pad)
        ttk.Spinbox(controls, from_=1, to=8, textvariable=self.variants_var, width=6).grid(
            row=0,
            column=3,
            sticky="w",
            **pad,
        )
        checks = [
            ("Matrix intelligence", self.matrix_var),
            ("Polish", self.polish_var),
            ("Auto shortlist", self.shortlist_var),
            ("Helix learning memory", self.learning_memory_var),
            ("Lyric/head sync", self.sync_lyrics_var),
            ("Vendor gate (strict)", self.vendor_bar_var),
        ]
        for index, (label, variable) in enumerate(checks):
            ttk.Checkbutton(controls, text=label, variable=variable).grid(
                row=1 + index // 3,
                column=index % 3,
                sticky="w",
                **pad,
            )

        birdsong = ttk.LabelFrame(shell, text="Optional birdsong overlay")
        birdsong.pack(fill=tk.X, **pad)
        ttk.Checkbutton(birdsong, text="Enable", variable=self.birdsong_var).grid(
            row=0,
            column=0,
            **pad,
        )
        ttk.Checkbutton(
            birdsong,
            text="Confidence auto-enable",
            variable=self.birdsong_auto_var,
        ).grid(row=0, column=1, **pad)
        ttk.Label(birdsong, text="Profile").grid(row=0, column=2, **pad)
        ttk.Combobox(
            birdsong,
            textvariable=self.birdsong_profile_var,
            values=["wild", "canopy", "ambient", "dawn"],
            width=10,
            state="readonly",
        ).grid(row=0, column=3, **pad)
        ttk.Label(birdsong, text="Intensity").grid(row=0, column=4, **pad)
        ttk.Spinbox(
            birdsong,
            from_=0.2,
            to=2.4,
            increment=0.1,
            textvariable=self.birdsong_intensity_var,
            width=7,
        ).grid(row=0, column=5, **pad)
        ttk.Label(birdsong, text="Min confidence").grid(row=0, column=6, **pad)
        ttk.Spinbox(
            birdsong,
            from_=0.0,
            to=1.0,
            increment=0.05,
            textvariable=self.birdsong_min_conf_var,
            width=7,
        ).grid(row=0, column=7, **pad)

        actions = ttk.Frame(shell)
        actions.pack(fill=tk.X, padx=8, pady=(7, 4))
        self.run_button = ttk.Button(
            actions,
            text="Build Sequence",
            style="Primary.TButton",
            command=self._run_sequence,
        )
        self.run_button.pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="Open Output Folder",
            command=self._open_output_folder,
        ).pack(side=tk.LEFT, padx=8)
        self.status_label = ttk.Label(actions, text="Ready")
        self.status_label.pack(side=tk.LEFT, padx=12)
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=180)
        self.progress.pack(side=tk.RIGHT, padx=4)

        log_frame = ttk.LabelFrame(shell, text="Live run log")
        log_frame.pack(fill=tk.BOTH, expand=True, **pad)
        self.log_text = tk.Text(
            log_frame,
            wrap=tk.WORD,
            height=15,
            bg="#0a0a0b",
            fg="#e4e1db",
            insertbackground="#e4e1db",
            relief=tk.FLAT,
            font=("Cascadia Mono", 9),
        )
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=8)

    def _path_row(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        kind: str,
        filetypes: list[tuple[str, str]] | None = None,
    ) -> None:
        pad = {"padx": 8, "pady": 5}
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            columnspan=2,
            sticky="ew",
            **pad,
        )
        if kind == "file":
            command = lambda: self._browse_file(variable, filetypes or [("All files", "*.*")])
        else:
            command = lambda: self._browse_folder(variable)
        ttk.Button(parent, text="Browse", command=command).grid(
            row=row,
            column=3,
            sticky="w",
            **pad,
        )

    def _browse_file(
        self,
        target_var: tk.StringVar,
        filetypes: list[tuple[str, str]],
    ) -> None:
        selected = filedialog.askopenfilename(initialdir=str(WORKSPACE_ROOT), filetypes=filetypes)
        if selected:
            target_var.set(selected)
            if target_var is self.layout_var:
                self.layout_preset_var.set("Custom")
                self._refresh_drummer_status()

    def _browse_folder(self, target_var: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=str(WORKSPACE_ROOT))
        if selected:
            target_var.set(selected)

    def _log(self, message: str) -> None:
        self.log_text.insert(tk.END, str(message) + "\n")
        self.log_text.see(tk.END)

    def _apply_layout_preset(self) -> None:
        preset = self.layout_preset_var.get()
        if preset == "Custom":
            return
        selected = self.layout_presets.get(preset)
        if selected:
            self.layout_var.set(str(selected))
            output = DEFAULT_OUTPUT if preset == LATEST_PRESET else selected.parent / "outputs"
            self.output_var.set(str(output))
            self._refresh_drummer_status()

    def _prepare_latest_layout_on_startup(self) -> None:
        self._prepare_latest_layout(announce=False)

    def _prepare_latest_layout(self, announce: bool = True) -> None:
        if self._running:
            return
        self.status_label.configure(text="Preparing layout…")
        self._log("Preparing Helixville4 with the authored Drummer V3 xmodel…")
        try:
            from tools.build_helixville4_finished_drummer_layout import (
                build_finished_drummer_layout,
            )

            payload = build_finished_drummer_layout(LATEST_LAYOUT_DIR)
            drummer = dict(payload.get("finished_band_export", {}) or {})
            self.layout_presets[LATEST_PRESET] = LATEST_LAYOUT
            self.layout_preset_var.set(LATEST_PRESET)
            self.layout_var.set(str(LATEST_LAYOUT))
            self.output_var.set(str(DEFAULT_OUTPUT))
            self._refresh_drummer_status()
            self.status_label.configure(text="Ready")
            self._log(
                "Latest layout ready: "
                f"{drummer.get('drummer_submodel_count', 0)} submodels, "
                f"{drummer.get('drummer_node_count', 0)} nodes."
            )
            if announce:
                messagebox.showinfo(
                    "Latest Layout Ready",
                    "Helixville4 + Drummer V3 is generated and selected.",
                )
        except Exception as exc:
            self.status_label.configure(text="Layout preparation failed")
            self.drummer_status_var.set(f"Drummer layout unavailable • {exc}")
            self._log(f"Layout preparation failed: {exc}")
            self._log(traceback.format_exc())
            if announce:
                messagebox.showerror(
                    "Layout Build Failed",
                    "Could not prepare the latest Helixville4 layout. See the log.",
                )

    def _refresh_drummer_status(self) -> None:
        info = inspect_drummer_layout(Path(self.layout_var.get().strip()))
        if info["ready"]:
            self.drummer_status_var.set(
                f"READY • {info['state']} • {info['pose_count']} poses • "
                f"{info['submodel_count']} submodels • {info['node_count']} nodes"
            )
        else:
            self.drummer_status_var.set(f"NOT READY • {info['state']}")

    def _load_last_review(self) -> None:
        summary = latest_drummer_summary(Path(self.output_var.get().strip() or DEFAULT_OUTPUT))
        if summary is None:
            return
        self._latest_summary = summary
        self.review_button.configure(state=tk.NORMAL)

    def _open_drummer_review(self) -> None:
        summary = self._latest_summary or latest_drummer_summary(
            Path(self.output_var.get().strip() or DEFAULT_OUTPUT)
        )
        if summary is None:
            messagebox.showinfo(
                "No Drummer Review Yet",
                "Build a sequence first. Helix will then expose the classified hit lanes and placement audit.",
            )
            return
        self._latest_summary = summary
        review = DrummerReviewWindow(self, summary)
        review.transient(self)
        review.focus_set()

    def _run_options(self) -> BetaRunOptions:
        return BetaRunOptions(
            profile=self.profile_var.get().strip() or "master",
            template=Path(self.template_var.get().strip()),
            audio=Path(self.audio_var.get().strip()),
            layout=Path(self.layout_var.get().strip()),
            output_dir=Path(self.output_var.get().strip()),
            variants=max(1, int(self.variants_var.get())),
            vendor_bar=bool(self.vendor_bar_var.get()),
            matrix_intelligence=bool(self.matrix_var.get()),
            polish=bool(self.polish_var.get()),
            auto_shortlist=bool(self.shortlist_var.get()),
            learning_memory=bool(self.learning_memory_var.get()),
            sync_lyrics=bool(self.sync_lyrics_var.get()),
            birdsong=bool(self.birdsong_var.get()),
            birdsong_auto=bool(self.birdsong_auto_var.get()),
            birdsong_profile=self.birdsong_profile_var.get().strip() or "wild",
            birdsong_intensity=float(self.birdsong_intensity_var.get()),
            birdsong_min_confidence=float(self.birdsong_min_conf_var.get()),
        )

    def _validate_options(self, options: BetaRunOptions) -> bool:
        checks = [
            (options.audio, "Choose an audio file before running."),
            (options.layout, "The selected layout file does not exist."),
            (options.template, "The selected template XSQ does not exist."),
        ]
        for path, message in checks:
            if not path.is_file():
                messagebox.showwarning("Missing Input", message)
                return False
        drummer = inspect_drummer_layout(options.layout)
        if not drummer["ready"]:
            proceed = messagebox.askyesno(
                "Drummer V3 Not Ready",
                "This layout does not expose the latest Drummer V3 pose model. "
                "Continue with fallback routing?",
            )
            if not proceed:
                return False
        options.output_dir.mkdir(parents=True, exist_ok=True)
        return True

    def _run_sequence(self) -> None:
        if self._running:
            return
        options = self._run_options()
        if not self._validate_options(options):
            return
        argv = build_engine_argv(options)
        self._set_running(True)
        self._log("")
        self._log("Starting beta sequence build.")
        self._log("Engine arguments: " + " ".join(argv))
        threading.Thread(
            target=self._run_engine,
            args=(argv, options.output_dir),
            daemon=True,
        ).start()

    def _run_engine(self, argv: list[str], output_dir: Path) -> None:
        writer = QueueWriter(self._events.put)
        rc = 1
        try:
            from core.sequence_builder import main as run_engine

            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                rc = int(run_engine(argv) or 0)
        except SystemExit as exc:
            rc = int(exc.code) if isinstance(exc.code, int) else 1
        except BaseException:
            traceback.print_exc(file=writer)
            rc = 1
        finally:
            writer.flush()
        summary = latest_drummer_summary(output_dir) if rc == 0 else None
        self._events.put(("done", {"return_code": rc, "summary": summary}))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "log":
                    self._log(str(payload))
                elif kind == "done":
                    self._finish_run(dict(payload))
        except queue.Empty:
            pass
        self.after(90, self._drain_events)

    def _finish_run(self, payload: dict[str, Any]) -> None:
        rc = int(payload.get("return_code", 1))
        self._set_running(False)
        if rc == 0:
            self.status_label.configure(text="Completed")
            self._log("Beta run complete.")
            summary = payload.get("summary")
            if isinstance(summary, dict):
                self._latest_summary = summary
                self.review_button.configure(state=tk.NORMAL)
                summary_text = (
                    f"Drummer: {summary['placed_effects']}/{summary['placement_requests']} "
                    f"effects placed from {summary['analyzed_cues']} cues • "
                    f"{summary['fallback_mode']} detection"
                )
                if summary.get("events"):
                    summary_text += (
                        f" • {float(summary.get('average_confidence', 0.0)) * 100:.0f}% avg confidence"
                    )
                if summary.get("quality_grade") or summary.get("quality_score") != "":
                    quality = f"{summary.get('quality_grade', '')} {summary.get('quality_score', '')}".strip()
                    summary_text += f" • quality {quality}"
                self.run_summary_var.set(summary_text)
                self._log(summary_text)
                self._log(f"Assessment report: {summary['report_path']}")
            else:
                self.run_summary_var.set("Run completed; no report was found for assessment.")
        else:
            self.status_label.configure(text=f"Failed ({rc})")
            self.run_summary_var.set("Run failed. The live log contains the engine error.")
            self._log(f"Run failed with exit code {rc}.")

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.run_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        if running:
            self.status_label.configure(text="Running…")
            self.progress.start(12)
        else:
            self.progress.stop()

    def _open_output_folder(self) -> None:
        summary_folder = str((self._latest_summary or {}).get("show_folder", "") or "").strip()
        folder = Path(summary_folder or self.output_var.get().strip() or DEFAULT_OUTPUT)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror("Open Folder Failed", str(exc))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-check" in args:
        return self_check()
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    os.chdir(WORKSPACE_ROOT)
    app = HelixGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())