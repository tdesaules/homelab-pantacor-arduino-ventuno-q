#!/usr/bin/env bash
# Lab-only bounded raw NVMe write test, restoring original bytes afterward.
# Requires explicit opt-in, an unpartitioned disk without recognized signatures.
set -euo pipefail
test "$(id -u)" -eq 0
echo '### Existing Docker engine and pinned local image'
docker version --format '{{.Server.Version}}'
image=$(docker image inspect ghcr.io/arduino/app-bricks/python-apps-base:0.11.0 --format '{{.Id}}')
docker image inspect "$image" --format '{{.Id}} {{.Architecture}} {{json .RepoDigests}}'
docker run --rm --pull=never --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --user 65532:65532 --memory 128m \
    --pids-limit 32 --entrypoint python3 "$image" -c \
    'import os,platform; assert os.getuid()==65532; assert platform.machine()=="aarch64"; print("PASS: ARM64 container, non-root, read-only, limited cgroups")'
echo '### Boot commands and watchdog devices'
grep -E '^[[:space:]]*(linux|initrd|devicetree)' /boot/grub/grub.cfg
ls -l /dev/watchdog* || true
echo '### NVMe write test'
test "${PV_ALLOW_NVME_SCRATCH:-}" = 'yes' || { echo 'SKIP: set PV_ALLOW_NVME_SCRATCH=yes explicitly'; exit 0; }
test "$(lsblk -nr -o NAME /dev/nvme0n1 | wc -l)" -eq 1
test -z "$(lsblk -nr -o MOUNTPOINTS /dev/nvme0n1 | tr -d '[:space:]')"
test -z "$(wipefs -n --noheadings /dev/nvme0n1)"
test "$(blockdev --getsize64 /dev/nvme0n1)" -gt 120000000000
test "$(blockdev --getsize64 /dev/nvme0n1)" -lt 130000000000
python3 - <<'PY'
import hashlib, os, pathlib, tempfile, time
model = pathlib.Path('/sys/class/nvme/nvme0/model').read_text().strip()
assert model == 'NE-128 2242', model
offset, size = 1024**3, 64 * 1024**2
fd, name = tempfile.mkstemp(prefix='pv-nvme-original-', dir='/var/tmp')
backup = pathlib.Path(name)
print('Original-byte backup:', name, flush=True)
with open('/dev/nvme0n1', 'r+b', buffering=0) as disk:
    disk.seek(offset)
    original = disk.read(size)
    assert len(original) == size
    with os.fdopen(fd, 'wb') as f:
        f.write(original)
        f.flush()
        os.fsync(f.fileno())
    try:
        data = os.urandom(size)
        start = time.monotonic()
        disk.seek(offset)
        assert disk.write(data) == size
        os.fsync(disk.fileno())
        os.posix_fadvise(disk.fileno(), offset, size, os.POSIX_FADV_DONTNEED)
        disk.seek(offset)
        assert hashlib.sha256(disk.read(size)).digest() == hashlib.sha256(data).digest()
        print('PASS: NVMe 64 MiB write/fsync/read/checksum;', round(time.monotonic()-start, 2), 's')
    finally:
        disk.seek(offset)
        assert disk.write(original) == size
        os.fsync(disk.fileno())
        os.posix_fadvise(disk.fileno(), offset, size, os.POSIX_FADV_DONTNEED)
        disk.seek(offset)
        assert disk.read(size) == original, 'Restoration failed; retain backup: ' + name
        backup.unlink()
        print('PASS: original NVMe bytes restored and verified')
PY
