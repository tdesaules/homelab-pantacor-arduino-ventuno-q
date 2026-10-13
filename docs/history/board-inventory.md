# Inventaire initial par SSH

Collecte en lecture seule du 10 octobre 2026, après configuration du mot de
passe par le propriétaire. Il s'agit de l'état observé, pas d'une preuve de
l'état logiciel à la sortie d'usine.

| Élément | Observation |
| --- | --- |
| OS | Ubuntu 24.04.4 LTS (Noble) |
| Build constructeur | `20260710-235` |
| Noyau | `6.8.0-1078-qcom`, build `#83-Ubuntu`, aarch64 |
| Device tree compatible | `arduino,monza`, `qcom,monaco-monza`, `qcom,qcs8300` |
| Console dans la ligne de commande | `ttyMSM0,115200n8` |
| eMMC | `mmcblk0`, 59,3 Gio, 71 partitions visibles |
| Racine | `mmcblk0p71`, ext4, 55,9 Gio |
| Partition montée sur `/boot/efi` | `mmcblk0p69`, FAT, 512 Mio |
| Partition montée sur `/var/persist` | `mmcblk0p70`, ext4, 30 Mio |
| NVMe | `nvme0n1`, 119,2 Gio, modèle déclaré `NE-128 2242` |
| Ethernet | `end0`, connecté |
| Wi-Fi | `wlp3s0`, détecté mais déconnecté |
| USB | Récepteur Logitech Logi Bolt et périphérique Arduino détectés |
| Services systemd en échec | Aucun au moment de la collecte |

## Points à investiguer

- Le NVMe se présente comme un **2242**, alors que le manuel Arduino décrit
  une fixation pour **2230**. Le propriétaire confirme l'utilisation d'un
  adaptateur et une fixation correcte, sans contrainte sur le connecteur.
  La détection électrique est confirmée ; les tests d'E/S restent à réaliser.
- Les identifiants `monza`, `monaco-monza` et `qcs8300` sont des pistes pour
  retrouver le BSP. Ils ne remplacent pas l'identification commerciale QCS8275.
- La présence de `/boot/efi` ne suffit pas à établir la chaîne complète de boot
  ni son intégration possible au rollback Pantavisor.
- Le Wi-Fi et les périphériques USB sont détectés mais leur fonctionnement
  applicatif n'est pas encore validé. Le NVMe n'a pas subi de test d'écriture.
- Identifier les labels des partitions, le chargeur de démarrage, les sources
  du noyau et sa configuration avant de concevoir l'image Pantavisor.

Aucun formatage, flash, changement réseau ni mise à jour n'a été effectué
pendant cette collecte.
