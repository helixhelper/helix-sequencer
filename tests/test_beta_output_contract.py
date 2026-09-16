from __future__ import annotations

import json
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

from core import beta_output_contract


def _write_silence(path: Path, *, duration_ms: int = 1000) -> None:
    sample_rate = 8000
    frames = int(sample_rate * (duration_ms / 1000.0))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\x00\x00" * frames)


def _write_layout(path: Path) -> None:
    drummer_submodels = [
        "HX_SNOWMAN_DRUMMER_HIT_KICK",
        "HX_SNOWMAN_DRUMMER_HIT_SNARE",
        "HX_SNOWMAN_DRUMMER_HIT_HIHAT",
        "HX_SNOWMAN_DRUMMER_HIT_LEFT_TOM",
        "HX_SNOWMAN_DRUMMER_HIT_RIGHT_TOM",
        "HX_SNOWMAN_DRUMMER_HIT_LEFT_CRASH",
        "HX_SNOWMAN_DRUMMER_HIT_RIGHT_CRASH",
        "HX_SNOWMAN_DRUMMER_HIT_BOTH_CRASH",
        "HX_SNOWMAN_DRUMMER_DOWNBEAT_IMPACT",
    ]
    submodels = "".join(
        f'<subModel name="{name}" layout="ranges" type="ranges" line0="1-4" />'
        for name in drummer_submodels
    )
    path.write_text(
        (
            "<xrgb><models>"
            '<model name="TREE_A" DisplayAs="Custom" CustomWidth="2" CustomHeight="2" '
            'parm1="2" parm2="2" StringType="RGB Nodes" CustomModel="1,2;3,4" StartChannel="900000" />'
            '<model name="TREE_B" DisplayAs="Custom" CustomWidth="2" CustomHeight="2" '
            'parm1="2" parm2="2" StringType="RGB Nodes" CustomModel="1,2;3,4" StartChannel="902000" />'
            '<model name="HX_SNOWMAN_DRUMMER" DisplayAs="Custom" CustomWidth="2" CustomHeight="2" '
            'parm1="2" parm2="2" StringType="RGB Nodes" CustomModel="1,2;3,4" '
            'HelixImplementationState="drummer_v3_beta" HelixNodeCount="4" StartChannel="904000">'
            f"{submodels}</model>"
            "</models><modelGroups/></xrgb>"
        ),
        encoding="utf-8",
    )


def _write_timing_only_xsq(path: Path) -> None:
    drummer_marks = [
        ("kick:kick_hit", 100, 180),
        ("snare:snare_hit", 220, 300),
        ("hihat:hihat_hit", 340, 420),
        ("tom:left_tom_hit", 460, 550),
        ("cymbal:right_crash_hit", 600, 720),
    ]
    drummer_xml = "".join(
        f'<Effect label="{label}" startTime="{start}" endTime="{end}"></Effect>'
        for label, start, end in drummer_marks
    )
    path.write_text(
        (
            "<xsequence>"
            "<head><sequenceType>Media</sequenceType>"
            "<mediaFile>C:\\stale\\template-audio.mp3</mediaFile>"
            "<sequenceDuration>999.000</sequenceDuration></head>"
            "<ColorPalettes><ColorPalette>C_BUTTON_Palette1=#FFFFFF,C_CHECKBOX_Palette1=1</ColorPalette></ColorPalettes>"
            "<EffectDB><Effect>E_TEXTCTRL_Eff_On_End=0,E_TEXTCTRL_Eff_On_Start=100</Effect></EffectDB>"
            "<DisplayElements>"
            '<Element collapsed="0" type="timing" name="AUTO Audio Reactive v27.3.alt1" visible="0" active="0" />'
            '<Element collapsed="0" type="timing" name="AUTO Drummer v27.3.alt1" visible="0" active="0" />'
            "</DisplayElements>"
            "<ElementEffects>"
            '<Element type="timing" name="AUTO Audio Reactive v27.3.alt1"><EffectLayer>'
            '<Effect label="beat:one" startTime="50" endTime="150"></Effect>'
            '<Effect label="beat:two" startTime="250" endTime="350"></Effect>'
            '<Effect label="beat:three" startTime="450" endTime="550"></Effect>'
            '<Effect label="beat:four" startTime="650" endTime="750"></Effect>'
            "</EffectLayer></Element>"
            '<Element type="timing" name="AUTO Drummer v27.3.alt1"><EffectLayer>'
            f"{drummer_xml}</EffectLayer></Element>"
            "</ElementEffects></xsequence>"
        ),
        encoding="utf-8",
    )


def test_finalize_xsq_builds_coherent_xlights_show_folder(tmp_path: Path) -> None:
    layout = tmp_path / "source-layout.xml"
    audio = tmp_path / "current-song.wav"
    output = tmp_path / "show" / "current-song,v27.3.xsq"
    output.parent.mkdir(parents=True)
    _write_layout(layout)
    _write_silence(audio)
    _write_timing_only_xsq(output)

    summary = beta_output_contract.finalize_xsq_output(
        output,
        layout_path=layout,
        audio_path=audio,
    )

    assert summary["display_model_rows"] > 0
    assert summary["effect_model_rows"] > 0
    assert summary["model_effects"] > 0
    assert summary["models_with_effects"] >= 2
    assert summary["drummer_model_effects"] >= 5
    assert summary["auto_drummer_timing_events"] == 5
    assert summary["media_exists"] is True
    assert summary["media_file"] == audio.name
    assert Path(str(summary["media_resolved_path"])).resolve() == (output.parent / audio.name).resolve()
    assert summary["sequence_duration"] == "1.000"
    assert summary["channel_overlap_count"] == 0
    assert summary["channel_assignments_preserved"] is False
    assert dict(summary["layout_preflight"])["ok"] is True
    assert summary["root_models_with_effects"] >= summary["root_model_participation_required"]

    placed = dict(summary["drummer"])["placed_by_type"]
    assert placed["kick"] >= 1
    assert placed["snare"] >= 1
    assert placed["hihat"] >= 1
    assert placed["tom"] >= 1
    assert placed["cymbal"] >= 1

    assert (output.parent / "xlights_rgbeffects.xml").exists()
    assert (output.parent / "xlights_networks.xml").exists()
    assert (output.parent / audio.name).exists()
    assert output.with_name(f"{output.stem}.show.json").exists()

    root = ET.parse(output).getroot()
    media = str(root.findtext("./head/mediaFile", default="") or "")
    assert "template-audio.mp3" not in media
    assert media == audio.name
    assert (output.parent / media).exists()

    rows = {
        row.attrib.get("name", ""): row
        for row in root.findall("./ElementEffects/Element")
        if row.attrib.get("type") == "model"
    }
    required_rows = [
        "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_HIT_KICK",
        "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_HIT_SNARE",
        "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_HIT_HIHAT",
        "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_HIT_LEFT_TOM",
        "HX_SNOWMAN_DRUMMER/HX_SNOWMAN_DRUMMER_HIT_RIGHT_CRASH",
    ]
    for name in required_rows:
        assert name in rows
        assert any(effect.tag.endswith("Effect") for effect in rows[name].iter())


def test_preview_layout_channels_are_sequential_and_remove_placeholders(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    _write_layout(layout)

    summary = beta_output_contract.normalize_preview_channels(layout)

    assert summary["models"] == 3
    assert summary["overlap_count"] == 0
    assert summary["rewritten"] is True
    assert summary["preserved_existing"] is False
    starts = [
        int(model.attrib["StartChannel"])
        for model in ET.parse(layout).getroot().findall("./models/model")
    ]
    assert starts[0] == 1
    assert starts == sorted(starts)
    assert all(start < 900000 for start in starts)


def test_preview_channel_spans_respect_single_color_models(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    layout.write_text(
        (
            "<xrgb><models>"
            '<model name="MONO" DisplayAs="Single Line" parm1="10" parm2="1" StringType="Single Color Red" StartChannel="900000" />'
            '<model name="RGB" DisplayAs="Single Line" parm1="4" parm2="1" StringType="RGB Nodes" StartChannel="902000" />'
            "</models><modelGroups/></xrgb>"
        ),
        encoding="utf-8",
    )

    summary = beta_output_contract.normalize_preview_channels(layout)
    allocations = {item["model"]: item for item in summary["allocations"]}

    assert allocations["MONO"]["channels"] == 10
    assert allocations["RGB"]["channels"] == 12
    assert allocations["RGB"]["start_channel"] == 11


def test_preview_channels_preserve_compact_valid_assignments(tmp_path: Path) -> None:
    layout = tmp_path / "xlights_rgbeffects.xml"
    layout.write_text(
        (
            "<xrgb><models>"
            '<model name="A" DisplayAs="Single Line" parm1="4" parm2="1" StringType="RGB Nodes" StartChannel="1" />'
            '<model name="B" DisplayAs="Single Line" parm1="4" parm2="1" StringType="RGB Nodes" StartChannel="20" />'
            "</models><modelGroups/></xrgb>"
        ),
        encoding="utf-8",
    )

    summary = beta_output_contract.normalize_preview_channels(layout)

    assert summary["preserved_existing"] is True
    assert summary["rewritten"] is False
    starts = [int(model.attrib["StartChannel"]) for model in ET.parse(layout).getroot().findall("./models/model")]
    assert starts == [1, 20]


def test_relative_media_reference_survives_moving_show_folder(tmp_path: Path) -> None:
    layout = tmp_path / "layout.xml"
    audio = tmp_path / "song.wav"
    show = tmp_path / "show"
    output = show / "song,v27.3.xsq"
    show.mkdir()
    _write_layout(layout)
    _write_silence(audio)
    _write_timing_only_xsq(output)

    beta_output_contract.finalize_xsq_output(output, layout_path=layout, audio_path=audio)
    moved = tmp_path / "moved-show"
    show.rename(moved)
    moved_output = moved / output.name

    contract = beta_output_contract.inspect_xsq_contract(moved_output)

    assert contract["media_file"] == audio.name
    assert contract["media_exists"] is True
    assert Path(str(contract["media_resolved_path"])).resolve() == (moved / audio.name).resolve()


def test_show_manifest_records_the_verified_contract(tmp_path: Path) -> None:
    layout = tmp_path / "layout.xml"
    audio = tmp_path / "song.wav"
    output = tmp_path / "show" / "song,v27.3.xsq"
    output.parent.mkdir(parents=True)
    _write_layout(layout)
    _write_silence(audio, duration_ms=500)
    _write_timing_only_xsq(output)

    beta_output_contract.finalize_xsq_output(output, layout_path=layout, audio_path=audio)

    manifest = json.loads(output.with_name(f"{output.stem}.show.json").read_text(encoding="utf-8"))
    assert manifest["model_effects"] > 0
    assert manifest["drummer_model_effects"] > 0
    assert manifest["media_exists"] is True
    assert manifest["media_file"] == audio.name
    assert manifest["channel_overlap_count"] == 0
    assert manifest["layout_preflight"]["ok"] is True
    assert manifest["root_models_with_effects"] >= manifest["root_model_participation_required"]
