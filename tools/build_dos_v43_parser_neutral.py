#!/usr/bin/env python3
"""Build v0.43 with parser-neutral Korean rank bytes.

v0.42 removed the seven raw scene-command bytes from Korean ``ESC+rank+rank``
payloads, but the DOS cinematic/event parser also treats space, underscore,
``$`` and ``^`` structurally.  Those four values still occur inside v0.42
Korean pairs, including the Jan-Ette encounter.

v0.43 removes *every* byte used structurally by the parser from Korean rank
pairs::

    SPACE _ $ ^ ! % & ] @ # |

Excluding space makes the Huffman stream slightly larger.  The DOS message bank
is fixed at 256 KiB, so the builder uses the unused zero sentinel slots already
present at the end of MSG.HDR to split a few large logical ranges at message
boundaries.  This reduces bank-alignment padding without changing any message
ID, decoded text, or the fixed MSG.HDR file size.

Once Korean payload bytes are parser-neutral, the v25-v39 special delimiter and
trailing-marker redirects are no longer needed.  v0.43 restores those four
parser copies (VBASE/VMAZE/VPCVW/VTREA) to the stock delimiter/trailing code,
while keeping all unrelated v0.41 fixes.
"""

from __future__ import annotations

import argparse
import base64
import itertools
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path

import build_dos_v42_scene_safe as v42
from build_dos_messages import (
    BANK_SIZE,
    DEFAULT_ESCAPE,
    MAX_DOS_DATA_SIZE,
    build_huffman_tree,
    encode_huffman,
    encode_translation,
    huffman_codes,
    iter_translation_units,
    serialize_huffman_tree,
)
from build_dos_v19_baseline import sha256, write_deterministic_zip
from build_dos_v20_ui_complete import OVERLAY_ORIGIN, near_call
from build_dos_v25_scene_text import ORIGINAL_FIND_TARGET, SCENE_FIND_CALLS
from build_dos_v26_scene_text import TRAILING_MARKER_PATCH_OFFSET
from build_dos_v28_all_scene_text import ORIGINAL_TRAILING, PARSER_COPIES
from extract_gold_messages import HEADER_ENTRIES, RangeEntry, extract_messages, parse_header


FULL_PARSER_RESERVED = b" _$^!%&]@#|"
FULL_PARSER_RESERVED_SET = frozenset(FULL_PARSER_RESERVED)
JAN_ETTE_MESSAGE_RANGE = range(29600, 29757)
MAX_HUFFMAN_ITERATIONS = 32

# Keep a comfortable limit below the 38 spare DOS header slots.  The current
# v0.42 corpus needs only four additional ranges.
MAX_ADDITIONAL_RANGES = 12

PARSER_RESTORE = {
    "VBASE.OVR": {
        "find_calls": SCENE_FIND_CALLS,
        "trailing_site": TRAILING_MARKER_PATCH_OFFSET,
    },
    **PARSER_COPIES,
}


def parser_neutral_rank_alphabet(codes: dict[int, tuple[int, ...]]) -> list[int]:
    """Return Huffman symbols safe to use as either Korean rank byte."""
    return sorted(
        (
            value
            for value in codes
            if value != DEFAULT_ESCAPE and value not in FULL_PARSER_RESERVED_SET
        ),
        key=lambda value: (len(codes[value]), value),
    )


def build_parser_neutral_codebook(
    texts: list[str],
    codes: dict[int, tuple[int, ...]],
) -> tuple[dict[str, tuple[int, int]], list[int]]:
    frequencies: Counter[str] = Counter()
    for text in texts:
        for unit in iter_translation_units(text):
            if isinstance(unit, str) and (ord(unit) > 0x7F or ord(unit) not in codes):
                frequencies[unit] += 1

    alphabet = parser_neutral_rank_alphabet(codes)
    ordered_chars = sorted(
        frequencies,
        key=lambda character: (-frequencies[character], ord(character)),
    )
    capacity = len(alphabet) * len(alphabet)
    if len(ordered_chars) > capacity:
        raise ValueError(
            f"{len(ordered_chars)} custom characters exceed parser-neutral capacity {capacity}"
        )
    return {
        character: pair
        for character, pair in zip(ordered_chars, itertools.product(alphabet, repeat=2))
    }, alphabet


def rank_payload_token_counts(raw: bytes) -> Counter[int]:
    """Count parser tokens only when they occur inside Korean rank pairs."""
    counts: Counter[int] = Counter()
    cursor = 0
    while cursor < len(raw):
        value = raw[cursor]
        if value != DEFAULT_ESCAPE:
            cursor += 1
            continue
        if cursor + 1 >= len(raw):
            raise ValueError("record ends after escape byte")
        if raw[cursor + 1] == DEFAULT_ESCAPE:
            cursor += 2
            continue
        if cursor + 2 >= len(raw):
            raise ValueError("record ends inside Korean pair")
        for payload in raw[cursor + 1 : cursor + 3]:
            if payload in FULL_PARSER_RESERVED_SET:
                counts[payload] += 1
        cursor += 3
    return counts


def _segment_size(message_ids: tuple[int, ...], packed_by_id: dict[int, bytes]) -> int:
    return sum(1 + len(packed_by_id[message_id]) for message_id in message_ids)


def _layout_size(
    segments: list[tuple[int, tuple[int, ...]]],
    packed_by_id: dict[int, bytes],
) -> int:
    cursor = 0
    for _range_index, message_ids in segments:
        size = _segment_size(message_ids, packed_by_id)
        if size > BANK_SIZE:
            return MAX_DOS_DATA_SIZE + BANK_SIZE + size
        bank_offset = cursor % BANK_SIZE
        if bank_offset + size > BANK_SIZE:
            cursor += BANK_SIZE - bank_offset
        cursor += size
    return cursor


def _initial_segments(
    entries: list[RangeEntry],
    records: list[object],
) -> list[tuple[int, tuple[int, ...]]]:
    ids_by_range: dict[int, list[int]] = defaultdict(list)
    for record in records:
        ids_by_range[record.range_index].append(record.message_id)
    segments: list[tuple[int, tuple[int, ...]]] = []
    for entry in entries:
        message_ids = tuple(ids_by_range[entry.range_index])
        if not message_ids:
            raise ValueError(f"range {entry.range_index} contains no records")
        if message_ids[0] != entry.start_id or message_ids[-1] != entry.start_id + entry.id_span:
            raise ValueError(f"range {entry.range_index} message IDs do not match MSG.HDR")
        if any(right != left + 1 for left, right in zip(message_ids, message_ids[1:])):
            raise ValueError(f"range {entry.range_index} is not contiguous")
        segments.append((entry.range_index, message_ids))
    return segments


def choose_padding_splits(
    entries: list[RangeEntry],
    records: list[object],
    packed_by_id: dict[int, bytes],
    available_extra_ranges: int,
) -> tuple[list[tuple[int, tuple[int, ...]]], int, list[dict[str, object]]]:
    """Greedily split ranges until the fixed 256 KiB DOS bank fits.

    A split never changes record order.  It merely starts a new MSG.HDR range at
    a message boundary so a prefix can occupy otherwise wasted bytes at the end
    of the current 0x400-byte bank.
    """
    segments = _initial_segments(entries, records)
    initial_size = _layout_size(segments, packed_by_id)
    current_size = initial_size
    max_extra = min(available_extra_ranges, MAX_ADDITIONAL_RANGES)
    split_steps: list[dict[str, object]] = []

    while current_size > MAX_DOS_DATA_SIZE:
        used_extra = len(segments) - len(entries)
        if used_extra >= max_extra:
            raise ValueError(
                f"parser-neutral bank still uses {current_size} bytes after {used_extra} splits; "
                f"limit is {MAX_DOS_DATA_SIZE}"
            )

        best_segments: list[tuple[int, tuple[int, ...]]] | None = None
        best_size = current_size
        best_step: dict[str, object] | None = None
        for segment_index, (range_index, message_ids) in enumerate(segments):
            if len(message_ids) < 2:
                continue
            for split_at in range(1, len(message_ids)):
                left = message_ids[:split_at]
                right = message_ids[split_at:]
                trial = (
                    segments[:segment_index]
                    + [(range_index, left), (range_index, right)]
                    + segments[segment_index + 1 :]
                )
                trial_size = _layout_size(trial, packed_by_id)
                if trial_size < best_size:
                    best_size = trial_size
                    best_segments = trial
                    best_step = {
                        "original_range_index": range_index,
                        "split_before_message_id": right[0],
                        "size_before": current_size,
                        "size_after": trial_size,
                        "bytes_saved": current_size - trial_size,
                    }

        if best_segments is None or best_step is None:
            raise ValueError(
                f"no range split can reduce parser-neutral bank below {current_size} bytes"
            )
        segments = best_segments
        current_size = best_size
        split_steps.append(best_step)

    return segments, initial_size, split_steps


def pack_segments(
    segments: list[tuple[int, tuple[int, ...]]],
    packed_by_id: dict[int, bytes],
) -> tuple[bytes, list[RangeEntry], int]:
    output = bytearray()
    output_entries: list[RangeEntry] = []
    padding_bytes = 0

    for new_index, (_old_range_index, message_ids) in enumerate(segments):
        size = _segment_size(message_ids, packed_by_id)
        if size > BANK_SIZE:
            raise ValueError(
                f"range segment {message_ids[0]}..{message_ids[-1]} uses {size} bytes (> {BANK_SIZE})"
            )
        bank_offset = len(output) % BANK_SIZE
        if bank_offset + size > BANK_SIZE:
            padding = BANK_SIZE - bank_offset
            output.extend(bytes(padding))
            padding_bytes += padding
        start = len(output)
        bank = start // BANK_SIZE
        offset = start % BANK_SIZE
        if bank > 0xFF:
            raise ValueError(f"message bank index {bank} exceeds DOS u8 bank field")
        output_entries.append(
            RangeEntry(
                range_index=new_index,
                start_id=message_ids[0],
                bank_offset=offset,
                id_span=len(message_ids) - 1,
                bank=bank,
            )
        )
        for message_id in message_ids:
            payload = packed_by_id[message_id]
            if len(payload) > 0xFF:
                raise ValueError(
                    f"message {message_id} Huffman payload is {len(payload)} bytes (>255)"
                )
            output.append(len(payload))
            output.extend(payload)

    return bytes(output), output_entries, padding_bytes


def patch_vbfont_from_v42(
    vbfont: bytes,
    old_codebook_report: dict[str, object],
    new_misc: bytes,
    new_codebook: dict[str, tuple[int, int]],
    new_alphabet: list[int],
) -> tuple[bytes, dict[str, object]]:
    old_codebook = v42._codebook_pairs_from_report(old_codebook_report)
    old_order = list(old_codebook)
    new_order = list(new_codebook)
    if set(old_order) != set(new_order):
        raise ValueError("v43 must preserve the exact active v42 Korean character set")

    old_alphabet = v42.recover_dense_rank_alphabet(old_codebook)
    converged = parser_neutral_rank_alphabet(huffman_codes(new_misc))
    if converged != new_alphabet:
        raise ValueError("parser-neutral rank alphabet did not converge with final MISC.HDR")

    data = bytearray(vbfont)
    old_inverse = v42._rank_table(old_alphabet)
    actual_inverse = bytes(
        data[v42.VBFONT_INVERSE_TABLE : v42.VBFONT_INVERSE_TABLE + 256]
    )
    if actual_inverse != old_inverse:
        raise ValueError("v42 VBFONT inverse-rank table does not match its published codebook")
    data[v42.VBFONT_INVERSE_TABLE : v42.VBFONT_INVERSE_TABLE + 256] = v42._rank_table(
        new_alphabet
    )

    active_bytes = len(old_order) * v42.VBFONT_GLYPH_RECORD_SIZE
    glyph_start = v42.VBFONT_GLYPH_TABLE
    glyph_end = glyph_start + active_bytes
    if glyph_end > len(data):
        raise ValueError("v42 VBFONT active glyph table is truncated")
    old_glyphs = bytes(data[glyph_start:glyph_end])
    old_index = {character: index for index, character in enumerate(old_order)}
    reordered = b"".join(
        old_glyphs[
            old_index[character] * v42.VBFONT_GLYPH_RECORD_SIZE :
            (old_index[character] + 1) * v42.VBFONT_GLYPH_RECORD_SIZE
        ]
        for character in new_order
    )
    if len(reordered) != active_bytes:
        raise AssertionError("v43 active glyph reorder changed table size")
    data[glyph_start:glyph_end] = reordered

    old_len_pattern = (
        b"\xBB" + len(old_alphabet).to_bytes(2, "little") + b"\xF7\xE3"
    )
    new_len_pattern = (
        b"\xBB" + len(new_alphabet).to_bytes(2, "little") + b"\xF7\xE3"
    )
    resident = bytes(
        data[v42.VBFONT_RESIDENT_STRING_START : v42.VBFONT_RESIDENT_WIDTH_START]
    )
    pattern_at = resident.find(old_len_pattern)
    if pattern_at < 0 or resident.find(old_len_pattern, pattern_at + 1) >= 0:
        raise ValueError("expected exactly one v42 ALPHABET_LEN multiply in resident_string")
    alphabet_patch_offset = v42.VBFONT_RESIDENT_STRING_START + pattern_at
    data[alphabet_patch_offset : alphabet_patch_offset + len(old_len_pattern)] = new_len_pattern

    if (
        vbfont[v42.VBFONT_V39_DISPATCHER_START : v42.VBFONT_V39_DISPATCHER_END]
        != bytes(data[v42.VBFONT_V39_DISPATCHER_START : v42.VBFONT_V39_DISPATCHER_END])
    ):
        raise AssertionError("v39 resident dispatcher changed during v43 VBFONT migration")
    if len(data) != len(vbfont):
        raise AssertionError("VBFONT0.VGA size changed")

    embedded_records = (
        len(vbfont) - v42.VBFONT_GLYPH_TABLE
    ) // v42.VBFONT_GLYPH_RECORD_SIZE
    return bytes(data), {
        "target_file": "VBFONT0.VGA",
        "old_rank_alphabet_size": len(old_alphabet),
        "new_rank_alphabet_size": len(new_alphabet),
        "active_glyph_record_count": len(new_order),
        "glyph_record_size": v42.VBFONT_GLYPH_RECORD_SIZE,
        "inverse_rank_table_offset": f"0x{v42.VBFONT_INVERSE_TABLE:04X}",
        "glyph_table_offset": f"0x{v42.VBFONT_GLYPH_TABLE:04X}",
        "alphabet_size_patch_offset": f"0x{alphabet_patch_offset + 1:04X}",
        "glyph_table_reordered": old_order != new_order,
        "glyph_character_set_preserved": True,
        "legacy_tail_bytes_preserved": True,
        "embedded_records_from_table_to_eof_floor": embedded_records,
        "v39_dispatcher_preserved": True,
    }


def restore_stock_parser_paths(name: str, source: bytes) -> tuple[bytes, dict[str, object]]:
    spec = PARSER_RESTORE[name]
    data = bytearray(source)
    restored_calls: list[dict[str, object]] = []
    for offset in spec["find_calls"]:
        if data[offset] != 0xE8:
            raise ValueError(f"{name} delimiter call at 0x{offset:04X} is not a near CALL")
        stock = near_call(ORIGINAL_FIND_TARGET, OVERLAY_ORIGIN + offset)
        before = bytes(data[offset : offset + len(stock)])
        data[offset : offset + len(stock)] = stock
        restored_calls.append(
            {
                "offset": f"0x{offset:04X}",
                "changed": before != stock,
                "stock_target": f"0x{ORIGINAL_FIND_TARGET:04X}",
            }
        )

    site = spec["trailing_site"]
    before_trailing = bytes(data[site : site + len(ORIGINAL_TRAILING)])
    data[site : site + len(ORIGINAL_TRAILING)] = ORIGINAL_TRAILING
    if len(data) != len(source):
        raise AssertionError(f"{name} size changed while restoring stock parser")
    return bytes(data), {
        "find_calls": restored_calls,
        "trailing_site": f"0x{site:04X}",
        "trailing_changed": before_trailing != ORIGINAL_TRAILING,
        "stock_trailing_restored": bytes(
            data[site : site + len(ORIGINAL_TRAILING)]
        ) == ORIGINAL_TRAILING,
    }


def transcode_message_bank(
    hdr_raw: bytes,
    data_raw: bytes,
    misc_raw: bytes,
    old_codebook_report: dict[str, object],
) -> tuple[bytes, bytes, bytes, dict[str, object], dict[str, tuple[int, int]], list[int]]:
    declared, entries, sentinel_count = parse_header(hdr_raw, "dos")
    records = extract_messages(data_raw, entries, misc_raw)
    old_codebook = v42._codebook_pairs_from_report(old_codebook_report)
    texts = {
        record.message_id: v42.decode_localized_display(
            base64.b64decode(record.raw_base64), old_codebook
        )
        for record in records
    }
    old_raw_by_id = {
        record.message_id: base64.b64decode(record.raw_base64) for record in records
    }

    base_alphabet = sorted(huffman_codes(misc_raw))
    codes = huffman_codes(misc_raw)
    output_misc = misc_raw
    codebook: dict[str, tuple[int, int]] = {}
    rank_alphabet: list[int] = []
    encoded_by_id: dict[int, bytes] = {}
    iterations = 0

    for iterations in range(1, MAX_HUFFMAN_ITERATIONS + 1):
        codebook, rank_alphabet = build_parser_neutral_codebook(list(texts.values()), codes)
        encoded_by_id = {
            message_id: encode_translation(text, codes, codebook, DEFAULT_ESCAPE)
            for message_id, text in texts.items()
        }
        frequencies: Counter[int] = Counter(
            value for raw in encoded_by_id.values() for value in raw
        )
        output_misc = serialize_huffman_tree(build_huffman_tree(frequencies, base_alphabet))
        next_codes = huffman_codes(output_misc)
        if parser_neutral_rank_alphabet(next_codes) == rank_alphabet:
            codes = next_codes
            break
        codes = next_codes
    else:
        raise ValueError("parser-neutral rank alphabet failed to converge")

    packed_by_id = {
        message_id: encode_huffman(raw, codes)
        for message_id, raw in encoded_by_id.items()
    }
    segments, unsplit_size, split_steps = choose_padding_splits(
        entries,
        records,
        packed_by_id,
        sentinel_count,
    )
    output_data, output_entries, padding_bytes = pack_segments(segments, packed_by_id)
    used_data_bytes = len(output_data)
    if used_data_bytes > MAX_DOS_DATA_SIZE:
        raise ValueError(
            f"parser-neutral message bank uses {used_data_bytes} bytes; limit is {MAX_DOS_DATA_SIZE}"
        )
    output_data += bytes(MAX_DOS_DATA_SIZE - used_data_bytes)

    total_header_slots = declared + sentinel_count
    if len(output_entries) > total_header_slots:
        raise ValueError("range splitting exhausted fixed MSG.HDR entry slots")
    output_sentinels = total_header_slots - len(output_entries)
    entry_struct = HEADER_ENTRIES["dos"]
    output_header = bytearray(struct.pack("<H", len(output_entries)))
    for entry in output_entries:
        output_header.extend(
            entry_struct.pack(entry.start_id, entry.bank_offset, entry.id_span, entry.bank)
        )
    output_header.extend(bytes(output_sentinels * entry_struct.size))
    if len(output_header) != len(hdr_raw):
        raise AssertionError("MSG.HDR size changed after consuming sentinel slots")

    old_counts: Counter[int] = Counter()
    new_counts: Counter[int] = Counter()
    jan_old: Counter[int] = Counter()
    jan_new: Counter[int] = Counter()
    for message_id, raw in old_raw_by_id.items():
        old_counts.update(rank_payload_token_counts(raw))
        if message_id in JAN_ETTE_MESSAGE_RANGE:
            jan_old.update(rank_payload_token_counts(raw))
    for message_id, raw in encoded_by_id.items():
        new_counts.update(rank_payload_token_counts(raw))
        if message_id in JAN_ETTE_MESSAGE_RANGE:
            jan_new.update(rank_payload_token_counts(raw))

    if sum(old_counts.values()) == 0:
        raise ValueError("v42 input unexpectedly contains no parser-token rank collisions")
    if sum(new_counts.values()) != 0 or sum(jan_new.values()) != 0:
        raise ValueError("parser structural bytes remain inside v43 Korean rank pairs")

    # Verify every Unicode/control stream round-trips exactly under the new codebook.
    for message_id, raw in encoded_by_id.items():
        if v42.decode_localized_display(raw, codebook) != texts[message_id]:
            raise ValueError(f"message {message_id} changed during v43 transcode")

    # Re-extract the final packed bank with the final Huffman tree.  This also
    # validates every split range and the DOS game-facing MSG.HDR lookup layout.
    final_records = extract_messages(bytes(output_data), output_entries, output_misc)
    final_raw = {
        record.message_id: base64.b64decode(record.raw_base64) for record in final_records
    }
    if set(final_raw) != set(encoded_by_id):
        raise ValueError("message ID set changed after split-range packing")
    for message_id, expected in encoded_by_id.items():
        if final_raw[message_id] != expected:
            raise ValueError(f"message {message_id} changed after split-range packing")

    def token_dict(counter: Counter[int]) -> dict[str, int]:
        return {chr(value): counter[value] for value in FULL_PARSER_RESERVED}

    report = dict(old_codebook_report)
    report.update(
        {
            "format": "Wizardry VII DOS v43 parser-neutral Korean codebook",
            "custom_character_count": len(codebook),
            "huffman_iterations": iterations,
            "reserved_rank_bytes": [f"0x{value:02X}" for value in FULL_PARSER_RESERVED],
            "reserved_rank_ascii": FULL_PARSER_RESERVED.decode("ascii"),
            "rank_alphabet_size": len(rank_alphabet),
            "rank_payload_collisions_before": sum(old_counts.values()),
            "rank_payload_collisions_after": sum(new_counts.values()),
            "rank_payload_collisions_before_by_token": token_dict(old_counts),
            "rank_payload_collisions_after_by_token": token_dict(new_counts),
            "jan_ette_collisions_before": sum(jan_old.values()),
            "jan_ette_collisions_after": sum(jan_new.values()),
            "jan_ette_collisions_before_by_token": token_dict(jan_old),
            "jan_ette_collisions_after_by_token": token_dict(jan_new),
            "unsplit_used_data_bytes": unsplit_size,
            "used_data_bytes": used_data_bytes,
            "padded_data_size": len(output_data),
            "padding_bytes_between_ranges": padding_bytes,
            "original_declared_range_count": declared,
            "new_declared_range_count": len(output_entries),
            "original_zero_sentinel_count": sentinel_count,
            "remaining_zero_sentinel_count": output_sentinels,
            "range_split_count": len(output_entries) - declared,
            "range_split_steps": split_steps,
            "codebook": {
                character: {
                    "codepoint": f"U+{ord(character):04X}",
                    "bytes": f"{pair[0]:02X} {pair[1]:02X}",
                }
                for character, pair in codebook.items()
            },
        }
    )
    return (
        bytes(output_header),
        bytes(output_data),
        output_misc,
        report,
        codebook,
        rank_alphabet,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v42-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")
    source_dir = args.v42_dir / "DSAVANT" if (args.v42_dir / "DSAVANT").is_dir() else args.v42_dir

    old_hdr = (source_dir / "MSG.HDR").read_bytes()
    old_data = (source_dir / "MSG.DBS").read_bytes()
    old_misc = (source_dir / "MISC.HDR").read_bytes()
    old_codebook_report = json.loads(
        (source_dir / "korean_codebook.json").read_text(encoding="utf-8")
    )
    (
        new_hdr,
        new_data,
        new_misc,
        new_codebook_report,
        new_codebook,
        new_alphabet,
    ) = transcode_message_bank(old_hdr, old_data, old_misc, old_codebook_report)

    payloads: dict[str, bytes] = {}
    vbfont_report: dict[str, object] | None = None
    parser_report: dict[str, object] = {}
    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        data = path.read_bytes()
        if name == "MSG.HDR":
            data = new_hdr
        elif name == "MSG.DBS":
            data = new_data
        elif name == "MISC.HDR":
            data = new_misc
        elif name == "korean_codebook.json":
            data = json.dumps(
                new_codebook_report, ensure_ascii=False, indent=2
            ).encode("utf-8")
        elif name == "VBFONT0.VGA":
            data, vbfont_report = patch_vbfont_from_v42(
                data,
                old_codebook_report,
                new_misc,
                new_codebook,
                new_alphabet,
            )
        elif name in PARSER_RESTORE:
            data, parser_report[name] = restore_stock_parser_paths(name, data)
        payloads[f"DSAVANT/{name}"] = data

    if vbfont_report is None:
        raise ValueError("VBFONT0.VGA was not found in v42 payload")
    if set(parser_report) != set(PARSER_RESTORE):
        missing = sorted(set(PARSER_RESTORE) - set(parser_report))
        raise ValueError(f"v42 payload is missing parser overlays: {missing}")

    tx_keys = {
        "custom_character_count",
        "huffman_iterations",
        "reserved_rank_bytes",
        "reserved_rank_ascii",
        "rank_alphabet_size",
        "rank_payload_collisions_before",
        "rank_payload_collisions_after",
        "rank_payload_collisions_before_by_token",
        "rank_payload_collisions_after_by_token",
        "jan_ette_collisions_before",
        "jan_ette_collisions_after",
        "jan_ette_collisions_before_by_token",
        "jan_ette_collisions_after_by_token",
        "unsplit_used_data_bytes",
        "used_data_bytes",
        "padded_data_size",
        "padding_bytes_between_ranges",
        "original_declared_range_count",
        "new_declared_range_count",
        "original_zero_sentinel_count",
        "remaining_zero_sentinel_count",
        "range_split_count",
        "range_split_steps",
    }
    report = {
        "format": "Wizardry VII DOS v43 parser-neutral Korean event hotfix",
        "status": "requires fresh-new-game field verification",
        "v42_result": "tester reported the Jan-Ette/H'Jenn-Ra symptom unchanged",
        "new_finding": [
            "v42 reserved only ! % & ] @ # | inside Korean ranks",
            "the same parser also treats SPACE, _, $, and ^ structurally",
            "v42 Jan-Ette records still contained those structural bytes inside Korean pairs",
        ],
        "changes": [
            "exclude all 11 structural parser bytes from every Korean rank pair",
            "consume a few existing zero MSG.HDR sentinel slots to split ranges and recover bank padding",
            "preserve every message ID, Unicode string, and literal scene-control byte",
            "restore VBASE/VMAZE/VPCVW/VTREA delimiter and trailing-marker sites to stock code",
            "update only the resident VBFONT rank mapping needed by the new dense codebook",
            "retain unrelated v0.41 roster, save, UI, and overlay-safe changes",
        ],
        "event_regression_target": {
            "messages": [JAN_ETTE_MESSAGE_RANGE.start, JAN_ETTE_MESSAGE_RANGE.stop - 1],
            "expected": "Jan-Ette/Helazoid encounter",
            "must_not_appear": "H'Jenn-Ra/T'Rang text or MON42 picture",
        },
        "message_transcode": {
            key: value for key, value in new_codebook_report.items() if key in tx_keys
        },
        "renderer": vbfont_report,
        "parser_restore": parser_report,
        "invariants": [
            "zero structural parser tokens inside all Korean rank pairs",
            "zero structural parser tokens inside Jan-Ette Korean rank pairs",
            "all messages re-extract byte-identically after split-range packing",
            "MSG.HDR file size unchanged and only former sentinel slots are consumed",
            "MSG.DBS remains exactly 256 KiB",
            "VBFONT0.VGA and parser overlay file sizes remain unchanged",
        ],
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V43_REPORT.json"] = report_raw

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
