from __future__ import annotations

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


def install_legacy_branding(root: tk.Tk, resolve: PathResolver) -> None:
    """Restore the original Helix identity/support affordances onto the beta GUI.

    This deliberately stays separate from sequencing logic. Missing art or desktop
    browser integration must never prevent the beta engine from launching.
    """

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

    legacy_panel = ttk.Frame(header)
    legacy_panel.pack(side=tk.RIGHT, anchor="ne")

    image_panel = ttk.Frame(legacy_panel)
    image_panel.pack(side=tk.LEFT, padx=(0, 8))

    mascot_photo = _load_photo(resolve(MASCOT_FILENAME), 56, 56)
    logo_photo = _load_photo(resolve(LOGO_FILENAME), 42, 42)
    photos = [photo for photo in (mascot_photo, logo_photo) if photo is not None]
    # Retain references so Tk does not garbage-collect the images.
    setattr(root, "_legacy_branding_photos", photos)

    if mascot_photo is not None:
        ttk.Label(image_panel, image=mascot_photo).pack(side=tk.LEFT, padx=(0, 5))
    if logo_photo is not None:
        ttk.Label(image_panel, image=logo_photo).pack(side=tk.LEFT)

    buttons = ttk.Frame(legacy_panel)
    buttons.pack(side=tk.RIGHT, anchor="ne")
    ttk.Button(
        buttons,
        text="Instructions",
        command=lambda: open_instructions(root, resolve),
    ).grid(row=0, column=0, padx=3, pady=2)
    ttk.Button(
        buttons,
        text="Legal",
        command=lambda: open_legal(root, resolve),
    ).grid(row=0, column=1, padx=3, pady=2)
    ttk.Button(
        buttons,
        text="Support Author",
        command=lambda: _open_support(AUTHOR_SUPPORT_URL),
    ).grid(row=1, column=0, padx=3, pady=2)
    ttk.Button(
        buttons,
        text="Support xLights",
        command=lambda: _open_support(SUPPORT_DONATE_URL),
    ).grid(row=1, column=1, padx=3, pady=2)
