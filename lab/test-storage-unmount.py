#!/usr/bin/env python3
"""Compile the real shutdown function and inject transient/permanent umount failures."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = subprocess.check_output(['git', '-C', str(ROOT / 'artifacts/pantavisor'), 'show',
    '48c582334875dde17634973049885c7ab6049116:storage.c'], text=True)
patch = ROOT / 'meta-ventuno/recipes-pv/pantavisor/files/0003-retry-busy-storage-unmount.patch'
stub = r'''
#include <assert.h>
#include <errno.h>
#define PATH_MAX 4096
#define IM_APPENGINE 1
#define pv_log(...) ((void)0)
static int calls, sleeps, remaining, failure = EBUSY, mode;
static int pv_config_get_system_init_mode(void) { return mode; }
static void pv_paths_storage(char *path, int size) { path[0] = 0; }
static void pv_fs_path_sync(const char *path) {}
static int umount(const char *path) {
    calls++;
    if (remaining) { remaining--; errno = failure; return -1; }
    return 0;
}
static void usleep(int usec) { assert(usec == 100000); sleeps++; }
'''
main = r'''
int main(void) {
    remaining = 2;
    pv_storage_umount();
    if (calls != 3 || sleeps != 2) return 42;
    calls = sleeps = 0; remaining = 100;
    pv_storage_umount();
    assert(calls == 21 && sleeps == 20);
    calls = sleeps = 0; failure = EINVAL;
    pv_storage_umount();
    assert(calls == 1 && sleeps == 0);
    calls = sleeps = 0; mode = IM_APPENGINE;
    pv_storage_umount();
    assert(calls == 0 && sleeps == 0);
    return 0;
}
'''
with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts', prefix='umount-test-') as directory:
    directory = Path(directory)
    (directory / 'storage.c').write_text(source)
    subprocess.run(['git', 'apply', '--unsafe-paths', '--directory', str(directory), str(patch)], check=True)
    for label, text, expected in [('baseline', source, 42), ('fixed', (directory / 'storage.c').read_text(), 0)]:
        start = text.index('void pv_storage_umount()')
        end = text.index('\n}', start) + 2
        path = directory / (label + '.c')
        path.write_text(stub + text[start:end] + main)
        executable = directory / label
        subprocess.run(['cc', '-std=c11', str(path), '-o', str(executable)], check=True)
        assert subprocess.run([str(executable)]).returncode == expected
print('PASS: transient EBUSY is retried; permanent errors and appengine remain bounded')
