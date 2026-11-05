# v0.29 runtime download status: D001

This is an incremental inventory/access checkpoint, not new game analysis.
Parent: **SYNDICATE-F001-20261101**. Keep the full F001 archive and its manifest.
No original payload from F001 changed; this delta adds this note and one audit.

## Received and checked

| Input | Result |
| --- | --- |
| Linux dependency archive | Present. SHA-256 matches the publisher record: `e45801015b0d8e0dc7a6396997e01bd2b5c7dc01bfec0cf18f692fa83ac48ce6`. |
| Core source distribution | Present. SHA-256 matches the publisher record: `c839319fd153d9c2f6933afd9662a0c837889d2dc9a2fb80310e2c51d0ae65e8`. |
| Tool source ZIP | Present and complete ZIP CRC check passed. Its local SHA-256 is in the audit; no independently retrieved publisher hash is claimed for this ZIP. |

The source and dependency files are not the native offline kit. They are not
embedded again in this delta because they are separate supplied installation
inputs, not additions to the authored research handoff. Retain them separately.

## Still missing

Open the [release package group](https://gitlab.com/brewster-jennings-group/fdisbull/-/packages/74791804)
and download **`fdisbull-0.29.0-linux-x86_64-offline.tar.gz`**.
Expected size: **103,013,282 bytes**. Expected SHA-256:

```text
b6f43aa6933c8e4e12b643f1dead105d96e5ac0a0bb6c9671032c31fffd97a3f
```

The archive is not present in the inspected workspace. Neither a downloaded
native backend nor a complete v0.29 installation is claimed.

## What was attempted

The authenticated GitLab connector again confirmed release `v0.29.0` at
`09a820952ad3f54d0d0707db0515a8010f7eceb1`. Browser tab discovery failed before
returning a tab ID, reporting that originating browser context was required.
That does not mean the user is logged out. The available connector download
action only accepts project Markdown uploads, not generic package registry
files. An unauthenticated HEAD attempt failed at DNS resolution; there was no
HTTP response or authenticated download. No secrets were accessed or requested.

## Applying this handoff

Verify the delta using F001's existing `tools/handoff_bundle.py verify-delta`
command and its original `MANIFEST.json`. The delta contains exactly two added
payload files, no modified files and no deletions. Review and copy `payload/`
into a working copy of the baseline, not the preserved original. The included
`RESULT_MANIFEST.json` describes the resulting full 325-file state and is the
parent manifest for any next delta. Omitted files are unchanged, not missing.

The archive does not automatically apply itself. No runtime execution, new
product tests, repository writes, main-branch audit or release changes occurred.
See [the exact receipt](../audit/release-download-attempt-2026-11-01.json).
