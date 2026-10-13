#!/usr/bin/env python3
"""Exercise revision-name guards in real ARM64 GRUB, without booting a kernel."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from autonomous_boot import grub_default, grub_entry
from revision_names import BOOT_REVISION_PATTERN, valid_revision

ROOT = Path(__file__).resolve().parents[1]
reference = ROOT / 'artifacts/grub-reference'
record = json.loads((reference / 'reference.json').read_text())
for name, key in [('grubaa64.efi', 'sha256'), ('arm64-efi.tar.gz', 'modules_sha256')]:
    assert hashlib.sha256((reference / name).read_bytes()).hexdigest() == record[key]
cases = ['0', 'locals/0.1.0', 'locals/v0.1.0', 'locals/0.1.0-rc.1', 'locals/k0s-os-070',
         'locals/' + 'a' * 64, 'locals/' + 'a' * 65, 'locals/sha256-' + 'a' * 64,
         '0.1.0', 'locals/', 'locals/.', 'locals/..', 'locals/../x',
         'locals/x panic=0', 'locals/x;reboot', 'locals/$(reboot)']
output = ROOT / 'artifacts/grub-revision-names' / uuid.uuid4().hex
output.mkdir(parents=True)
with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='grub-names-') as work:
    work = Path(work)
    fixture = work / 'fixture'
    (fixture / 'boot/grub').mkdir(parents=True)
    with tarfile.open(reference / 'arm64-efi.tar.gz') as archive:
        archive.extractall(fixture / 'boot/grub', filter='data')
    checks = []
    for index, name in enumerate(cases):
        assert "'" not in name
        checks.append(f'''    set revision='{name}'
    if regexp '^{BOOT_REVISION_PATTERN}$' "$revision"; then
        echo 'CASE_{index}=accepted'
    else
        echo 'CASE_{index}=rejected'
    fi''')
    # Also parse the real generated selectors/entry, without selecting them.
    config = 'set timeout=0\nset default=0\nmenuentry "Revision validation" {\n    insmod regexp\n' + '\n'.join(checks) + '\n    halt\n}\n'
    config += grub_entry(record['root_uuid'], 'a' * 32, emulated=True)
    (output / 'default-selector.cfg').write_text(grub_default(record['root_uuid']))
    (fixture / 'boot/grub/grub.cfg').write_text(config)
    (output / 'grub.cfg').write_text(config)
    subprocess.run(['grub2-script-check', str(output / 'grub.cfg')], check=True)
    support = work / 'support.ext4'
    with support.open('wb') as stream: stream.truncate(64 * 1024 ** 2)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-U', record['root_uuid'], '-d', str(fixture), str(support)], check=True)
    efi = work / 'efi'
    for folder in ('EFI/BOOT', 'EFI/ubuntu'):
        (efi / folder).mkdir(parents=True)
        (efi / folder / 'grub.cfg').write_text(f"search --no-floppy --fs-uuid --set=root {record['root_uuid']}\nset prefix=($root)/boot/grub\nconfigfile $prefix/grub.cfg\n")
    shutil.copyfile(reference / 'grubaa64.efi', efi / 'EFI/BOOT/BOOTAA64.EFI')
    with (output / 'console.log').open('wb') as log:
        subprocess.run(['qemu-system-aarch64', '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a57',
            '-m', '512', '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-nic', 'none',
            '-bios', '/usr/share/edk2/aarch64/QEMU_EFI.fd',
            '-drive', f'file={support},format=raw,if=virtio',
            '-drive', f'file=fat:ro:{efi},format=raw,if=virtio,readonly=on'],
            stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
text = (output / 'console.log').read_text(errors='replace')
for index, name in enumerate(cases):
    expected = 'accepted' if valid_revision(name) else 'rejected'
    assert f'CASE_{index}={expected}' in text, (index, name, expected)
(output / 'result.json').write_text(json.dumps({'cases': len(cases), 'passed': True}, indent=2) + '\n')
print('PASS: revision names accepted/rejected by real ARM64 GRUB. Logs:', output)
