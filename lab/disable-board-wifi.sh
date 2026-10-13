#!/usr/bin/env bash
# Persistently disable Wi-Fi through Ubuntu's NetworkManager; keep Ethernet.
set -euo pipefail
test "$(id -u)" -eq 0
test "$(findmnt -n -o SOURCE /)" = /dev/mmcblk0p71
case "$(nmcli -g GENERAL.STATE device show end0)" in
    '100 '*) ;;
    *) echo 'Ethernet is not connected; inspect access before disabling Wi-Fi'; exit 1 ;;
esac
echo '### Before'
nmcli radio wifi
nmcli device status
echo '### Disable Wi-Fi'
nmcli radio wifi off
echo '### After'
test "$(nmcli radio wifi)" = disabled
nmcli radio wifi
nmcli device status
rfkill list
python3 - <<'PY'
import configparser
from pathlib import Path
path = Path('/var/lib/NetworkManager/NetworkManager.state')
state = configparser.ConfigParser()
state.read(path)
assert state.getboolean('main', 'WirelessEnabled') is False
print('Persistent NetworkManager state: WirelessEnabled=false')
PY
ip -4 address show dev end0
systemctl is-active ssh NetworkManager
