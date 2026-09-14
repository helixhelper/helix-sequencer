# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
root = Path(globals().get("SPECPATH", ".")).resolve()

datas = [
    (str(root / "SEQUENCER_INSTRUCTIONS.txt"), "."),
    (str(root / "launch_sequencer_app.cmd"), "."),
    (str(root / "launch_sequencer_app.vbs"), "."),
    (str(root / "app_icon.ico"), "."),
    (str(root / "c82.ico"), "."),
    (str(root / "c82.png"), "."),
    (str(root / "xlights" / "effect_catalog.json"), "xlights"),
]
for source, destination in (
    (root / "template.xsq", "."),
    (root / "xlights_rgbeffects.xml", "."),
    (root / "xlights_rgbeffects.xbkp", "."),
    (root / "helixville4", "helixville4"),
    (
        root / "fixtures" / "band_geometry" / "models" / "HX_SNOWMAN_DRUMMER_V3.xmodel",
        "fixtures/band_geometry/models",
    ),
):
    if source.exists():
        datas.append((str(source), destination))
for mascot_name in ("helixmascot.jpg", "helixmascot.jpeg", "helixmascot.png"):
    mascot_path = root / mascot_name
    if mascot_path.exists():
        datas.append((str(mascot_path), "."))
        break
datas += collect_data_files("imageio_ffmpeg")

hiddenimports = [
    "core.audio_intelligence",
    "core.drummer_xlights",
    "core.effect_engine",
    "core.effect_engine_beat_grid",
    "core.engine_profiles",
    "core.model_parser",
    "core.sequence_builder",
    "audio.drum_classification",
    "audio.drum_detection",
    "animation.drummer_motion",
    "effects.drum_effects",
    "mapping.drum_mapper",
    "tools.build_helixville4_finished_drummer_layout",
    "tools.build_helpers.drummer_v3_layout",
    "tools.build_helpers.helixia",
    "tools.build_helpers.helixville4_finished_band",
    "tools.build_helpers.helixville4_full_band",
    "tools.utilities",
    "xlights.layout_sync",
    "xlights.timing_tracks",
    "xlights.xml_io",
    "xlights.xsq_writer",
    "imageio_ffmpeg",
    "requests",
    "librosa",
    "numpy",
]

a = Analysis(
    ["gui_launcher.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchaudio", "torchvision", "whisper"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="HelixSequenceWeaverBeta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # The beta executable is the GUI. Engine execution happens in-process.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / "app_icon.ico"),
)
