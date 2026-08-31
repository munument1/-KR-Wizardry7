.code16
.intel_syntax noprefix
.section .text

# The Add Character roster draws the first three bytes of race/profession
# strings through the single-character renderer.  Korean glyphs are encoded as
# ESC + two ranked bytes, so the stock byte-at-a-time path renders those three
# bytes as unrelated symbols.  This resident helper turns that exact three-call
# sequence back into one Korean glyph while leaving ordinary single-byte draws
# unchanged.

.equ ESCAPE_BYTE, 0x17
.equ ORIGINAL_CHAR_CONTINUE, 0x0913
.equ INV_TABLE_OFFSET, 0x0D00
.equ GLYPH_TABLE_OFFSET, 0x0E00
.equ ALPHABET_LEN, 121
.equ CUSTOM_COUNT, 1110
.equ SLOT_CHAR, 0x007F
.equ SLOT_WIDTH_ADDR, 0x010F
.equ SLOT_FIRST_ADDR, 0x0508
.equ SLOT_FIRST_LAST, 0x050F
.equ SLOT_SECOND_LAST, 0x090F

.global roster_char_stream
.global roster_char_stream_end

roster_char_stream:
    push bp
    mov bp, sp
    push bx
    push cx
    push dx
    push si
    push di

    xor ax, ax
    mov al, byte ptr [bp+6]
    mov dl, byte ptr cs:[stream_state]
    cmp dl, 0
    je .idle
    cmp dl, 1
    je .first_ranked_byte

    # State 2: AL is the second ranked byte.  Reconstruct the same dense glyph
    # index used by resident_string, install the 7x7 glyph in slot 127, and let
    # the original character wrapper draw that slot exactly once.
    mov dl, al
    xor bx, bx
    mov bl, byte ptr cs:[first_byte]
    mov al, byte ptr cs:[INV_TABLE_OFFSET + bx]
    cmp al, 0xFF
    je .invalid_pair
    mov cl, al

    xor bx, bx
    mov bl, dl
    mov al, byte ptr cs:[INV_TABLE_OFFSET + bx]
    cmp al, 0xFF
    je .invalid_pair
    mov ch, al

    xor ax, ax
    mov al, cl
    mov bx, ALPHABET_LEN
    mul bx
    xor bx, bx
    mov bl, ch
    add ax, bx
    cmp ax, CUSTOM_COUNT
    jae .invalid_pair

    mov bx, ax
    mov ax, bx
    shl bx, 1
    shl bx, 1
    shl bx, 1
    sub bx, ax
    add bx, GLYPH_TABLE_OFFSET
    mov si, bx
    mov di, SLOT_FIRST_ADDR
    mov cx, 7
.copy_glyph:
    mov al, byte ptr cs:[si]
    mov byte ptr cs:[di], al
    mov byte ptr cs:[di+0x0400], al
    inc si
    inc di
    loop .copy_glyph
    mov byte ptr cs:[SLOT_FIRST_LAST], 0
    mov byte ptr cs:[SLOT_SECOND_LAST], 0
    mov byte ptr cs:[SLOT_WIDTH_ADDR], 8
    mov word ptr [bp+6], SLOT_CHAR
    mov byte ptr cs:[stream_state], 0
    jmp .continue_original

.invalid_pair:
    mov word ptr [bp+6], 0x003F
    mov byte ptr cs:[stream_state], 0
    jmp .continue_original

.idle:
    cmp al, ESCAPE_BYTE
    jne .continue_original
    mov byte ptr cs:[stream_state], 1
    jmp .suppress_draw

.first_ranked_byte:
    cmp al, ESCAPE_BYTE
    je .literal_escape
    mov byte ptr cs:[first_byte], al
    mov byte ptr cs:[stream_state], 2
    jmp .suppress_draw

.literal_escape:
    mov byte ptr cs:[stream_state], 0

.continue_original:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    # resident_char already established BP at 0x0910.  We replaced only that
    # three-byte prologue with a jump here, so resume at the original +3 body.
    jmp ORIGINAL_CHAR_CONTINUE

.suppress_draw:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    mov sp, bp
    pop bp
    retf

.align 2
stream_state:
    .byte 0
first_byte:
    .byte 0
roster_char_stream_end:
