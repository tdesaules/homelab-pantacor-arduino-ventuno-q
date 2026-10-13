#!/usr/bin/env python3
"""Retain Pantavisor logs from the previous and current revisions, read-only."""
from pathlib import Path
import shlex
import uuid
from local_updates import Session

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / 'artifacts/cluster-audit' / uuid.uuid4().hex
directory.mkdir(parents=True, mode=0o700)
session = Session('192.168.1.20', 2222, directory)
for revision in ('k0s-051', 'core-tools-060'):
    path = '/pantavisor/logs/locals/' + revision + '/pantavisor/pantavisor.log'
    (directory / (revision + '.log')).write_text(session.run('cat ' + shlex.quote(path), timeout=90))
print('History:', directory)
