#!/usr/bin/env python3
"""Release entry point for the v42 scene-safe Korean transcoder.

The first v42 implementation correctly removed scene-control values from rank
payloads, but it assumed that rebuilding the codebook would keep exactly the
same Unicode order as v41.  The published v41 codebook is a legacy char->pair
mapping and its historical order is not guaranteed to match a fresh frequency
sort.

This wrapper makes the migration robust:

* accept both legacy ``char: "AA BB"`` and modern metadata codebooks;
* allow the new safe codebook to choose a different character order;
* locate the v41 rank/glyph tables from the renderer's assembled layout rather
  than searching a large binary cave for a 256-byte value sequence;
* reorder the already embedded 38-byte glyph records in DS.EXE to the new
  Unicode order, instead of regenerating any font bitmap;
* retain any legacy glyph that is no longer referenced at the unused tail;
* then update the inverse-rank table and rank-alphabet size as v42 intended.

No executable code is relocated and DS.EXE keeps the same byte size.
"""

from __future__ import annotations

from typing import Any

import build_dos_v42_scene_safe as impl
from build_dos_messages import DEFAULT_ESCAPE, huffman_codes
from patch_dos_korean_renderer import Assembler16, emit_renderer, emit_width_hook


GLYPH_RECORD_SIZE = 38


def compatible_codebook_pairs(report: dict[str, object]) -> dict[str, tuple[int, int]]:
    raw = report.get("codebook")
    if not isinstance(raw, dict):
        raise ValueError("korean_codebook.json has no codebook object")
    result: dict[str, tuple[int, int]] = {}
    for character, metadata in raw.items():
        if not isinstance(character, str):
            raise ValueError("invalid codebook character key")
        encoded: Any = metadata.get("bytes") if isinstance(metadata, dict) else metadata
        if not isinstance(encoded, str):
            raise ValueError(f"codebook entry {character!r} has no byte pair")
        parts = encoded.split()
        if len(parts) != 2:
            raise ValueError(f"codebook entry {character!r} is not a two-byte pair")
        result[character] = (int(parts[0], 16), int(parts[1], 16))
    return result


def renderer_table_runtime_offset(alphabet_size: int, glyph_count: int) -> int:
    """Recreate only the code layout to resolve the rank-table label."""
    asm = Assembler16(impl.CAVE_START)
    emit_renderer(asm, alphabet_size, glyph_count)
    emit_width_hook(asm)
    asm.label("rank_table")
    return asm.labels["rank_table"]


def patch_renderer_rank_decoder_reordered(
    ds_exe: bytes,
    old_misc: bytes,
    old_codebook_report: dict[str, object],
    new_misc: bytes,
    new_codebook: dict[str, tuple[int, int]],
    new_alphabet: list[int],
) -> tuple[bytes, dict[str, object]]:
    old_pairs = compatible_codebook_pairs(old_codebook_report)
    old_order = list(old_pairs)
    new_order = list(new_codebook)
    old_set = set(old_order)
    new_set = set(new_order)
    added = sorted(new_set - old_set)
    if added:
        raise ValueError(
            "new v42 codebook contains characters with no embedded v41 glyph: "
            f"added={added[:8]!r}"
        )
    # A historical codebook can contain a glyph that later message patches no
    # longer reference. Keep such records after the active v42 glyphs so the
    # fixed-size renderer payload and its old glyph-count guard remain valid.
    missing_order = [character for character in old_order if character not in new_set]
    embedded_order = new_order + missing_order

    old_codes = huffman_codes(old_misc)
    old_alphabet = sorted(
        (value for value in old_codes if value != DEFAULT_ESCAPE),
        key=lambda value: (len(old_codes[value]), value),
    )
    converged_alphabet = impl.safe_rank_alphabet(huffman_codes(new_misc))
    if converged_alphabet != new_alphabet:
        raise ValueError("safe rank alphabet did not converge with final MISC.HDR")

    old_table = impl._rank_table(old_alphabet)
    new_table = impl._rank_table(new_alphabet)
    data = bytearray(ds_exe)
    cave_start = impl.MZ_HEADER_SIZE + impl.CAVE_START
    cave_end = min(len(data), impl.MZ_HEADER_SIZE + impl.CAVE_END)

    table_runtime_offset = renderer_table_runtime_offset(
        len(old_alphabet), len(old_order)
    )
    table_file_offset = impl.MZ_HEADER_SIZE + table_runtime_offset
    if not cave_start <= table_file_offset < cave_end:
        raise ValueError("assembled v41 rank-table offset falls outside renderer cave")
    actual_table = bytes(data[table_file_offset:table_file_offset + 256])
    if actual_table != old_table:
        first_diff = next(
            (
                index
                for index, (actual, expected) in enumerate(zip(actual_table, old_table))
                if actual != expected
            ),
            None,
        )
        raise ValueError(
            "v41 inverse-rank table does not match MISC.HDR at assembled offset; "
            f"first_diff={first_diff!r}"
        )

    glyph_file_offset = table_file_offset + 256
    glyph_bytes = len(old_order) * GLYPH_RECORD_SIZE
    glyph_end = glyph_file_offset + glyph_bytes
    if glyph_end > cave_end:
        raise ValueError("embedded glyph table extends outside the verified renderer cave")
    old_glyphs = bytes(data[glyph_file_offset:glyph_end])
    if len(old_glyphs) != glyph_bytes:
        raise ValueError("embedded glyph table is truncated")

    old_index = {character: index for index, character in enumerate(old_order)}
    reordered = b"".join(
        old_glyphs[
            old_index[character] * GLYPH_RECORD_SIZE:
            (old_index[character] + 1) * GLYPH_RECORD_SIZE
        ]
        for character in embedded_order
    )
    if len(reordered) != len(old_glyphs):
        raise AssertionError("glyph reorder changed the renderer payload size")
    data[glyph_file_offset:glyph_end] = reordered
    data[table_file_offset:table_file_offset + 256] = new_table

    old_size_pattern = (
        b"\xB9" + len(old_alphabet).to_bytes(2, "little") + b"\xF7\xE1"
    )
    new_size_pattern = (
        b"\xB9" + len(new_alphabet).to_bytes(2, "little") + b"\xF7\xE1"
    )
    code_region = bytes(data[cave_start:table_file_offset])
    size_at = code_region.find(old_size_pattern)
    if size_at < 0 or code_region.find(old_size_pattern, size_at + 1) >= 0:
        raise ValueError("expected exactly one renderer alphabet-size multiply before rank table")
    size_file_offset = cave_start + size_at
    data[size_file_offset:size_file_offset + len(old_size_pattern)] = new_size_pattern

    if len(data) != len(ds_exe):
        raise AssertionError("v42 renderer migration changed DS.EXE size")

    return bytes(data), {
        "old_rank_alphabet_size": len(old_alphabet),
        "new_rank_alphabet_size": len(new_alphabet),
        "rank_table_runtime_offset": f"0x{table_runtime_offset:04X}",
        "rank_table_file_offset": f"0x{table_file_offset:X}",
        "alphabet_size_file_offset": f"0x{size_file_offset + 1:X}",
        "glyph_table_file_offset": f"0x{glyph_file_offset:X}",
        "glyph_record_size": GLYPH_RECORD_SIZE,
        "active_glyph_record_count": len(new_order),
        "embedded_glyph_record_count": len(embedded_order),
        "unused_legacy_glyphs": missing_order,
        "glyph_order_changed": old_order != embedded_order,
        "glyph_table_reordered": True,
        "glyph_character_set_preserved": set(embedded_order) == old_set,
    }


# Patch the implementation before entering its normal build pipeline. This
# keeps all message/Huffman/range audits in one place while making the legacy
# v41 -> v42 renderer migration correct.
impl._codebook_pairs_from_report = compatible_codebook_pairs
impl.patch_renderer_rank_decoder = patch_renderer_rank_decoder_reordered


if __name__ == "__main__":
    raise SystemExit(impl.main())
