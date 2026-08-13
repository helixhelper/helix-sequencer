from __future__ import annotations

import xml.etree.ElementTree as ET

from core import effect_engine


def test_set_sequence_duration_updates_head_value() -> None:
    root = ET.fromstring("<xsequence><head><sequenceDuration>132.039</sequenceDuration></head></xsequence>")

    effect_engine._set_sequence_duration(root, 2.0)

    assert root.findtext("head/sequenceDuration") == "2.000"
