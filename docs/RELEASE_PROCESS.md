# Release process

This is the operational entry point for releases. The current intended release is
**0.35.0**. Its integration and unattended qualification remain unfinished as of
2026-11-14; this document is a required process, not a completion certificate.
[Release status](RELEASE_STATUS.md) records dated outcomes and historical releases.

## Authority and ownership

Original GitHub `seeker-cyber-maker/fDisBull` is the source, review and publication
authority. The local bare hub and GitLab preserve recovery copies. The separate
`TiGa-RCE/fdisbull` import is preserved provenance, not a competing release line.
Working checkouts and installed prefixes are not release authorities.

Drive Space owns the current source inventory and integration handoff. n8n owns
the automated qualification, packaging and publication sequence. A reviewer owns
only a concrete, bounded review. Reviewers return their result and end the turn;
they do not wait indefinitely for another chat. The retired Release chat is not
part of this process. See [CI coordination](CI_COORDINATION.md).

## One release identity and one record

A version string alone never identifies executable behavior. Every candidate and
installation must identify its full source commit, package digest, build identity,
platform and separately prepared backend identities. Report schema and bundled
skill identities from that package, not from whichever checkout happens to be
the shell's working directory. Development changes sharing a version string must
remain identifiable as distinct candidates; published version/tag/assets are
immutable.

n8n maintains one current release record in its existing control state. Link that
record from the current release-status entry; do not create competing chat-owned
status ledgers. Reuse the existing build/package manifests and receipts. The
record indexes, rather than copies, the evidence for:

- Intended version, primary repository, integration ref and full source SHA.
- Contribution disposition: integrated, equivalent/already included, or preserved
  with a specific unresolved integration issue; include dirty-work provenance.
- Workflow/control and backend identities, required platform/profile coverage,
  run IDs, attempt, stage, last substantive progress, deadline and next action.
- Exact artifact names, sizes and digests, build manifest and consumer receipts.
- Publication/tag identity, actual download verification and local installation
  selector/identity checks, each with its own outcome.
- Original failures, bounded recovery actions and any manual intervention.

Missing evidence remains missing. A nested `passed: true`, an empty command list,
zero executed required-native cases, or a tag's existence cannot establish release
qualification. Historical records stay intact and visibly historical.

## Ordered delivery

| Stage | Owner | Required outcome |
| --- | --- | --- |
| Preserve and integrate | Drive Space | Account for unique committed and dirty source across repositories/worktrees, preserve eligible work on primary GitHub, resolve integration conflicts and retain provenance. Do not publish private target bytes or sweep another agent's live edits. Mirrored refs alone do not establish integration. |
| Freeze candidate | Drive Space → n8n | Hand off a clean primary-GitHub commit with version 0.35.0, contribution disposition and explicit required coverage. Publish finished CI changes into that candidate first. No unresolved contribution is silently omitted. |
| Qualify | n8n | Run ordinary and required-native Linux acceptance on the exact candidate. Required backends must execute. Separately identify workflow-control code and reused native binaries; do not attribute another commit's result to the candidate. |
| Package | n8n | Produce the complete offline delivery and manifests from the qualified candidate. Verify private-input exclusions, package identity, bundled documentation and skills. Do not silently rebuild different bytes during publication. |
| Consume | n8n | Install/use those exact artifacts in a fresh disconnected consumer. Required DOS/Windows profiles and inputs must actually execute, including PE32/Win16 where declared for this release. Run a compact real target journey through the packaged CLI and check its resulting analysis and identity. |
| Publish and read back | n8n | Create the new immutable tag/release only after qualification; upload the qualified artifacts, download them from their intended delivery endpoints and verify their digests and manifest. Reconcile uncertain responses before repeating publication actions. |
| Install and verify | n8n coordinates supported host installer | Install a fresh shared prefix, validate its payload and capabilities, activate the selector, then run `scripts/check_local_install.py --version 0.35.0 --commit FULL_SHA`. Verify ordinary command resolution selects that same installation. Preserve the prior prefix for rollback. |
| Close | n8n | Retain the full chain from integrated source to downloaded release and active installation, deliver the terminal notification, and verify owned-worker cleanup and executor release. Report explicit failed or incomplete stages. |

Code, version or dependency changes after freeze create a new candidate and
invalidate affected acceptance. A receipt-parser correction may revalidate an
unchanged retained export, with the correction and assisted closure recorded.
It does not retroactively turn an interrupted run into unattended success.

## Runtime and documentation consistency

The supported command wrappers must resolve the same shared selector. Inspect
actual executable, module and environment paths; a checkout's `.venv` must not
silently import another checkout. Preserve dirty work before correcting stale
workspaces. Do not reset, delete or advance every checkout to make them look alike.

Current capability documentation and bundled skills must describe the frozen
package. Mark old release notes and architecture snapshots as historical; do not
change their version headings to imply they were requalified. Fix contradictory
current provider instructions. The status entry must distinguish source, tagged,
published, downloadable, consumed and locally active states.

## Unattended acceptance and bounded failure

After the frozen candidate is admitted to the existing n8n path, the successful
proof must reach delivery and verification without a chat shepherd, manual stage
launches, mid-run source patches or storage-reserve approvals. Existing finite
workers and durable state own waiting and continuation. Reuse current services;
do not add watcher layers or duplicate provider polling.

Known repairable failures receive bounded repairs and verified canonical reruns.
Unknown failures produce an explicit attention outcome through the existing
deduplicated notification route. Preserve uncertain action intents; never replay
a mutation merely because observation failed. Stage timeouts must not leave an
idle holder retaining the executor after all owned work has been reconciled.

Fixed disk-reserve gates are removed under the user's 2026-11-14 policy. Ordinary
allocation needs no confirmation. Keep actual mounted-destination validation,
normal I/O error reporting and preservation of unique work.

The 0.35.0 process is resolved only when the integrated release has completed this
chain unattended. Component tests, a mirror-sync result, an operator-assisted
closure and an induced recovery rehearsal remain useful but separate evidence.
