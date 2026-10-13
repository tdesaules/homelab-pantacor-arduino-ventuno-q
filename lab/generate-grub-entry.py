#!/usr/bin/env python3
"""Generate a diagnostic GRUB stanza locally; does not install or select it."""
import argparse
import json
from pathlib import Path
import re
import uuid
from revision_names import valid_revision

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rootfs-uuid', type=uuid.UUID, required=True)
parser.add_argument('--output-dir', type=Path, default=root / 'artifacts/prototype-1084')
parser.add_argument('--trial-id', type=uuid.UUID)
args = parser.parse_args()
inputs = json.loads((args.output_dir / 'build-inputs.json').read_text())
release = inputs['kernel_release']
if not re.fullmatch(r'[a-zA-Z0-9.-]+', release):
    raise SystemExit('Invalid kernel release')
if bool(args.trial_id) != bool(inputs.get('bounded_trial')):
    raise SystemExit('Bounded image and --trial-id must be used together')
identifier = args.trial_id.hex if args.trial_id else None
directory = '/boot/pantavisor-diagnostic' + ('/' + identifier if identifier else '')
entry_id = 'pantavisor-trial-' + identifier if identifier else 'pantavisor-diagnostic-1084'
extra = ' ventuno_trial=' + identifier if identifier else ''
duration = inputs.get('trial_return_seconds', 180)
maximum = min(inputs.get('trial_max_seconds', 180), 1800) if inputs.get('trial_supervisor_version') == 4 else 180
if not isinstance(duration, int) or not 180 <= duration <= maximum:
    raise SystemExit('Invalid bounded trial duration for this image')
if identifier:
    extra += f' ventuno_return_seconds={duration}'
    revision = inputs.get('boot_revision', '0')
    if not valid_revision(revision):
        raise SystemExit('Invalid boot revision')
    extra += ' pv_rev=' + revision
entry = f'''# Diagnostic entry only. Ubuntu's default entry must remain unchanged.
# Bounded trials return within {duration} seconds once the guard is running.
menuentry 'Pantavisor diagnostic {release}' --id {entry_id} {{
    insmod part_gpt
    insmod ext2
    insmod gzio
    search --no-floppy --fs-uuid --set=root {args.rootfs_uuid}
    echo '[VENTUNO] Loading diagnostic kernel'
    linux {directory}/vmlinuz-{release} rdinit=/init console=tty0 console=ttyMSM0,115200n8 earlycon loglevel=7 pcie_pme=nomsi video=LVDS-1:d panic=10{extra}
    echo '[VENTUNO] Loading diagnostic initramfs'
    initrd {directory}/initramfs-ventuno-q.cpio.gz
    echo '[VENTUNO] Starting bounded diagnostic boot'
}}
'''
path = args.output_dir / 'grub-diagnostic.cfg'
path.write_text(entry)
print(path)
