.code16
.intel_syntax noprefix
.section .text
.global stub
stub:
    mov ax, word ptr cs:[0x364A]
    test ax, ax
    jz .done
    mov bx, sp
    push word ptr [bx+4]
    push word ptr [bx+2]
    push cs
    push offset .return_here
    push ax
    push RES_OFF
    retf
.return_here:
    add sp, 4
.done:
    ret
