"""Check application storage identity, backing device, counter and persistent token."""
import json
import re
import uuid
from runtime_validation import core_ready, host_pid1_ready, is_ready, section


def validate_nvme(text, inputs, starts, expected_identity=None):
    if not (is_ready(text, starts) and core_ready(text, 1, inputs['core_image']['release']) and host_pid1_ready(text)):
        raise ValueError('Runtime/core/application has not reached the expected state')
    block = section(text, '### Application storage').split('\n### ', 1)[0].strip()
    fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
    if fields.get('APPDATA_MOUNTED') != '1' or fields.get('APPDATA_UUID') != inputs['app_storage']['filesystem_uuid']:
        raise ValueError('Wrong or missing application filesystem')
    if fields.get('APPDATA_FILESYSTEM') != 'ext4':
        raise ValueError('Unexpected application filesystem type')
    device = fields['APPDATA_DEVICE']
    df = block.splitlines()[-1].split()
    if df[0] != device or df[-1] != '/diagnostic-data' or not re.fullmatch(r'/dev/(nvme\d+n\d+p\d+|vdb)', device):
        raise ValueError('Application data is not on the expected separate device')
    _, heartbeat_text = section(text, '### Persistent application data').split('\n', 1)
    heartbeat, _ = json.JSONDecoder().raw_decode(heartbeat_text)
    identity = str(uuid.UUID(heartbeat['identity']))
    if identity != heartbeat['identity'] or (expected_identity and identity != expected_identity):
        raise ValueError('Persistent application identity changed')
    return {'application_starts': starts, 'application_identity': identity,
            'filesystem_uuid': fields['APPDATA_UUID'], 'device': device, 'core_starts': 1}
