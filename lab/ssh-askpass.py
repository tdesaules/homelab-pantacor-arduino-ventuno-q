#!/usr/bin/env python3
"""Read the lab password from the ignored local access document."""
from pathlib import Path
import re
import sys

if len(sys.argv) > 1 and 'password' not in sys.argv[1].lower():
    sys.exit(1)
text = (Path(__file__).resolve().parents[1] / 'docs/access.local.md').read_text()
match = re.search(r'Mot de passe : `([^`]+)`', text)
if not match:
    sys.exit('Password missing from local access document')
print(match.group(1))
