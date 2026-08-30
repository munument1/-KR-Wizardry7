#!/usr/bin/env python3
"""Audit root-CS helper ranges against every Wizardry VII DOS overlay.

OVR files are loaded at root-CS runtime origin 0x5047. A helper placed at or
above that origin is not resident merely because the original DS.EXE bytes are
zero there: any sufficiently large overlay can overwrite it. This audit uses
the pristine purchased archive as the authority for overlay lengths and reports
exact overlaps for the known v20/v21/v37 helper locations plus the v38 UI
relocations.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from build_dos_v19_baseline import read_original
from build_dos_v20_ui_complete import (
    ORIGINAL_OVERLAY_HASHES,
    OVERLAY_ORIGIN,
    WIDTH_ADAPTER,
    width_adapter_bytes,
)
from build_dos_v21_stat_repaint import (
    STAT_REPAINT_HELPER,
    stat_repaint_helper_bytes,
)
from build_dos_v25_scene_text import scene_find_helper_bytes
from build_dos_v26_scene_text import trailing_ascii_helper_bytes
from build_dos_v37_fixed_scene_helpers import (
    RELOCATED_FIND_HELPER,
    RELOCATED_TRAILING_HELPER,
)
from build_dos_v38_resident_ui_helpers import (
    NEW_STAT_REPAINT_HELPER,
    NEW_WIDTH_ADAPTER,
    compact_stat_repaint_bytes,
    relocated_width_adapter_bytes,
)


def overlaps(start: int, size: int, overlay_size: int) -> int:
    left = start - OVERLAY_ORIGIN
    right = left + size
    return max(0, min(right, overlay_size) - max(left, 0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip", type=Path, required=True)
    args = parser.parse_args()

    helpers = {
        "v20_width_adapter": (WIDTH_ADAPTER, len(width_adapter_bytes())),
        "v21_stat_repaint": (STAT_REPAINT_HELPER, len(stat_repaint_helper_bytes())),
        "v37_scene_find": (RELOCATED_FIND_HELPER, len(scene_find_helper_bytes())),
        "v37_trailing_ascii": (
            RELOCATED_TRAILING_HELPER,
            len(trailing_ascii_helper_bytes()),
        ),
        "v38_width_adapter": (NEW_WIDTH_ADAPTER, len(relocated_width_adapter_bytes())),
        "v38_stat_repaint": (
            NEW_STAT_REPAINT_HELPER,
            len(compact_stat_repaint_bytes()),
        ),
    }

    with zipfile.ZipFile(args.original_zip) as archive:
        overlays = {
            name: read_original(archive, name)
            for name in sorted(ORIGINAL_OVERLAY_HASHES)
        }

    overlay_layout = {
        name: {
            "file_size": len(data),
            "runtime_start": f"0x{OVERLAY_ORIGIN:04X}",
            "runtime_end_exclusive": f"0x{OVERLAY_ORIGIN + len(data):04X}",
        }
        for name, data in overlays.items()
    }

    helper_layout: dict[str, object] = {}
    for label, (start, size) in helpers.items():
        collisions = []
        for name, data in overlays.items():
            count = overlaps(start, size, len(data))
            if count:
                collisions.append(
                    {
                        "overlay": name,
                        "overlap_bytes": count,
                        "helper_bytes": size,
                    }
                )
        helper_layout[label] = {
            "start": f"0x{start:04X}",
            "end_exclusive": f"0x{start + size:04X}",
            "size": size,
            "below_overlay_origin": start + size <= OVERLAY_ORIGIN,
            "collisions": collisions,
        }

    max_name, max_data = max(overlays.items(), key=lambda item: len(item[1]))
    report = {
        "overlay_origin": f"0x{OVERLAY_ORIGIN:04X}",
        "largest_overlay": {
            "name": max_name,
            "file_size": len(max_data),
            "runtime_end_exclusive": f"0x{OVERLAY_ORIGIN + len(max_data):04X}",
        },
        "overlays": overlay_layout,
        "helpers": helper_layout,
        "findings": [
            "v20 0xF790 and v21 0xF7B0 are fully overwritten by VMAZE and VMNPC",
            "v37 0xFDB0 and 0xFDF0 are fully overwritten by VMNPC",
            "v38 0x38F4 and 0x3906 are below the 0x5047 overlay origin",
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
