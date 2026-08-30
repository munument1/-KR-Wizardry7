# Wizardry VII DOS Korean v39 — overlay-safe resident architecture

Date: 2026-08-30

## Executive summary

The v37 runtime still placed persistent helper code in the root-CS overlay load
window. This is structurally unsafe even when the corresponding DS.EXE bytes are
zero on disk.

Every OVR is loaded at runtime origin `0x5047`. The pristine GOG DOS archive has
these important maximum extents:

- `VBASE.OVR`: `0x5047..0xE562`
- `VMAZE.OVR`: `0x5047..0xFDAF`
- `VMNPC.OVR`: `0x5047..0xFFC0`

Therefore the following historical helper addresses are not resident:

- v20 width adapter `0xF790`
- v21 stat repaint helper `0xF7B0`
- v37 scene find helper `0xFDB0`
- v37 trailing-ASCII helper `0xFDF0`

`VMAZE` overwrites the first two. `VMNPC` reaches beyond both v37 scene helper
addresses.

## Why this explains the save failure

The game can load a save into `VMAZE`, which overwrites root-CS `0xF790`. When
the pause/save path later loads `VBASE`, that overlay ends at `0xE562`, so it
does not restore the original DS bytes at `0xF790`. The v20-patched VBASE file
selector still contains rendered-width calls to `0xF790`; those calls therefore
jump into stale VMAZE code instead of the width adapter.

The actual VBASE save routine body remains unchanged from the original. The
observed `VGA.DRV` fatal `Memory unavailable loading picture.` is consistent
with execution/stack corruption before the save file is written.

## v39 layout

v39 removes every persistent executable helper from `0x5047+`.

### Root CS

The v19 root width trampoline occupies `0x38CA..0x38F3`. Its original routine
has an unreachable tail before the next root function at `0x3921`. v39 uses
that fixed resident area:

- `0x38F4`: one-argument rendered-width entry
- `0x38F8`: one-argument trailing-ASCII entry
- `0x38FB`: shared adapter body
- `0x390C`: compact stat repaint helper
- helper block size: 44 bytes
- helper block end: `0x3920`

All of these addresses are below overlay origin `0x5047`.

### Resident font segment

The verified v19 FontResident layout is:

- character `0x0910`
- string `0x0937`
- width `0x0A30`
- current resident code end `0x0AEE`
- inverse table `0x0D00`
- glyph table `0x0E00`

v39 adds a 124-byte dispatcher at `0x0AF0..0x0B6B`, still well before the
inverse table.

The `resident_width` entry at `0x0A30` is changed only from its three-byte
`push bp; mov bp,sp` prologue to a near jump to `0x0AF0`. The dispatcher creates
the same frame and then selects an operation from the existing second argument:

- `0`, `2`, `3`, etc.: continue into the original rendered-width body at `0x0A33`
- `0x20`: Korean-aware search for standalone space
- `0x5F`: Korean-aware search for standalone underscore
- `0x0100`: return the final standalone ASCII/literal byte, or zero when the
  final logical unit is Korean

The two scene-find arguments already have the same stack shape as
`rendered_width(text, font_index)`, so no overlay code expansion is required.
The one-argument trailing-marker sites call the new root adapter at `0x38F8`,
which supplies operation `0x0100` before entering `0x38CA`.

## Files

Implementation:

- `src/dos_v39/font_dispatch.S`
- `src/dos_v39/root_helpers.S`
- `tools/build_dos_v39_overlay_safe_resident.py`
- `tests/test_build_dos_v39_overlay_safe_resident.py`
- `tools/audit_dos_overlay_resident_collisions.py`

The Python builder embeds byte-for-byte assembled forms of the two assembly
sources so the Windows build does not require GNU binutils.

## Build

Use the exact verified v37 `DSAVANT` payload as input:

```powershell
cd "D:\Codex_Trans\Wizardry 7"

git pull

python tools\build_dos_v39_overlay_safe_resident.py `
  --v37-dir "D:\Wizardry 7\DSAVANT" `
  --output-dir "outputs\v39_overlay_safe_resident" `
  --zip-output "outputs\Wizardry7_Korean_v39_overlay_safe_resident.zip"
```

Optional structural audit against the pristine purchased archive:

```powershell
python tools\audit_dos_overlay_resident_collisions.py `
  --original-zip "D:\Wizardry 7.zip"
```

## Runtime QA

Minimum user QA after installing the v39 `DSAVANT` files:

1. Load the preserved valid save.
2. Enter gameplay.
3. Open the `D` menu.
4. Select `저장 & 계속`.
5. Confirm that the game remains running and `SAVEGAME.DBS` is updated.
6. Start a new game far enough to see the opening/Aletheides/landing text.

This single pass exercises both the previously failing save UI width path and
the relocated scene parser.

## Do not regress

Do not place persistent helpers anywhere in the root-CS interval beginning at
`0x5047` unless the overlay loader itself is redesigned. A zero-filled region
in the on-disk DS.EXE image is not a resident cave when an OVR can occupy the
same runtime addresses.
