# Wizardry VII DOS Korean localization — Codex handoff

Date: 2026-08-30

## 0. Executive summary

The canonical target is **Wizardry VII: Crusaders of the Dark Savant DOS (the DOS build bundled by GOG)**. Wizardry Gold is only a translation/reference asset.

The message layer and v19 resident Hangul renderer are substantially understood and can produce a working Korean build. The remaining blocking work is **UI layout adaptation for 7x7 Hangul inside UI code written around a 6x6 Latin font**.

Do **not** continue from the latest experimental UI ZIPs. Several later layout experiments were intentionally aggressive and regressed flow, alignment, or overlay execution. The best current binary checkpoint is the local artifact **`Wizardry7_DOS_v19_CleanInstall_Baseline.zip`**, SHA-256:

`34c2fdf46052039cffc96b11929af3c1b0b6e3e95d28c82f5c70aac244810f2a`

It uses the full synchronized message/codebook/font set, includes the confirmed modal-buffer fix, keeps only the known-safe 7px stat row adjustment, and **does not modify skill row spacing**.

The next engineer should reproduce that baseline from source/local GOG files, then solve layout issues one screen/path at a time with static disassembly first and minimal user tests.

---

## 1. Repository checkpoint

Repository:

`https://github.com/munument1/-KR-Wizardry7`

Open PR:

- PR #2: `Fix DOS message banks and add v19 FontResident renderer`
- branch: `fix/gog-launcher-playsoundw`
- head before this handoff commit: `21f0318e2223a67b45a3b5e1ad3c4ee87b88c70a`

Important tracked files:

- `tools/build_dos_messages.py`
- `tools/repack_dos_message_banks.py`
- `tools/build_galmuri7_bitmap_table.py`
- `src/dos_v19/fontresident.S`
- `src/dos_v19/char_stub.S`
- `src/dos_v19/string_stub.S`
- `src/dos_v19/width_stub.S`
- `.github/workflows/build-dos-v19-resident.yml`
- `.github/workflows/build-galmuri7-table.yml`
- `docs/v18_message_crash_root_cause.md`
- `docs/dos_translation_plan.md`
- `docs/korean_rendering_plan.md`

Repository policy remains: **do not commit purchased game binaries or generated install/test ZIPs**.

---

## 2. Canonical local inputs

The user has a clean GOG DOS install/archive and the full translation sheet. Treat those as local build inputs, not repository assets.

Translation sheet:

`Wizardry 7 Gold 한국어 번역 데이터`

Google Sheet ID:

`1S1FQEDL73HhZy1sGEbWjVrBDnk5eBJWW6WkrRD5jGfo`

The full message build currently finds:

- 11,019 DOS message records
- 10,182 applicable translations
- source mismatches skipped: `2563, 2564, 25042, 25043`
- 1,110 custom glyphs
- 121-byte pair alphabet

---

## 3. DOS message format — confirmed

### `MSG.HDR`

Each non-sentinel entry is six bytes:

```text
u16 start_id
u16 bank_offset
u8  inclusive_id_span
u8  bank
```

### `MSG.DBS`

- 256 banks
- 0x400 bytes per bank
- total 262,144 bytes

Record:

```text
[u8 record_len][payload]
payload = [u8 decoded_len][Huffman bitstream]
```

### `MISC.HDR`

- signed little-endian int16 Huffman tree
- negative values point to internal nodes
- nonnegative values are leaves/literal bytes
- bit order is MSB-first

### Critical bank invariant

When DOS walks preceding subindices within one `MSG.HDR` entry, it does not load the next bank. Therefore **every record start in an entry must remain inside the bank named by that entry**. Only the final target payload may cross a bank boundary.

All builders/repackers must verify:

```text
record_start_crossings = 0
used_bank_count <= 256
```

This is the confirmed root cause of the old v18 black-screen/message corruption regression. See `docs/v18_message_crash_root_cause.md`.

---

## 4. v19 Hangul renderer — confirmed architecture

Encoding:

```text
ESC 0x17 + pair_byte_1 + pair_byte_2
```

One Korean/custom glyph therefore occupies three encoded bytes.

Current font:

- Latin source font: 6x6
- Korean glyphs: Galmuri7-derived 7x7 in an 8-pixel cell

Root stubs:

- character: `CS:3877`
- string: `CS:3895`
- width: `CS:38CA`

Resident routines:

- character: `0x0910`
- string: `0x0937`
- width: `0x0A30`

CI assembler constants:

```text
INV_TABLE_OFFSET   = 0x0D00
GLYPH_TABLE_OFFSET = 0x0E00
ALPHABET_LEN       = 121
CUSTOM_COUNT       = 1110
```

### Very important: `CS:38CA` is not `strlen()`

Conceptually it is:

```c
rendered_width(text, font_index)
```

It takes two arguments. A global replacement of `strlen` callers with this routine is unsafe.

Keep these three concepts distinct:

```text
encoded byte length
logical character count
rendered pixel width
```

---

## 5. Best known working local baseline

Artifact:

`Wizardry7_DOS_v19_CleanInstall_Baseline.zip`

SHA-256:

`34c2fdf46052039cffc96b11929af3c1b0b6e3e95d28c82f5c70aac244810f2a`

Included files:

- `DS.EXE`
- `VBFONT0.VGA`
- `MSG.HDR`
- `MSG.DBS`
- `MISC.HDR`
- `VPCMK.OVR`
- `VPCVW.OVR`
- `korean_codebook.json`

Baseline build report:

```json
{
  "records": 11019,
  "translations": 10182,
  "mismatches": [2563, 2564, 25042, 25043],
  "custom_chars": 1110,
  "pair_alphabet": 121,
  "misc_bytes": 484,
  "padding": 28527,
  "max_range_bytes": 941,
  "used_banks": 244
}
```

Font report:

```json
{
  "file_size": 11536,
  "second_stride_alloc": 80,
  "resident_size": 478,
  "glyph_bytes": 7770
}
```

Important baseline file hashes:

```text
DS.EXE        10200dbc8ca3bd3af3d486cfbc37961fc9c21ff6908d1f5d6474fac2424a184c
MISC.HDR      0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4
MSG.DBS       6e316eb669047b4a998694ed3c314879a7e2890c749619d43d0d03e18a8ae4dc
MSG.HDR       94622ce99f0e442df9823abcc522d72e3c0ef41d066934a4af090211c0a5525d
VBFONT0.VGA   e425f17118abbc2d7599c61f89324ea9162939a97383f35d17c11e90d7cd4750
VPCMK.OVR     702211c25215eb0e1e3d4a9a0373afa83c15b963ec1912f74a3c1055c878b04e
VPCVW.OVR     473f2d703e7a9f608f63e69a153fbdbd31ddfb86ff55d6743f2d59f51d457a83
codebook      0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9
```

Observed user result: creation/review screens run and Korean renders correctly. Overlap remains, especially stat/skill UI, but this is the safest checkpoint for further work.

---

## 6. Confirmed root fix: existing-character modal local-buffer overflow

A character-selection modal used this stack layout:

```text
BP-0x38                 2-byte handle
BP-0x36 .. BP-0x23      20-byte temporary text buffer
BP-0x22                 character/list count
```

A 20-byte encoded title plus NUL writes 21 bytes, clearing the adjacent character count. User boundary tests matched this exactly: shorter titles worked; a boundary-length title could display while the list became empty; longer titles corrupted the UI.

### Confirmed `VPCMK.OVR` fix

Frame expansion:

```text
file offset 0x0ABB
B8 C8 FF  ->  B8 A0 FF
```

Relocate six scratch-buffer references from `BP-0x36` to `BP-0x60`:

```text
0x0B22
0x0B2F
0x0B52
0x0B61
0x0B84
0x0B94

8D 46 CA  ->  8D 46 A0
```

This fixed the `확인` / portrait modal lockup. Preserve this change.

Do not confuse the remaining **visual clipping/alignment** of long Korean modal titles with the fixed memory-corruption bug.

---

## 7. Correction to the older handoff: creation stat labels are IDs 204..211

An older debug note incorrectly treated IDs `5050..5057` as the character-creation stat label set.

Actual `VPCMK.OVR` initialization loads eight 10-byte stat-label slots from IDs **204..211**:

```text
204 STR -> 근력
205 INT -> 지능
206 PIE -> 신앙
207 VIT -> 체력
208 DEX -> 민첩
209 SPD -> 속도
210 PER -> 지각
211 KAR -> 업보
```

The eight destinations are effectively:

```text
0x9544 + 10 * row
```

IDs `5050..5057` are the full stat names and belong to another path/screen. Do not use them as evidence for the creation stat panel.

---

## 8. Confirmed skill-string fixed-slot issue

In `VPCMK.OVR`, skill display names are copied into fixed 20-byte slots:

```text
0x0E38 + 20 * display_row
```

The skill message is `5500 + skill_index`.

Therefore the display string must fit **including the NUL terminator**.

The translation:

```text
5516 SKULDUGGERY -> 자물쇠 및 함정
```

was unsafe: the custom encoded payload reached the slot boundary and the terminator overflowed.

The current safe baseline temporarily uses:

```text
자물쇠/함정
```

Keep every 20-byte fixed-buffer path length-audited. Do not assume visual length equals encoded length.

Skill category strings `600..604` also use fixed 20-byte slots but the current Korean translations fit.

---

## 9. Known stat/skill geometry discovered so far

### Stat rows

Creation (`VPCMK.OVR`):

```text
0x19D7  row multiplier 6
0x19DD  base Y 35
```

Review (`VPCVW.OVR`):

```text
0x12B3  row multiplier 6
0x12B9  base Y 35
```

The clean baseline uses the previously tested 7px stat-row adjustment. It reduces overlap but does not fully solve the stat editor because **labels, values, arrows, bonus row, hitboxes, and repaint rectangles are separate calculations**.

User screenshots show that merely moving the stat labels or changing the row stride leaves `근력/지능` text, numeric values, and arrow glyphs colliding.

### Skill list

`VPCMK.OVR` list-draw code around `0x24C8` contains two original Y calculations:

```text
0x24FE  mov ax, 6
0x2504  add ax, 0x72    ; 114
0x2526  mov ax, 6
0x252C  add ax, 0x72
```

These draw skill label/value rows, but changing only these values is **not sufficient**. Skill UI has separate cursor/hitbox/clip/repaint calculations and fixed `SKILL POINTS` placement.

Important: offsets above are **instruction starts**, not automatically the byte to replace. Always disassemble and patch the immediate operand, not the opcode.

---

## 10. Important runtime-address lesson for overlays

Do not compute a near/far call target inside an OVR from file offsets alone.

A failed experiment demonstrated that `VPCMK.OVR` file offset zero maps to a nonzero runtime CS location (observed mapping used `CS:5047` for the loaded overlay). A patch intended to call the root width routine at `CS:38CA` instead jumped to an unrelated address because the overlay load base was omitted from the displacement calculation.

Any OVR control-flow patch must be validated in **runtime address space**, not just by file-offset arithmetic.

Also: do **not append code to an OVR** unless the overlay loader/file format is explicitly changed to load it. One failed v3 experiment appended 58 bytes to the end of `VPCMK.OVR`; the overlay still loaded the original extent, so calls into the appended area crashed immediately.

---

## 11. Experimental UI build history — what failed and why

These artifacts were local test ZIPs and are **not repository checkpoints**.

| Build | Result | Lesson |
| --- | --- | --- |
| `UI_LayoutFix_OVR_Revert_Test` | creation flow returned to working state; profession screen displayed | OVR rollback proved the creation regression was in layout OVR changes, not a generic renderer failure |
| `7x7_SkillLayout_Corrected` | still returned to main character menu | simply changing apparent skill row immediates is not safe/sufficient |
| `7x7_Korean_Spacing_Test` | main-menu regression; new Korean strings rendered as mixed/wrong glyphs | subset message rebuild changed codebook without matching `VBFONT0` tables; message/codebook/font must always be generated as one synchronized set |
| `CleanInstall_Baseline` | working Korean flow; remaining overlap reduced but visible | **current safest baseline** |
| `VPCMK_KoreanSpacing_v2` | superseded before becoming a reliable checkpoint | do not treat as baseline |
| `VPCMK_KoreanSpacing_v3` | character menu crashed | appended helper code past OVR loaded extent; invalid approach |
| `VPCMK_Layout_v4` | menu text corrupted, then game froze | incorrect runtime call displacement to `CS:38CA` |
| `VPCMK_Alignment_v5` | flow worked farther, but bonus row overlapped and selection arrows were off-row | text, arrow, hitbox, and bonus positions are separate |
| `Layout_v6` | main menu visibly unchanged; stat issues remained | patched the wrong/repaint path rather than the initial full-menu draw path |
| `Layout_v7` | still had stat horizontal overlap, bonus residue, skill-point clipping/spacing, long-modal clipping, skill name/value/arrow collisions | piecemeal coordinate edits still missed clip/repaint/fixed-label paths |
| `Layout_v8` | superseded; no stable full confirmation | common centering changes still required careful call-site validation |
| `Layout_v9_Systematic` | stat overlap remained; after `스킬 보너스를 받았습니다!` no skill allocation UI appeared | **global/systematic mass replacement broke control flow**; reject |
| `Layout_v10_ConservativeRecovery` | previously centered items reverted left; `근력/지능` overlap remained | rollback was too broad; reject |

Do not continue by stacking any of v3..v10 on top of another experimental build.

---

## 12. Current user-visible unresolved issues

Starting from the working baseline, the screenshots/tests established these real layout problems:

1. **Stat editor horizontal collision**
   - `근력`, `지능`, etc. collide with numeric values and/or left/right arrows.
   - Fix labels + value columns + arrows + hitboxes as one layout unit.

2. **Stat vertical spacing**
   - 7x7/8px Korean cells need more row spacing than original 6px UI.
   - Moving only labels causes bonus/cursor mismatch.

3. **Bonus row**
   - fixed-position `보너스` label/value can overlap the last stat row.
   - old value pixels may remain if repaint/clear rect does not cover the new location.

4. **Skill list rows**
   - Korean skill names, numbers, and arrows collide.
   - changing only label/value Y does not fix cursor, hitbox, clipping, or repaint regions.

5. **`스킬 포인트`**
   - separate fixed label/value row; earlier changes left its spacing unchanged or clipped its top.

6. **Modal titles**
   - e.g. `확인할 캐릭터` can be left-clipped even after the buffer-overflow fix.
   - this is a layout/clipping issue, not memory corruption.

7. **Main character menu / main UI centering**
   - several Korean labels remain left-shifted because paths still assume six-pixel Latin widths.
   - there are distinct initial-draw and redraw/selection paths; patching one does not guarantee the other.

8. **Skill-allocation flow safety**
   - a broad layout patch caused the flow to stop after `스킬 보너스를 받았습니다!`.
   - treat any change around skill allocation as control-flow sensitive.

---

## 13. Do not repeat these mistakes

### Never do a global `strlen -> rendered_width` rewrite

Earlier Test3 and v9-style broad patching caused major regressions.

`strlen()` may be used for:

- encoded byte indexing
- buffer bounds
- truncation/copy lengths
- UI centering
- gameplay/state logic

Only proven **pixel-layout** callers should be converted.

### Never do a global literal `6 -> 7/8` replacement

The constant 6 is not necessarily a font row height. It may be an index, margin, count, X coordinate, gameplay constant, etc.

### Do not patch multiple subsystems before a test

Keep these categories separate:

```text
renderer
message/codebook/font generation
modal memory safety
stat layout
skill layout
alignment
clipping/repaint
```

### Do not regenerate only a subset of translated messages with a new codebook

If the pair ranking/codebook changes, the resident inverse table and glyph table must be regenerated in the same build. Otherwise valid encoded bytes point at the wrong glyphs.

### Do not append executable bytes to an OVR

Preserve overlay file size unless the overlay format/loader is deliberately redesigned.

---

## 14. Recommended Codex plan

### Step 1 — reproduce the baseline byte-for-byte

Before changing UI, make source/local build tooling reproduce the `CleanInstall_Baseline` hashes above from:

- pristine GOG DOS files
- current translation sheet
- Galmuri7 7x7 table
- v19 resident renderer artifacts
- known modal-buffer patch

If byte-identical reproduction is impractical, at minimum verify the same build counts, codebook size, `record_start_crossings=0`, and successful full message scan.

### Step 2 — turn experimental binary edits into a deterministic patcher

Create a source-controlled patch tool with explicit guards such as:

```python
expect_bytes(file, offset, original_bytes)
patch_bytes(file, offset, replacement_bytes)
assert len(output) == len(input)  # for OVRs unless deliberately changed
```

Do not keep hand-editing anonymous ZIP binaries.

### Step 3 — solve stat editor as one component

Static-disassemble the full stat screen and identify all calculations for:

- stat label X/Y
- stat numeric value X/Y
- left arrow X/Y
- right arrow X/Y
- mouse/keyboard selection row
- hit rectangles
- bonus label/value
- repaint/erase rectangle

Only after all paths are mapped, define one layout model and patch every dependent calculation consistently.

Do not move `근력` alone.

### Step 4 — solve skill allocation as one component

Map, for each of `VPCMK`, `VPCVW`, and `VPCLV`:

- list top/bottom clip bounds
- label/value X and Y
- row stride
- selection arrow position
- mouse hitboxes
- redraw/clear region
- `SKILL POINTS` label and value Y
- calls/state transitions after the skill-bonus notification

First make **only VPCMK creation skill allocation** work. Do not change VPCVW/VPCLV until creation is verified.

### Step 5 — alignment audit by semantics, not byte patterns

Build a call-site list for every `strlen*6`-like site and classify it:

```text
PIXEL_CENTERING
PIXEL_RIGHT_ALIGN
BYTE_LENGTH
BUFFER_LENGTH
INDEXING
UNKNOWN
```

Convert only proven pixel-layout sites to `rendered_width(text, font_index)` or an equivalent local calculation.

For overlays, calculate call displacements with the actual runtime overlay load base and confirm in disassembly.

### Step 6 — modal title clipping

The memory-overflow problem is already solved. Separately map the title draw rectangle/available width for the character-selection modal. Prefer widening/repositioning the title layout over shortening Korean translations unless the original UI space truly cannot accommodate them.

---

## 15. Minimal user-test protocol

The user has already done many repetitive manual tests. Keep future tests high-signal.

For each new test package:

1. Start from the known clean baseline, not the previous experiment.
2. Change **one subsystem** only.
3. Provide exact overwrite files and a hash.
4. Ask for at most one short path/test unless a second result is genuinely required.

Suggested checkpoints:

```text
A. character menu opens
B. create -> name -> stat screen
C. stat arrows/bonus render and operate
D. profession selection
E. "skill bonus" -> skill allocation UI appears
F. skill arrows and skill points operate
G. review existing character
H. level-up screen
```

Do not ask the user to retest already proven boundaries unless the underlying code path changed.

---

## 16. Useful source/binary facts for immediate continuation

- Clean original `VPCMK.OVR` size: 29,885 bytes (`0x74BD`). Preserve unless loader changes.
- Confirmed modal fix offsets: `0x0ABB`, `0x0B22`, `0x0B2F`, `0x0B52`, `0x0B61`, `0x0B84`, `0x0B94`.
- Creation stat-label IDs: `204..211`.
- Skill category IDs: `600..604`.
- Skill IDs: `5500..5534`.
- `SKILL POINTS`: `5534`.
- Skill display slot: 20 bytes per row at `0x0E38 + 20*display_row` in `VPCMK`.
- v19 width routine: root `CS:38CA`; two arguments, not a drop-in `strlen` replacement.
- Current Korean custom sequence: `0x17 + pair1 + pair2`.
- Original Huffman leaf alphabet does not contain NUL; pair bytes therefore do not introduce an embedded C-string NUL.

---

## 17. What is confirmed vs. still uncertain

### Confirmed

- DOS/GOG build is canonical target.
- v19 renderer architecture works.
- full synchronized message/codebook/font generation works.
- bank-safe message packing is mandatory.
- modal 20-byte scratch-buffer overflow root cause and fix.
- creation stat labels are 204..211.
- skill list uses fixed 20-byte name slots.
- broad/global layout patching is unsafe.
- remaining visible problems are mainly UI geometry, clipping/repaint, and control-flow-sensitive skill allocation paths.

### Not yet confirmed

- complete list of all six-pixel row/centering sites that are semantically safe to alter.
- final stat editor X/Y coordinates.
- final skill list top/stride/`SKILL POINTS` geometry.
- exact common modal title clip/centering path for every modal variant.
- safe global strategy for main-menu/overlay centering without touching byte-length semantics.

---

## 18. Handoff instruction to Codex

Use the repository and this report as the authoritative starting point. Treat the later local v3-v10 UI ZIPs as failed experiments, not work to preserve. Reproduce the clean v19 baseline first, add deterministic guarded patch tooling, then fix the stat editor and creation skill allocation path with static disassembly and runtime-aware addresses. Avoid mass pattern replacement. Preserve the user-tested modal-buffer fix and the synchronized full translation/codebook/font pipeline. Keep manual tests minimal and isolate one subsystem per build.
