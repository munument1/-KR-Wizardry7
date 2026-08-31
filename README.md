# Wizardry 7 Korean translation workspace

The local GOG installation is never committed. Original translation-related
files are copied to the ignored `original/` directory before analysis or patch
experiments.

## Project status

- The active target is now the DOS release in `DSAVANT`; the Gold prototype is
  preserved as rendering research and a fallback.
- The current source release is **v39**. Korean menus, the animated Korean
  title, the Aletheides opening, the first planetary event, save-and-resume,
  save-and-quit, and reload of the newly written save have been runtime-verified.
- The v20-v37 save failure was caused by persistent helpers at `0xF790` and
  `0xF7B0` being overwritten by loaded overlays. v39 moves every root helper
  below overlay origin `0x5047` and moves scene parsing into the resident font
  segment before its `0x0D00` inverse table.
- DOS `MSG.DBS` Huffman decoding and the six-byte `MSG.HDR` range layout are
  supported by the message extractor.
- DOS and Gold share 11,016 messages byte-for-byte after decoding; only two
  message boundaries differ, and DOS has one additional message.
- DOS `SCENARIO.DBS` uses the same fixed-width item/monster layout as Gold, so
  all 1,600 extracted scenario rows can be reused.
- DOS translation CSV reinsertion supports the original Huffman tree and a
  reversible three-byte Korean character stream. The generated codebook and
  renderer patch are kept synchronized by guarded builders and tests.
- GOG Wizardry 7 Gold message and scenario string extraction is implemented.
- Translation-ready CSV and workbook generation is implemented locally.
- An x86 WinMM proxy renders two-byte KS X 1001 Hangul through the game's
  original VBFONT renderer.
- An 8x8 `한` smoke test has been verified in the running game.
- The game's basic string-width routine is hooked so a two-byte Hangul code is
  measured as one glyph.
- The proxy forwards `PlaySoundW` for the GOG launcher and installs fixed-address
  hooks only inside the actual Wizardry executable.
- All executable and overlay changes are fixed-size and hash/byte guarded. The
  purchased game archive, patched game binaries, generated ZIPs, and extracted
  text remain local and are intentionally excluded from Git.

This public repository intentionally excludes purchased game files, extracted
game text, locally generated patches, API credentials, and build outputs. Supply
your own GOG installation when running the tools.

## Build the current v39 overlay-safe package

After reproducing the v37 payload locally, build v39 with:

```powershell
python tools\build_dos_v39_overlay_safe_resident.py `
  --v37-dir outputs\v37_fixed_scene_helpers_final `
  --output-dir outputs\v39_overlay_safe_resident_final `
  --zip-output outputs\Wizardry7_Korean_v39_overlay_safe_resident.zip
```

The generated package contains patched commercial-game payloads and therefore
must remain local. GitHub releases publish the source toolchain and release
notes only. Run the full regression suite with:

```powershell
python -m unittest discover -s tests -v
```

## Extract the main message database

DOS (`MISC.HDR` is found automatically beside `MSG.HDR`):

```powershell
python tools\extract_gold_messages.py `
  --hdr "D:\Wizardry 7\DSAVANT\MSG.HDR" `
  --data "D:\Wizardry 7\DSAVANT\MSG.DBS" `
  --output-dir outputs\dos_extracted\msg
```

Gold:

```powershell
python tools\extract_gold_messages.py `
  --hdr original\MSG.HDR `
  --data original\MSG.GLD `
  --output-dir extracted\msg
```

Outputs:

- `messages_for_translation.csv`: UTF-8 BOM spreadsheet-friendly translation table.
- `messages.json`: metadata plus all records and lossless Base64/hex payloads.
- `messages.jsonl`: one machine-readable record per line.
- `extraction_report.json`: source hashes and structural validation counts.

The CSV displays non-printable game control bytes as `<0xNN>`. Do not translate,
delete, or reorder these markers. The JSON outputs retain the original payloads
for later byte-perfect rebuild verification.

## Rebuild the DOS message database

Export the Google Sheet `Messages` tab as CSV, then run:

```powershell
python tools\build_dos_messages.py `
  --hdr "D:\Wizardry 7\DSAVANT\MSG.HDR" `
  --data "D:\Wizardry 7\DSAVANT\MSG.DBS" `
  --misc "D:\Wizardry 7\DSAVANT\MISC.HDR" `
  --translations messages_translated.csv `
  --output-dir outputs\dos_patch\DSAVANT
```

The builder rejects source-text mismatches, Huffman-compresses applicable
translations, and emits `MISC.HDR`, `MSG.HDR`, `MSG.DBS`, and
`korean_codebook.json`.  It packs each complete `MSG.HDR` range inside one
`0x400`-byte bank (inserting unreferenced padding between ranges) because the
DOS subindex walker cannot cross a bank while scanning preceding records.
The build report must show `record_start_crossings: 0` and `used_bank_count <= 256`.
Do not install these files yet:
the DOS executable still needs the matching renderer-side decoder.

To repair an existing translated DOS message layer while preserving its
Huffman payloads byte-for-byte, use:

```powershell
python tools\repack_dos_message_banks.py `
  --hdr translated\MSG.HDR `
  --data translated\MSG.DBS `
  --misc translated\MISC.HDR `
  --output-dir outputs\dos_patch\repacked
```

The command writes a new six-byte `MSG.HDR`, a padded 256 KiB `MSG.DBS`, the
unchanged `MISC.HDR`, and `REPACK_REPORT.json`. It refuses a range larger than
one 0x400-byte bank, because representing that case requires splitting the
entry table rather than silently producing unsafe data.

## Extract item and monster names

For DOS, pass `D:\Wizardry 7\DSAVANT\SCENARIO.DBS` to the same extractor.

```powershell
python tools\extract_gold_scenario_strings.py `
  --scenario original\SCENARIO.GLD `
  --output-dir extracted\scenario
```

The scenario translation CSV contains 600 item-name slots and four 16-byte name
variants for each of 250 monsters. Empty slots are retained so record indices and
binary offsets stay stable. Korean insertion will require a custom game encoding;
the 16-byte capacity refers to encoded bytes, not Unicode character count.

## Korean rendering prototype

The x86 WinMM proxy now renders an API-supplied KS X 1001 Hangul glyph in the
running GOG Gold game. It uses a two-byte game encoding and dynamically replaces
one reserved glyph in the active VBFONT before calling the game's original draw
routine.

Build the proxy from a Visual Studio developer environment:

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_winmm_proxy.ps1
```

Build the current smoke-test assets:

```powershell
node tools\make_vbfont0_8x8.mjs
node tools\make_hangul_smoke_patch.mjs
```

Generated files are written below `outputs/`. The smoke patch replaces `HUMAN`
and the main-menu `CREATE` label with `한`; it is test data, not a translation
release. See `docs/korean_rendering_plan.md` for the verified addresses, encoding,
current limitations, and next implementation steps.
