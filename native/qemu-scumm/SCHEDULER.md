# Early SCUMM script-slot scheduler model

Portable C scheduling component for the early SCUMM integration. It is **not yet wired into QEMU CPUArchState or the native interpreter**, and does not claim full SCUMM script semantics.

Provides bounded script slots, explicit global/room/object ownership, first-free slot allocation, immediate execution callback on \`start\`, ascending slot-order cycle callbacks, yield/wake, return/stop, chain, bounded nested-call context push/pop, and room teardown that stops room/object-owned slots while preserving global slots. Each callback receives an instruction budget; it is responsible for executing the actual script interpreter and returning CONTINUE, YIELD, RETURN or FAULT. Nested calls save/restore script ID, PC and locals, but not game-specific interpreter internals or resource state.

Slot capacity is caller-configured up to 64; this is a safety bound, not a claim about every original game's exact slot count. Local variable capacity is bounded to 32. Event journal overflow drops new events and increments a loss counter. Room scope requires the slot's room ID to match the current room at start. Object scope is removed with its owning room in this first model.

Compile and test:

\`\`\`sh
cc -std=c11 -Wall -Wextra -Werror -pedantic -O2 scheduler.c test_scheduler.c -o test_scheduler
./test_scheduler
cc -std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -fno-omit-frame-pointer -g scheduler.c test_scheduler.c -o test_scheduler_san
./test_scheduler_san
\`\`\`

Before native integration, compare exact v2 scheduling rules against the selected game/reference: slot allocation, slot reuse, priority/ascending order, nested runScript behavior, delay and actor waits, stop/chain semantics, room/global ownership and error unwinding. This model is a foundation and test oracle, not a qualified emulator scheduler.
