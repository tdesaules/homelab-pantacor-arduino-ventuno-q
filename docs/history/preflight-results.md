# Qualification préalable au portage

Tests du 10 octobre 2026 sur Ubuntu constructeur, noyau `6.8.0-1078-qcom`.
Les journaux complets horodatés sont dans `artifacts/` (non versionnés).
Les tests ne constituent pas une qualification de Pantavisor, qui n'est pas
encore installé, ni un test d'endurance.

## Résultats

| Vérification | Résultat | Limite |
| --- | --- | --- |
| SSH et sudo | Réussis | Authentification par mot de passe de lab |
| Boot | UEFI → shim ARM64 → GRUB 2.12 → noyau/initrd Ubuntu | Boot custom pas encore testé |
| Secure Boot UEFI | Désactivé, Setup Mode | Ne prouve pas l'absence de vérification des firmwares Qualcomm en amont |
| eMMC | Fichier temporaire 64 Mio, écriture, fsync, relecture et SHA-256 réussis | Pas de test après coupure ou reboot |
| NVMe lecture | 256 Mio en accès direct, environ 1,4 Go/s sur ce court test | Pas un benchmark soutenu |
| NVMe écriture | 64 Mio à l'offset 1 Gio, fsync, relecture et SHA-256 réussis | Test brut, pas de système de fichiers NVMe |
| Restauration NVMe | Octets d'origine sauvegardés, restaurés et comparés | Le SSD reste sans partition/signature détectée |
| Namespaces | mount, PID, réseau, UTS et IPC créés avec succès | USER_NS constaté dans la config, pas testé fonctionnellement |
| Réseau conteneurs | Paire veth créée et supprimée dans un namespace isolé | Pas de test bridge/NAT applicatif |
| SquashFS | Image Zstd créée, montée en loop, contenu comparé | Un petit jeu de données |
| OverlayFS | Montage sur SquashFS, écriture dans upperdir vérifiée | Test temporaire |
| Cgroups | v2 actif, contrôleurs disponibles ; conteneur démarré avec limites mémoire/PID | Pas de test de dépassement des limites |
| dm-verity / dm-crypt | Modules chargés, cibles présentes dans dmsetup | Volumes vérifiés/chiffrés pas testés |
| Conteneur ARM64 | Image Arduino locale exécutée, non-root, racine read-only, sans réseau | Docker 29.1.3, pas LXC/Pantavisor |
| Ethernet | 2500 Mb/s full duplex ; 5 pings passerelle, aucune perte | Débit utile et reconnexion pas mesurés |
| Wi-Fi | ath11k_pci ; scan réussi en 2,4/5/6 GHz | Association, DHCP et trafic attendent un réseau de test |
| USB hôte | xHCI et usbhid actifs, récepteur Logi Bolt reconnu | Événements clavier/souris et disque externe à tester physiquement |
| USB gadget | Options ECM/NCM présentes dans le noyau | Aucun UDC exposé dans le câblage actuel ; USB-C utilisé pour l'alimentation |
| Watchdog | `/dev/watchdog0` présent, métadonnées collectées | Expiration/reset volontaire pas déclenché |
| Nettoyage | Aucun fichier scratch/backup de test restant ni loop de test | Modules chargés peuvent rester jusqu'au reboot |

## Anomalies de référence

Le journal du boot constructeur contient notamment :

- variations de caractéristiques CPU entre cœurs ;
- erreurs de mise à jour OPP/tension CPU ;
- avertissement NVMe SUBNQN et échec de création hwmon ;
- erreurs UCSI de déclaration des modes alternatifs USB-C ;
- timeouts Bluetooth et firmware `qca/hpnv21g.30c` manquant ;
- erreurs initiales de lecture de descripteur USB.

Ces messages précèdent le portage. Aucun service systemd n'est en échec à la
fin de la collecte. La fenêtre d'erreurs noyau de cinq minutes consultée après
les premiers tests était vide. Cela ne démontre pas l'absence de défauts sous charge.

## Conséquences pour la première image

1. Réutiliser initialement le noyau **linux-qcom 6.8.0-1078.83**, ses modules
   exactement correspondants et les firmwares constructeur.
2. Conserver les partitions Qualcomm, les DTB et la partition `persist`.
   Les slots firmware `_a`/`_b` ne constituent pas un rollback Pantavisor prêt à l'emploi.
3. Construire un initramfs ARM64 Pantavisor ; intégrer notamment les modules
   Ethernet, NVMe, Wi-Fi et OverlayFS. L'eMMC et ext4 sont compilés dans le noyau.
4. Étudier le backend **GRUB** de Pantavisor pour la sélection des révisions,
   le try-boot et le retour à la dernière révision validée. La présence de GRUB
   ne suffit pas à rendre ce protocole fonctionnel.
5. Commencer par un démarrage expérimental avec un chemin de retour Ubuntu,
   après sauvegarde des artefacts et préparation effective de la récupération.
6. Construire les conteneurs réseau/SSH et diagnostic, puis intégrer les données
   NVMe en ext4 et la gestion locale `pvr`.

Les prérequis observés permettent de commencer la construction du prototype.
La sélection de la version Pantavisor/meta-pantavisor et de la chaîne de build
reste à faire ; aucune recette de build fonctionnelle n'est encore fournie.

## Points restant nécessaires

- Fournir/configurer un SSID de test pour valider l'association et le trafic Wi-Fi.
- Brancher un stockage USB de test et effectuer les essais HID/hotplug.
- Pour le réseau gadget : libérer le port USB-C données avec une alimentation adaptée.
- Sauvegarder les partitions/artefacts nécessaires et tester la récupération EDL
  avant les essais qui modifient le démarrage.
- Valider le démarrage custom, LXC, les mises à jour et le rollback après build.
- Tester la persistance après reboot, l'expiration du watchdog et la récupération
  après échec de boot dans cette phase dédiée.

## Reproduction

Depuis le poste, avec la clé SSH de la carte déjà connue et
`docs/access.local.md` renseigné :

```bash
chmod 700 scripts/ssh-askpass.py
python3 scripts/run-board-check.py scripts/collect-board-info.sh
python3 scripts/run-board-check.py --sudo scripts/check-runtime.sh
python3 scripts/run-board-check.py --sudo scripts/check-bsp.sh
python3 scripts/run-board-check.py --sudo scripts/check-nvme-container.sh
```

La collecte d'inventaire affiche le code de chaque commande : un code global
zéro n'indique pas que chaque outil était disponible. Les tests fonctionnels
s'arrêtent sur une erreur. Le wrapper archive stdout/stderr et le code SSH est
affiché ; le mot de passe transite par askpass et, pour sudo, par l'entrée SSH.

Le test d'écriture NVMe exige en plus `--allow-nvme-scratch`. Il est spécifique
au modèle de ce lab, exige un disque non partitionné/non monté sans signature,
et écrit réellement 64 Mio après sauvegarde temporaire des octets d'origine.
Une interruption brutale pourrait laisser cette zone modifiée et le fichier
`/var/tmp/pv-nvme-original-*` à restaurer. Ce n'est pas un test générique pour
un disque contenant des données.
