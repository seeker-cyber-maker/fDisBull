; Reusable raw x86-16 module, not a standalone COM.
bits 16
org 0
; AX input/output; all other registers/stack preserved; arithmetic FLAGS clobbered.
imul ax, ax, strict word 25173
add ax, strict word 13849
