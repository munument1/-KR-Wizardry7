# Wizardry VII DOS v0.49 gameplay choice centering root cause

Date: 2026-09-14

## Symptom

Korean choice labels in gameplay menus are shifted left out of their button frames. Reproductions include the locked-door menu (`자물쇠 따기`, `강제 개방`, `나가기`), chest/thief menus, and longer event choices.

## Root cause

Four late `VTREA.OVR` display helpers still call resident byte `strlen` (`CS:4AD7`) and convert that byte count to pixels with `* 6` before centering. Korean message glyphs are encoded as `0x17 + rank + rank`, so one visible Hangul glyph occupies three bytes. The centering code therefore substantially overestimates Korean label width and subtracts too much from the button center.

The existing rendered-width adapter at resident `CS:38F4` already parses Korean escape triples and returns real pixel width. Earlier UI passes correctly redirected many display-only sites to this adapter, but these four calls were missed.

## Why the previous audit missed them

`tools/audit_dos_ui_layout.py` originally computed a 16-bit near-call target without wrapping the result to 16 bits. Calls in the upper half of large overlays therefore appeared to target `0x14AD7` instead of resident `0x4AD7` and were omitted from the inventory.

The audit now applies `& 0xFFFF` to near-call target arithmetic.

## Patched VTREA sites

All offsets are `VTREA.OVR` file offsets.

- `0x8356`: variable-width button centering
- `0x84FB`: fixed-center half-width calculation
- `0x8603`: variable-width button centering
- `0x8C46`: fixed-center half-width calculation

For `0x8356` and `0x8603`, the original expression `(cell_width - strlen(text)) * 6 / 2` is changed in-place to `(cell_width * 6 - rendered_width(text)) / 2`.

For `0x84FB` and `0x8C46`, `strlen(text) * 6 / 2` is changed to `rendered_width(text) / 2`.

The nearby logical/grid-count `strlen` at `VTREA.OVR + 0x764D` is explicitly preserved. This is intentionally not a global `strlen` or six-pixel replacement.

## Guardrails

The test builder starts from the exact published v0.48 package and verifies source hashes. The resulting game payload changes only `VTREA.OVR`; file size is unchanged. Unit tests verify the four call redirects and that logical site `0x764D` still targets normal `strlen`.

Expected patched `VTREA.OVR` SHA-256:

`23cb96744b68998fddb1c8bf5b1fa61f9eca18f492f58318f324861b0217570a`

## Separate book crash

The New City library book crash is tracked separately. A static validation of the published v0.48 message layer decodes all 11,019 referenced records with zero record-start bank crossings and zero malformed Korean escape streams. Therefore the old v18 `MSG.DBS` bank-placement defect and a generic malformed Korean message stream are not supported as the immediate cause. The UI-only test package does not claim to fix the book crash.
