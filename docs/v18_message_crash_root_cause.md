# Wizardry 7 DOS v18 message crash: root-cause report

Date: 2026-08-23

## Verdict

DIAG C and DIAG E fail because the rebuilt `MSG.DBS` violates a hidden DOS
record-placement constraint.  The DOS lookup routine can follow a target
record payload across a `0x400`-byte bank boundary, but it cannot follow the
length-byte positions of preceding subindices in the same `MSG.HDR` entry
across that boundary.

The v18 builder writes all ranges sequentially and records only each range's
starting bank/offset.  It does not align or repack a complete range so that
all of its record starts remain in the starting bank.  Consequently the DOS
routine indexes beyond its current 1 KiB message-bank cache and interprets
unrelated cache memory as record lengths and packed data.

Measured against the supplied files:

| Data set | Violating `MSG.HDR` entries | Misaddressed subindex records |
| --- | ---: | ---: |
| Clean DOS original | 0 | 0 |
| v18 / DIAG C / DIAG E | 187 | 1,911 |

DIAG E contains the same `MISC.HDR`, `MSG.HDR`, and `MSG.DBS` bytes as DIAG C,
so its string-width patch cannot correct this file-layout defect.

## DOS code evidence

`DS.EXE` is a 16-bit MZ executable with a `0x200`-byte header.  Code/image
offsets below therefore map to file offsets by adding `0x200`.

### `MSG.HDR` lookup and six-byte entry format

The range lookup starts at image `CS:045D` / file `0x065D`.

- `CS:0463` reads the range count at data offset `DS:100C`.
- `CS:048E-0493` multiplies the selected index by six.
- `CS:0493-0496` adds the entry-table base `DS:100E`.
- `CS:049B` reads the `u16` start ID at entry `+0`.
- `CS:04A8` reads the inclusive `u8` ID span at entry `+4`.
- The message reader at `CS:05B2` reads the `u16` bank offset at `+2` and at
  `CS:059F` reads the `u8` bank at `+5`.

Thus the DOS entry is exactly:

```text
u16 start_id, u16 bank_offset, u8 inclusive_id_span, u8 bank
```

The supplied original and v18 headers both declare 1,924 entries, retain 38
zero sentinel slots, and describe 11,019 records.  All v18 offsets are below
`0x400`, all bank fields fit in eight bits, and all inclusive span fields fit
in eight bits.

### `MSG.DBS` bank loading

The bank-cache loader is at image `CS:04C6` / file `0x06C6`.

- `CS:0519-0525` shifts the bank number left ten times, establishing the
  `bank * 0x400` file address.
- `CS:0532-0541` reads exactly `0x400` bytes into the current-bank buffer at
  `DS:3E12`.
- Four cached banks are maintained, but the current-bank view used by the
  record walker begins at `DS:3E12`.

### The faulty hidden assumption

The main message reader starts at image `CS:0582` / file `0x0782`.

To reach a requested subindex, `CS:05BD-05D7` repeatedly does the equivalent
of:

```text
length = current_bank_buffer[offset]
offset += 1 + length
message_id += 1
```

This loop neither tests `offset >= 0x400` nor loads the following bank.  An
offset beyond `0x3FF` therefore indexes memory after `DS:3E12`, not the next
logical `MSG.DBS` bank.

In contrast, after it has found the target record, `CS:05F2-063E` explicitly
handles that one packed payload crossing the boundary: it copies the tail of
the current bank, loads `bank + 1`, resets the offset to zero, and copies the
remainder.  This explains an otherwise surprising property of the original
data: an entry's final record payload may cross a bank, but the length byte of
every record in that entry remains in the entry's starting bank.

The clean original has 245 supported final-payload crossings and zero
record-start crossings.  Its largest entry occupies 1,060 bytes only because
the final payload is allowed to extend into the next bank.

The v18 sequential layout breaks that invariant.  The first violations in
file order include:

| Entry | ID range | Starting bank:offset | First misaddressed ID |
| ---: | --- | --- | ---: |
| 14 | 700-707 | `0:984` | 703 |
| 17 | 847-939 | `1:555` | 899 |
| 25 | 1150-1169 | `2:913` | 1162 |
| 45 | 1770-1796 | `4:1017` | 1771 |
| 62 | 2500-2555 | `7:1005` | 2502 |

Entry 62 is especially relevant during startup: IDs 2500-2574 are decoded by
the pre-frame initialization/protection logic around image `CS:0A0B`.  A
DOSBox-X breakpoint at `CS:0582` observed ID `0x0A05` (2565) as the first
decode in that run.  The exact first ID is RNG-dependent; ID 2565 belongs to
the following safe entry, while most of entry 62 (2502-2555) is structurally
misaddressed in v18.

## Huffman loader and decoder

The suspected Huffman-node limit is not the failure.

### `MISC.HDR` loading

The loader is at image `CS:3DA9` / file `0x3FA9`.

- `CS:3DB3` sets `CX=0400h`.
- `CS:3DB6-3DC4` selects the table segment and performs DOS read function
  `AH=3Fh` into offset zero.

The DOS program therefore loads and makes available the full 1,024-byte
table, not only the English tree's used `0x1E4` bytes.

### Huffman decode

The decoder is at image `CS:3E02` / file `0x4002`.

- `CS:3E1D-3E20` reads the first packed byte into `AL`, clears `AH`, and saves
  it as the decoded output count.  It is an unsigned eight-bit length, so a
  single decoded record is limited to 255 bytes.
- `CS:3E2F-3E38` emits exactly that many bytes.
- `CS:3E4F-3E84` treats a table word with bit 15 set as a negative internal
  node reference, negates it, and multiplies it by four.  Node offsets are
  16-bit; the 1,024-byte table can hold 256 four-byte nodes.
- `CS:3E3A` writes a terminating zero word after the output.

Tree measurements:

| Tree | Leaves | Internal nodes | Maximum node | Used bytes |
| --- | ---: | ---: | ---: | ---: |
| Original | 122 | 121 | 120 | `0x1E4` (484) |
| v18 | 228 | 227 | 226 | `0x38C` (908) |

The v18 tree remains within the DOS decoder's 256-node/1,024-byte limit.  All
11,019 v18 records round-trip through an instruction-equivalent offline
decoder.  The largest v18 decoded record is 86 bytes and the largest packed
payload is 81 bytes, so neither eight-bit record-length field is near 255.

## Other requested constraints

- `MSG.DBS` is exactly `0x40000` bytes.  v18's last referenced starting bank
  is 223, within the `u8` field and file limit.
- `id_span` is inclusive.  One entry describes `id_span + 1` records; v18
  preserves every original span and ID range.
- A main index with multiple subindices is not decoded into one concatenated
  destination buffer.  Each requested subindex is decoded separately.  The
  critical group-level constraint applies to packed record *start addresses*,
  not to a combined decoded destination.
- The base executable's packed staging buffer at `CS:0582` has room for the
  one-byte packed length limit.  Known base-module decoded buffers are also
  larger than the v18 startup records.  Overlay-specific UI buffers still
  merit QA after the placement bug is fixed, but they do not explain the
  invalid reads proven above.
- The sequence of C0 control bytes (`00-1F` and `7F`) is byte-identical between
  original and v18 for all 11,019 records.  Control-code loss is not the
  initial cause.
- The string-width routine patched in DIAG E is a real independent high-byte
  bug at image `CS:38CA` / file `0x3ACA`, but E reaches the same malformed
  record-placement path first and therefore remains black.

## Required repair invariant

Do not merely re-run generic Huffman validation.  A repaired builder must
prove, for every header entry and every subindex:

```text
floor(record_length_byte_address / 0x400) == entry.bank
```

Only the final selected record's payload bytes may extend into `entry.bank+1`.
The rebuilt file must also remain within 256 banks and the fixed 1,924-entry
header capacity unless the executable's header storage/loading is separately
changed.

## Runtime differential confirmation

Using the supplied v18 font/driver files and the clean original `DS.EXE`, two
DOSBox-X runs were made with only the message layer changed:

- Original v18 `MISC.HDR`/`MSG.HDR`/`MSG.DBS`: remained a completely black
  screen after 10 seconds.
- The same files after range-aware repacking: passed the intro animation and
  reached the Crusaders of the Dark Savant title screen.

The repacked run preserved all 11,019 decoded message byte strings exactly;
only physical record placement and the corresponding six-byte header offsets
changed.  This is a runtime A/B confirmation of the static cause, not merely
an offline Huffman round-trip result.

No game patch was produced as part of this root-cause phase.
