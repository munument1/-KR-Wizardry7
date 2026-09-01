#!/usr/bin/env python3
"""Build v42 with scene-safe Korean rank bytes.

v0.41 stores each Korean glyph as ``ESC + rank + rank``.  Some field/cinematic
paths still inspect raw bytes for scene commands, so a rank byte equal to one of
``! % & ] @ # |`` can be mistaken for a real command.  That can select the
wrong event/picture and then desynchronize the following text stream.

v42 transcodes the already-localized v0.41 message bank to a rank alphabet that
never uses those structural bytes.  Literal ASCII control bytes remain exactly
unchanged.  Space (0x20) stays available for compression because the v39 scene
delimiter dispatcher already skips complete Korean glyph units.

The v0.41 runtime renderer is the v19/v39 resident renderer in VBFONT0.VGA, not
the older experimental DS.EXE cave renderer.  v42 therefore updates:

* VBFONT0.VGA 0x0D00: 256-byte inverse-rank table;
* VBFONT0.VGA 0x0E00: fixed-size 7-byte resident glyph records, reordered to
  match the new safe codebook while retaining unused legacy glyphs at the tail;
* resident_string's ``ALPHABET_LEN`` immediate between 0x0937 and 0x0A30.

The v39 dispatcher at 0x0AF0 and DS.EXE are left untouched.  File sizes and
save format remain unchanged.
"""

from __future__ import annotations

import argparse
import base64
import itertools
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any

from build_dos_messages import (
    DEFAULT_ESCAPE,
    MAX_DOS_DATA_SIZE,
    build_huffman_tree,
    encode_huffman,
    encode_translation,
    huffman_codes,
    iter_translation_units,
    pack_message_ranges,
    serialize_huffman_tree,
)
from build_dos_v19_baseline import sha256, write_deterministic_zip
from extract_gold_messages import HEADER_ENTRIES, extract_messages, parse_header


# Raw structural bytes used by the cinematic/event text language.  0x20 is
# intentionally not reserved: v25/v39 already protects Korean glyphs while
# searching for spaces/underscores, and removing 0x20 can exceed 256 KiB.
SCENE_RANK_RESERVED = bytes.fromhex("21 25 26 5D 40 23 7C")
SCENE_RANK_RESERVED_SET = frozenset(SCENE_RANK_RESERVED)
JAN_ETTE_MESSAGE_RANGE = range(29600, 29757)
MAX_HUFFMAN_ITERATIONS = 32

# v19 resident renderer layout, retained by v39/v41.
VBFONT_RESIDENT_STRING_START = 0x0937
VBFONT_RESIDENT_WIDTH_START = 0x0A30
VBFONT_V39_DISPATCHER_START = 0x0AF0
VBFONT_V39_DISPATCHER_END = 0x0B6C
VBFONT_INVERSE_TABLE = 0x0D00
VBFONT_GLYPH_TABLE = 0x0E00
VBFONT_GLYPH_RECORD_SIZE = 7
V19_EXPECTED_ALPHABET_LEN = 121
V19_EXPECTED_CUSTOM_COUNT = 1110


def _codebook_pairs_from_report(report: dict[str, object]) -> dict[str, tuple[int, int]]:
    """Accept both historical ``char: 'AA BB'`` and metadata codebooks."""
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
    """Recover the rank alphabet used when rectangular pairs were assigned."""
    pairs = list(codebook.values())
    if not pairs:
        raise ValueError("cannot recover rank alphabet from an empty codebook")

    first_left = pairs[0][0]
    alphabet: list[int] = []
    for left, right in pairs:
        if left != first_left:
            break
        alphabet.append(right)
    if not alphabet or alphabet[0] != first_left:
        raise ValueError("published codebook does not begin with rank pair (0, 0)")
    if len(alphabet) == len(pairs):
        raise ValueError("codebook is too small to expose a complete rank row")
    if len(set(alphabet)) != len(alphabet):
        raise ValueError("recovered first rank row contains duplicate bytes")

    size = len(alphabet)
    for index, pair in enumerate(pairs):
        if index // size >= size:
            raise ValueError("published codebook exceeds recovered rectangular capacity")
        expected = (alphabet[index // size], alphabet[index % size])
        if pair != expected:
            raise ValueError(
                "published codebook is not a dense rectangular rank sequence at "
                f"index {index}: expected {expected!r}, found {pair!r}"
            )
    return alphabet


def decode_localized_display(raw: bytes, codebook: dict[str, tuple[int, int]]) -> str:
    """Decode v41 Korean stream while preserving literal non-printable bytes."""
    reverse = {pair: character for character, pair in codebook.items()}
    output: list[str] = []
    cursor = 0
    while cursor < len(raw):
        value = raw[cursor]
        cursor += 1
        if value != DEFAULT_ESCAPE:
            if 0x20 <= value <= 0x7E:
                output.append(chr(value))
            else:
                output.append(f"<0x{value:02X}>")
            continue
        if cursor >= len(raw):
            raise ValueError("localized record ends after escape byte")
        if raw[cursor] == DEFAULT_ESCAPE:
            output.append(f"<0x{DEFAULT_ESCAPE:02X}>")
            cursor += 1
            continue
        if cursor + 1 >= len(raw):
            raise ValueError("localized record ends inside a Korean pair")
        pair = (raw[cursor], raw[cursor + 1])
        cursor += 2
        try:
            output.append(reverse[pair])
        except KeyError as exc:
            raise ValueError(f"unknown localized codebook pair {pair!r}") from exc
    return "".join(output)


def safe_rank_alphabet(codes: dict[int, tuple[int, ...]]) -> list[int]:
    return sorted(
        (
            value
            for value in codes
            if value != DEFAULT_ESCAPE and value not in SCENE_RANK_RESERVED_SET
        ),
        key=lambda value: (len(codes[value]), value),
    )


def build_safe_unicode_codebook(
    texts: list[str],
    codes: dict[int, tuple[int, ...]],
) -> tuple[dict[str, tuple[int, int]], list[int]]:
    frequencies: Counter[str] = Counter()
    for text in texts:
        for unit in iter_translation_units(text):
            if isinstance(unit, str) and (ord(unit) > 0x7F or ord(unit) not in codes):
                frequencies[unit] += 1

    alphabet = safe_rank_alphabet(codes)
    ordered_chars = sorted(
        frequencies,
        key=lambda character: (-frequencies[character], ord(character)),
    )
    capacity = len(alphabet) * len(alphabet)
    if len(ordered_chars) > capacity:
        raise ValueError(
            f"{len(ordered_chars)} custom characters exceed safe pair capacity {capacity}"
        )
    pairs = itertools.product(alphabet, repeat=2)
    return {
        character: pair
        for character, pair in zip(ordered_chars, pairs)
    }, alphabet


def count_reserved_rank_payloads(raw: bytes) -> int:
    """Count structural bytes only when they occur inside Korean rank pairs."""
    count = 0
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
        count += int(raw[cursor + 1] in SCENE_RANK_RESERVED_SET)
        count += int(raw[cursor + 2] in SCENE_RANK_RESERVED_SET)
        cursor += 3
    return count


def _rank_table(alphabet: list[int]) -> bytes:
    ranks = {value: index for index, value in enumerate(alphabet)}
    if len(ranks) > 0xFF:
        raise ValueError("rank alphabet no longer fits the byte inverse table")
    return bytes(ranks.get(value, 0xFF) for value in range(256))


def patch_vbfont_rank_decoder(
    vbfont: bytes,
    old_codebook_report: dict[str, object],
    new_misc: bytes,
    new_codebook: dict[str, tuple[int, int]],
    new_alphabet: list[int],
) -> tuple[bytes, dict[str, object]]:
    """Migrate the resident v19/v39 VBFONT0 renderer to the safe rank mapping."""
    old_codebook = _codebook_pairs_from_report(old_codebook_report)
    old_order = list(old_codebook)
    old_alphabet = recover_dense_rank_alphabet(old_codebook)
    if len(old_alphabet) != V19_EXPECTED_ALPHABET_LEN:
        raise ValueError(
            f"v41 rank alphabet is {len(old_alphabet)}, expected {V19_EXPECTED_ALPHABET_LEN}"
        )
    if len(old_order) != V19_EXPECTED_CUSTOM_COUNT:
        raise ValueError(
            f"v41 glyph count is {len(old_order)}, expected {V19_EXPECTED_CUSTOM_COUNT}"
        )

    converged = safe_rank_alphabet(huffman_codes(new_misc))
    if converged != new_alphabet:
        raise ValueError("safe rank alphabet did not converge with final MISC.HDR")

    new_order = list(new_codebook)
    old_set = set(old_order)
    new_set = set(new_order)
    added = sorted(new_set - old_set)
    if added:
        raise ValueError(
            "new v42 codebook contains characters without a v41 resident glyph: "
            f"{added[:8]!r}"
        )
    unused_legacy = [character for character in old_order if character not in new_set]
    embedded_order = new_order + unused_legacy
    if len(embedded_order) != len(old_order):
        raise AssertionError("resident glyph count changed during migration")

    if len(vbfont) < VBFONT_GLYPH_TABLE + len(old_order) * VBFONT_GLYPH_RECORD_SIZE:
        raise ValueError("VBFONT0.VGA is too small for the resident glyph table")
    data = bytearray(vbfont)

    old_inverse = _rank_table(old_alphabet)
    actual_inverse = bytes(
        data[VBFONT_INVERSE_TABLE : VBFONT_INVERSE_TABLE + len(old_inverse)]
    )
    if actual_inverse != old_inverse:
        first_diff = next(
            (
                index
                for index, (actual, expected) in enumerate(zip(actual_inverse, old_inverse))
                if actual != expected
            ),
            None,
        )
        raise ValueError(
            "VBFONT0 0x0D00 inverse table does not match published v41 codebook; "
            f"first_diff={first_diff!r}"
        )
    new_inverse = _rank_table(new_alphabet)
    data[VBFONT_INVERSE_TABLE : VBFONT_INVERSE_TABLE + 256] = new_inverse

    glyph_bytes = len(old_order) * VBFONT_GLYPH_RECORD_SIZE
    glyph_start = VBFONT_GLYPH_TABLE
    glyph_end = glyph_start + glyph_bytes
    old_glyphs = bytes(data[glyph_start:glyph_end])
    old_index = {character: index for index, character in enumerate(old_order)}
    reordered = b"".join(
        old_glyphs[
            old_index[character] * VBFONT_GLYPH_RECORD_SIZE :
            (old_index[character] + 1) * VBFONT_GLYPH_RECORD_SIZE
        ]
        for character in embedded_order
    )
    if len(reordered) != glyph_bytes:
        raise AssertionError("resident glyph migration changed glyph table size")
    data[glyph_start:glyph_end] = reordered

    old_len_pattern = (
        b"\xBB"
        + len(old_alphabet).to_bytes(2, "little")
        + b"\xF7\xE3"  # mov bx,ALPHABET_LEN ; mul bx
    )
    new_len_pattern = (
        b"\xBB"
        + len(new_alphabet).to_bytes(2, "little")
        + b"\xF7\xE3"
    )
    resident = bytes(data[VBFONT_RESIDENT_STRING_START:VBFONT_RESIDENT_WIDTH_START])
    pattern_at = resident.find(old_len_pattern)
    if pattern_at < 0 or resident.find(old_len_pattern, pattern_at + 1) >= 0:
        raise ValueError(
            "expected exactly one v41 ALPHABET_LEN multiply in resident_string"
        )
    alphabet_patch_offset = VBFONT_RESIDENT_STRING_START + pattern_at
    data[
        alphabet_patch_offset : alphabet_patch_offset + len(old_len_pattern)
    ] = new_len_pattern

    old_dispatcher = vbfont[VBFONT_V39_DISPATCHER_START:VBFONT_V39_DISPATCHER_END]
    new_dispatcher = bytes(
        data[VBFONT_V39_DISPATCHER_START:VBFONT_V39_DISPATCHER_END]
    )
    if old_dispatcher != new_dispatcher:
        raise AssertionError("v39 resident scene dispatcher was modified")
    if len(data) != len(vbfont):
        raise AssertionError("VBFONT0.VGA size changed")

    return bytes(data), {
        "target_file": "VBFONT0.VGA",
        "old_rank_alphabet_source": "published_codebook_dense_pairs",
        "old_rank_alphabet_size": len(old_alphabet),
        "new_rank_alphabet_size": len(new_alphabet),
        "inverse_rank_table_offset": f"0x{VBFONT_INVERSE_TABLE:04X}",
        "glyph_table_offset": f"0x{VBFONT_GLYPH_TABLE:04X}",
        "glyph_record_size": VBFONT_GLYPH_RECORD_SIZE,
        "active_glyph_record_count": len(new_order),
        "embedded_glyph_record_count": len(embedded_order),
        "unused_legacy_glyphs": unused_legacy,
        "glyph_table_reordered": old_order != embedded_order,
        "glyph_character_set_preserved": set(embedded_order) == old_set,
        "alphabet_size_patch_offset": f"0x{alphabet_patch_offset + 1:04X}",
        "v39_dispatcher_preserved": True,
    }


def transcode_message_bank(
    hdr_raw: bytes,
    data_raw: bytes,
    misc_raw: bytes,
    old_codebook_report: dict[str, object],
) -> tuple[bytes, bytes, bytes, dict[str, object], dict[int, str], dict[int, bytes]]:
    declared, entries, sentinel_count = parse_header(hdr_raw, "dos")
    records = extract_messages(data_raw, entries, misc_raw)
    old_codebook = _codebook_pairs_from_report(old_codebook_report)
    texts = {
        record.message_id: decode_localized_display(
            base64.b64decode(record.raw_base64), old_codebook
        )
        for record in records
    }

    base_alphabet = sorted(huffman_codes(misc_raw))
    codes = huffman_codes(misc_raw)
    output_misc = misc_raw
    codebook: dict[str, tuple[int, int]] = {}
    rank_alphabet: list[int] = []
    encoded_by_id: dict[int, bytes] = {}
    iterations = 0

    for iterations in range(1, MAX_HUFFMAN_ITERATIONS + 1):
        codebook, rank_alphabet = build_safe_unicode_codebook(list(texts.values()), codes)
        encoded_by_id = {
            message_id: encode_translation(text, codes, codebook, DEFAULT_ESCAPE)
            for message_id, text in texts.items()
        }
        frequencies: Counter[int] = Counter(
            value for raw in encoded_by_id.values() for value in raw
        )
        output_misc = serialize_huffman_tree(
            build_huffman_tree(frequencies, base_alphabet)
        )
        next_codes = huffman_codes(output_misc)
        if safe_rank_alphabet(next_codes) == rank_alphabet:
            codes = next_codes
            break
        codes = next_codes
    else:
        raise ValueError("safe rank alphabet failed to converge")

    packed_by_id = {
        message_id: encode_huffman(raw, codes)
        for message_id, raw in encoded_by_id.items()
    }
    by_range: dict[int, list[object]] = {}
    for record in records:
        by_range.setdefault(record.range_index, []).append(record)
    output_data, output_entries, padding_bytes = pack_message_ranges(
        entries,
        by_range,
        packed_by_id,
    )
    used_data_bytes = len(output_data)
    if used_data_bytes > MAX_DOS_DATA_SIZE:
        raise ValueError(
            f"safe message bank uses {used_data_bytes} bytes; DOS limit is {MAX_DOS_DATA_SIZE}"
        )
    output_data += bytes(MAX_DOS_DATA_SIZE - used_data_bytes)

    entry_struct = HEADER_ENTRIES["dos"]
    output_header = bytearray(struct.pack("<H", declared))
    for entry in output_entries:
        output_header.extend(
            entry_struct.pack(entry.start_id, entry.bank_offset, entry.id_span, entry.bank)
        )
    output_header.extend(bytes(sentinel_count * entry_struct.size))

    old_raw_by_id = {
        record.message_id: base64.b64decode(record.raw_base64) for record in records
    }
    old_collisions = sum(count_reserved_rank_payloads(raw) for raw in old_raw_by_id.values())
    new_collisions = sum(count_reserved_rank_payloads(raw) for raw in encoded_by_id.values())
    jan_ette_old = sum(
        count_reserved_rank_payloads(old_raw_by_id[message_id])
        for message_id in JAN_ETTE_MESSAGE_RANGE
        if message_id in old_raw_by_id
    )
    jan_ette_new = sum(
        count_reserved_rank_payloads(encoded_by_id[message_id])
        for message_id in JAN_ETTE_MESSAGE_RANGE
        if message_id in encoded_by_id
    )
    if old_collisions == 0:
        raise ValueError("v41 input unexpectedly has no reserved rank-byte collisions")
    if new_collisions != 0 or jan_ette_new != 0:
        raise ValueError("reserved rank-byte collisions remain after v42 transcode")

    new_reverse = {pair: char for char, pair in codebook.items()}
    for message_id, raw in encoded_by_id.items():
        reconstructed: list[str] = []
        cursor = 0
        while cursor < len(raw):
            value = raw[cursor]
            cursor += 1
            if value != DEFAULT_ESCAPE:
                reconstructed.append(
                    chr(value) if 0x20 <= value <= 0x7E else f"<0x{value:02X}>"
                )
                continue
            if raw[cursor] == DEFAULT_ESCAPE:
                reconstructed.append(f"<0x{DEFAULT_ESCAPE:02X}>")
                cursor += 1
                continue
            pair = (raw[cursor], raw[cursor + 1])
            cursor += 2
            reconstructed.append(new_reverse[pair])
        if "".join(reconstructed) != texts[message_id]:
            raise ValueError(f"message {message_id} changed during safe transcode")

    report = dict(old_codebook_report)
    report.update(
        {
            "format": "Wizardry VII DOS v42 scene-safe Korean codebook",
            "custom_character_count": len(codebook),
            "huffman_iterations": iterations,
            "used_data_bytes": used_data_bytes,
            "padding_bytes_between_ranges": padding_bytes,
            "padded_data_size": len(output_data),
            "reserved_rank_bytes": [f"0x{value:02X}" for value in SCENE_RANK_RESERVED],
            "rank_alphabet_size": len(rank_alphabet),
            "rank_alphabet": [f"{value:02X}" for value in rank_alphabet],
            "rank_payload_collisions_before": old_collisions,
            "rank_payload_collisions_after": new_collisions,
            "jan_ette_collisions_before": jan_ette_old,
            "jan_ette_collisions_after": jan_ette_new,
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
        texts,
        encoded_by_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v41-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")
    source_dir = (
        args.v41_dir / "DSAVANT"
        if (args.v41_dir / "DSAVANT").is_dir()
        else args.v41_dir
    )

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
        _texts,
        _encoded,
    ) = transcode_message_bank(old_hdr, old_data, old_misc, old_codebook_report)
    new_codebook = _codebook_pairs_from_report(new_codebook_report)
    new_alphabet = [int(value, 16) for value in new_codebook_report["rank_alphabet"]]

    payloads: dict[str, bytes] = {}
    renderer_report: dict[str, object] | None = None
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
            data, renderer_report = patch_vbfont_rank_decoder(
                data,
                old_codebook_report,
                new_misc,
                new_codebook,
                new_alphabet,
            )
        payloads[f"DSAVANT/{name}"] = data

    if renderer_report is None:
        raise ValueError("VBFONT0.VGA was not found in v41 payload")

    report = {
        "format": "Wizardry VII DOS v42 scene/event-safe Korean rank encoding",
        "root_cause": [
            "v41 Korean rank bytes may equal raw cinematic control bytes ! % & ] @ # |",
            "the event control dispatcher can mistake an internal Korean payload byte for a real command",
            "this can select the wrong scene/picture and desynchronize following text",
        ],
        "changes": [
            "transcode all localized message records to a rank alphabet that excludes scene-control bytes",
            "keep literal ASCII scene commands unchanged",
            "keep 0x20 space available for compression; the v39 delimiter helper already protects Korean spaces",
            "rewrite VBFONT0.VGA inverse-rank table and resident ALPHABET_LEN",
            "reorder fixed 7-byte resident glyph records to the new safe codebook order",
            "retain unused legacy glyph records at the tail so CUSTOM_COUNT and file size stay unchanged",
            "leave DS.EXE and the v39 0x0AF0 scene dispatcher untouched",
            "retain the v41 roster M/F boundary fix and all v39 overlay-safe helpers",
        ],
        "event_regression_target": {
            "messages": [JAN_ETTE_MESSAGE_RANGE.start, JAN_ETTE_MESSAGE_RANGE.stop - 1],
            "expected": "Jan-Ette/Helazoid encounter remains on its own event branch",
            "wrong_v41_symptom": "H'Jenn-Ra/T'Rang scene and MON42 picture may be selected",
        },
        "message_transcode": {
            key: value
            for key, value in new_codebook_report.items()
            if key
            in {
                "custom_character_count",
                "huffman_iterations",
                "used_data_bytes",
                "padding_bytes_between_ranges",
                "padded_data_size",
                "reserved_rank_bytes",
                "rank_alphabet_size",
                "rank_payload_collisions_before",
                "rank_payload_collisions_after",
                "jan_ette_collisions_before",
                "jan_ette_collisions_after",
            }
        },
        "renderer": renderer_report,
        "invariants": [
            "all decoded message text and literal control bytes round-trip unchanged",
            "no reserved scene-control byte appears inside any Korean rank pair",
            "MSG.DBS remains exactly 256 KiB",
            "DS.EXE is byte-for-byte inherited from v0.41",
            "VBFONT0.VGA and every OVR keep their file sizes",
            "v39 resident scene dispatcher, save format, roster fix, and gameplay code are unchanged",
        ],
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V42_REPORT.json"] = report_raw

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
