# Named DinoPark menu, quit and DOS-exit actions

The Z provider exposes the original office menu and terminal prompts as named
text actions. Start in the office; the existing `go office` route reaches it
from supported locations. The original engine owns every menu transition and
the program's termination.

| Context | Named Z command | Qualified result |
| --- | --- | --- |
| Office | `open game menu` or `open menu` | The original Main Menu is visible. |
| Game menu | `resume park` | The original menu thumb returns to the qualified office. |
| Game menu | `quit park` | The original quit confirmation is visible; the park is still active. |
| Quit confirmation | `cancel quit` | The original cancellation returns to a qualified menu or office. |
| Quit confirmation | `confirm quit` | The original save-first question appears, or the original title menu is reached directly. |
| Save-first question | `decline save` | The park is left without creating a new save; the title menu is matched. |
| Title menu | `exit dos` or `exit to dos` | The selected original DOS program terminates with kernel evidence. |
| Pending transition | `continue transition` | Original execution advances without another key or mouse-button input. |

The provider's current scene offers the applicable actions. Ordinary routes,
purchases and financial actions are hidden while a terminal prompt is open.
Fresh context tokens apply to every action, including cancellation and waits.
Use the existing native `save park` action before starting the quit sequence
when the park needs to be preserved. The save-first scene currently qualifies
the explicit decline path; other original menu controls retain partial coverage.

One sequence leaving the current park is:

```text
open game menu
quit park
confirm quit
decline save
```

If Z offers a transition context, issue `continue transition` until its
qualified destination appears. At the title menu, issue `exit to dos` and
continue any offered transition. Each original input is sent once. A cancelled
quit can be followed by a new quit intent after the cancellation is verified.

## Scene descriptions

- **Game menu:** A menu covers the office. Music and sound controls sit beside
  Load Game, Save Game and Quit Game. Resume your park or request to quit.
- **Quit confirmation:** The original game asks whether you are sure you want
  to quit this park. Confirm to reach its save question, or cancel to keep playing.
- **Save before quitting:** The original game asks whether to save first.
  Declining leaves this park without making a new save and returns to the title
  menu. Native saving remains available before requesting quit.
- **DinoPark title menu:** The park has been left. New Game, Old Game and Exit
  to DOS stand against the animated park backdrop. Exit to DOS terminates the
  original program.
- **Terminal transition:** The last original input has been sent. The destination
  is still settling. Continue this transition without repeating that input.
- **DOS — DinoPark exited:** DinoPark has terminated. The original DOS kernel
  confirmed this program's exit. There are no further game actions in this session.

## Control and evidence contract

The source binding checks the qualified original executable. Sparse text
anchors qualify the menu, prompt and title variants from stored native frames;
foreground quit/save prompts take precedence over menu text behind them.
Unrelated save/load dialogs and conflicting prompts cannot authorize a click.
Pointer preparation advances the original engine, then checks the source
context again before queuing one button press. Resume uses the same original
thumb control as the existing native-save handler.

A known prompt or an unsettled transition returns `accepted` with partial
effects. Only a matched title menu confirms park departure. Each invocation
waits for at most four requested guest seconds and shares a twenty-second
budget with all later continuations of that transition. Reaching the budget or
an unexpected stop leaves the outcome unknown and blocks further action input.
A continuation never renews that budget or resends its triggering input.

DOS completion requires the advertised `lifecycle.dos_guest_exit` capability,
the selected PSP independently bound from entry registers/load mapping,
nonresident exit, requested code zero and `DOS_Terminate` evidence after
process cleanup. Black frames, elapsed time and worker cleanup cannot supply
that certificate. After termination, `look` uses retained exit state and makes
no native frame, register or park-memory request.

Delivery uses the [retained-reply protocol](Z_REPLY_RECOVERY.md). Its delivery
hold remains independent of terminal transition state and action recovery.
On an unknown terminal action, the provider remains available for read-only
inspection and explicit recovery. Restoring an owned earlier live checkpoint
resets terminal projection state and requalifies the restored native park.
New live checkpoints require a qualified park scene; terminal prompts and the
exited context are outside that checkpoint-creation coverage.

The text actions are implemented in `dinopark_terminal.py` and connected to the
ordinary `ZService` action protocol. No investigator input or caller coordinates
are required. Recognition profiles and source helpers belong in the PR; the
original game, screenshots, native states and raw test evidence remain private.
