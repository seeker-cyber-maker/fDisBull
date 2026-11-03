; Minimal Snake v1 -- newly authored analysis fixture, CC0-1.0.
; MASM 5.1 / LINK, 8086 small-model DOS MZ executable.
; Graphics/input shell is separate from the pure snake_step procedure.
; Board: 30 x 20 cells, index y*30+x; head is snake_cells[0].
; Directions: 0 up, 1 right, 2 down, 3 left. Status: 0 active,1 dead,2 won.
; LCG: seed=(seed*25173+13849) mod 65536, initial seed=1234h.
; On eating, advance RNG once; scan from seed%600 for first free cell.
; Default paused. No timer, BIOS, DOS or mouse calls occur in snake_step.
.8086
.model small
.stack 512

.data
PUBLIC snake_cells, snake_length, direction, pending_direction, paused
PUBLIC game_status, score, rng_seed, tick_count, key_events, mouse_events
PUBLIC frame_count, mouse_present, food_cell, turn_queued
snake_cells       dw 600 dup(0)
snake_length      dw 3
direction         dw 1
pending_direction dw 1
paused            dw 1
game_status       dw 0
score             dw 0
rng_seed          dw 1234h
tick_count        dw 0
key_events        dw 0
mouse_events      dw 0
frame_count       dw 0
mouse_present     dw 0
food_cell         dw 312
turn_queued       dw 0

; Shell bookkeeping and pure-kernel scratch are outside the public state.
last_tick         dw 0
mouse_buttons     dw 0
mouse_x           dw 0
mouse_y           dw 0
needs_render      dw 1
step_requested    dw 0
quit_requested    dw 0
next_cell         dw 0
next_x            dw 0
next_y            dw 0
growing           dw 0
rect_color        db 0
rect_x            dw 0
rect_y            dw 0
rect_w            dw 0
rect_h            dw 0
text_title        db 'SNAKE v1  SCORE ',0
text_paused       db 'PAUSED ',0
text_running      db 'RUNNING',0
text_dead         db 'DEAD   ',0
text_won          db 'WON    ',0
text_controls     db 'Arrows/WASD  P:pause N:step R:reset Esc',0
text_up           db 'UP',0
text_left         db 'L',0
text_right        db 'R',0
text_down         db 'DN',0
text_pause        db 'PAUSE',0
text_step         db 'STEP',0
text_restart      db 'RESET',0
text_mouse        db 'MOUSE',0
text_nomouse      db 'KEYS ',0

.code
PUBLIC main_loop, reset_game, snake_step, poll_input, poll_mouse, render_frame
start:
    mov ax,@data
    mov ds,ax
    mov ax,0013h
    int 10h
    mov ax,@data
    mov ds,ax
    xor ax,ax
    push ds
    push es
    int 33h
    pop es
    pop ds
    cmp ax,0ffffh
    jne start_no_mouse
    mov mouse_present,1
    ; Fix the driver's logical coordinate range to actual VGA pixel units.
    mov ax,7
    xor cx,cx
    mov dx,319
    push ds
    push es
    int 33h
    pop es
    pop ds
    mov ax,8
    xor cx,cx
    mov dx,199
    push ds
    push es
    int 33h
    pop es
    pop ds
    mov ax,1
    push ds
    push es
    int 33h
    pop es
    pop ds
start_no_mouse:
    call reset_game
    call refresh_clock
main_loop:
    call poll_input
    call poll_mouse
    cmp quit_requested,0
    je main_not_quit
    jmp exit_game
main_not_quit:
    cmp step_requested,0
    je main_auto_tick
    mov step_requested,0
    cmp paused,1
    jne main_render
    call snake_step
    mov needs_render,1
    call refresh_clock
    jmp main_render
main_auto_tick:
    cmp paused,0
    jne main_render
    cmp game_status,0
    jne main_render
    call read_clock
    sub dx,last_tick
    cmp dx,4
    jb main_render
    ; Do not catch up missed periods: at most one step at each observation.
    call snake_step
    mov needs_render,1
    call refresh_clock
main_render:
    cmp needs_render,0
    je main_loop
    call render_frame
    mov needs_render,0
    jmp main_loop

exit_game:
    cmp mouse_present,0
    je exit_text
    mov ax,2
    push ds
    push es
    int 33h
    pop es
    pop ds
exit_text:
    mov ax,0003h
    int 10h
    mov ax,4c00h
    int 21h

; read_clock returns low 16 BIOS ticks in DX, preserving every other register.
read_clock proc near
    push ax
    push bx
    push cx
    push si
    push di
    push bp
    push ds
    push es
    xor ah,ah
    int 1ah
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop cx
    pop bx
    pop ax
    ret
read_clock endp
refresh_clock proc near
    push dx
    call read_clock
    mov last_tick,dx
    pop dx
    ret
refresh_clock endp

; A reset repeats the initial state, including deterministic diagnostic counters.
; mouse_present is a shell capability and survives restart.
reset_game proc near
    push ax
    push cx
    push di
    push es
    mov ax,ds
    mov es,ax
    lea di,snake_cells
    mov cx,600
    xor ax,ax
    cld
    rep stosw
    mov snake_cells,308
    mov snake_cells+2,307
    mov snake_cells+4,306
    mov snake_length,3
    mov direction,1
    mov pending_direction,1
    mov paused,1
    mov game_status,0
    mov score,0
    mov rng_seed,1234h
    mov food_cell,312
    mov tick_count,0
    mov key_events,0
    mov mouse_events,0
    mov frame_count,0
    mov turn_queued,0
    mov step_requested,0
    mov needs_render,1
    pop es
    pop di
    pop cx
    pop ax
    ret
reset_game endp

; Pure step. All register values are preserved. Input state invariants:
; length 1..600, occupied unique in-range cells, directions0..3,
; food free/in-range when active. Mutable state only; no OS interactions.
snake_step proc near
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    cmp game_status,0
    je ss_active
    jmp ss_done
ss_active:
    inc tick_count
    mov ax,direction
    add ax,2
    and ax,3
    cmp ax,pending_direction
    je ss_keep_direction
    mov ax,pending_direction
    mov direction,ax
ss_keep_direction:
    mov ax,direction
    mov pending_direction,ax
    mov turn_queued,0
    mov ax,snake_cells
    xor dx,dx
    mov bx,30
    div bx
    mov next_x,dx
    mov next_y,ax
    cmp direction,0
    jne ss_not_up
    dec next_y
    jmp ss_check_bounds
ss_not_up:
    cmp direction,1
    jne ss_not_right
    inc next_x
    jmp ss_check_bounds
ss_not_right:
    cmp direction,2
    jne ss_left
    inc next_y
    jmp ss_check_bounds
ss_left:
    dec next_x
ss_check_bounds:
    cmp next_x,30
    jb ss_x_ok
    jmp ss_dead
ss_x_ok:
    cmp next_y,20
    jb ss_y_ok
    jmp ss_dead
ss_y_ok:
    mov ax,next_y
    mov bx,30
    mul bx
    add ax,next_x
    mov next_cell,ax
    mov growing,0
    cmp ax,food_cell
    jne ss_collision_length
    mov growing,1
ss_collision_length:
    mov cx,snake_length
    cmp growing,0
    jne ss_collision_start
    dec cx
ss_collision_start:
    xor si,si
    jcxz ss_safe
ss_collision_loop:
    cmp ax,snake_cells[si]
    jne ss_not_collision
    jmp ss_dead
ss_not_collision:
    add si,2
    loop ss_collision_loop
ss_safe:
    cmp growing,0
    je ss_shift
    inc snake_length
    inc score
ss_shift:
    mov bx,snake_length
    dec bx
    shl bx,1
    jz ss_write_head
ss_shift_loop:
    mov ax,snake_cells[bx-2]
    mov snake_cells[bx],ax
    sub bx,2
    jnz ss_shift_loop
ss_write_head:
    mov ax,next_cell
    mov snake_cells,ax
    cmp growing,0
    je ss_done
    cmp snake_length,600
    jne ss_place_food
    mov game_status,2
    mov paused,1
    mov food_cell,0ffffh
    jmp ss_done
ss_place_food:
    call find_food
    jmp ss_done
ss_dead:
    mov game_status,1
    mov paused,1
ss_done:
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
snake_step endp

; Pure helper: deterministic RNG once, then bounded first-free scan.
; Called only after growth with length<600. Clobbers AX,BX,CX,DX,SI,DI,BP.
find_food proc near
    mov ax,rng_seed
    mov bx,25173
    mul bx
    add ax,13849
    mov rng_seed,ax
    xor dx,dx
    mov bx,600
    div bx
    mov di,dx
    mov bp,600
ff_try:
    xor si,si
    mov cx,snake_length
ff_scan:
    cmp di,snake_cells[si]
    je ff_occupied
    add si,2
    loop ff_scan
    mov food_cell,di
    ret
ff_occupied:
    inc di
    cmp di,600
    jb ff_in_range
    xor di,di
ff_in_range:
    dec bp
    jnz ff_try
    ; Defensive bounded exit; valid state always finds a free cell.
    mov game_status,2
    mov paused,1
    mov food_cell,0ffffh
    ret
find_food endp

; Queue AX direction once per tick. Reject direct reversal and invalid enum.
queue_direction proc near
    push bx
    cmp game_status,0
    jne qd_done
    cmp turn_queued,0
    jne qd_done
    cmp ax,3
    ja qd_done
    mov bx,direction
    add bx,2
    and bx,3
    cmp ax,bx
    je qd_done
    ; An unchanged heading does not consume the one-turn admission slot.
    cmp ax,direction
    je qd_done
    mov pending_direction,ax
    mov turn_queued,1
    mov needs_render,1
qd_done:
    pop bx
    ret
queue_direction endp

toggle_pause proc near
    cmp game_status,0
    jne tp_done
    xor paused,1
    mov needs_render,1
    call refresh_clock
 tp_done:
    ret
toggle_pause endp
request_step proc near
    cmp game_status,0
    jne rs_done
    cmp paused,1
    jne rs_done
    mov step_requested,1
rs_done:
    ret
request_step endp

; Consume at most one real BIOS keyboard event per poll.
poll_input proc near
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov ah,1
    int 16h
    jnz pi_available
    jmp pi_done
pi_available:
    xor ah,ah
    int 16h
    ; DOS BIOS contract preserves DS/ES; restore defensively before state use.
    pop es
    pop ds
    push ds
    push es
    inc key_events
    cmp al,27
    jne pi_not_escape
    mov quit_requested,1
    jmp pi_done
pi_not_escape:
    cmp al,' '
    jne pi_not_space
    call toggle_pause
    jmp pi_done
pi_not_space:
    cmp al,'A'
    jb pi_ascii
    cmp al,'Z'
    ja pi_ascii
    add al,32
pi_ascii:
    cmp al,'p'
    jne pi_not_pause
    call toggle_pause
    jmp pi_done
pi_not_pause:
    cmp al,'n'
    jne pi_not_step
    call request_step
    jmp pi_done
pi_not_step:
    cmp al,'r'
    jne pi_not_reset
    call reset_game
    call refresh_clock
    jmp pi_done
pi_not_reset:
    cmp al,'w'
    jne pi_scan_up
    jmp pi_up
pi_scan_up:
    cmp ah,48h
    jne pi_ascii_right
    jmp pi_up
pi_ascii_right:
    cmp al,'d'
    jne pi_scan_right
    jmp pi_right
pi_scan_right:
    cmp ah,4dh
    jne pi_ascii_down
    jmp pi_right
pi_ascii_down:
    cmp al,'s'
    jne pi_scan_down
    jmp pi_down
pi_scan_down:
    cmp ah,50h
    jne pi_ascii_left
    jmp pi_down
pi_ascii_left:
    cmp al,'a'
    jne pi_scan_left
    jmp pi_left
pi_scan_left:
    cmp ah,4bh
    jne pi_done
pi_left:
    mov ax,3
    call queue_direction
    jmp pi_done
pi_up:
    xor ax,ax
    call queue_direction
    jmp pi_done
pi_right:
    mov ax,1
    call queue_direction
    jmp pi_done
pi_down:
    mov ax,2
    call queue_direction
pi_done:
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
poll_input endp

; Poll real INT33 mouse; only a rising left-button edge dispatches a control.
poll_mouse proc near
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    cmp mouse_present,0
    jne pm_present
    jmp pm_done
pm_present:
    mov ax,3
    int 33h
    pop es
    pop ds
    push ds
    push es
    mov mouse_x,cx
    mov mouse_y,dx
    mov ax,mouse_buttons
    mov mouse_buttons,bx
    test bx,1
    jnz pm_pressed
    jmp pm_done
pm_pressed:
    test ax,1
    jz pm_edge
    jmp pm_done
pm_edge:
    inc mouse_events
    cmp cx,256
    jae pm_x_min
    jmp pm_done
pm_x_min:
    cmp cx,311
    jbe pm_x_max
    jmp pm_done
pm_x_max:
    cmp dx,120
    jb pm_dpad
    cmp dx,139
    ja pm_not_pause
    call toggle_pause
    jmp pm_done
pm_not_pause:
    cmp dx,144
    jae pm_step_min
    jmp pm_done
pm_step_min:
    cmp dx,163
    ja pm_not_step
    call request_step
    jmp pm_done
pm_not_step:
    cmp dx,168
    jb pm_done
    cmp dx,187
    ja pm_done
    call reset_game
    call refresh_clock
    jmp pm_done
pm_dpad:
    cmp dx,40
    jb pm_done
    cmp dx,59
    ja pm_not_up
    cmp cx,280
    jb pm_done
    cmp cx,303
    ja pm_done
    xor ax,ax
    call queue_direction
    jmp pm_done
pm_not_up:
    cmp dx,64
    jb pm_done
    cmp dx,83
    ja pm_not_horizontal
    cmp cx,279
    ja pm_maybe_right
    mov ax,3
    call queue_direction
    jmp pm_done
pm_maybe_right:
    cmp cx,288
    jb pm_done
    mov ax,1
    call queue_direction
    jmp pm_done
pm_not_horizontal:
    cmp dx,88
    jb pm_done
    cmp dx,107
    ja pm_done
    cmp cx,280
    jb pm_done
    cmp cx,303
    ja pm_done
    mov ax,2
    call queue_direction
pm_done:
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
poll_mouse endp

; Filled rectangle: AX=x, BX=y, CX=width, DX=height, AL overwritten by color
; is avoided by passing color in private rect_color. Caller sets rect_color.
; ES must be A000h. Preserves every register and DS/ES.
fill_rect proc near
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    mov rect_x,ax
    mov rect_y,bx
    mov rect_w,cx
    mov rect_h,dx
    mov ax,bx
    mov bp,320
    mul bp
    add ax,rect_x
    mov di,ax
    mov si,rect_h
    mov al,rect_color
    cld
fr_row:
    mov cx,rect_w
    rep stosb
    add di,320
    sub di,rect_w
    dec si
    jnz fr_row
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
fill_rect endp

; Cell AX packed index, rect_color. ES=A000h. Leaves 1 pixel cell gutters.
draw_cell proc near
    push ax
    push bx
    push cx
    push dx
    xor dx,dx
    mov bx,30
    div bx
    mov bx,ax
    mov ax,dx
    shl ax,1
    shl ax,1
    shl ax,1
    add ax,8
    shl bx,1
    shl bx,1
    shl bx,1
    add bx,24
    mov cx,7
    mov dx,7
    call fill_rect
    pop dx
    pop cx
    pop bx
    pop ax
    ret
draw_cell endp

; BIOS output helpers preserve registers, including DS/ES across firmware calls.
text_position proc near
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov ah,2
    xor bh,bh
    int 10h
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
text_position endp
text_char proc near
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov ah,0eh
    xor bh,bh
    mov bl,15
    int 10h
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
text_char endp
text_z proc near
    push ax
    push si
    cld
 tz_loop:
    lodsb
    or al,al
    jz tz_done
    call text_char
    jmp tz_loop
 tz_done:
    pop si
    pop ax
    ret
text_z endp
text_number proc near
    push ax
    push bx
    push cx
    push dx
    xor cx,cx
    mov bx,10
 tn_div:
    xor dx,dx
    div bx
    push dx
    inc cx
    or ax,ax
    jnz tn_div
 tn_print:
    pop ax
    add al,'0'
    call text_char
    loop tn_print
    pop dx
    pop cx
    pop bx
    pop ax
    ret
text_number endp

render_frame proc near
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    cmp mouse_present,0
    je rf_hidden
    mov ax,2
    push ds
    push es
    int 33h
    pop es
    pop ds
rf_hidden:
    mov ax,0a000h
    mov es,ax
    xor di,di
    xor ax,ax
    mov cx,32000
    cld
    rep stosw
    ; Grey border outside the 30x20 legal board.
    mov rect_color,8
    mov ax,6
    mov bx,22
    mov cx,244
    mov dx,164
    call fill_rect
    mov rect_color,0
    mov ax,8
    mov bx,24
    mov cx,240
    mov dx,160
    call fill_rect
    mov rect_color,2
    mov cx,snake_length
    lea si,snake_cells
rf_body:
    lodsw
    call draw_cell
    loop rf_body
    mov rect_color,10
    mov ax,snake_cells
    call draw_cell
    cmp food_cell,600
    jae rf_buttons
    mov rect_color,12
    mov ax,food_cell
    call draw_cell
rf_buttons:
    mov rect_color,1
    mov ax,280
    mov bx,40
    mov cx,24
    mov dx,20
    call fill_rect
    mov ax,256
    mov bx,64
    call fill_rect
    mov ax,288
    call fill_rect
    mov ax,280
    mov bx,88
    call fill_rect
    mov ax,256
    mov bx,120
    mov cx,56
    call fill_rect
    mov bx,144
    call fill_rect
    mov bx,168
    call fill_rect
    mov dh,0
    mov dl,0
    call text_position
    lea si,text_title
    call text_z
    mov ax,score
    call text_number
    mov dh,1
    mov dl,0
    call text_position
    lea si,text_paused
    cmp game_status,1
    jne rf_not_dead
    lea si,text_dead
    jmp rf_state_text
rf_not_dead:
    cmp game_status,2
    jne rf_not_won
    lea si,text_won
    jmp rf_state_text
rf_not_won:
    cmp paused,0
    jne rf_state_text
    lea si,text_running
rf_state_text:
    call text_z
    mov dh,1
    mov dl,32
    call text_position
    lea si,text_nomouse
    cmp mouse_present,0
    je rf_mouse_text
    lea si,text_mouse
rf_mouse_text:
    call text_z
    mov dh,5
    mov dl,35
    call text_position
    lea si,text_up
    call text_z
    mov dh,8
    mov dl,32
    call text_position
    lea si,text_left
    call text_z
    mov dl,36
    call text_position
    lea si,text_right
    call text_z
    mov dh,11
    mov dl,35
    call text_position
    lea si,text_down
    call text_z
    mov dh,15
    mov dl,32
    call text_position
    lea si,text_pause
    call text_z
    mov dh,18
    mov dl,32
    call text_position
    lea si,text_step
    call text_z
    mov dh,21
    mov dl,32
    call text_position
    lea si,text_restart
    call text_z
    mov dh,24
    mov dl,0
    call text_position
    lea si,text_controls
    call text_z
    inc frame_count
    cmp mouse_present,0
    je rf_done
    mov ax,1
    push ds
    push es
    int 33h
    pop es
    pop ds
rf_done:
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
render_frame endp
end start
