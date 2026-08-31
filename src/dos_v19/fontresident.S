.code16
.intel_syntax noprefix
.section .text

.equ ESCAPE_BYTE, 0x17
.equ ROOT_FONT_TABLE, 0x364A
.equ ROOT_DRIVER_PTR, 0x2DB3
.equ FONT_TRACKING, 0x0007
.equ FONT_SECOND_SIZE, 0x000E
.equ FONT_WIDTH_TABLE, 0x0010
.equ SLOT_CHAR, 0x007F
.equ SLOT_WIDTH_ADDR, 0x010F
.equ SLOT_FIRST_ADDR, 0x0508
.equ SLOT_FIRST_LAST, 0x050F
.equ SLOT_SECOND_LAST, 0x090F

# supplied by --defsym: INV_TABLE_OFFSET, GLYPH_TABLE_OFFSET,
# ALPHABET_LEN, CUSTOM_COUNT
.global resident_char
.global resident_string
.global resident_width
.global resident_end

resident_char:
    push bp
    mov bp, sp
    push bx
    push dx
    push es
    mov ax, word ptr [bp+4]
    mov word ptr cs:[root_seg], ax
    mov word ptr cs:[FONT_SECOND_SIZE], 8
    push word ptr [bp+8]
    push word ptr [bp+6]
    call draw_char
    add sp, 4
    pop es
    pop dx
    pop bx
    mov sp, bp
    pop bp
    retf

resident_string:
    push bp
    mov bp, sp
    push si
    push di
    push bx
    push cx
    push dx
    push es
    cld
    mov ax, word ptr [bp+4]
    mov word ptr cs:[root_seg], ax
    mov word ptr cs:[FONT_SECOND_SIZE], 8
    mov si, word ptr [bp+6]
.rs_loop:
    xor ax, ax
    mov al, byte ptr [si]
    inc si
    test al, al
    jz .rs_done
    cmp al, ESCAPE_BYTE
    jne .rs_ascii
    mov dl, byte ptr [si]
    inc si
    cmp dl, ESCAPE_BYTE
    je .rs_literal_escape
    mov dh, byte ptr [si]
    inc si
    xor bx, bx
    mov bl, dl
    mov al, byte ptr cs:[INV_TABLE_OFFSET + bx]
    cmp al, 0xFF
    je .rs_bad_pair
    mov cl, al
    xor bx, bx
    mov bl, dh
    mov al, byte ptr cs:[INV_TABLE_OFFSET + bx]
    cmp al, 0xFF
    je .rs_bad_pair
    mov ch, al
    xor ax, ax
    mov al, cl
    mov bx, ALPHABET_LEN
    mul bx
    xor bx, bx
    mov bl, ch
    add ax, bx
    cmp ax, CUSTOM_COUNT
    jae .rs_bad_pair
    mov bx, ax
    call install_glyph
    push 0
    push SLOT_CHAR
    call draw_char
    add sp, 4
    jmp .rs_loop
.rs_bad_pair:
    mov ax, 0x003F
    jmp .rs_ascii
.rs_literal_escape:
    mov ax, ESCAPE_BYTE
.rs_ascii:
    push word ptr [bp+8]
    push ax
    call draw_char
    add sp, 4
    jmp .rs_loop
.rs_done:
    pop es
    pop dx
    pop cx
    pop bx
    pop di
    pop si
    mov sp, bp
    pop bp
    retf

draw_char:
    push bp
    mov bp, sp
    # VGA.DRV's near implementation reads character/font from fixed stack
    # positions. Keep SP == BP across this far call, like the stock wrapper.
    mov ax, word ptr cs:[root_seg]
    mov es, ax
    mov ax, word ptr [bp+6]
    shl ax, 1
    mov bx, ROOT_FONT_TABLE
    add bx, ax
    mov ax, word ptr es:[bx]
    test ax, ax
    jz .dc_done
    call far ptr es:[ROOT_DRIVER_PTR]
.dc_done:
    mov sp, bp
    pop bp
    ret

install_glyph:
    push ax
    push bx
    push cx
    push si
    push di
    mov ax, bx
    shl bx, 1
    shl bx, 1
    shl bx, 1
    sub bx, ax
    add bx, GLYPH_TABLE_OFFSET
    mov si, bx
    mov di, SLOT_FIRST_ADDR
    mov cx, 7
.ig_copy:
    mov al, byte ptr cs:[si]
    mov byte ptr cs:[di], al
    mov byte ptr cs:[di+0x0400], al
    inc si
    inc di
    loop .ig_copy
    mov byte ptr cs:[SLOT_FIRST_LAST], 0
    mov byte ptr cs:[SLOT_SECOND_LAST], 0
    mov byte ptr cs:[SLOT_WIDTH_ADDR], 8
    pop di
    pop si
    pop cx
    pop bx
    pop ax
    ret

resident_width:
    push bp
    mov bp, sp
    push si
    push bx
    push cx
    push dx
    push es
    cld
    mov ax, word ptr [bp+4]
    mov word ptr cs:[root_seg], ax
    mov word ptr cs:[FONT_SECOND_SIZE], 8
    mov si, word ptr [bp+6]
    xor cx, cx
.rw_loop:
    xor ax, ax
    mov al, byte ptr [si]
    inc si
    test al, al
    jz .rw_done
    cmp al, ESCAPE_BYTE
    jne .rw_ascii
    mov dl, byte ptr [si]
    inc si
    cmp dl, ESCAPE_BYTE
    je .rw_literal_escape
    mov dh, byte ptr [si]
    inc si
    xor bx, bx
    mov bl, dl
    mov al, byte ptr cs:[INV_TABLE_OFFSET + bx]
    cmp al, 0xFF
    je .rw_bad_pair
    mov dl, al
    xor bx, bx
    mov bl, dh
    mov al, byte ptr cs:[INV_TABLE_OFFSET + bx]
    cmp al, 0xFF
    je .rw_bad_pair
    add cx, 8
    jmp .rw_loop
.rw_bad_pair:
    mov ax, 0x003F
    jmp .rw_ascii
.rw_literal_escape:
    mov ax, ESCAPE_BYTE
.rw_ascii:
    push word ptr [bp+8]
    push ax
    call char_width
    add sp, 4
    add cx, ax
    jmp .rw_loop
.rw_done:
    mov ax, cx
    pop es
    pop dx
    pop cx
    pop bx
    pop si
    mov sp, bp
    pop bp
    retf

char_width:
    push bp
    mov bp, sp
    push bx
    push dx
    push es
    mov ax, word ptr cs:[root_seg]
    mov es, ax
    mov ax, word ptr [bp+6]
    shl ax, 1
    mov bx, ROOT_FONT_TABLE
    add bx, ax
    mov ax, word ptr es:[bx]
    test ax, ax
    jz .cw_zero
    mov es, ax
    mov bx, word ptr [bp+4]
    shl bx, 1
    add bx, FONT_WIDTH_TABLE
    xor ax, ax
    mov al, byte ptr es:[bx+1]
    xor dx, dx
    mov dl, byte ptr es:[FONT_TRACKING]
    cmp dl, 0x80
    jb .cw_positive_tracking
    mov dh, 0xFF
.cw_positive_tracking:
    add ax, dx
    jmp .cw_done
.cw_zero:
    xor ax, ax
.cw_done:
    pop es
    pop dx
    pop bx
    pop bp
    ret

.align 2
root_seg:
    .word 0
resident_end:
