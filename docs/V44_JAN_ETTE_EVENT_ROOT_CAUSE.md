# Wizardry VII DOS Korean v0.44 — Jan-Ette event root cause

Date: 2026-09-01

## Symptom

In the Korean build, walking toward the early beginner-dungeon area could show the H'Jenn-Ra/T'Rang encounter and MON42 instead of the expected Jan-Ette Helazoid encounter. Earlier builds also showed broken Korean text after the wrong scene; v0.43 fixed the text corruption, but the wrong NPC/event selection remained.

## Runtime isolation

A/B runtime testing narrowed the failure to `VBASE.OVR`:

- v0.43 Korean core (`DS.EXE`, `MSG.DBS/HDR`, `MISC.HDR`, `VBFONT0.VGA`) with stock overlays: Jan-Ette normal.
- Same core plus v0.43 `VMNPC.OVR`: Jan-Ette normal.
- Same core plus v0.43 `VBASE.OVR`: H'Jenn-Ra reproduced.
- v0.43 `VBASE.OVR` with only file offset `0x667B` restored to the original call: Jan-Ette normal.
- Full v0.43 package with only that three-byte restoration: Jan-Ette normal.

This excludes message encoding, VMAZE, scenario data, and VMNPC as the direct cause of the wrong encounter.

## Faulty patch

v0.35 introduced an Enter-only copy-protection shortcut in `VBASE.OVR` at file offset `0x667B`:

```text
original GOG: E8 4C 73    ; call resident routine at CS:2A11
v0.35-v0.43: B8 01 00    ; mov ax,1
```

The change was intended to force successful verification. The assumption was that the called routine only returned success/failure.

That assumption was incorrect.

## Resident routine side effect

The original call targets resident `DS.EXE` code at `CS:2A11`. The relevant tail is:

```asm
2A4B  mov ax,[59F6]
2A4E  dec ax
2A4F  cmp ax,bx
2A51  jne 2A59
2A53  mov ax,[59F8]
2A56  mov [1008],ax
2A59  inc word ptr [bp-2]
...
2A65  mov ax,1
2A68  ret
```

The routine therefore does not merely produce `AX=1`. During successful processing it also performs the required state update:

```text
DS:1008 <- DS:59F8
```

Replacing the entire call with `mov ax,1` skipped that state initialization. The game then entered the early field with incorrect state and selected the H'Jenn-Ra/T'Rang encounter in place of Jan-Ette.

## v0.44 fix

v0.44 restores the original three-byte call at `VBASE.OVR + 0x667B`:

```text
B8 01 00 -> E8 4C 73
```

Every other v0.43 payload byte is preserved.

The original GOG routine already reaches a successful return while preserving the required state side effect, so the separate `mov ax,1` replacement is both unnecessary and harmful.

## Regression rule

Do not bypass this path by replacing the call itself with a constant success return. Any future copy-protection/UI change must preserve the original routine's state side effects, especially the update to `DS:1008`.
