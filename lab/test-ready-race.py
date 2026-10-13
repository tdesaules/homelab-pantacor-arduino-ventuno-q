#!/usr/bin/env python3
"""Exercise the actual pinned C callbacks in both event orders, before/after patch."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REV = '48c582334875dde17634973049885c7ab6049116'
PATCH = ROOT / 'meta-ventuno/recipes-pv/pantavisor/files/0001-preserve-early-platform-readiness.patch'
source = subprocess.check_output(['git', '-C', str(ROOT / 'artifacts/pantavisor'), 'show', REV + ':platforms.c'], text=True)

def function(source, name):
    start = source.index(name)
    start = source.rfind('\n', 0, start) + 1
    end = source.index('\n}', start) + 2
    return source[start:end]

stub = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <sys/types.h>
#include <unistd.h>
enum { PLAT_STARTING, PLAT_STARTED, PLAT_READY, PLAT_STOPPING, PLAT_STOPPED };
struct pv_platform_log { int console_pt; };
struct pv_platform {
    struct { int current, goal; } status;
    int pipefd[2], pipefd_listener;
    pid_t init_pid;
    char *name, *type;
    struct pv_platform_log log;
};
struct pv_cont_ctrl { int (*get_console_fd)(struct pv_platform *, struct pv_platform_log *); };
#define pv_log(...) ((void)0)
#define PV_LOG_LOGGERS 0
#define PV_PLATFORM_LXC_CONSOLE_LOG 0
static int ignored, subscribed;
static void pv_event_socket_ignore(int *listener) { ignored++; }
static int pv_config_get_bool(int key) { return 0; }
static int start_pvlogger_for_platform(struct pv_platform *p) { return 0; }
static int console(struct pv_platform *p, struct pv_platform_log *log) { return 0; }
static const struct pv_cont_ctrl *_pv_platforms_get_ctrl(char *type) {
    static const struct pv_cont_ctrl ctrl = {console}; return &ctrl;
}
static void pv_platform_subscribe_fd(int fd, char *name, int src) { subscribed++; }
static void pv_platform_set_status(struct pv_platform *p, int status) { p->status.current = status; }
'''
main = r'''
static void notify(struct pv_platform *p, pid_t pid) {
    assert(pipe(p->pipefd) == 0);
    assert(write(p->pipefd[1], &pid, sizeof(pid)) == sizeof(pid));
    close(p->pipefd[1]);
    _read_platform_pipefd_cb(p->pipefd[0], 0, p);
    assert(p->init_pid == pid && p->pipefd[0] == -1);
}
int main(void) {
    struct pv_platform p = {.status = {PLAT_STARTING, PLAT_READY}};
    /* Signal arrives before PID notification: the reported incident. */
    assert(pv_platform_set_ready(&p) == 0);
    notify(&p, 123);
    if (p.status.current != PLAT_READY) return 42;
    assert(ignored == 1 && subscribed == 1);
    /* Normal ordering and duplicate READY remain valid. */
    p.status.current = PLAT_STARTING;
    notify(&p, 456);
    assert(p.status.current == PLAT_STARTED);
    assert(pv_platform_set_ready(&p) == 0);
    assert(pv_platform_set_ready(&p) == 0);
    /* A failed start still overrides an early READY. */
    notify(&p, -1);
    assert(p.status.current == PLAT_STOPPED);
    assert(pv_platform_set_ready(&p) == -1);
    p.status.current = PLAT_STOPPING;
    notify(&p, 789);
    assert(p.status.current == PLAT_STOPPING);
    assert(pv_platform_set_ready(&p) == -1);
    /* A fresh restart must earn readiness again. */
    p.status.current = PLAT_STARTING;
    notify(&p, 999);
    assert(p.status.current == PLAT_STARTED);
    p.status.goal = PLAT_STARTED;
    assert(pv_platform_set_ready(&p) == -1);
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='ready-race-', dir=ROOT / 'artifacts') as directory:
    directory = Path(directory)
    (directory / 'platforms.c').write_text(source)
    subprocess.run(['git', 'apply', '--unsafe-paths', '--directory', str(directory), str(PATCH)], check=True)
    fixed = (directory / 'platforms.c').read_text()
    for label, code, expected in [('baseline', source, 42), ('fixed', fixed, 0)]:
        harness = stub + '\n' + function(code, 'static void _read_platform_pipefd_cb(') + '\n' + function(code, 'int pv_platform_set_ready(') + '\n' + main
        path = directory / (label + '.c')
        path.write_text(harness)
        executable = directory / label
        subprocess.run(['cc', '-std=c11', '-O2', str(path), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)])
        assert result.returncode == expected, (label, result.returncode)
print('PASS: baseline reproduces READY regression; patched callbacks preserve both event orders, failure, stop and restart semantics')
