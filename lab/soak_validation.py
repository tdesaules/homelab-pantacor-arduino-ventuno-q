"""Parse prolonged-boot evidence and reject restarts, stale data and resource faults."""
import json
import re
from runtime_validation import core_ready, host_pid1_ready, is_ready, section


def block(text, heading):
    return section(text, heading).split('\n### ', 1)[0].strip()


def validate_snapshot(text, trial, inputs, deadline, require_watchdog=False, previous=None):
    if not (is_ready(text, 1) and core_ready(text, 1, inputs['core_image']['release']) and host_pid1_ready(text)):
        raise ValueError('Revision/core/application is not READY with its original start counter and expected identity')
    if 'ventuno_trial=' + trial not in block(text, '### Kernel command line').split():
        raise ValueError('Unexpected trial token')
    boot_id = block(text, '### Boot ID')
    if not re.fullmatch('[0-9a-f-]{36}', boot_id):
        raise ValueError('Invalid boot ID')
    host = dict(line.split('=', 1) for line in block(text, '### Host PID 1').splitlines() if '=' in line)
    if host['supervisor_version'] != '4' or int(host['return_after']) != deadline:
        raise ValueError('Unexpected guardian version or deadline')
    if require_watchdog and (host['watchdog'] != 'armed' or int(host['watchdog_timeout']) != 30):
        raise ValueError('Hardware watchdog is not armed as expected')
    _, heartbeat_text = section(text, '### Persistent application data').split('\n', 1)
    heartbeat, _ = json.JSONDecoder().raw_decode(heartbeat_text)
    uptime = float(block(text, '### Uptime').split()[0])
    lag = uptime - heartbeat['uptime']
    if not -1 <= lag <= 10:
        raise ValueError(f'Application heartbeat is stale or invalid: lag={lag:.1f}s')
    memory = block(text, '### Memory')
    available = int(re.search(r'^MemAvailable:\s+(\d+) kB$', memory, re.M).group(1))
    if available < 128 * 1024:
        raise ValueError(f'Host memory availability too low: {available} KiB')
    free_kib = int(block(text, '### Storage').splitlines()[-1].split()[-3])
    if free_kib < 32 * 1024:
        raise ValueError(f'Runtime store free space too low: {free_kib} KiB')
    anomalies = block(text, '### Kernel anomalies')
    if anomalies != 'none':
        raise ValueError('Kernel fault detected: ' + anomalies)
    temperatures = {}
    for line in block(text, '### Thermal').splitlines():
        if line == 'none': continue
        name, value = line.rsplit(' ', 1)
        temperatures[name] = int(value)
    sample = {
        'boot_id': boot_id, 'guardian_pid': int(host['guardian_pid']),
        'elapsed': int(host['elapsed']), 'uptime': uptime,
        'heartbeat_uptime': heartbeat['uptime'], 'heartbeat_lag': lag,
        'mem_available_kib': available, 'store_free_kib': free_kib,
        'temperatures_millicelsius': temperatures,
        'load_average': block(text, '### Load').split()[:3],
        'watchdog': host['watchdog'],
    }
    if previous:
        if sample['boot_id'] != previous['boot_id'] or sample['guardian_pid'] != previous['guardian_pid']:
            raise ValueError('Host or guardian restarted during the observation')
        if sample['elapsed'] <= previous['elapsed'] or sample['uptime'] <= previous['uptime']:
            raise ValueError('Guardian or host clock did not advance')
        if sample['heartbeat_uptime'] < previous['heartbeat_uptime']:
            raise ValueError('Application heartbeat moved backwards')
    return sample
