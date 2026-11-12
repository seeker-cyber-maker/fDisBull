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
