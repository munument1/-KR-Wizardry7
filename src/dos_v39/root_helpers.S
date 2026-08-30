.code16
.intel_syntax noprefix
.section .text

.equ ROOT_WIDTH_TARGET, 0x38CA
.equ RECT_FILL_TARGET, 0x3948
.equ VPCMK_STAT_DRAW_TARGET, 0x69F2

.global width_entry
.global trailing_entry
.global stat_repaint

# One-argument UI width adapter. AX=0 selects normal font 0 in the resident
# dispatcher. Both entries share the same call frame so the complete root block
# fits in the dead tail at 0x38F4..0x3920.
width_entry:
    xor ax, ax
    jmp short common

# One-argument scene trailing-byte adapter. 0x0100 is outside valid font indices
# and is interpreted by the FontResident dispatcher as trailing_ascii(text).
trailing_entry:
    mov ax, 0x0100

common:
    push bp
    mov bp, sp
    push ax
    push word ptr [bp+4]
    call ROOT_WIDTH_TARGET
    add sp, 4
    mov sp, bp
    pop bp
    ret

# The VPCMK caller already has the normal two stat-draw arguments on stack.
# Clear the rectangle, then tail-jump to the normal draw routine so its RET
# returns directly to the original caller and leaves argument cleanup unchanged.
stat_repaint:
    push 0
    push 0x6C
    push 0x00A8
    push 0x20
    push 0x66
    call RECT_FILL_TARGET
    add sp, 10
    jmp VPCMK_STAT_DRAW_TARGET
