# Agent contributions and file handoff

For the November 3 rewind, KQ1 and Library recovery state, read the
[dated recovery handoff](agent-handoffs/2026-11-03-rewind-library-recovery.md).
It supersedes the older snapshots only for the facts explicitly rechecked there.

A completed contribution returns a verified draft GitLab MR URL to its originating
chat, plus the exact source branch/head, target/base, tests, limitations and file
links. Use one publisher per origin/ref. An origin is a stable chat/task ID, not a
model name or a new ID on every retry. Existing stacked MRs keep their target.
Do not merge, approve, force-push, retarget, install credentials or trigger agents
as a side effect of submitting work.

## Local agent with Git and API access

1. Read the current `AGENTS.md`, inspect branch/status and identify the intended
   stack parent. Work in an isolated worktree on a unique branch. Commit only
   inspected authored source. Review the full diff and run relevant tests.
2. Push that branch through the existing authorized GitLab remote, fast-forward
   only. For a new branch use an empty lease so a concurrent creator cannot be
   overwritten: `git push --force-with-lease=refs/heads/<branch>: gitlab HEAD:refs/heads/<branch>`.
   This is creation-only, not permission to replace a branch. On retries read
   the remote head first; an exact match needs no push. If it differs, stop and
   reconcile ownership/history before any ordinary fast-forward update. Never
   use a force update or silently switch to GitHub.
3. Prepare the following JSON outside the checkout. Replace every example value
   with actual evidence. `base` is the selected target's exact current head;
   `head` is the already-pushed authored commit. `tests` and `limitations` are
   explicitly reported evidence, not qualifications inferred by the helper.

```json
{
  "schema": 1,
  "project_id": 88349936,
  "origin": "chat:<stable-chat-id>/task:<stable-task-id>",
  "source_branch": "agent/<unique-task>",
  "target_branch": "main",
  "head": "<40-lowercase-hex-source-head>",
  "base": "<40-lowercase-hex-target-head>",
  "title": "Describe the concrete contribution",
  "summary": "Problem and resulting behavior, with scope and attribution.",
  "tests": ["local: <command> @ <exact-head>: <result>"],
  "limitations": ["Hosted CI unverified; no merge requested."],
  "attachments": [
    {"path": "report.md", "sha256": "<64-hex-sha256>", "reviewed": true}
  ]
}
```

Reports resolve relative to the manifest. Inspect their entire content before
setting `reviewed: true`; hash with `shasum -a 256 report.md`. The allowlist is
UTF-8 `.md`, `.txt`, `.json`, `.csv`, at most 128 KiB each and eight reports.
The secret/payload heuristic is only defense in depth. Never upload game files,
assets, saves, emulator/native states, byte-containing FDBs, encoded original
bytes, credentials, private logs, or archives. Author a compact sanitized report.
Authored code belongs in a source commit; a report attachment is a separate
GitLab Markdown upload referenced by an MR note. Do not commit reports merely
to disguise missing upload capability.

```sh
python3 scripts/gitlab_handoff.py --manifest /private/work/handoff.json
python3 scripts/gitlab_handoff.py --manifest /private/work/handoff.json \
  --receipt /private/work/handoff-receipt.json --publish
```

The first command is offline and writes nothing. The second uses existing
`glab` API access for this fixed private project. It never commits or pushes.
It reads back the branch and MR, uploads report bytes, downloads and compares
SHA-256, then reads back the note before returning verified URLs. Existing MRs
must match the stable identity marker, exact head, target, project and draft
state. Closed/merged MRs and identity mismatches require reconciliation, not
another MR. It appends dedicated report notes and never edits descriptions.
If the target advanced, revalidate the intended stack, update the manifest base
and use a new receipt path; never change an existing target to make it pass.

Receipts must be retained outside the checkout, reused on retry, and relayed to
the originating chat. `preview`, `blocked`, `partial` and `verified` are distinct.
Exit 2 prints the reason and any known MR URL. Durable `pending` records reserve
mutations before requests. A failed request may have executed: do not delete the
receipt or blindly retry an upload. MR/note timeouts recover through remote
identity markers; an upload timeout without a returned path needs a publisher
or project maintainer to inspect project uploads before clearing its pending
reservation. Confirm a known non-execution or reconcile the actual upload path
and hash. Keep the original receipt as evidence. No automatic request retries.
Separate clones must explicitly coordinate one publisher; local file locking
cannot provide a distributed lock or exactly-once delivery across two machines.

## Chat agents and connector-only agents

Determine capabilities first; an authenticated website, Git transport and a
connector are different access paths. Do not claim a chat can push without a
working source-write tool. A connector may create authored commits/branches and
draft MRs even when local CLI API access fails.

With the GitLab connector, read the project, branch heads and all pages of MRs
filtered by source branch. Reuse and validate the existing origin/ref marker
using the same contract above. For a new contribution, create a unique branch
from the exact approved stack/base and commit only authored source with explicit
file actions. Use file-level optimistic commit IDs for updates; never force an
existing branch. Read back the commit and changed files before creating a draft
MR. Preserve the `fdisbull-handoff` marker generated by the offline preview.
Read back the MR and source head before returning its URL.

The current connector exposes upload download, but **no upload creation tool**.
Do not fabricate an attachment URL or put a report in source just to get a link.
Use an already-authenticated GitLab browser's normal file attachment control,
or give the inspected report and manifest to an authorized publishing agent with
working upload access. Add the SHA-256/head to the dedicated report note and
verify the uploaded bytes through the authenticated download API or connector.
Report `partial: attachment pending` until upload and note readback succeed.
The local helper can later recognize notes using its exact report marker and
link format; use the offline preview's key and current head/report hash.

Without source-write access, export an authored-only patch (or individual source
files), sanitized reports, hashes and the manifest to the originating chat's
supported file attachment surface. Include project, origin, intended source ref,
target/base, prepared head if one exists, touched paths, tests and limitations.
If the chat has no checkout, say `head: unprepared` in its handoff narrative;
never invent a commit. A publishing agent inspects/imports into a new isolated
branch, records the actual new head, verifies tests, then prepares a valid
manifest and submits. The pending handoff is not a filed MR. Do not export a
whole working directory or indiscriminately attach a Git bundle containing
private inputs or unrelated history.

Return this receipt shape to the originating chat (and attach the MR to the task
when the host supports it):

```text
Status: verified | partial | blocked
MR: <read-back URL, or none>
Origin: <stable ID>
Source/head: <branch> @ <exact SHA, or unprepared>
Target/base: <branch> @ <exact SHA>
Files: <verified attachment URLs + SHA-256, or pending reason>
Tests: <commands, exact revision, results; local vs hosted>
Limitations/blockers: <what remains, whether denied/pending/uncertain>
```

## Optional GitLab-triggered Codex tasks

The generic handoff above does not need an embedded model or webhook. As checked
on 2026-11-01, the existing saved fDisBull Cloud environment is GitHub-backed;
do not repoint it silently. A **new** GitLab project environment can support
manual `@codex review` and coding requests. During environment creation,
“Enable Codex activity from GitLab” installs a persistent project webhook for MR,
comment and issue events. New OAuth grants, service credentials and that webhook
need specific action-time approval. Propose the exact private project, access
scope and environment first. Keep automatic reviews on MR open/every push and
polling disabled. Group-wide activation is outside this workflow.

Source: [OpenAI GitLab integration](https://learn.chatgpt.com/docs/third-party/gitlab).
Upload contract: [GitLab Markdown uploads API](https://docs.gitlab.com/api/project_markdown_uploads/).

Known host state at implementation: GitLab connector and repository-scoped Git
fetch/push work; ordinary `glab` reports incomplete OAuth configuration, and
reusing the current Git credential in memory returns API HTTP 401. No tokens
were created or saved. CLI publishing therefore stays blocked until existing
API authentication is repaired through the normal approved flow. Connector MR
creation and an authenticated browser upload remain independent supported paths.
