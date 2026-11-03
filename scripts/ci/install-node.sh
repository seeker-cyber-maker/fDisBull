#!/usr/bin/env bash
# CI-container toolchain only; do not run this installer on a developer host.
set -euo pipefail
test "$(uname -s):$(uname -m)" = Linux:x86_64
node_version=v22.23.4
node_archive="node-$node_version-linux-x64.tar.xz"
node_sha256=1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce
mkdir -p .native/toolchains
curl --fail --location --retry 2 "https://nodejs.org/dist/$node_version/$node_archive" \
  --output ".native/toolchains/$node_archive"
echo "$node_sha256  .native/toolchains/$node_archive" | sha256sum --check
tar -xJf ".native/toolchains/$node_archive" -C .native/toolchains
install -m 755 ".native/toolchains/node-$node_version-linux-x64/bin/node" /usr/local/bin/node
test "$(node --version)" = "$node_version"
# The previous distro Node 18 failed these real browser-runtime prerequisites.
node --input-type=module -e 'if (!globalThis.crypto?.subtle || typeof WebAssembly.compile !== "function") throw Error("Required Web Crypto / WebAssembly APIs are unavailable"); console.log(JSON.stringify({node:process.version,web_crypto:true,webassembly:true}))'
