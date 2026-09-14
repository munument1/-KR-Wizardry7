# Wizardry VII DOS Korean v0.49 readable-text buffer fix

## Symptom

In New City, reading the translated **Book of Fables / The Witch's Tale** from the character inventory works for the first few lines and then DOS Wizardry VII terminates/crashes.

## Root cause

The item `READ` path is in `VPCVW.OVR`.  Its readable-text loop begins at file offset `0x3C7B` (runtime `0x8CC2`) and repeatedly decodes message IDs into a stack buffer.

The original routine allocates only `0x56` (86) bytes and passes `BP-0x56` to the resident message decoder:

```asm
; VPCVW.OVR + 0x3C7B
mov ax, 0xFFAA       ; -86 bytes
call 0x4452          ; common stack-frame prologue
...
lea ax, [bp-0x56]    ; decode destination
push ax
push [bp+4]          ; current message id
call 0x0582          ; resident message decoder
```

The resident decoder writes the decoded record plus a two-byte zero terminator.  Therefore the old frame safely holds at most 84 decoded bytes.

The English Book of Fables was split into short records that fit.  Korean uses the project's `ESC + rank + rank` three-byte glyph encoding, so several translated records are larger even though they contain fewer visible characters.

For v0.48:

- Book range: message IDs `21600..21655`
- first unsafe record: `21606`, 92 decoded bytes
- largest Book record: `21633`, 111 decoded bytes
- unsafe Book records with the old 84-byte payload capacity: `21606, 21609, 21611, 21623, 21633, 21640, 21645, 21651`
- largest decoded record in the entire current 11,019-message bank: 122 bytes

Thus the crash is a stack overwrite in the readable-item display routine, not a bad save, malformed Korean pair, or Huffman/bank-layout failure.

## v0.49 repair

The routine is expanded to the largest buffer that keeps the existing compact signed-disp8 addressing:

- stack frame: 86 -> 127 bytes
- decode buffer: `BP-0x56` -> `BP-0x7F`
- parser buffer reference: `BP-0x56` -> `BP-0x7F`

Only three immediate/displacement bytes in `VPCVW.OVR` change:

- `0x3C7C`: `AA -> 81`
- `0x3CA7`: `AA -> 81`
- `0x3CBB`: `AA -> 81`

The new buffer has 125 bytes available after reserving the decoder's two-byte terminator.  The largest current translated message is 122 bytes, so every current message fits with three bytes of margin.

No message text is shortened or reverted to English.  `MSG.HDR`, `MSG.DBS`, `MISC.HDR`, `SCENARIO.DBS`, fonts, NPC parser fixes, topic-key fixes, and save format remain unchanged.

## Regression requirements

A release build must prove:

1. the source v0.48 `VPCVW.OVR` SHA-256 is exactly `3e7930fad44ae846a24ab28f2905d1c9d7b3b5d8ebb5bbf815cbd5c49e505ea9`;
2. exactly three bytes change in `VPCVW.OVR`;
3. the output `VPCVW.OVR` SHA-256 is exactly `4878ef941364e0d91e37e857a2c07946b648729849e178e7e7be7ac02a9216ee`;
4. Book message 21606 exceeds the old capacity, proving the reproduced overflow condition;
5. Book message 21633 is 111 decoded bytes;
6. the entire v0.48 message bank has no record larger than the new 125-byte safe payload capacity;
7. all v0.48 game files other than `VPCVW.OVR` and the diagnostic `korean_codebook.json` annotation are byte-identical.
