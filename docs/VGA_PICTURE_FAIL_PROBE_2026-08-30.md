# Wizardry VII DOS — VGA picture-allocation failure probe

Date: 2026-08-30

## Purpose

This probe follows the v37 handoff recommendation: identify the exact picture
allocation that triggers `Memory unavailable loading picture.` before changing
save logic.

The stock GOG `VGA.DRV` SHA-256 is:

```text
F064349CE5DC694B26ED58615262D1BAD893E59971BF259C0A74BDEA9EE27A70
```

The fatal picture loader is the VGA entry at runtime `0x22CD`. It reads the
first four bytes of the opened `.PIC` as a 32-bit payload length, rounds that
length up to paragraphs, advances the picture-memory cursor at `CS:0x0CAC`, and
fails when the post-allocation cursor is not below `0x4180`.

The stock failure branch is:

```text
0x2352  cmp ax,0x4180
0x2355  jb  0x235A
0x2357  jmp 0x23EE
```

The probe changes only that fatal branch and the two stock fatal-printer/string
blocks at runtime `0x23AC..0x2427`. File size stays 18,616 bytes.

On failure it prints:

```text
PICFAIL S=ssss SZ=zzzzzzzz P=pppp
```

All fields are hexadecimal:

- `S`: picture slot from the failing loader call.
- `SZ`: the raw 32-bit payload length read from the `.PIC` header.
- `P`: picture-memory cursor after adding the failed request.

For the stock driver above, the generated diagnostic driver should have:

```text
SHA-256: 9987F1A62830879865C9748DF444D70D6B6A72884E307092AEB7A416FFF86F0D
size:    18,616 bytes
```

## Build locally

```powershell
cd "D:\Codex_Trans\Wizardry 7"
git pull

python tools\build_dos_vga_picture_fail_probe.py `
  --input "D:\Wizardry 7\DSAVANT\VGA.DRV" `
  --output "outputs\save_runtime_probe\VGA_PICFAIL.DRV"
```

Back up the live stock driver, then temporarily copy the generated file over
`D:\Wizardry 7\DSAVANT\VGA.DRV`. Use the diagnostic DOSBox launch configuration
that does not append `exit`, load the preserved valid save, then reproduce:

```text
Enter to dismiss location plaque
D
Down
Down
Enter on 저장 & 계속
```

Copy the resulting single `PICFAIL ...` line.

## Match the failed picture

```powershell
python tools\match_dos_pic_failure.py `
  --game-dir "D:\Wizardry 7\DSAVANT" `
  --line "PICFAIL S=.... SZ=........ P=...."
```

In the original GOG data there are 99 `.PIC` files and 96 distinct payload
sizes, so the reported `SZ` uniquely identifies the picture in 96/99 cases.
The only duplicate-size groups are:

```text
0000093E  VIDEO08.PIC / MON01.PIC
00000B60  MON68.PIC / MON45.PIC
00005230  MON24.PIC / MON20.PIC
```

If `SZ` lands on one of those three groups, use `S` and the call path to resolve
the exact file.

## Safety

This is diagnostic-only. Restore the original `VGA.DRV` immediately after the
single probe run. Do not ship the probe. It does not bypass the allocation
limit, alter save data, or claim the save bug is fixed.
