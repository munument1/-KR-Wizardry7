# Wizardry 7 Gold Korean translation workspace

The local GOG installation is never committed. Original translation-related
files are copied to the ignored `original/` directory before analysis or patch
experiments.

## Project status

- GOG Wizardry 7 Gold message and scenario string extraction is implemented.
- Translation-ready CSV and workbook generation is implemented locally.
- An x86 WinMM proxy renders two-byte KS X 1001 Hangul through the game's
  original VBFONT renderer.
- An 8x8 `한` smoke test has been verified in the running game.
- The game's basic string-width routine is hooked so a two-byte Hangul code is
  measured as one glyph.
- Next: message control-code/line-wrap validation and a CSV reinsertion tool.

This public repository intentionally excludes purchased game files, extracted
game text, locally generated patches, API credentials, and build outputs. Supply
your own GOG installation when running the tools.

## Extract the main message database

```powershell
python tools\extract_gold_messages.py `
  --hdr original\MSG.HDR `
  --gld original\MSG.GLD `
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

## Extract item and monster names

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
