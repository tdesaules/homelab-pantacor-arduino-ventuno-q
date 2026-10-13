#!/usr/bin/env bash
set -eu
echo '### Ethernet identity'
cat /sys/class/net/end0/address
readlink -f /sys/class/net/end0/device/driver
ip -4 -o address show dev end0
echo '### NetworkManager DHCP configuration'
nmcli -g ipv4.method,ipv4.dhcp-client-id,ipv4.dhcp-hostname connection show 'Wired connection 1'
nmcli -f DHCP4.OPTION device show end0
