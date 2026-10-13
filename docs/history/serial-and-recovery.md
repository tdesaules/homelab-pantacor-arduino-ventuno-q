# Console série et récupération Ventuno Q

## Console confirmée : JCTL, logique 1,8 V

Sources consultées : fiche technique Arduino, section **JCTL (MPU Remote Debug)**,
et schémas **ABX00181 V1.0, feuille 23/51, HEADERS_JCTL.SchDoc**.
Les PDF sont archivés dans `artifacts/recovery/` avec leurs empreintes dans
`hardware-reference-sources.json`.

| JCTL | Signal vu de la carte | Adaptateur compatible 1,8 V |
| --- | --- | --- |
| 1 ou 7 | GND | GND |
| 4 | TX, `UART_DBG_1V8` | RXD |
| 6 | RX, `UART_DBG_1V8` | TXD |

Paramètres : **115200 bauds, 8 bits, sans parité, 1 bit d'arrêt, sans contrôle
de flux matériel/logiciel**. Linux expose `ttyMSM0`, nœud
`soc@0/geniqup@9c0000/serial@99c000` confirmé sur la carte.

Le connecteur est un 2×5. Repérer physiquement la broche 1 avec le pinout officiel
avant câblage ; ne pas déduire l'orientation de cette table.

### Adaptateur actuellement disponible

Référence communiquée : **HW-597**.
Marquages communiqués : `5V`, `VCC`, `3V3`, `TXD`, `RXD`, `GND`.
Les niveaux logiques TXD/RXD ne sont pas confirmés par une fiche technique
fiable du module exact. Les broches d'alimentation
5 V/3,3 V ne prouvent pas que TXD/RXD supportent 1,8 V, même si seuls TXD/RXD/GND
sont raccordés. **Pas de branchement direct confirmé avec cet adaptateur.**

Pour avancer : identifier la puce et la référence du module (photo recto/verso),
ou utiliser un adaptateur UART explicitement 1,8 V / un traducteur de niveaux
UART approprié. Arduino recommande Bughopper pour JCTL.

- La carte reste alimentée par son alimentation USB-C PD.
- Ne pas relier `5V`, `VCC` ou `3V3` de l'adaptateur à JCTL.
- JCTL 9 est une **sortie/référence 1,8 V**, pas une entrée d'alimentation.
- JHAT 8/10 est un autre UART partagé avec Bluetooth ; ce n'est pas la console
  de boot actuellement sélectionnée.

Après validation des niveaux et du câblage, capturer un démarrage Ubuntu complet
et vérifier l'entrée clavier dans la console avant de sélectionner le prototype.

## Récupération constructeur préparée

Téléchargements figés par SHA-256 dans `bsp/recovery-downloads.json` :

- Arduino Flasher CLI **0.5.4**, Linux amd64, téléchargé, vérifié et exécutable ;
- image officielle Ventuno Q **20260729-248**, Ubuntu 24.04.4, noyau
  `6.8.0-1080-qcom`, téléchargée et vérifiée (6 949 821 785 octets).

Cette image restaure une base constructeur antérieure à l'Ubuntu 24.04.5/noyau
1084 actuellement installé. Les mises à jour devront ensuite être réappliquées.

```bash
python3 scripts/fetch-recovery.py
python3 scripts/prepare-recovery-tools.py
artifacts/recovery/flasher-0.5.4/arduino-flasher-cli version
artifacts/recovery/flasher-0.5.4/arduino-flasher-cli list ventunoq
```

La version, l'aide `flash` et le catalogue ont été vérifiés. **Aucune opération
de flash ni entrée en EDL n'a été exécutée.**

### Procédure EDL constructeur à valider matériellement

Selon le guide officiel :

1. Débrancher alimentation et câble USB de données.
2. Relier JCTL **1 (GND)** et **2 (FORCED_USB_BOOT_N)**.
3. Alimenter par jack/bornier avec une source adaptée.
4. Connecter ensuite l'USB-C de données au poste.
5. Identifier la carte EDL côté poste et valider les permissions USB.

Le montage actuel alimenté uniquement par USB-C n'offre pas cette liaison de
données directe. Une alimentation alternative sera nécessaire pour suivre
cette procédure ; la console UART 1,8 V ne remplace pas le lien USB EDL.

La commande de restauration, **destructive pour le système et les données de
la carte**, est documentée ici pour une future intervention, pas pour le test
de détection EDL :

```bash
artifacts/recovery/flasher-0.5.4/arduino-flasher-cli flash ventunoq \
  artifacts/recovery/arduino-ventunoq-ubuntu-24.04-desktop-arm64-image-x13-20260729-248.tar.zst
```

Conserver aussi les captures BSP locales. Elles ne remplacent pas une sauvegarde
complète de l'eMMC ni une sauvegarde cohérente de toutes les données utilisateur.
La récupération reste **préparée, mais non éprouvée sur cette carte**.

Sources :

- [Fiche technique, source Arduino](https://github.com/arduino/docs-content/blob/main/content/hardware/ventuno/boards/ventuno-q/datasheet/en-datasheet.md)
- [Schémas](https://docs.arduino.cc/resources/schematics/ABX00181-schematics.pdf)
- [Pinout](https://docs.arduino.cc/resources/pinouts/ABX00181-full-pinout.pdf)
- [Restauration officielle](https://docs.arduino.cc/tutorials/ventuno-q/flash-image/)
