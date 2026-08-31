.code16
.intel_syntax noprefix
.section .text
.global stub
stub:
    push bp
    mov bp, sp
    sub sp, 4
    mov ax, word ptr cs:[0x364A]
    test ax, ax
    jz .zero
    mov word ptr [bp-4], RES_OFF
    mov word ptr [bp-2], ax
    push word ptr [bp+6]
    push word ptr [bp+4]
    call far ptr [bp-4]
    add sp, 4
    jmp .done
.zero:
    xor ax, ax
.done:
    mov sp, bp
    pop bp
    ret
