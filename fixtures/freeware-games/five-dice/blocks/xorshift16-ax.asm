; Reusable raw x86-16 module, not a standalone COM.
bits 16
org 0
; AX input/output; all other registers/stack preserved; arithmetic FLAGS clobbered.
test ax, 0x0100
jz short .next_0
xor ax, strict word 0x8000
.next_0:
test ax, 0x0080
jz short .next_1
xor ax, strict word 0x4000
.next_1:
test ax, 0x0040
jz short .next_2
xor ax, strict word 0x2000
.next_2:
test ax, 0x0020
jz short .next_3
xor ax, strict word 0x1000
.next_3:
test ax, 0x0010
jz short .next_4
xor ax, strict word 0x0800
.next_4:
test ax, 0x0008
jz short .next_5
xor ax, strict word 0x0400
.next_5:
test ax, 0x0004
jz short .next_6
xor ax, strict word 0x0200
.next_6:
test ax, 0x0002
jz short .next_7
xor ax, strict word 0x0100
.next_7:
test ax, 0x0001
jz short .next_8
xor ax, strict word 0x0080
.next_8:
test ax, 0x0200
jz short .next_9
xor ax, strict word 0x0001
.next_9:
test ax, 0x0400
jz short .next_10
xor ax, strict word 0x0002
.next_10:
test ax, 0x0800
jz short .next_11
xor ax, strict word 0x0004
.next_11:
test ax, 0x1000
jz short .next_12
xor ax, strict word 0x0008
.next_12:
test ax, 0x2000
jz short .next_13
xor ax, strict word 0x0010
.next_13:
test ax, 0x4000
jz short .next_14
xor ax, strict word 0x0020
.next_14:
test ax, 0x8000
jz short .next_15
xor ax, strict word 0x0040
.next_15:
test ax, 0x0001
jz short .next_16
xor ax, strict word 0x0100
.next_16:
test ax, 0x0002
jz short .next_17
xor ax, strict word 0x0200
.next_17:
test ax, 0x0004
jz short .next_18
xor ax, strict word 0x0400
.next_18:
test ax, 0x0008
jz short .next_19
xor ax, strict word 0x0800
.next_19:
test ax, 0x0010
jz short .next_20
xor ax, strict word 0x1000
.next_20:
test ax, 0x0020
jz short .next_21
xor ax, strict word 0x2000
.next_21:
test ax, 0x0040
jz short .next_22
xor ax, strict word 0x4000
.next_22:
test ax, 0x0080
jz short .next_23
xor ax, strict word 0x8000
.next_23:
