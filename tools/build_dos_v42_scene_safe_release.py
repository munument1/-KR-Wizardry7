#!/usr/bin/env python3
"""Release entry point for the v42 scene-safe Korean transcoder.

The published v41 renderer and codebook were produced from the rank ordering
that existed while the codebook was assigned. Later Huffman retraining can
change code lengths without changing those assigned byte pairs, so deriving the
old renderer rank table from the final MISC.HDR is not reliable.

This wrapper recovers the historical rank alphabet from the published dense
rectangular codebook. It also reads the actual rank-table address from the
installed v41 renderer machine code, so later source-code layout changes cannot
make migration offsets drift. The embedded 38-byte glyph records are reordered
to the new safe codebook order, while unused historical glyphs remain at the
tail. DS.EXE keeps exactly the same size.
"""

from __future__ import annotations

from typing import Any

import build_dos_v42_scene_safe as impl
from build_dos_messages import huffman_codes


GLYPH_RECORD_SIZE = 38
RANK_LOAD_OPCODE = bytes.fromhex("2E 8A 87")  # mov al,cs:[bx+imm16]


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


def recover_dense_rank_alphabet(
    codebook: dict[str, tuple[int, int]],
) -> list[int]:
    """Recover the alphabet used when sequential rectangular pairs were assigned."""
    pairs = list(codebook.values())
    if not pairs:
        raise ValueError("cannot recover rank alphabet from an empty codebook")
    first_left = pairs[0][0]
    alphabet: list[int] = []
    for left, right in pairs:
        if left != first_left:
            break
        alphabet.append(right)
    if not alphabet:
        raise ValueError("published codebook has no first rectangular rank row")
    if alphabet[0] != first_left:
        raise ValueError("published codebook does not begin with rank pair (0, 0)")
    if len(alphabet) == len(pairs):
        raise ValueError("codebook is too small to expose a complete rank row")
    if len(set(alphabet)) != len(alphabet):
        raise ValueError("recovered first rank row contains duplicate bytes")

    size = len(alphabet)
    for index, pair in enumerate(pairs):
        expected = (alphabet[index // size], alphabet[index % size])
        if pair != expected:
            raise ValueError(
                "published codebook is not a dense rectangular rank sequence at "
                f"index {index}: expected {expected!r}, found {pair!r}"
            )
    return alphabet


def renderer_rank_table_pointer(ds_exe: bytes) -> tuple[int, int]:
    """Read the rank-table imm16 used by both Korean rank loads in v41."""
    image = ds_exe[impl.MZ_HEADER_SIZE:]
    # Both table loads are near the beginning of the injected renderer. Limit
    # the scan to code, not the much larger binary glyph payload.
    start = impl.CAVE_START
    end = min(len(image), start + 0x400)
    code = image[start:end]
    pointers: list[int] = []
    cursor = 0
    while True:
        found = code.find(RANK_LOAD_OPCODE, cursor)
        if found < 0:
            break
        immediate_at = found + len(RANK_LOAD_OPCODE)
        if immediate_at + 2 <= len(code):
            pointer = int.from_bytes(code[immediate_at:immediate_at + 2], "little")
            if impl.CAVE_START <= pointer < impl.CAVE_END:
                pointers.append(pointer)
        cursor = found + 1
    unique = sorted(set(pointers))
    if len(unique) != 1 or len(pointers) < 2:
        raise ValueError(
            "could not resolve one v41 rank-table pointer from renderer code: "
            f"pointers={[hex(value) for value in pointers]}"
        )
    return unique[0], len(pointers)


def patch_renderer_rank_decoder_reordered(
    ds_exe: bytes,
    old_misc: bytes,
    old_codebook_report: dict[str, object],
    new_misc: bytes,
    new_codebook: dict[str, tuple[int, int]],
    new_alphabet: list[int],
) -> tuple[bytes, dict[str, object]]:
    del old_misc  # historical ranks come from the published pair assignment
    old_pairs = compatible_codebook_pairs(old_codebook_report)
    old_order = list(old_pairs)
    old_alphabet = recover_dense_rank_alphabet(old_pairs)
    new_order = list(new_codebook)
    old_set = set(old_order)
    new_set = set(new_order)
    added = sorted(new_set - old_set)
    if added:
        raise ValueError(
            "new v42 codebook contains characters with no embedded v41 glyph: "
            f"added={added[:8]!r}"
        )
    missing_order = [character for character in old_order if character not in new_set]
    embedded_order = new_order + missing_order

    converged_alphabet = impl.safe_rank_alphabet(huffman_codes(new_misc))
    if converged_alphabet != new_alphabet:
        raise ValueError("safe rank alphabet did not converge with final MISC.HDR")

    old_table = impl._rank_table(old_alphabet)
    new_table = impl._rank_table(new_alphabet)
    data = bytearray(ds_exe)
    cave_start = impl.MZ_HEADER_SIZE + impl.CAVE_START
    cave_end = min(len(data), impl.MZ_HEADER_SIZE + impl.CAVE_END)

    table_runtime_offset, pointer_reference_count = renderer_rank_table_pointer(ds_exe)
    table_file_offset = impl.MZ_HEADER_SIZE + table_runtime_offset
    if not cave_start <= table_file_offset < cave_end:
        raise ValueError("v41 machine-code rank-table pointer falls outside renderer cave")
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
            "v41 inverse-rank table does not match published codebook ranks at "
            f"machine-code pointer; first_diff={first_diff!r}, "
            f"actual0={actual_table[:8].hex(' ')}, expected0={old_table[:8].hex(' ')}"
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
        "old_rank_alphabet_source": "published_codebook_dense_pairs",
        "old_rank_alphabet_size": len(old_alphabet),
        "new_rank_alphabet_size": len(new_alphabet),
        "rank_table_pointer_source": "v41_renderer_machine_code",
        "rank_table_pointer_reference_count": pointer_reference_count,
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


impl._codebook_pairs_from_report = compatible_codebook_pairs
impl.patch_renderer_rank_decoder = patch_renderer_rank_decoder_reordered


if __name__ == "__main__":
    raise SystemExit(impl.main())
