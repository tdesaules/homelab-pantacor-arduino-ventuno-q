#!/usr/bin/env bash
# Offline maintenance: archive the original installation, add a revision, enable safe default.
set -euo pipefail
test "$(id -u)" -eq 0
python3 - "$@" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

upgrade_id = sys.argv[1]
assert re.fullmatch('[0-9a-f]{32}', upgrade_id)
stage = Path('/home/arduino/.cache/ventuno-runtime-upgrade-' + upgrade_id)
request = json.loads((stage / 'request.json').read_text())
assert request['upgrade_id'] == upgrade_id
install_id = request['install_id']
assert re.fullmatch('[0-9a-f]{32}', install_id)
revision = request['revision']
# Keep this standalone remote validator aligned with lab/revision_names.py.
assert re.fullmatch(r'locals/[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', revision)
root = Path('/boot/pantavisor')
store = root / 'pvstore.ext4'
assert (root / 'install-id').read_text().strip() == install_id
assert subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip() == '/dev/mmcblk0p71'
assert subprocess.check_output(['findmnt', '-n', '-o', 'UUID', '/'], text=True).strip() == request['root_uuid']
assert 'ventuno_install=' not in Path('/proc/cmdline').read_text()
assert not subprocess.check_output(['losetup', '-j', str(store)], text=True).strip()

def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
def run(*args): return subprocess.run(args, check=True)
def clean(path):
    header = subprocess.check_output(['dumpe2fs', '-h', str(path)], stderr=subprocess.DEVNULL, text=True)
    assert 'needs_recovery' not in header and 'orphan_present' not in header
    run('e2fsck', '-f', '-n', str(path))
def env(path):
    return dict(line.split('=', 1) for line in subprocess.check_output(['grub-editenv', str(path), 'list'], text=True).splitlines())

required = {'initramfs', 'build-inputs.json', 'grub-default.cfg', 'grub-entry.cfg'}
optional = {'k0s-root.squashfs', 'k0s_revision.py', 'core-root.squashfs', 'resource_policy.py'}
assert required <= set(request['files']) <= required | optional
for name, digest in request['files'].items():
    assert not (stage / name).is_symlink() and sha(stage / name) == digest
inputs = json.loads((stage / 'build-inputs.json').read_text())
assert inputs['autonomous_boot'] and (inputs.get('core_only') or inputs.get('k0s'))
if inputs.get('k0s'):
    assert inputs['cgroup_v2'] and request['files']['k0s-root.squashfs'] == inputs['k0s']['rootfs_sha256']
    if 'core-root.squashfs' in request['files']:
        assert request['files']['core-root.squashfs'] == inputs['core_image']['sha256']
assert sha(root / 'kernel') == inputs['bsp']['kernel_sha256']
assert not env(Path('/boot/grub/grubenv')).get('next_entry')
private = env(root / 'state/grubenv')
assert private['pv_rev'] in ('locals/core-only-040', 'locals/runtime-041', 'locals/k0s-050', 'locals/k0s-051', 'locals/core-tools-060') and not private.get('pv_try')
assert re.search(r'^GRUB_DEFAULT=0$', Path('/etc/default/grub').read_text(), re.M)
for name in ('grub-default.cfg', 'grub-entry.cfg'): run('grub-script-check', str(stage / name))
clean(store)
assert shutil.disk_usage(root).free > 2 * store.stat().st_size
base = Path('/var/lib/ventuno-autonomous') / install_id
record_path = base / 'installation.json'
record = json.loads(record_path.read_text())
assert store.stat().st_ino == record['store_inode'] and store.stat().st_size == record['store_size']
assert sha(root / 'initramfs') == record['files']['initramfs']
assert sha(Path('/boot/grub/grub.cfg')) == record['installed_grub_sha256']
default_snippet = Path('/etc/grub.d/09_ventuno_default')
if default_snippet.exists(): assert sha(default_snippet) == record['default_snippet_sha256']
backup = base / ('runtime-upgrade-' + upgrade_id)
backup.mkdir(mode=0o700)
backups = {'store.ext4': store, 'initramfs': root / 'initramfs', 'build-inputs.json': root / 'build-inputs.json',
           'private.grubenv': root / 'state/grubenv', 'boot-budget': root / 'state/boot-budget',
           'main.grubenv': Path('/boot/grub/grubenv'), 'grub.cfg': Path('/boot/grub/grub.cfg'),
           '41_ventuno_persistent': Path('/etc/grub.d/41_ventuno_persistent'), 'installation.json': record_path}
for name, source in backups.items(): shutil.copy2(source, backup / name)
if default_snippet.exists(): shutil.copy2(default_snippet, backup / default_snippet.name)
assert sha(backup / 'store.ext4') == sha(store)
run('sync')
if inputs.get('k0s'):
    # Create only a new namespace on the already provisioned disk. Never format.
    profile = inputs['app_storage']
    device = Path('/dev/disk/by-uuid') / profile['filesystem_uuid']
    assert device.resolve() == Path('/dev/nvme0n1p1')
    assert Path('/sys/class/nvme/nvme0/serial').read_text().strip() == profile['serial']
    assert subprocess.check_output(['blkid', '-s', 'PARTUUID', '-o', 'value', str(device)], text=True).strip() == profile['partition_uuid']
    assert not subprocess.check_output(['lsblk', '-n', '-o', 'MOUNTPOINTS', str(device)], text=True).strip()
    clean(device)
    app_mount = backup / 'app-mount'
    app_mount.mkdir()
    run('mount', '-o', 'nosuid,nodev', str(device), str(app_mount))
    try:
        assert (app_mount / '.ventuno-app-storage').read_text().strip() == 'ventuno-appdata-v1 ' + profile['filesystem_uuid']
        app = app_mount / 'perm/k0s'
        if app.exists():
            assert not app.is_symlink() and (app / '.ventuno-k0s').read_text() == 'ventuno-k0s-poc-v1\n'
            if request.get('archive_k0s'):
                archived = app_mount / 'perm' / ('k0s-before-' + upgrade_id)
                assert not archived.exists()
                app.rename(archived)
                (backup / 'archived-k0s.txt').write_text(str(archived.relative_to(app_mount)) + '\n')
        if not app.exists(): app.mkdir(mode=0o755)
        for name in ('data', 'workloads', 'access', 'log'):
            assert not (app / name).is_symlink()
            (app / name).mkdir(mode=0o755, exist_ok=True)
        (app / 'access').chmod(0o700)
        (app / '.ventuno-k0s').write_text('ventuno-k0s-poc-v1\n')
        run('sync')
    finally:
        run('umount', str(app_mount))
mountpoint = backup / 'store-mount'
mountpoint.mkdir()
run('mount', '-o', 'loop,nosuid,nodev,noexec', str(store), str(mountpoint))
try:
    old = mountpoint / 'trails' / private['pv_rev'] / '.pvr/json'
    state = json.loads(old.read_text())
    original_state = json.loads(old.read_text())
    platforms = {key for key in state if key.endswith('/run.json')}
    assert platforms in ({'bsp/run.json', 'core/run.json'}, {'bsp/run.json', 'core/run.json', 'k0s/run.json'})
    assert 'k0s/run.json' not in state or inputs.get('k0s')
    assert state['bsp/pantavisor'] == sha(root / 'initramfs')
    state['bsp/pantavisor'] = request['files']['initramfs']
    if inputs.get('k0s'):
        import importlib.util
        sys.path.insert(0, str(stage))
        spec = importlib.util.spec_from_file_location('k0s_revision', stage / 'k0s_revision.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        config = (mountpoint / 'objects' / state['core/lxc.container.conf']).read_bytes()
        builder = helper.replace_k0s if 'k0s/run.json' in state else helper.add_k0s
        state, added = builder(state, config, (stage / 'k0s-root.squashfs').read_bytes(), inputs['kernel_release'],
                               inputs['core_image'].get('memory_limit'),
                               inputs.get('resource_policy', {}).get('memory_total_kib'))
        if 'core-root.squashfs' in request['files']:
            state['core/root.squashfs'] = request['files']['core-root.squashfs']
            added[state['core/root.squashfs']] = (stage / 'core-root.squashfs').read_bytes()
        if revision.startswith('locals/core-tools-'):
            assert set(state) == set(original_state)
            assert all(state[key] == value for key, value in original_state.items()
                       if key not in ('core/root.squashfs', 'core/lxc.container.conf', 'bsp/pantavisor'))
        for digest, data in added.items():
            obj = mountpoint / 'objects' / digest
            if obj.exists(): assert sha(obj) == digest
            else: obj.write_bytes(data)
    obj = mountpoint / 'objects' / state['bsp/pantavisor']
    if obj.exists(): assert sha(obj) == state['bsp/pantavisor']
    else: shutil.copyfile(stage / 'initramfs', obj)
    target = mountpoint / 'trails' / revision
    target.mkdir(parents=True, exist_ok=False)
    for name in ('.pvr', '.pv'): (target / name).mkdir()
    for name, value in state.items():
        if name.startswith('#'): continue
        relative = Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, dict): path.write_text(json.dumps(value, sort_keys=True, separators=(',', ':')))
        else:
            assert re.fullmatch('[0-9a-f]{64}', value)
            source = mountpoint / 'objects' / value
            assert sha(source) == value
            os.link(source, path)
    (target / '.pvr/json').write_text(json.dumps(state, sort_keys=True, separators=(',', ':')) + '\n')
    (target / '.pvr/config').write_text('{"#spec":"pvr-repo@1"}\n')
    run('sync')
finally:
    run('umount', str(mountpoint))
clean(store)
# Keep recovery latched until the explicit first activation. Old files remain backed up.
run('grub-editenv', str(root / 'state/boot-budget'), 'set', 'ventuno_boots=0', 'ventuno_recovery=1')
run('grub-editenv', str(root / 'state/grubenv'), 'set', 'pv_try=' + revision)
run('grub-editenv', str(root / 'state/grubenv'), 'unset', 'ventuno_attempt')
for name in ('initramfs', 'build-inputs.json'):
    temporary = root / (name + '.new')
    shutil.copyfile(stage / name, temporary)
    temporary.chmod(0o600)
    os.replace(temporary, root / name)
for source, destination in [('grub-entry.cfg', '41_ventuno_persistent'), ('grub-default.cfg', '09_ventuno_default')]:
    path = Path('/etc/grub.d') / destination
    path.write_text("#!/bin/sh\ncat <<'VENTUNO_EOF'\n" + (stage / source).read_text() + 'VENTUNO_EOF\n')
    path.chmod(0o755)
candidate = backup / 'grub.cfg.candidate'
generated = subprocess.run(['grub-mkconfig', '-o', str(candidate)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
(backup / 'grub-mkconfig.log').write_text(generated.stdout)
generated.check_returncode()
run('grub-script-check', str(candidate))
assert next(line for line in candidate.read_text().splitlines() if line.startswith('menuentry ')).startswith("menuentry 'Ubuntu'")
os.replace(candidate, '/boot/grub/grub.cfg')
record['files']['initramfs'] = request['files']['initramfs']
record['files']['build-inputs.json'] = request['files']['build-inputs.json']
record['installed_grub_sha256'] = sha(Path('/boot/grub/grub.cfg'))
record['snippet_sha256'] = sha(Path('/etc/grub.d/41_ventuno_persistent'))
record['default_snippet_sha256'] = sha(Path('/etc/grub.d/09_ventuno_default'))
record['ubuntu_default_preserved'] = False
record['runtime_upgrade'] = request | {'backup': str(backup), 'previous_revision': private['pv_rev']}
record_path.write_text(json.dumps(record, indent=2) + '\n')
(backup / 'upgrade.json').write_text(json.dumps(record['runtime_upgrade'], indent=2) + '\n')
run('sync')
print('Upgrade prepared; recovery latched, no reboot scheduled. Backup:', backup)
PY
