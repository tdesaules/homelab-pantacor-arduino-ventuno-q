#!/usr/bin/env bash
set -eu
systemctl show ventuno-os-update -p ActiveState -p SubState -p Result -p ExecMainStatus
python3 - <<'PY'
from pathlib import Path
lines = Path('/var/log/ventuno-os-update.log').read_text(errors='replace').splitlines()
print('\n'.join(lines[-45:]))
PY
snap changes
