; Five Dice, original DOS COM fixture, NASM syntax.
org 100h
bits 16
start:
 push cs
 pop ds
 mov word [seed],12345
 mov byte [turn],0
 mov word [total],0
next_turn:
 mov byte [rolls],0
 mov byte [holds],0
 call roll
show:
 mov dx,heading
 call puts
 mov al,[turn]
 add al,'1'
 call putc
 mov dx,categorymsg
 call puts
 xor bx,bx
 mov bl,[turn]
 shl bx,1
 mov dx,[categories+bx]
 call puts
 mov dx,rollmsg
 call puts
 mov al,[rolls]
 add al,'0'
 call putc
 mov dx,dicemsg
 call puts
 xor bx,bx
printdice:
 mov al,[dice+bx]
 add al,'0'
 call putc
 mov al,' '
 call putc
 inc bx
 cmp bx,5
 jb printdice
 mov dx,holdmsg
 call puts
 xor bx,bx
printholds:
 mov al,[holds]
 mov cl,bl
 shr al,cl
 and al,1
 add al,'0'
 call putc
 mov al,' '
 call putc
 inc bx
 cmp bx,5
 jb printholds
 mov dx,totalmsg
 call puts
 mov ax,[total]
 call number
 mov dx,cardmsg
 call puts
 mov ax,[scores]
 call number
 mov al,'/'
 call putc
 mov ax,[scores+2]
 call number
 mov al,'/'
 call putc
 mov ax,[scores+4]
 call number
 mov dx,menu
 call puts
 mov ah,01h
 int 21h
 cmp al,'1'
 jb command
 cmp al,'5'
 ja command
 sub al,'1'
 mov cl,al
 mov al,1
 shl al,cl
 xor [holds],al
 jmp show
command:
 and al,0dfh
 cmp al,'R'
 jne .score
 cmp byte [rolls],3
 jae show
 call roll
 jmp show
.score:
 cmp al,'S'
 jne show
 call score
 xor bx,bx
 mov bl,[turn]
 shl bx,1
 mov [scores+bx],ax
 add [total],ax
 push ax
 mov dx,scoremsg
 call puts
 pop ax
 call number
 mov dx,newline
 call puts
 inc byte [turn]
 cmp byte [turn],3
 jb next_turn
 mov dx,endmsg
 call puts
 mov ax,[total]
 call number
 mov dx,newline
 call puts
 mov ax,4c00h
 int 21h
roll:
 xor bx,bx
.loop:
 mov al,[holds]
 mov cl,bl
 shr al,cl
 test al,1
 jnz .skip
 ; 16-bit LCG; state belongs to provider
 mov ax,[seed]
 mov dx,25173
 mul dx
 add ax,13849
 mov [seed],ax
 xor dx,dx
 mov cx,6
 div cx
 inc dl
 mov [dice+bx],dl
.skip:
 inc bx
 cmp bx,5
 jb .loop
 inc byte [rolls]
 ret
score:
 xor ax,ax
 xor bx,bx
 cmp byte [turn],0
 jne .pair
.sum:
 xor dx,dx
 mov dl,[dice+bx]
 add ax,dx
 inc bx
 cmp bx,5
 jb .sum
 ret
.pair:
 cmp byte [turn],1
 jne .five
 ; highest pair, score twice value; zero if no pair
 mov bl,6
.find:
 xor cx,cx
 xor si,si
.count:
 cmp [dice+si],bl
 jne .n
 inc cl
.n: inc si
 cmp si,5
 jb .count
 cmp cl,2
 jae .found
 dec bl
 jnz .find
 ret
.found:
 mov al,bl
 shl ax,1
 ret
.five:
 mov al,[dice]
 mov bx,1
.check:
 cmp al,[dice+bx]
 jne .zero
 inc bx
 cmp bx,5
 jb .check
 mov ax,50
 ret
.zero: xor ax,ax
 ret
puts:
 mov ah,09h
 int 21h
 ret
putc:
 push dx
 mov dl,al
 mov ah,02h
 int 21h
 pop dx
 ret
number:
 xor cx,cx
 mov bx,10
.digit:
 xor dx,dx
 div bx
 push dx
 inc cx
 test ax,ax
 jnz .digit
.out:
 pop dx
 add dl,'0'
 mov ah,02h
 int 21h
 loop .out
 ret
heading db 13,10,'FIVE DICE - turn $'
categorymsg db ' category $'
cat1 db 'SUM$'
cat2 db 'PAIR$'
cat3 db 'FIVE$'
categories dw cat1,cat2,cat3
rollmsg db ' roll $'
dicemsg db 13,10,'Dice:  $'
holdmsg db 13,10,'Hold:  $'
totalmsg db 13,10,'Total: $'
cardmsg db 13,10,'Scorecard SUM/PAIR/FIVE (0 until scored): $'
menu db 13,10,'1-5 toggle hold, R reroll, S score: $'
scoremsg db 13,10,'Turn score: $'
endmsg db 'Game over! Total: $'
newline db 13,10,'$'
seed dw 0
total dw 0
scores dw 0,0,0
turn db 0
rolls db 0
holds db 0
dice times 5 db 0
