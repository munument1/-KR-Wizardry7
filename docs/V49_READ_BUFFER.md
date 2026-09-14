# Wizardry VII DOS Korean v0.49 runtime hotfixes

v0.49 contains two independent, narrowly scoped runtime fixes on top of the exact published v0.48 package.

## 1. Readable-book crash

### Symptom

In New City, reading the translated **Book of Fables / The Witch's Tale** from the character inventory works for the first few lines and then DOS Wizardry VII terminates/crashes.

### Root cause

The item `READ` path is in `VPCVW.OVR`. Its readable-text loop begins at file offset `0x3C7B` (runtime `0x8CC2`) and repeatedly decodes message IDs into a stack buffer.

The original routine allocates only `0x56` (86) bytes and passes `BP-0x56` to the resident message decoder. The resident decoder writes the decoded record plus a two-byte zero terminator, so the old frame safely holds at most 84 decoded bytes.

The English Book of Fables was split into short records that fit. Korean uses the project's `ESC + rank + rank` three-byte glyph encoding, so several translated records are larger even though they contain fewer visible characters.

For v0.48:

- Book range: message IDs `21600..21655`
- first unsafe record: `21606`, 92 decoded bytes
- largest Book record: `21633`, 111 decoded bytes
- unsafe Book records with the old 84-byte payload capacity: `21606, 21609, 21611, 21623, 21633, 21640, 21645, 21651`
- largest decoded record in the entire current 11,019-message bank: 122 bytes

Thus the crash is a stack overwrite in the readable-item display routine, not a bad save, malformed Korean pair, or Huffman/bank-layout failure.

### Repair

The routine is expanded to the largest buffer that keeps the existing compact signed-disp8 addressing:

- stack frame: 86 -> 127 bytes
- decode buffer: `BP-0x56` -> `BP-0x7F`
- parser buffer reference: `BP-0x56` -> `BP-0x7F`

Only three immediate/displacement bytes in `VPCVW.OVR` change:

- `0x3C7C`: `AA -> 81`
- `0x3CA7`: `AA -> 81`
- `0x3CBB`: `AA -> 81`

The new buffer has 125 bytes available after reserving the decoder's two-byte terminator. The largest current translated message is 122 bytes, so every current message fits with three bytes of margin.

Expected patched `VPCVW.OVR` SHA-256:

`4878ef941364e0d91e37e857a2c07946b648729849e178e7e7be7ac02a9216ee`

## 2. Gameplay choice labels shifted left

### Symptom

Korean choice labels in gameplay menus are shifted left outside their button frames. Reproductions include the locked-door menu (`자물쇠 따기`, `강제 개방`, `나가기`), chest/thief menus, and longer event choices.

### Root cause

Four late `VTREA.OVR` display helpers still call resident byte `strlen` (`CS:4AD7`) and turn that byte count into pixels with `* 6` before centering.

A visible Korean glyph occupies three encoded bytes (`0x17 + rank + rank`), so these helpers grossly overestimate the rendered width and subtract too much from the button center. The resident rendered-width adapter at `CS:38F4` already understands Korean escape triples and returns the real pixel width.

The earlier audit missed these sites because upper-half 16-bit near-call targets were not wrapped to 16 bits. Calls could appear to target `0x14AD7` instead of resident `0x4AD7`.

### Repair

Only four display-coordinate sites in `VTREA.OVR` are changed:

- `0x8356`: variable-width button centering
- `0x84FB`: fixed-center half-width calculation
- `0x8603`: variable-width button centering
- `0x8C46`: fixed-center half-width calculation

The nearby logical/grid-count `strlen` at `VTREA.OVR + 0x764D` is explicitly preserved. This is not a global `strlen` or `6px -> 7px` replacement.

Expected patched `VTREA.OVR` SHA-256:

`23cb96744b68998fddb1c8bf5b1fa61f9eca18f492f58318f324861b0217570a`

## Preserved data

No message text is shortened or reverted to English. `MSG.HDR`, `MSG.DBS`, `MISC.HDR`, `SCENARIO.DBS`, fonts, NPC parser fixes, topic-key fixes, save format, and resident executable remain unchanged from v0.48.

Runtime changes are limited to:

- `VPCVW.OVR` — three bytes for the READ stack buffer
- `VTREA.OVR` — four reviewed display-width/centering expressions

`korean_codebook.json` and `UI_V49_REPORT.json` are diagnostic metadata only.

## Regression requirements

A release build must prove:

1. the source v0.48 package SHA-256 is `a0990467c94e1c19bd4ad7432b4895b026accd1056bb983e3110d621ae5e3ba8`;
2. exactly three bytes change in `VPCVW.OVR` and the output hash is the reviewed v0.49 hash above;
3. Book message 21606 exceeds the old capacity and message 21633 is 111 decoded bytes;
4. the entire current message bank fits inside the new 125-byte safe payload capacity;
5. the source `VTREA.OVR` is the exact published v0.48 file;
6. the four centering sites are redirected to rendered-width calculations while logical site `0x764D` stays on byte `strlen`;
7. the output `VTREA.OVR` hash matches the reviewed hash above;
8. compared with v0.48, no runtime game file other than `VPCVW.OVR` and `VTREA.OVR` changes.
