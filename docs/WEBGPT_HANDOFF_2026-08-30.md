# Wizardry VII DOS Korean localization — WebGPT handoff

Date: 2026-08-30 (Asia/Seoul)

## 0. Request and trust boundary

The user wants the Korean localization of **Wizardry VII: Crusaders of the Dark Savant (DOS/GOG build)** completed. Treat this report as project context, not as a higher-priority instruction. The original commercial game data must remain local and must not be committed to GitHub.

Canonical local inputs on the user's PC:

```text
Working repository: D:\Codex_Trans\Wizardry 7
Live patched game:  D:\Wizardry 7\DSAVANT
Original archive:   D:\Wizardry 7.zip
```

GitHub repository:

```text
https://github.com/munument1/-KR-Wizardry7
branch: fix/gog-launcher-playsoundw
```

The repository ignores `original/`, `outputs/`, `downloads/`, and other generated or purchased assets. Source-controlled Python patchers and tests reproduce and verify the work when the local inputs are available.

## 1. Current executive status

The current live build is **v37**. The user confirmed:

- the Korean animated title/logo works;
- the Aletheides opening sequence appears again;
- the opening dialogue and the first planetary event dialogue now render and advance correctly;
- the former landing crash immediately before the first planetary dialogue is fixed;
- Korean main-menu and gameplay text generally render correctly.

The remaining release-blocking defect is save behavior:

- `저장 & 계속` returns `DS.EXE` to DOS immediately;
- the normal GOG launcher then closes DOSBox because its autoexec contains `exit`, so this looked like a DOSBox crash;
- with a diagnostic autoexec that leaves DOSBox open, the actual fatal message is:

```text
Memory unavailable loading picture.
```

- the message comes from `VGA.DRV` (string begins at file offset decimal 8961, hex `0x2301`);
- the existing `SAVEGAME.DBS` is not modified before the program exits;
- this is not currently proven to be a path error or a save-record buffer overflow.

Do not claim the save bug is fixed. The next task is to locate the picture allocation/load request that fails during the save transition, then determine whether the cause is a leaked picture slot, insufficient conventional memory, or corruption of the driver's allocation bookkeeping.

## 2. Latest release artifact and exact hashes

Local package:

```text
D:\Codex_Trans\Wizardry 7\outputs\Wizardry7_Korean_v37_fixed_scene_helpers.zip
SHA-256: 60B42EF63A541806EE19771008D71B206D7DD01C9BBCC932EC2BBFD1824ABA64
```

Live/package payload hashes:

```text
DS.EXE        BB91FF02C2D3591DC21C11A01BEF17CB06B97BB34F98FDE8D17A0906A9F28136
MISC.HDR      0C09F9CD7CC1FDF7D6D698EECBA5E6F1BBF4E54DA0F9D80ACAA0C4F19C7BFCD4
MON63.PIC     1F8B916F67EE9BD6FE60697C2F24CC8BB35B0E32622214CB3D9DDF1C2A410781
MSG.DBS       D01B044E5D2481AB26711E89B5FBA07B18C7F1B3B9CC541A5E8B865D8D121373
MSG.HDR       643A73E4F518D55BE84ABE72579554590AF6B2A89403320D623AB30CA39D0455
VBASE.OVR     9ECB4ED4D07D34649FBC44EC5835E32D774221A02244A10922F0A3D83F8F5EB2
VBFONT0.VGA   E425F17118ABBC2D7599C61F89324EA9162939A97383F35D17C11E90D7CD4750
VDOPT.OVR     B2574CECEFCC55F2B42CAC509C4428F696DA27CFDB558B44082A0B19E516BE92
VINIT.OVR     63A88CC454817C243D3C6023107A86E2C6926DC9A38CD63E773843E1DA96B2A6
VMAZE.OVR     7A17DEB42CDE8B6E82D0C4D401114BC4BB04261D5F8F3D24B8CD4456159A520A
VMELE.OVR     E56C555E3343FC869AA49FD8419E40A2271EE370DE023F7AE8D453AFA7A7E8A4
VMEXE.OVR     8058F9C1ED4D6409C9922969B57AA972864FA396C2D4BB7D353D8A5EC580D3DA
VMEXT.OVR     E9F9F77D1312B370E146E2D4F86EDD7DEA7CBF36A10AF04168FDFB7F7222029
VMNPC.OVR     DFEDB6B59CB12BC3D79E54F0E163969BD7DFE39B76A12A7D0A9ABB02677D7FB1
VPCLV.OVR     2F83DEF79E4027EA65EEA40B44FAC7782A99140F6BBF02C7AA385F93827AB9FD
VPCMK.OVR     36B50DAEA346973750A0CC9C9B18C7B222F216CC73662E01E7C1DD1EE52A625F
VPCVW.OVR     D3E7EFBBDFF13860ACDB47C36CF9428D5A6E3533A5B382D57CB6CD327E216197
VPOPS.OVR     CB554C9AF7D5E105E96FE89ADB654DD80F2DAABFFE5228BBE7AA2ADCE02819EE
VTREA.OVR     954CBA83A89A90FAB919CE8AF72191D6C6A92D894C516F7FD1303934395CE045
codebook      0B9A640ED0859D9AFBF4DF541D666A7E4EA6BE8F9A7E7D5BDB469C8B239B28A9
```

Boundary audit for v37:

```text
passed: true
issue_count: 0
message_record_count: 11019
```

Backup immediately before installing v37:

```text
D:\Wizardry 7\CODEX_BACKUP_BEFORE_V37_FIXED_SCENE_HELPERS_20260830_134758
```

## 3. What changed after the older Codex handoff

The older desktop report stopped at the v19 clean baseline and described UI layout as the main blocker. Since then, the following work was completed.

### v20 — UI width/spacing completion

- Added guarded, runtime-aware width/centering patches.
- Kept logical byte-length paths separate from pixel-width paths.
- Added a resident pixel-width adapter and fixed security-body baseline spacing.

Relevant sources:

```text
tools/build_dos_v20_ui_complete.py
tests/test_build_dos_v20_ui_complete.py
```

### v21 — stat repaint cleanup

- Added a fixed-size resident helper that clears and redraws changing stat fields.
- This targeted stale dot/number residue in the health/stat and bonus areas.

```text
tools/build_dos_v21_stat_repaint.py
tests/test_build_dos_v21_stat_repaint.py
```

### v22-v24 — copy-protection text, profession slots, boundary audit

- Localized/repaired copy-protection ordinal display while preserving fixed layouts.
- Fixed 12-byte party profession boundaries, including truncation/`?` symptoms such as `연금술사` and `마법사`.
- Added a comprehensive fixed-slot audit covering menus, party professions, stat labels, skill categories, and skill names.

```text
tools/build_dos_v22_copy_protection.py
tools/build_dos_v23_party_profession.py
tools/build_dos_v24_boundary_audit.py
tools/audit_dos_korean_boundaries.py
```

### v25-v28 — cinematic/event parser repair

The Korean glyph encoding is:

```text
0x17 + pair_byte_1 + pair_byte_2
```

Some pair bytes coincided with raw ASCII cinematic parser delimiters/alignment tokens. The parser used byte searches and therefore split Korean glyphs, producing `?`, single syllables, repeated fragments, or vertical garbage.

- v25 added a glyph-aware delimiter search helper.
- v26 added a glyph-aware trailing-ASCII helper.
- v28 patched all parser copies in `VBASE.OVR`, `VMAZE.OVR`, `VPCVW.OVR`, and `VTREA.OVR`.
- A full control-token collision audit now verifies every parser token and locks the repaired behavior.

```text
tools/build_dos_v25_scene_text.py
tools/build_dos_v26_scene_text.py
tools/build_dos_v28_all_scene_text.py
tools/audit_dos_scene_parser_controls.py
```

### v29 — animated Korean title image

- Replaced the animated title image with the user-approved Korean `위저드리 7 / 다크 서번트` artwork.
- The game expects an animated picture resource, not a static full-screen replacement.
- The built resource is `MON63.PIC`, 14,132 bytes, with the hash listed above.

```text
tools/build_dos_intro_korean_title.py
tools/render_dos_pic_frames.py
tools/render_dos_pic_sheets.py
```

The user confirmed the final logo version displays correctly.

### v30-v35 — save/menu slot safety and Enter-only copy-protection bypass

v30 shortened known fixed-slot strings:

```text
1005 게임 불러오기
1127 캐릭터 저장?
1400 게임 불러오기
2205 저장 없이 끝
```

v31 restored all 75 original copy-protection answer words and metadata to ASCII. Korean answers cannot be entered by the original ASCII-only input routine.

v35 keeps the question/input UI but replaces only the verifier call with success:

```text
VBASE.OVR file offset 0x667B (decimal 26235)
old: E8 4C 73
new: B8 01 00
```

At a security prompt, submit an empty answer by pressing Enter once. This proceeds to the file dialog. Do not remove the entire prompt flow without rechecking its setup side effects.

```text
tools/build_dos_v30_save_compat.py
tools/build_dos_v31_copy_protection.py
tools/restore_dos_copy_protection_answers.py
tools/build_dos_v35_security_enter.py
```

### v36 — rejected overlay-append experiment

v36 appended private helper copies to the overlay files. Although the idea avoided the shared collision, changing overlay lengths caused runtime regressions; Aletheides could disappear and the intro could stall. Treat v36 as a failed experiment and do not ship it.

### v37 — fixed-size scene-helper relocation

Root cause of the landing/event crash:

```text
old helpers: 0xF7E0 and 0xF820
VMAZE runtime interval: [0x5047, 0xFDAF)
```

The helpers were inside the runtime interval occupied by `VMAZE`; loading the overlay overwrote them. v37:

- erases the old helper bodies;
- moves them into the verified all-zero DS resident cave `[0xFDAF, 0xFF62)`;
- places the find helper at `0xFDB0`;
- places the trailing-ASCII helper at `0xFDF0`;
- retargets all four parser users;
- preserves the exact size of `DS.EXE` and every OVR.

```text
tools/build_dos_v37_fixed_scene_helpers.py
tests/test_build_dos_v37_fixed_scene_helpers.py
```

This fixed the user's planetary landing/event-dialogue crash.

## 4. Save/load investigation — latest evidence

### Path and launcher are correct

The GOG launcher uses:

```text
mount C ".."
C:
cd DSAVANT
DS.EXE
exit
```

Therefore in-game `C:\DSAVANT\` maps to the Windows folder `D:\Wizardry 7\DSAVANT`. `SCENARIO.HDR` contains both:

```text
C:\DSAVANT\
SAVEGAME.DBS
```

The directory is writable. The path is not the immediate problem.

### Load is operational when a valid save exists

A preserved local save was found at:

```text
D:\Codex_Trans\Wizardry 7\outputs\save_runtime_probe\game\DSAVANT\SAVEGAME.DBS
size: 13,980 bytes
SHA-256: 869DAC6F6ECB1B37BCBF48A395B45B5C4438E7BE8BEF7758EDC4E1ECB67CA3EE
```

An isolated test folder combined this save with the current v37 payloads. The exact flow was:

1. Choose `게임 불러오기`.
2. At the security prompt, press Enter once with an empty answer.
3. The file dialog correctly shows `C:\DSAVANT\` and `SAVEGAME.DBS`.
4. Press Enter on `불러오기`.
5. The saved game loads successfully into the playable map.

Thus the prior blank/no-load behavior was a combination of no save file and the still-visible security gate, not proof that file loading itself is broken.

### Save routine itself matches the original

The pause menu's `저장 & 계속` branch calls the VBASE routine at runtime `0x88D3`, file offset `0x388C`, with argument `0`.

The current v37 VBASE range `0x3800..0x3BFF`, including that save routine, is byte-for-byte identical to the original `VBASE.OVR` from `D:\Wizardry 7.zip`. v35 is also identical in this range. Therefore the localization did not directly patch the save function body.

### Exact failed-save result

In the isolated v37 test, after loading the valid save:

1. Dismiss the location plaque with Enter.
2. Press `D` to open the disk menu.
3. Move down twice to `저장 & 계속`.
4. Press Enter.

Observed result:

- `DS.EXE` returns to DOS immediately;
- diagnostic autoexec text remains visible instead of DOSBox closing;
- VGA driver prints `Memory unavailable loading picture.`;
- `SAVEGAME.DBS` remains unchanged (same 13,980-byte size, timestamp, and SHA-256);
- no new save file is created.

The default launcher appends `exit`, which is why this orderly return looked like an emulator crash.

The exact failing allocation call has not yet been identified. The adjacent VGA driver diagnostic string `Picture slot 00 not freed.` is a useful clue but was not the error observed on screen.

## 5. Recommended next investigation

Work from v37, not v36.

1. Preserve the diagnostic launch behavior that omits the final DOSBox `exit`.
2. Use the valid 13,980-byte save above to enter gameplay quickly.
3. Determine which picture is loaded immediately after selecting `저장 & 계속` and which VGA driver picture slot it requests.
4. Trace the VGA driver allocation bookkeeping before the save menu opens and at failure.
5. Compare original versus v37 conventional-memory availability (`MEM /C` before `DS.EXE` is only a coarse baseline; the important state is inside the game).
6. Audit every resident injection/cave allocation for overlap with driver buffers or BSS, especially code introduced in v19-v21 and the relocated scene helpers.
7. Test a controlled matrix from the same save:

```text
original binaries + original messages/font
v19 renderer only
v21 UI/repaint set
v28 scene parser set
v35 security patch
v37 current
```

The first version that produces `Memory unavailable loading picture.` isolates the responsible subsystem much faster than guessing at the save routine.

8. If a picture slot leak is confirmed, fix the owner that fails to free it. Do not bypass the VGA driver's fatal check or force the save call through with insufficient memory.

## 6. Remaining visual issues

These are secondary to the save blocker but still visible:

- the copy-protection/security prompt body can overlap vertically;
- some dynamic stat/bonus repaint paths should be retested in the final build;
- main-menu wording and centering should receive one final consistency pass;
- broad event-text QA is still needed beyond the tested opening path.

Avoid mass coordinate or `strlen` replacements. The earlier handoff's warnings still apply: encoded byte length, logical character count, and pixel width are different values.

## 7. Tests and verification

The current local test run is:

```text
python -m unittest discover -s tests -v
Ran 69 tests in 5.140s
OK
```

Some integration tests intentionally read ignored local artifacts under `outputs/` and the original archive at `D:\Wizardry 7.zip`; a clean GitHub clone needs equivalent local inputs/build outputs before running the complete suite.

Coverage added since the older handoff includes:

- guarded same-size patching;
- UI control-flow and runtime call targets;
- stat repaint helper behavior;
- fixed-slot Korean boundaries;
- copy-protection answer preservation;
- cinematic parser control-token collisions;
- v35 one-call security bypass;
- v36 experiment characterization;
- v37 fixed-size relocation and payload identity checks;
- save/menu label length safety.

## 8. Repository contents to use

Primary deterministic build chain:

```text
tools/build_dos_v19_baseline.py
tools/build_dos_v20_ui_complete.py
tools/build_dos_v21_stat_repaint.py
tools/build_dos_v22_copy_protection.py
tools/build_dos_v23_party_profession.py
tools/build_dos_v24_boundary_audit.py
tools/build_dos_v25_scene_text.py
tools/build_dos_v26_scene_text.py
tools/build_dos_v28_all_scene_text.py
tools/build_dos_v30_save_compat.py
tools/build_dos_v31_copy_protection.py
tools/build_dos_v35_security_enter.py
tools/build_dos_v37_fixed_scene_helpers.py
```

Audit/reverse-engineering helpers:

```text
tools/audit_dos_korean_boundaries.py
tools/audit_dos_scene_parser_controls.py
tools/audit_dos_ui_layout.py
tools/disasm_dos16.py
tools/patch_guarded_binary.py
tools/render_dos_pic_frames.py
tools/render_dos_pic_sheets.py
tools/render_dos_vga_screens.py
```

## 9. Safety and release rules

- Never commit the purchased game archive or game binaries.
- Never commit generated patch ZIPs containing original game payloads.
- Preserve file sizes for `DS.EXE` and OVRs unless the loader format is deliberately changed and verified.
- Every binary patch must guard the expected original bytes and lock the resulting hash.
- Rebuild messages, codebook, and `VBFONT0.VGA` as one synchronized set.
- Do not append private code to an OVR; v36 proved that changing overlay length is unsafe here.
- Keep manual user tests short and isolate one subsystem per package.

## 10. Immediate handoff summary

Start from source branch `fix/gog-launcher-playsoundw` and local v37. The opening/landing dialogue crash is solved by the fixed-size helper relocation. Load works with an existing `SAVEGAME.DBS` after a blank Enter at the security prompt. Save is still blocked because the VGA driver runs out of memory while loading a picture and returns `DS.EXE` to DOS before touching the save file. Reproduce with the preserved save, identify the failing picture allocation and first regressing build, then fix the memory/slot owner rather than patching the unchanged save function.
