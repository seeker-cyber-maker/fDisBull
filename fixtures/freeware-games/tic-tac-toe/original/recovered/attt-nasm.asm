; Mechanical TASM-to-NASM COM adaptation. See README.
bits 16
org 100h
jmp start
; Ancient TicTacToe
; TASM @ DOS
; Sai Kurogetsu
; 2015-01-01



board00	db	32
board01	db	32
board02	db	32
board10	db	32
board11	db	32
board12	db	32
board20	db	32
board21	db	32
board22	db	32
drawCount	dw	1
drawChar	db	32
curBoardCell	db	32
playerNum	db	1
playerWon	db	0
playerStarts	db	1
player1WonCount	db	0
player2WonCount	db	0
turnCount	db	0

procDrawChar:
	mov	cx, [drawCount]
	procDrawChar_loop:
		mov	dl, [drawChar]
		mov	ah, 02h
		int	21h
		dec	cx
		cmp	cx, 0
		jnz	procDrawChar_loop
	ret

procDrawMarginLeft:
	mov	word [drawCount], 27
	mov	byte [drawChar], 32
	call	procDrawChar
	ret

procDrawMarginRight:
	mov	word [drawCount], 28
	mov	byte [drawChar], 32
	call	procDrawChar
	ret

procDrawCellEmpty:
	mov	word [drawCount], 7
	mov	byte [drawChar], 32
	call	procDrawChar
	ret

procDrawCell:
	mov	word [drawCount], 3
	mov	byte [drawChar], 32
	call	procDrawChar

	mov	word [drawCount], 1
	mov	cl, [curBoardCell]
	mov	[drawChar], cl
	call	procDrawChar

	mov	word [drawCount], 3
	mov	byte [drawChar], 32
	call	procDrawChar
	ret

procDrawCellVerticalBorder:
	mov	word [drawCount], 2
	mov	byte [drawChar], 219
	call	procDrawChar
	ret

procDrawCellHorizontalBorder:
	mov	word [drawCount], 25
	mov	byte [drawChar], 219
	call	procDrawChar
	ret

procPrintStringPlayerTurn:
	mov	word [drawCount], 15
	mov	byte [drawChar], 32
	call	procDrawChar

	cmp	byte [player1WonCount], 100
	jl	procPrintStringPlayerTurn_p1_2digits
	jmp	procPrintStringPlayerTurn_p1_3digits

	procPrintStringPlayerTurn_p1_2digits:
		mov	ah, 02h
		mov	dl, 32
		int	21h
		cmp	byte [player1WonCount], 10
		jl	procPrintStringPlayerTurn_p1_1digit
		jmp	procPrintStringPlayerTurn_p1_3digits

	procPrintStringPlayerTurn_p1_1digit:
		int	21h

	procPrintStringPlayerTurn_p1_3digits:
	mov	dl, [player1WonCount]
	add	dl, 48
	int	21h

	mov	word [drawCount], 17
	mov	byte [drawChar], 32
	call	procDrawChar

	mov	ah, 02h
	mov	dl, 'P'
	int	21h
	mov	dl, 'L'
	int	21h
	mov	dl, 'A'
	int	21h
	mov	dl, 'Y'
	int	21h
	mov	dl, 'E'
	int	21h
	mov	dl, 'R'
	int	21h
	mov	dl, ' '
	int	21h
	mov	dl, ' '
	int	21h
	mov	dl, [playerNum]
	add	dl, 48
	int	21h

	mov	word [drawCount], 17
	mov	byte [drawChar], 32
	call	procDrawChar

	cmp	byte [player2WonCount], 100
	jl	procPrintStringPlayerTurn_p2_2digits
	jmp	procPrintStringPlayerTurn_p2_3digits

	procPrintStringPlayerTurn_p2_2digits:
		mov	ah, 02h
		mov	dl, 32
		int	21h
		cmp	byte [player2WonCount], 10
		jl	procPrintStringPlayerTurn_p2_1digit
		jmp	procPrintStringPlayerTurn_p2_3digits

	procPrintStringPlayerTurn_p2_1digit:
		int	21h

	procPrintStringPlayerTurn_p2_3digits:
	mov	dl, [player2WonCount]
	add	dl, 48
	int	21h

	mov	word [drawCount], 16
	mov	byte [drawChar], 32
	call	procDrawChar

	ret

procPrintStringWon:
	mov	word [drawCount], 38
	mov	byte [drawChar], 32
	call	procDrawChar
	mov	ah, 02h
	mov	dl, 'W'
	int	21h
	mov	dl, 'I'
	int	21h
	mov	dl, 'N'
	int	21h
	mov	dl, 'S'
	int	21h
	mov	word [drawCount], 38
	mov	byte [drawChar], 32
	call	procDrawChar
	ret

procPrintStringDraw:
	mov	word [drawCount], 118
	mov	byte [drawChar], 32
	call	procDrawChar
	mov	ah, 02h
	mov	dl, 'D'
	int	21h
	mov	dl, 'R'
	int	21h
	mov	dl, 'A'
	int	21h
	mov	dl, 'W'
	int	21h
	mov	word [drawCount], 38
	mov	byte [drawChar], 32
	call	procDrawChar
	ret

procParseInput:
	cmp	al, 1bh
	jz	procParseInput_exit

	cmp	byte [playerNum], 2
	jz	procParseInput_player2

	procParseInput_player1:
		cmp	al, 'q'
		jz	procParseInput_player1_00
		cmp	al, 'w'
		jz	procParseInput_player1_01
		cmp	al, 'e'
		jz	procParseInput_player1_02
		cmp	al, 'a'
		jz	procParseInput_player1_10
		cmp	al, 's'
		jz	procParseInput_player1_11
		cmp	al, 'd'
		jz	procParseInput_player1_12
		cmp	al, 'z'
		jz	procParseInput_player1_20
		cmp	al, 'x'
		jz	procParseInput_player1_21
		cmp	al, 'c'
		jz	procParseInput_player1_22
		ret

	procParseInput_player1_00:
		cmp	byte [board00], 32
		jnz	procParseInput_end
		mov	byte [board00], 'x'
		jmp	procParseInput_player1End
	procParseInput_player1_01:
		cmp	byte [board01], 32
		jnz	procParseInput_end
		mov	byte [board01], 'x'
		jmp	procParseInput_player1End
	procParseInput_player1_02:
		cmp	byte [board02], 32
		jnz	procParseInput_end
		mov	byte [board02], 'x'
		jmp	procParseInput_player1End
	procParseInput_player1_10:
		cmp	byte [board10], 32
		jnz	procParseInput_end
		mov	byte [board10], 'x'
		jmp	procParseInput_player1End
	procParseInput_player1_11:
		cmp	byte [board11], 32
		jnz	procParseInput_end
		mov	byte [board11], 'x'
		jmp	procParseInput_player1End
	procParseInput_player1_12:
		cmp	byte [board12], 32
		jnz	procParseInput_end
		mov	byte [board12], 'x'
		jmp	procParseInput_player1End
	procParseInput_player1_20:
		cmp	byte [board20], 32
		jnz	procParseInput_end
		mov	byte [board20], 'x'
		jmp	procParseInput_player1End
	procParseInput_player1_21:
		cmp	byte [board21], 32
		jnz	procParseInput_end
		mov	byte [board21], 'x'
		jmp	procParseInput_player1End
	procParseInput_player1_22:
		cmp	byte [board22], 32
		jnz	procParseInput_end
		mov	byte [board22], 'x'
		jmp	procParseInput_player1End

	procParseInput_player2:
		cmp	al, '7'
		jz	procParseInput_player2_00
		cmp	al, '8'
		jz	procParseInput_player2_01
		cmp	al, '9'
		jz	procParseInput_player2_02
		cmp	al, '4'
		jz	procParseInput_player2_10
		cmp	al, '5'
		jz	procParseInput_player2_11
		cmp	al, '6'
		jz	procParseInput_player2_12
		cmp	al, '1'
		jz	procParseInput_player2_20
		cmp	al, '2'
		jz	procParseInput_player2_21
		cmp	al, '3'
		jz	procParseInput_player2_22
		ret

	procParseInput_player2_00:
		cmp	byte [board00], 32
		jnz	procParseInput_end
		mov	byte [board00], 'o'
		jmp	procParseInput_player2End
	procParseInput_player2_01:
		cmp	byte [board01], 32
		jnz	procParseInput_end
		mov	byte [board01], 'o'
		jmp	procParseInput_player2End
	procParseInput_player2_02:
		cmp	byte [board02], 32
		jnz	procParseInput_end
		mov	byte [board02], 'o'
		jmp	procParseInput_player2End
	procParseInput_player2_10:
		cmp	byte [board10], 32
		jnz	procParseInput_end
		mov	byte [board10], 'o'
		jmp	procParseInput_player2End
	procParseInput_player2_11:
		cmp	byte [board11], 32
		jnz	procParseInput_end
		mov	byte [board11], 'o'
		jmp	procParseInput_player2End
	procParseInput_player2_12:
		cmp	byte [board12], 32
		jnz	procParseInput_end
		mov	byte [board12], 'o'
		jmp	procParseInput_player2End
	procParseInput_player2_20:
		cmp	byte [board20], 32
		jnz	procParseInput_end
		mov	byte [board20], 'o'
		jmp	procParseInput_player2End
	procParseInput_player2_21:
		cmp	byte [board21], 32
		jnz	procParseInput_end
		mov	byte [board21], 'o'
		jmp	procParseInput_player2End
	procParseInput_player2_22:
		cmp	byte [board22], 32
		jnz	procParseInput_end
		mov	byte [board22], 'o'
		jmp	procParseInput_player2End

	procParseInput_player1End:
		mov	byte [playerNum], 2
		inc	byte [turnCount]
		ret

	procParseInput_player2End:
		mov	byte [playerNum], 1
		inc	byte [turnCount]
		ret

	procParseInput_end:
		ret

	procParseInput_exit:
		mov	ax, 4c00h
		int	21h

procCheckBoard:

	; check if player 1 wins

	cmp	byte [board00], 'x'
	jz	procCheckBoard_x_00
	jmp	procCheckBoard_x_00_fail

	procCheckBoard_x_00:
		cmp	byte [board01], 'x'
		jz	procCheckBoard_x_00_01
		procCheckBoard_x_00_01_fallback:
		cmp	byte [board10], 'x'
		jz	procCheckBoard_x_00_10
		procCheckBoard_x_00_10_fallback:
		cmp	byte [board11], 'x'
		jz	procCheckBoard_x_00_11
		jmp	procCheckBoard_x_00_fail

	procCheckBoard_x_00_01:
		cmp	byte [board02], 'x'
		jz	procCheckBoard_x_won
		jmp	procCheckBoard_x_00_01_fallback

	procCheckBoard_x_00_10:
		cmp	byte [board20], 'x'
		jz	procCheckBoard_x_won
		jmp	procCheckBoard_x_00_10_fallback

	procCheckBoard_x_00_11:
		cmp	byte [board22], 'x'
		jz	procCheckBoard_x_won
		jmp	procCheckBoard_x_00_fail

	procCheckBoard_x_00_fail:

	cmp	byte [board01], 'x'
	jz	procCheckBoard_x_01
	jmp	procCheckBoard_x_01_fail

	procCheckBoard_x_01:
		cmp	byte [board11], 'x'
		jz	procCheckBoard_x_01_11
		jmp	procCheckBoard_x_01_fail

	procCheckBoard_x_01_11:
		cmp	byte [board21], 'x'
		jz	procCheckBoard_x_won
		jmp	procCheckBoard_x_01_fail

	procCheckBoard_x_01_fail:

	cmp	byte [board02], 'x'
	jz	procCheckBoard_x_02
	jmp	procCheckBoard_x_02_fail

	procCheckBoard_x_02:
		cmp	byte [board12], 'x'
		jz	procCheckBoard_x_02_12
		procCheckBoard_x_02_12_fallback:
		cmp	byte [board11], 'x'
		jz	procCheckBoard_x_02_11
		jmp	procCheckBoard_x_02_fail

	procCheckBoard_x_02_12:
		cmp	byte [board22], 'x'
		jz	procCheckBoard_x_won
		jmp	procCheckBoard_x_02_12_fallback

	procCheckBoard_x_02_11:
		cmp	byte [board20], 'x'
		jz	procCheckBoard_x_won
		jmp	procCheckBoard_x_02_fail

	procCheckBoard_x_02_fail:

	cmp	byte [board10], 'x'
	jz	procCheckBoard_x_10
	jmp	procCheckBoard_x_10_fail

	procCheckBoard_x_10:
		cmp	byte [board11], 'x'
		jz	procCheckBoard_x_10_11
		jmp	procCheckBoard_x_10_fail

	procCheckBoard_x_10_11:
		cmp	byte [board12], 'x'
		jz	procCheckBoard_x_won
		jmp	procCheckBoard_x_10_fail

	procCheckBoard_x_10_fail:

	cmp	byte [board20], 'x'
	jz	procCheckBoard_x_20
	jmp	procCheckBoard_x_20_fail

	procCheckBoard_x_20:
		cmp	byte [board21], 'x'
		jz	procCheckBoard_x_20_21
		jmp	procCheckBoard_x_20_fail

	procCheckBoard_x_20_21:
		cmp	byte [board22], 'x'
		jz	procCheckBoard_x_won
		jmp	procCheckBoard_x_20_fail

	procCheckBoard_x_20_fail:

	; check if player 2 wins

	cmp	byte [board00], 'o'
	jz	procCheckBoard_o_00
	jmp	procCheckBoard_o_00_fail

	procCheckBoard_o_00:
		cmp	byte [board01], 'o'
		jz	procCheckBoard_o_00_01
		procCheckBoard_o_00_01_fallback:
		cmp	byte [board10], 'o'
		jz	procCheckBoard_o_00_10
		procCheckBoard_o_00_10_fallback:
		cmp	byte [board11], 'o'
		jz	procCheckBoard_o_00_11
		jmp	procCheckBoard_o_00_fail

	procCheckBoard_o_00_01:
		cmp	byte [board02], 'o'
		jz	procCheckBoard_o_won
		jmp	procCheckBoard_o_00_01_fallback

	procCheckBoard_o_00_10:
		cmp	byte [board20], 'o'
		jz	procCheckBoard_o_won
		jmp	procCheckBoard_o_00_10_fallback

	procCheckBoard_o_00_11:
		cmp	byte [board22], 'o'
		jz	procCheckBoard_o_won
		jmp	procCheckBoard_o_00_fail

	procCheckBoard_o_00_fail:

	cmp	byte [board01], 'o'
	jz	procCheckBoard_o_01
	jmp	procCheckBoard_o_01_fail

	procCheckBoard_o_01:
		cmp	byte [board11], 'o'
		jz	procCheckBoard_o_01_11
		jmp	procCheckBoard_o_01_fail

	procCheckBoard_o_01_11:
		cmp	byte [board21], 'o'
		jz	procCheckBoard_o_won
		jmp	procCheckBoard_o_01_fail

	procCheckBoard_o_01_fail:

	cmp	byte [board02], 'o'
	jz	procCheckBoard_o_02
	jmp	procCheckBoard_o_02_fail

	procCheckBoard_o_02:
		cmp	byte [board12], 'o'
		jz	procCheckBoard_o_02_12
		procCheckBoard_o_02_12_fallback:
		cmp	byte [board11], 'o'
		jz	procCheckBoard_o_02_11
		jmp	procCheckBoard_o_02_fail

	procCheckBoard_o_02_12:
		cmp	byte [board22], 'o'
		jz	procCheckBoard_o_won
		jmp	procCheckBoard_o_02_12_fallback

	procCheckBoard_o_02_11:
		cmp	byte [board20], 'o'
		jz	procCheckBoard_o_won
		jmp	procCheckBoard_o_02_fail

	procCheckBoard_o_02_fail:

	cmp	byte [board10], 'o'
	jz	procCheckBoard_o_10
	jmp	procCheckBoard_o_10_fail

	procCheckBoard_o_10:
		cmp	byte [board11], 'o'
		jz	procCheckBoard_o_10_11
		jmp	procCheckBoard_o_10_fail

	procCheckBoard_o_10_11:
		cmp	byte [board12], 'o'
		jz	procCheckBoard_o_won
		jmp	procCheckBoard_o_10_fail

	procCheckBoard_o_10_fail:

	cmp	byte [board20], 'o'
	jz	procCheckBoard_o_20
	jmp	procCheckBoard_o_20_fail

	procCheckBoard_o_20:
		cmp	byte [board21], 'o'
		jz	procCheckBoard_o_20_21
		jmp	procCheckBoard_o_20_fail

	procCheckBoard_o_20_21:
		cmp	byte [board22], 'o'
		jz	procCheckBoard_o_won
		jmp	procCheckBoard_o_20_fail

	procCheckBoard_o_20_fail:
	cmp	byte [turnCount], 9
	jz	procCheckBoard_draw
	ret

	procCheckBoard_x_won:
	mov	byte [playerWon], 1
	ret

	procCheckBoard_o_won:
	mov	byte [playerWon], 2
	ret

	procCheckBoard_draw:
	mov	byte [playerWon], 3
	ret

start:
	; did anyone win?
	cmp	byte [playerWon], 0
	jnz	won

	; draw header and top margin
	mov	word [drawCount], 80*4
	mov	byte [drawChar], 32
	call	procDrawChar
	call	procPrintStringPlayerTurn
	mov	word [drawCount], 80*4
	mov	byte [drawChar], 32
	call	procDrawChar

	; draw 1st line
	call	procDrawMarginLeft
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawMarginRight

	; draw 2nd line
	call	procDrawMarginLeft
	mov	cl, [board00]
	mov	[curBoardCell], cl
	call	procDrawCell
	call	procDrawCellVerticalBorder
	mov	cl, [board01]
	mov	[curBoardCell], cl
	call	procDrawCell
	call	procDrawCellVerticalBorder
	mov	cl, [board02]
	mov	[curBoardCell], cl
	call	procDrawCell
	call	procDrawMarginRight

	; draw 3rd line
	call	procDrawMarginLeft
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawMarginRight

	; draw 4th line
	call	procDrawMarginLeft
	call	procDrawCellHorizontalBorder
	call	procDrawMarginRight

	; draw 5th line
	call	procDrawMarginLeft
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawMarginRight

	; draw 6th line
	call	procDrawMarginLeft
	mov	cl, [board10]
	mov	[curBoardCell], cl
	call	procDrawCell
	call	procDrawCellVerticalBorder
	mov	cl, [board11]
	mov	[curBoardCell], cl
	call	procDrawCell
	call	procDrawCellVerticalBorder
	mov	cl, [board12]
	mov	[curBoardCell], cl
	call	procDrawCell
	call	procDrawMarginRight

	; draw 7th line
	call	procDrawMarginLeft
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawMarginRight

	; draw 8th line
	call	procDrawMarginLeft
	call	procDrawCellHorizontalBorder
	call	procDrawMarginRight

	; draw 9th line
	call	procDrawMarginLeft
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawMarginRight

	; draw 10th line
	call	procDrawMarginLeft
	mov	cl, [board20]
	mov	[curBoardCell], cl
	call	procDrawCell
	call	procDrawCellVerticalBorder
	mov	cl, [board21]
	mov	[curBoardCell], cl
	call	procDrawCell
	call	procDrawCellVerticalBorder
	mov	cl, [board22]
	mov	[curBoardCell], cl
	call	procDrawCell
	call	procDrawMarginRight

	; draw 11th line
	call	procDrawMarginLeft
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawCellVerticalBorder
	call	procDrawCellEmpty
	call	procDrawMarginRight

	; draw bottom margin
	mov	word [drawCount], 80*4
	mov	byte [drawChar], 32
	call	procDrawChar

	; wait for input
	mov	ax, 080ch
	int	21h

	call	procParseInput
	call	procCheckBoard

	jmp	start

won:
	; draw header and top margin
	mov	word [drawCount], 80*11
	mov	byte [drawChar], 32
	call	procDrawChar

	; inc player's stats
	cmp	byte [playerWon], 3
	jz	won_after_players
	cmp	byte [playerWon], 2
	jz	won_player2

	won_player1:
		inc	byte [player1WonCount]
		mov	byte [playerNum], 1
		jmp	won_after_players

	won_player2:
		inc	byte [player2WonCount]
		mov	byte [playerNum], 2

	won_after_players:

	cmp	byte [playerWon], 3
	jz	won_draw
	call	procPrintStringPlayerTurn
	call	procPrintStringWon
	jmp	won_after_draw

	won_draw:
		call	procPrintStringDraw
	won_after_draw:

	mov	word [drawCount], 80*11
	mov	byte [drawChar], 32
	call	procDrawChar

	; wait for input
	mov	ax, 080ch
	int	21h

	; reset game
	mov	byte [turnCount], 0
	mov	byte [playerWon], 0
	mov	byte [board00], 32
	mov	byte [board01], 32
	mov	byte [board02], 32
	mov	byte [board10], 32
	mov	byte [board11], 32
	mov	byte [board12], 32
	mov	byte [board20], 32
	mov	byte [board21], 32
	mov	byte [board22], 32

	; change player
	cmp	byte [playerStarts], 2
	jz	changePlayerDec
	jnz	changePlayerInc

	changePlayerDec:
		dec	byte [playerStarts]
		jmp	afterPlayerChanges
	changePlayerInc:
		inc	byte [playerStarts]
	afterPlayerChanges:

	mov	cl, [playerStarts]
	mov	[playerNum], cl

	; restart
	jmp	start

