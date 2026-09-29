from __future__ import annotations

import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from audio.drum_detection import detect_drum_event_streams_from_file
from mapping.drum_mapper import map_events_to_drummer_v3_poses, resolve_drum_streams

DRUMMER_V3_MODEL = "HX_SNOWMAN_DRUMMER"
DRUMMER_TARGETS = {
    "HX_SNOWMAN_DRUMMER_KICK", "HX_SNOWMAN_DRUMMER_SNARE",
    "HX_SNOWMAN_DRUMMER_HI_HAT", "HX_SNOWMAN_DRUMMER_TOM_LEFT",
    "HX_SNOWMAN_DRUMMER_TOM_RIGHT", "HX_SNOWMAN_DRUMMER_CYMBAL_LEFT",
    "HX_SNOWMAN_DRUMMER_CYMBAL_RIGHT", "HX_SNOWMAN_DRUMMER_LEFT_STICK",
    "HX_SNOWMAN_DRUMMER_RIGHT_STICK",
}

