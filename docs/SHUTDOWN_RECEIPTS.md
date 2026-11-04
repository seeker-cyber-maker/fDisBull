# DOS shutdown receipts

The native DOS backend also contains the observed corrupt-MCB cleanup exception while preserving an interrupted guest certificate. See [the first-write trace and original-game regression](VERIFICATION-TFTD-MCB-WRITER-2026-11-04.md). A clean host exit does not certify that the corrupted guest was repaired.

For inherited-pipe DOS sessions, successful shutdown now requires both a
completed native guest stop and a reaped host process with return code zero.
Process reaping alone is not successful guest shutdown.

## Python contract

`DebugSession.close()` returns a `fdisbull-shutdown-1` receipt on success. An
interrupted stop or abnormal process exit raises `DebuggerShutdownError`, a
`DebuggerError` subclass, with the retained receipt in `error.receipt`.
Existing lower-level cleanup exceptions retain their type and also carry that
receipt. A caller that previously ignored `close()`'s return cannot silently
continue after an interrupted stop.

```python
from fdisbull.dosbox_rpc import DebuggerShutdownError

try:
    receipt = debug.close()
except DebuggerShutdownError as error:
    receipt = error.receipt

assert receipt == debug.close_receipt
```

The receipt distinguishes:

| Field | Meaning |
| --- | --- |
| `closed` / `status` | A successful certificate (`true` / `closed`) or an interrupted outcome (`false` / `interrupted`). |
| `guest_stop` | Original native stop/wait observation, including an error or deadline result. |
| `guest_stop_complete` | Whether the native observation established an exited, non-running guest session. |
| `process_returncode` | Actual owned process return code, or unknown. Negative POSIX values indicate signal termination. |
| `termination_signal` | Positive signal number derived from a negative process return code, or null. |
| `process_reaped` | Whether process completion was observed; this is independent of guest-stop success. |
| `session_terminal` | The live session has relinquished ownership and may no longer send guest actions. |
| `cleanup_errors` | Phase/type/message records when host cleanup or receipt persistence fails. |
| `diagnostics` | Failure-only retained transport evidence, including process signals and a bounded native-log tail when available. |

`debug.closed` remains an internal terminal-ownership flag. It can be true
after an unsuccessful shutdown. Use the receipt to report the outcome.
Adapters must cache/forward that outcome rather than manufacture `closed: true`
from an ownership flag or a returned host cleanup call.

Repeated `close()` calls do not send another stop, recapture a log, or append
another close event. They return a copy of the successful cached certificate or
raise the cached interrupted outcome. The caller cannot mutate the retained
certificate by modifying a returned dictionary.

## JSON server and persistent evidence

`debug-stop` returns the actual DOS receipt:

```json
{"run":"RUN","closed":false,"status":"interrupted","process_reaped":true,"receipt":{"format":"fdisbull-shutdown-1","closed":false,"status":"interrupted"}}
```

The example abbreviates receipt fields. A successful JSON request does not
convert an interrupted native stop into success. Terminal ownership is removed
and the project is closed after the operation, including failure cases. A later
request must inspect retained evidence rather than replay the stop against a
new guest.

The canonical receipt is saved as the run's `close` debug event, and its
normalized state is reflected in `debug_runs`. The same observation can be read
after reopening the private project; such readback performs no native action.
Receipt-persistence failure remains explicit in the in-memory certificate.

Transport cleanup reads at most the final 8,192 bytes of `emulator.log` before
removing its temporary directory. Retained text is sanitized as UTF-8 and
bounded to 8,192 encoded bytes; the full log is not embedded. This private
diagnostic can retain a fatal exception message that used to disappear during
cleanup. It does not recreate earlier native memory or recover an absent log.

Project and server teardown attempt every owned session even when an earlier
cleanup fails, then surface the first failure. Context cleanup preserves an
existing body exception while retaining shutdown evidence. A failed native
stop does not authorize replay, restoration or a replacement guest.

## Verification and scope

See the [November 4 native trace and receipt verification](VERIFICATION-SHUTDOWN-RECEIPTS-2026-11-04.md)
for original TFTD and DinoPark cases, canonical readback, idempotence, process
exit/signal evidence and injected readback loss. The contract is for the DOS
`DebugSession` and its public `debug-stop` route; other runtime implementations
retain their separate qualification boundaries. No native C++ corruption fix
or system installation is implied.
