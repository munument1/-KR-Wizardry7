.code16
.intel_syntax noprefix
.section .text

.equ ESCAPE_BYTE, 0x17
.equ WIDTH_CONTINUATION, 0x0A33

.global dispatch

dispatch:
    push bp
    mov bp, sp
    mov ax, word ptr [bp+8]
    cmp ax, 0x20
    je find_delimiter
    cmp ax, 0x5F
    je find_delimiter
    cmp ax, 0x0100
    je trailing_ascii
    jmp WIDTH_CONTINUATION

# Far-call stack after the root width trampoline:
#   [bp+4] = root CS (far return segment)
#   [bp+6] = text
#   [bp+8] = operation/font index
# For operation 0x20 or 0x5F, return the byte index of the first standalone
# delimiter while skipping complete ESC+rank+rank Korean glyph units.
find_delimiter:
    push si
    push bx
    cld
    mov si, word ptr [bp+6]
    xor bx, bx
.find_loop:
    lodsb
    test al, al
    jz .find_not_found
    cmp al, ESCAPE_BYTE
    jne .find_compare
    lodsb
    cmp al, ESCAPE_BYTE
    je .find_literal_escape
    inc si
    add bx, 3
    jmp .find_loop
.find_literal_escape:
    add bx, 2
    jmp .find_loop
.find_compare:
    cmp al, byte ptr [bp+8]
    je .find_found
    inc bx
    jmp .find_loop
.find_not_found:
    mov ax, 0xFFFF
    jmp .find_done
.find_found:
    mov ax, bx
.find_done:
    pop bx
    pop si
    mov sp, bp
    pop bp
    retf

# Operation 0x0100: return the final standalone ASCII/literal byte, or zero
# when the final logical unit is a Korean glyph. This matches the v26 helper
# semantics without placing executable code in the overlay load window.
trailing_ascii:
    push si
    push bx
    cld
    mov si, word ptr [bp+6]
    xor bx, bx
.trailing_loop:
    lodsb
    test al, al
    jz .trailing_done
    cmp al, ESCAPE_BYTE
    jne .trailing_ascii_byte
    lodsb
    cmp al, ESCAPE_BYTE
    je .trailing_literal_escape
    inc si
    xor bx, bx
    jmp .trailing_loop
.trailing_literal_escape:
    mov bx, ESCAPE_BYTE
    jmp .trailing_loop
.trailing_ascii_byte:
    xor ah, ah
    mov bx, ax
    jmp .trailing_loop
.trailing_done:
    mov ax, bx
    pop bx
    pop si
    mov sp, bp
    pop bp
    retf
