#!/usr/bin/env python3
"""Build v42 by removing scene-control bytes from Korean rank payloads.

v0.41 still allows the two rank bytes inside ``ESC + rank + rank`` Korean
characters to equal raw scene-parser control bytes.  Most text paths understand
our three-byte glyph unit, but the cinematic/event control dispatcher still
examines raw bytes.  A Korean payload byte such as ``%``, ``&`` or ``]`` can
therefore be mistaken for a real scene command.  The result can be much worse
than a bad glyph: the wrong picture/event branch may run and the following text
stream loses synchronization.

v42 transcodes the already-localized v0.41 message bank without needing the
translation workbook.  It keeps literal ASCII scene commands intact, but never
uses the following bytes as Korean rank payload bytes::

    ! % & ] @ # |

Space (0x20) deliberately remains available because it is the cheapest Huffman
symbol and excluding it can push MSG.DBS past the DOS 256 KiB bank limit.  The
scene delimiter helpers introduced in v25/v39 already skip complete Korean
glyphs when searching for spaces.

The Unicode character order does not change, so the existing pre-rendered glyph
table in DS.EXE remains valid.  Only the 256-byte inverse-rank table and the
embedded rank-alphabet size are rewritten in DS.EXE.  All file sizes remain
unchanged.
"""

from __future__ import annotations

import argparse
import base64
import itertools
import json
import struct
from collections import Counter
from pathlib import Path

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
from patch_dos_korean_renderer import CAVE_END, CAVE_START, MZ_HEADER_SIZE


# These bytes have raw structural meaning in the cinematic/event text parser.
# 0x20 (space) is intentionally NOT reserved; v25/v39 already protect it while
# splitting words, and keeping it in the rank alphabet saves several KiB.
SCENE_RANK_RESERVED = bytes.fromhex("21 25 26 5D 40 23 7C")
SCENE_RANK_RESERVED_SET = frozenset(SCENE_RANK_RESERVED)
JAN_ETTE_MESSAGE_RANGE = range(29600, 29757)
MAX_HUFFMAN_ITERATIONS = 32


def _codebook_pairs_from_report(report: dict[str, object]) -> dict[str, tuple[int, int]]:
    raw = report.get("codebook")
    if not isinstance(raw, dict):
        raise ValueError("korean_codebook.json has no codebook object")
    result: dict[str, tuple[int, int]] = {}
    for character, metadata in raw.items():
        if not isinstance(character, str) or not isinstance(metadata, dict):
            raise ValueError("invalid codebook entry")
        encoded = metadata.get("bytes")
        if not isinstance(encoded, str):
            raise ValueError(f"codebook entry {character!r} has no byte pair")
        left_hex, right_hex = encoded.split()
        result[character] = (int(left_hex, 16), int(right_hex, 16))
    return result


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
    pairs = itertools.product(alphabet, repeat=2)
    ordered_chars = sorted(
        frequencies,
        key=lambda character: (-frequencies[character], ord(character)),
    )
    capacity = len(alphabet) * len(alphabet)
    if len(ordered_chars) > capacity:
        raise ValueError(
            f"{len(ordered_chars)} custom characters exceed safe pair capacity {capacity}"
        )
    return {
        character: pair
        for character, pair in zip(ordered_chars, pairs)
    }, alphabet


def count_reserved_rank_payloads(raw: bytes) -> int:
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


def patch_renderer_rank_decoder(
    ds_exe: bytes,
    old_misc: bytes,
    old_codebook_report: dict[str, object],
    new_misc: bytes,
    new_codebook: dict[str, tuple[int, int]],
    new_alphabet: list[int],
) -> tuple[bytes, dict[str, object]]:
    old_pairs = _codebook_pairs_from_report(old_codebook_report)
    if list(old_pairs) != list(new_codebook):
        raise ValueError(
            "Unicode codebook order changed; existing pre-rendered glyph table cannot be reused"
        )

    old_codes = huffman_codes(old_misc)
    old_alphabet = sorted(
        (value for value in old_codes if value != DEFAULT_ESCAPE),
        key=lambda value: (len(old_codes[value]), value),
    )
    converged_alphabet = safe_rank_alphabet(huffman_codes(new_misc))
    if converged_alphabet != new_alphabet:
        raise ValueError("safe rank alphabet did not converge with final MISC.HDR")

    old_table = _rank_table(old_alphabet)
    new_table = _rank_table(new_alphabet)
    data = bytearray(ds_exe)
    cave_start = MZ_HEADER_SIZE + CAVE_START
    cave_end = min(len(data), MZ_HEADER_SIZE + CAVE_END)
    cave = bytes(data[cave_start:cave_end])

    table_at = cave.find(old_table)
    if table_at < 0 or cave.find(old_table, table_at + 1) >= 0:
        raise ValueError("expected exactly one v41 renderer rank table in DS.EXE cave")
    table_file_offset = cave_start + table_at
    data[table_file_offset : table_file_offset + 256] = new_table

    old_size_pattern = (
        b"\xB9" + len(old_alphabet).to_bytes(2, "little") + b"\xF7\xE1"
    )
    new_size_pattern = (
        b"\xB9" + len(new_alphabet).to_bytes(2, "little") + b"\xF7\xE1"
    )
    cave = bytes(data[cave_start:cave_end])
    size_at = cave.find(old_size_pattern)
    if size_at < 0 or cave.find(old_size_pattern, size_at + 1) >= 0:
        raise ValueError("expected exactly one renderer alphabet-size multiply in DS.EXE cave")
    size_file_offset = cave_start + size_at
    data[size_file_offset : size_file_offset + len(old_size_pattern)] = new_size_pattern

    return bytes(data), {
        "old_rank_alphabet_size": len(old_alphabet),
        "new_rank_alphabet_size": len(new_alphabet),
        "rank_table_file_offset": f"0x{table_file_offset:X}",
        "alphabet_size_file_offset": f"0x{size_file_offset + 1:X}",
        "glyph_order_preserved": True,
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
        elif name == "DS.EXE":
            data, renderer_report = patch_renderer_rank_decoder(
                data,
                old_misc,
                old_codebook_report,
                new_misc,
                new_codebook,
                new_alphabet,
            )
        payloads[f"DSAVANT/{name}"] = data

    if renderer_report is None:
        raise ValueError("DS.EXE was not found in v41 payload")

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
            "rewrite the DS.EXE inverse-rank table and alphabet-size constant only",
            "reuse the existing glyph table because Unicode character order is unchanged",
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
            "DS.EXE size and every OVR/VGA file size remain unchanged",
            "glyph order, save format, roster fix, and gameplay code are unchanged",
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
