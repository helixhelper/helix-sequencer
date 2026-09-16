from __future__ import annotations

import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

try:
    from PIL import Image, ImageTk  # type: ignore
except Exception:  # pragma: no cover - source installs may omit Pillow
    Image = None
    ImageTk = None


# These are the same support destinations used by the original Helix launcher.
SUPPORT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=BB6366BT755H6"
AUTHOR_SUPPORT_URL = "https://paypal.me/ryankorkowski"

MASCOT_FILENAME = "helixmascot.jpg"
LOGO_FILENAME = "c82.png"
ICON_FILENAME = "app_icon.ico"
INSTRUCTIONS_FILENAMES = ("SEQUENCER_INSTRUCTIONS.txt", "BETA_START_HERE.txt")
LEGAL_FILENAMES = ("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.md")

PathResolver = Callable[[str], Path]


def _read_first(resolve: PathResolver, names: tuple[str, ...]) -> tuple[str, Path | None]:
    for name in names:
        path = resolve(name)
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8"), path
            except OSError:
                continue
    return "", None


def instructions_text(resolve: PathResolver) -> str:
    text, _path = _read_first(resolve, INSTRUCTIONS_FILENAMES)
    return text or (
        "Helix instructions are not available in this build.\n\n"
        "Choose a template XSQ, audio file, and layout, then use Build Sequence."
    )


def legal_text(resolve: PathResolver) -> str:
    sections: list[str] = []
    for name in LEGAL_FILENAMES:
        path = resolve(name)
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if body:
            sections.append(f"{name}\n{'=' * len(name)}\n{body}")
    if sections:
        return "\n\n\n".join(sections)
    return "No bundled legal/license notices were found in this build."


def progress_stage_for_line(message: str) -> str | None:
    """Translate noisy engine output into a useful human-readable progress stage."""

    text = str(message or "").strip().lower()
    if not text:
        return None
    if any(token in text for token in ("traceback", "fatal", "error:", "failed", "exception")):
        return "Problem encountered"
    if any(
        token in text
        for token in (
            "beta run complete",
            "completed successfully",
            "sequence complete",
            "success: run completed",
        )
    ):
        return "Completed"
    if any(token in text for token in ("show folder", "mediafile", "writing xsq", "finaliz", "xlights_networks", "output_contract")):
        return "Writing xLights show files"
    if any(token in text for token in ("quality", "shortlist", "variant", "polish", "scor")):
        return "Evaluating and polishing variants"
    if any(token in text for token in ("drummer", "kick", "snare", "hihat", "hi-hat", "cymbal", " tom", "drum ")):
        return "Building the drummer performance"
    if any(token in text for token in ("effect", "choreograph", "placement", "model row", "render")):
        return "Building model effects and choreography"
    if any(token in text for token in ("audio", "beatgrid", "beat grid", "librosa", "onset", "tempo", "bpm", "analysis")):
        return "Analyzing audio and musical structure"
    if any(token in text for token in ("preparing helixville", "latest layout", "layout ready", "prepare layout")):
        return "Preparing Helixville layout"
    if any(token in text for token in ("starting beta sequence build", "engine arguments")):
        return "Starting sequence build"
    return None


def _load_photo(path: Path, max_width: int, max_height: int) -> tk.PhotoImage | None:
    if not path.is_file():
        return None
    if Image is not None and ImageTk is not None:
        try:
            with Image.open(path) as opened:
                image = opened.convert("RGBA")
                image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(image)
        except Exception:
            return None
    if path.suffix.lower() == ".png":
        try:
            return tk.PhotoImage(file=str(path))
        except tk.TclError:
            return None
    return None


def _text_window(parent: tk.Misc, title: str, text: str, geometry: str = "820x680") -> None:
    window = tk.Toplevel(parent)
    window.title(title)
    window.geometry(geometry)
    window.minsize(620, 460)
    window.configure(bg="#0a0a0b")

    viewer = ScrolledText(
        window,
        wrap=tk.WORD,
        bg="#0f1114",
        fg="#e4e1db",
        insertbackground="#e4e1db",
        relief=tk.FLAT,
        padx=14,
        pady=14,
        font=("Segoe UI", 10),
    )
    viewer.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 8))
    viewer.insert("1.0", text)
    viewer.configure(state=tk.DISABLED)

    ttk.Button(window, text="Close", command=window.destroy).pack(pady=(0, 12))
    window.transient(parent)
    window.lift()
    viewer.focus_set()


def open_instructions(parent: tk.Misc, resolve: PathResolver) -> None:
    _text_window(parent, "Instructions and Troubleshooting", instructions_text(resolve))


def open_legal(parent: tk.Misc, resolve: PathResolver) -> None:
    _text_window(parent, "Helix Legal / License", legal_text(resolve))


def _open_support(url: str) -> None:
    try:
        webbrowser.open(url, new=2)
    except Exception as exc:  # pragma: no cover - desktop/browser integration
        messagebox.showerror("Could Not Open Browser", str(exc))


def _invoke_root_method(root: tk.Tk, method_name: str) -> None:
    callback = getattr(root, method_name, None)
    if callable(callback):
        callback()


class ProgressReportWindow(tk.Toplevel):
    """Live user-facing view of what the sequencer is doing right now."""

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root)
        self.root = root
        self.title("Helix Progress Report")
        self.geometry("780x540")
        self.minsize(620, 420)
        self.configure(bg="#0a0a0b")
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self._running = False
        self._started_at: float | None = None
        self._tick_job: str | None = None

        self.status_var = tk.StringVar(value="Ready")
        self.stage_var = tk.StringVar(value="Waiting for a sequence run.")
        self.elapsed_var = tk.StringVar(value="Elapsed: 0:00")

        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=14, pady=(14, 8))
        ttk.Label(top, text="Progress Report", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(top, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.RIGHT)

        stage = ttk.LabelFrame(self, text="What Helix is doing")
        stage.pack(fill=tk.X, padx=14, pady=(0, 8))
        ttk.Label(stage, textvariable=self.stage_var, font=("Segoe UI", 11, "bold")).pack(
            side=tk.LEFT,
            padx=10,
            pady=8,
        )
        ttk.Label(stage, textvariable=self.elapsed_var).pack(side=tk.RIGHT, padx=10, pady=8)

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=14, pady=(0, 8))

        log_frame = ttk.LabelFrame(self, text="Live details")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 8))
        self.log = ScrolledText(
            log_frame,
            wrap=tk.WORD,
            bg="#0a0a0b",
            fg="#e4e1db",
            insertbackground="#e4e1db",
            relief=tk.FLAT,
            padx=10,
            pady=10,
            font=("Cascadia Mono", 9),
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.log.configure(state=tk.DISABLED)

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, padx=14, pady=(0, 12))
        ttk.Button(
            actions,
            text="Open Output",
            command=lambda: _invoke_root_method(root, "_open_output_folder"),
        ).pack(side=tk.LEFT)
        ttk.Button(actions, text="Hide", command=self.withdraw).pack(side=tk.RIGHT)

        self.withdraw()

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def begin(self) -> None:
        self.show()
        self._running = True
        self._started_at = time.monotonic()
        self.status_var.set("RUNNING")
        self.stage_var.set("Starting sequence build")
        self.elapsed_var.set("Elapsed: 0:00")
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)
        self.progress.start(12)
        self._schedule_tick()

    def set_running(self, running: bool) -> None:
        self._running = bool(running)
        if running:
            if self._started_at is None:
                self._started_at = time.monotonic()
            self.status_var.set("RUNNING")
            self.progress.start(12)
            self._schedule_tick()
        else:
            self.progress.stop()
            if self.status_var.get() == "RUNNING":
                self.status_var.set("FINISHING")

    def append(self, message: str) -> None:
        text = str(message)
        stage = progress_stage_for_line(text)
        current_status = self.status_var.get()
        if stage:
            # Completion is terminal for normal informational lines. The engine emits
            # assessment/quality summaries after SUCCESS, which must not make the GUI
            # look as if it resumed an earlier stage.
            if stage == "Problem encountered":
                self.stage_var.set(stage)
                self.status_var.set("ATTENTION")
            elif current_status != "COMPLETE":
                self.stage_var.set(stage)
                if stage == "Completed":
                    self.status_var.set("COMPLETE")
                    self._running = False
                    self.progress.stop()

        stamp = time.strftime("%H:%M:%S")
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, f"[{stamp}] {text}\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _schedule_tick(self) -> None:
        if self._tick_job is None:
            self._tick_job = self.after(500, self._tick)

    def _tick(self) -> None:
        self._tick_job = None
        if self._started_at is not None:
            elapsed = max(0, int(time.monotonic() - self._started_at))
            minutes, seconds = divmod(elapsed, 60)
            self.elapsed_var.set(f"Elapsed: {minutes}:{seconds:02d}")
        if self._running:
            self._schedule_tick()


def _install_progress_report_hooks(root: tk.Tk) -> ProgressReportWindow:
    existing = getattr(root, "_helix_progress_report", None)
    if isinstance(existing, ProgressReportWindow):
        return existing

    progress = ProgressReportWindow(root)
    setattr(root, "_helix_progress_report", progress)

    original_log = getattr(root, "_log", None)
    if callable(original_log):
        def mirrored_log(message: str) -> None:
            original_log(message)
            progress.append(message)
        setattr(root, "_log", mirrored_log)

    original_set_running = getattr(root, "_set_running", None)
    if callable(original_set_running):
        def mirrored_set_running(running: bool) -> None:
            if running:
                progress.begin()
            original_set_running(running)
            progress.set_running(running)
        setattr(root, "_set_running", mirrored_set_running)

    return progress


def install_legacy_branding(root: tk.Tk, resolve: PathResolver) -> None:
    """Restore original branding/support controls plus the live progress report."""

    icon_path = resolve(ICON_FILENAME)
    if icon_path.is_file():
        try:
            root.iconbitmap(str(icon_path))
        except tk.TclError:
            pass

    shell = next((child for child in root.winfo_children() if isinstance(child, ttk.Frame)), None)
    if shell is None:
        return
    header = next((child for child in shell.winfo_children() if isinstance(child, ttk.Frame)), None)
    if header is None:
        return

    progress = _install_progress_report_hooks(root)

    legacy_panel = ttk.Frame(header)
    legacy_panel.pack(side=tk.RIGHT, anchor="ne")

    image_panel = ttk.Frame(legacy_panel)
    image_panel.pack(side=tk.LEFT, padx=(0, 8))

    mascot_photo = _load_photo(resolve(MASCOT_FILENAME), 48, 48)
    logo_photo = _load_photo(resolve(LOGO_FILENAME), 36, 36)
    photos = [photo for photo in (mascot_photo, logo_photo) if photo is not None]
    setattr(root, "_legacy_branding_photos", photos)

    if mascot_photo is not None:
        ttk.Label(image_panel, image=mascot_photo).pack(side=tk.LEFT, padx=(0, 5))
    if logo_photo is not None:
        ttk.Label(image_panel, image=logo_photo).pack(side=tk.LEFT)

    buttons = ttk.Frame(legacy_panel)
    buttons.pack(side=tk.RIGHT, anchor="ne")

    ttk.Button(
        buttons,
        text="Run Sequence",
        style="Primary.TButton",
        command=lambda: _invoke_root_method(root, "_run_sequence"),
    ).grid(row=0, column=0, padx=3, pady=2)
    ttk.Button(buttons, text="Progress", command=progress.show).grid(row=0, column=1, padx=3, pady=2)
    ttk.Button(
        buttons,
        text="Instructions",
        command=lambda: open_instructions(root, resolve),
    ).grid(row=0, column=2, padx=3, pady=2)
    ttk.Button(
        buttons,
        text="Legal",
        command=lambda: open_legal(root, resolve),
    ).grid(row=0, column=3, padx=3, pady=2)
    ttk.Button(
        buttons,
        text="Open Output",
        command=lambda: _invoke_root_method(root, "_open_output_folder"),
    ).grid(row=1, column=0, padx=3, pady=2)
    ttk.Button(
        buttons,
        text="Support Author",
        command=lambda: _open_support(AUTHOR_SUPPORT_URL),
    ).grid(row=1, column=1, padx=3, pady=2)
    ttk.Button(
        buttons,
        text="Support xLights",
        command=lambda: _open_support(SUPPORT_DONATE_URL),
    ).grid(row=1, column=2, columnspan=2, padx=3, pady=2, sticky="ew")
