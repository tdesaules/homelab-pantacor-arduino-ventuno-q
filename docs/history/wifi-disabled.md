# Wi-Fi désactivé — périmètre Ethernet seul

Décision du propriétaire le 11 octobre 2026 : le Wi-Fi n'est pas utilisé et
sort du périmètre V1. Ethernet DHCP et SSH restent le réseau de gestion.

## Carte sous Ubuntu

Le script `scripts/disable-board-wifi.sh` vérifie d'abord que la carte fonctionne
sur sa racine eMMC et qu'Ethernet est connecté, puis exécute :

```bash
nmcli radio wifi off
```

Résultats vérifiés sur la carte :

- `nmcli radio wifi` : **disabled** ;
- `wlp3s0` : **unavailable** ;
- rfkill Wireless LAN : **Soft blocked: yes** ;
- `/var/lib/NetworkManager/NetworkManager.state` : **WirelessEnabled=false** ;
- `end0` toujours connecté sur `192.168.1.20/24` ;
- SSH et NetworkManager actifs.

L'état est enregistré pour les prochains démarrages de NetworkManager. Aucun
redémarrage matériel n'a été effectué pour cette opération. Il s'agit d'une
désactivation logicielle de la radio, pas d'une coupure électrique du module
combiné Wi-Fi/Bluetooth.

Trace : `artifacts/20261011T131339934713Z-disable-board-wifi.log`.

## Images custom

`bsp/ventuno-q-1084-selection.json` porte désormais `wifi_enabled: false` :

- retrait des pilotes ath11k et des firmwares WCN6855/QCA2066 de la sélection ;
- retrait du chargement Wi-Fi/QRTR-MHI dans le script précoce ;
- recalcul de la fermeture des dépendances et des index depmod ;
- ajout de `etc/modprobe.d/90-ventuno-no-wifi.conf`, qui bloque le pilote onboard ;
- vérification de l'absence d'ath11k, mac80211, cfg80211 et des firmwares ath11k.

Le noyau constructeur reste inchangé. La politique exclut les composants
chargeables Wi-Fi de l'initramfs ; elle ne recompile pas les options du noyau.

## Artefact vérifié

Répertoire : **`artifacts/prototype-1084-ethernet-only/`**.

| Élément | Résultat |
| --- | --- |
| Noyau | `6.8.0-1084-qcom` |
| Modules sélectionnés | 105 |
| Fichiers de firmware sélectionnés | 29 |
| Initramfs | 17 509 825 octets, environ **16,7 Mio** |
| SHA-256 | `47093340c5a91673f3b6ee79af794c206377abda033e84ed2c56c71b81586488` |

Contrôles statiques réussis, ainsi qu'un boot QEMU complet confirmant DHCP,
connexion SSH avec clé d'hôte épinglée, refus d'une clé non autorisée,
journalisation et retour automatique. Cette nouvelle variante n'a pas encore
été démarrée sur la carte ; Ubuntu y reste actif avec sa radio Wi-Fi désactivée.

Les anciens artefacts avec Wi-Fi sont conservés pour l'historique. Le transfert
d'essai et le test réseau utilisent par défaut la nouvelle variante Ethernet seule.
