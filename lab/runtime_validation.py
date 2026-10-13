"""Interpret actual runtime status, not the similarly named status_goal."""
import json


def section(text, heading):
    return text.split(heading + '\n', 1)[1].lstrip()


def container_status(text, name='diagnostic'):
    containers, _ = json.JSONDecoder().raw_decode(section(text, '### Pantavisor containers'))
    return next(item for item in containers if item['name'] == name)


def network_ready(text, starts):
    try:
        status = container_status(text, 'network')
        lines = section(text, '### Revision network').splitlines()
        return (status['status'] == 'READY' and f'NETWORK_STARTS={starts}' in lines
                and 'NETWORK_OWNER=revision' in lines and 'DHCP_BOUND=1' in lines)
    except (ValueError, KeyError, IndexError, StopIteration, TypeError):
        return False


def core_ready(text, starts, release=None):
    try:
        status = container_status(text, 'core')
        app = container_status(text)
        lines = section(text, '### Core').splitlines()
        actual_release, _ = json.JSONDecoder().raw_decode(section(text, '### Core release'))
        _, heartbeat_text = section(text, '### Persistent application data').split('\n', 1)
        heartbeat, _ = json.JSONDecoder().raw_decode(heartbeat_text)
        return (status['status'] == 'READY' and status['group'] == 'root'
                # Pantavisor 030 exposes the nobody role as an empty role list.
                and status['roles'] == ['mgmt'] and app['roles'] in ([], ['nobody'])
                and app['group'] == 'app' and heartbeat['management_http_status'] == 403
                and f'CORE_STARTS={starts}' in lines and 'NETWORK_OWNER=core' in lines
                and 'DHCP_BOUND=1' in lines and actual_release['name'] == 'ventuno-core'
                and (release is None or actual_release == release))
    except (ValueError, KeyError, IndexError, StopIteration, TypeError):
        return False


def host_pid1_ready(text):
    try:
        fields = dict(line.split('=', 1) for line in section(text, '### Host PID 1').splitlines() if '=' in line)
        return (fields['host_pid1_name'] == 'pantavisor'
                and fields['host_pid1_exe'] == '/usr/bin/pantavisor'
                and fields['pantavisor_pid'] == '1'
                and fields['supervisor_version'] in ('3', '4', '5')
                and int(fields['guardian_pid']) > 1)
    except (ValueError, KeyError, IndexError, TypeError):
        return False


def is_ready(text, starts):
    try:
        status = container_status(text)
        progress, _ = json.JSONDecoder().raw_decode(section(text, '### Revision progress'))
        counter, heartbeat_text = section(text, '### Persistent application data').split('\n', 1)
        heartbeat, _ = json.JSONDecoder().raw_decode(heartbeat_text)
        return (status['status'] == 'READY' and progress['status'] == 'DONE'
                and int(counter) == starts and heartbeat['starts'] == starts
                and heartbeat['pid'] == 1 and heartbeat['container'] == 'diagnostic')
    except (ValueError, KeyError, IndexError, StopIteration, TypeError):
        return False


def is_stopped(text):
    try:
        status = container_status(text)
        return status['status'] == 'STOPPED' and status['user_stopped'] in (True, 'true')
    except (ValueError, KeyError, IndexError, StopIteration, TypeError):
        return False
