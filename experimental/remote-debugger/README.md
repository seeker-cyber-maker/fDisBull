# IDA-style remote endpoints

This is the evidence area for the unreleased implementation described in
[the endpoint guide](../../docs/IDA_REMOTE.md). Production Python and guest C
sources live under `src/fdisbull`; the external IDA server is user supplied.

`evidence/2026-10-25/` contains selected real-session screenshots, traces and test
reports. It contains no vendor executable, game file, database, saved state or
boot image. The private failed development attempts and input runtimes remain
outside this evidence directory. The successful native PE gate separately
checks page-based execution stops, memory/register edits, a bounded trace, real
mouse input, RAM layers, a timeout, original/child isolation and offline exports.

The DinoPark replay is
[`examples/dinopark/verify_remote_endpoint.py`](../../examples/dinopark/verify_remote_endpoint.py).
It copies user-supplied inputs into a new private output directory and verifies
that the original inputs are unchanged. The bank image is an actual 320x200 game
frame, with an optional 8px coordinate overlay derived from that frame.

See [verification and limits](../../docs/IDA_REMOTE_VERIFICATION.md) for the
accepted gates and the Windows hardware-watch limitation. These receipts are
not GitHub CI, release approval or proof of complete IDA GUI interoperability.

The next local milestone is [shared DOS/Windows machine control](../../docs/UNIFIED_DEBUGGER.md).
Its fresh receipts are under `evidence/2026-10-25-unified/`: DOSBox inside
Linux/QEMU, real DinoPark replay, the shared outer-machine context, BIOS boot
breakpoints and traces, and regression gates for both Windows backends.
Earlier evidence directories are retained unchanged.
