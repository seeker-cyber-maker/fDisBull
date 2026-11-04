#!/usr/bin/env bash
# Source only inside the dedicated local Linux VM used for unified acceptance.
# No host daemon/socket or host credentials are mounted into this VM.
test "${FDISBULL_EXECUTION_ORIGIN:-}" = local-linux
test "${FDISBULL_LOCAL_DOCKER:-}" = 1
test "$(uname -s)" = Linux
# Guest-native ext4 provides Linux socket, link, device and ownership semantics.
# Its backing disk is the admitted external Apple container store on CACHE.
mkdir -p /run/fdisbull-local-docker /var/lib/fdisbull-local-docker native-evidence/pe
export DOCKER_HOST=unix:///run/fdisbull-local-docker/docker.sock
dockerd --host "$DOCKER_HOST" --data-root /var/lib/fdisbull-local-docker \
  --exec-root /run/fdisbull-local-docker/exec --pidfile /run/fdisbull-local-docker/dockerd.pid \
  --storage-driver vfs --iptables=false --bridge=none --ip-forward=false \
  > native-evidence/pe/local-docker-daemon.log 2>&1 &
local_docker_pid=$!
stop_local_docker() {
  kill "$local_docker_pid" 2>/dev/null || true
  wait "$local_docker_pid" 2>/dev/null || true
}
trap stop_local_docker EXIT
local_docker_ready=0
for ((local_docker_poll=0; local_docker_poll<30; local_docker_poll++)); do
  if docker info > native-evidence/pe/docker-info.txt 2>&1; then
    local_docker_ready=1
    break
  fi
  kill -0 "$local_docker_pid" 2>/dev/null || break
  sleep 1
done
test "$local_docker_ready" = 1
# Bridge networking is disabled in the isolated VM. The trusted Dockerfile's
# dependency downloads use the VM's network, never the macOS host network.
export FDISBULL_LOCAL_DOCKER_BUILD_NETWORK=host
