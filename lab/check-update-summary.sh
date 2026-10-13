#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import re
text = Path('/var/log/ventuno-os-update.log').read_text(errors='replace')
for line in text.splitlines():
    if re.match(r'^\d+ upgraded,', line) or line.endswith('_COMPLETE'):
        print(line)
for path in sorted(Path('/sys/class/remoteproc').glob('remoteproc*')):
    print(path.name, (path / 'name').read_text().strip(), (path / 'state').read_text().strip())
PY
echo '### Current kernel hashes and provenance'
sha256sum "/boot/vmlinuz-$(uname -r)" "/boot/config-$(uname -r)"
apt-cache policy "linux-image-$(uname -r)" "linux-modules-$(uname -r)"
apt-cache show "linux-image-$(uname -r)" "linux-modules-$(uname -r)" | grep -E '^(Package|Version|Source|Filename|SHA256):'
