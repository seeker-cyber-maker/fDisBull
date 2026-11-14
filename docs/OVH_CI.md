# OVH ordinary and native Linux CI

The dedicated Canadian OVH Docker runner uses both fdisbull-local-linux and
fdisbull-ovh-ca tags. Routine pushes, merge requests and tags do not start
pipelines. Start an API/web pipeline on one frozen commit, then play the
blocking native gate after ordinary acceptance. Run one job at a time.

The runner has one concurrent job. Build/helper containers have three CPUs
and 6 GiB memory; the sole allowed Docker-in-Docker service has one CPU and
2 GiB memory. Build containers remain unprivileged. Only the declared Docker
service may be privileged; no host Docker socket is mounted. The service uses
VFS so nested overlay support is not assumed. Compiler steps use two processes.
Actual container limits and n8n/website health need readback during qualification.

The unified Wine/QEMU job allows three hours on this TCG worker. Its script
budget is two hours forty minutes, followed by up to ten minutes for the
independent host export and ten minutes for artifact upload/cleanup. The
runner maximum must admit the full three-hour job. A script timeout remains
a failed qualification; reserved export time preserves its diagnostics.

Each job admits its next allocation while preserving 20 GB. Estimates are
ordinary 12 GB, stable 14 GB, layers 18 GB, unified 35 GB and control/summary
500 MB. Admission is not a running quota and never authorizes deletion.

All jobs share one resource group. Never-expiring GitLab job artifacts and a
private independent host copy preserve results. Host exports live at
/var/lib/fdisbull-ci/results/PIPELINE/JOB/ and contain a tracked-source postcheck
and closed, rehashed inventory. The final job verifies the four required exports
before validating source, pipeline, tests and packages. Failed/partial exports
remain available and cannot count as successful qualification.

This graph qualifies ordinary/native core with the existing explicit
--legacy-dos-only summary status. This includes selected PE/DOS/boot acceptance;
it does not qualify the optional complete chat offline consumer. That delivery
gate remains separate and must not be described as passed by a green core run.

Record exact commit, pipeline/runner/job identities and service health before
and after. Preserve failure evidence. Do not release, tag, install system-wide,
start Windows CI, or stop this VPS after CI: it also serves n8n and websites.

## Offline qualification health gate

A finite offline qualification controller can call
`scripts/ci/offline-qualification.py --receipt /existing/run/health-stage.json`
before or during a stage. The parent directory must already exist and each
capture needs a new receipt path. The gate verifies the adopted helper SHA-256,
executes its CLI with a 55-second outer timeout, and syncs the complete sanitized
record to the caller's bounded receipt before returning a decision. Exit zero
means the helper returned `healthy: true` and `receipt.durable: true` and the
caller receipt was synced; every other outcome fails closed. Existing receipts
are never replaced. Error receipts contain a bounded reason rather than raw
process output or exception text. A receipt-write failure cannot itself produce
a durable receipt and must stop the controller.

For Python controllers, load the module and call `capture_health(receipt_path)`;
its result has `continue` and `reason` fields. Production callers use the
pinned default helper and digest. The native helper owns the snapshot (120 s),
component sample (660 s), source freshness, and 20.1 GB disk predicates; this
caller does not recalculate or relax them. Homepage-only confirmation after five
seconds, where required, is a separate explicit controller policy, not an
automatic retry by this gate. This interface starts no watcher or scheduler.
