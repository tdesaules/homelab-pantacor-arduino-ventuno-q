#!/usr/bin/env bash
set -euo pipefail
root=$(git rev-parse --show-toplevel)
image=ghcr.io/siemens/kas/kas@sha256:22c70f90e21997c0b6743ad2d802cf1d942c28e974361c4733b8a026cb7ef809
mkdir -p "$root/artifacts/build" "$root/artifacts/downloads" "$root/artifacts/sstate-cache"
run_options=(--rm)
if [[ "${1:-}" == --detach ]]; then
    run_options=(--detach)
    shift
fi
exec podman run "${run_options[@]}" --name ventuno-kas --userns=keep-id:uid=30000,gid=30000 \
    --security-opt label=disable \
    -v "$root:/work" -w /work \
    -e KAS_WORK_DIR=/work -e KAS_BUILD_DIR=/work/artifacts/build \
    "$image" build /work/kas/ventuno-initramfs.yml "$@"
