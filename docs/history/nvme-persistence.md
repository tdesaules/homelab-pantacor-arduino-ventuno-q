# Persistance applicative sur NVMe

Le [jalon suivant](local-updates.md) valide la conservation de ces données
pendant les mises à jour/rollback applicatifs et ajoute Bash/Nushell à core.

Le prototype `artifacts/prototype-1084-nvme/` associe Pantavisor PID 1,
`core` **0.1.2** et le volume permanent de `diagnostic` sur le NVMe. Le système,
les objets de révision, les journaux Pantavisor et les données de `core` restent
dans le store de test eMMC de 256 Mio.

## Disque provisionné

Le 12 octobre 2026, le NVMe autorisé a été identifié sans partition, signature,
montage, swap ou holder actif. Une GPT et une partition ext4 ont été créées
une seule fois, après vérification du modèle, du numéro de série, de la taille
et de la racine Ubuntu sur `/dev/mmcblk0p71`.

| Paramètre | Valeur |
| --- | --- |
| Modèle | KingSpec `NE-128 2242` |
| Numéro de série | `0012327000631` |
| Capacité brute | 128 035 676 160 octets |
| Partition | `/dev/nvme0n1p1`, ext4, label `pv-appdata` |
| Taille de la partition | 128 034 275 328 octets |
| UUID ext4 | `5ccb2c2f-c0f7-44a1-a291-b261a7d060a3` |
| PARTUUID | `4f660ffa-861d-4bba-869e-52c393fefc17` |
| GUID du disque | `9b5ae2bd-e2d8-414d-9c7a-849ad102cebe` |

Le profil est dans `bsp/nvme-app-storage.json`. Les scripts
`inspect-nvme.sh`, `provision-nvme.py` et `provision-nvme.sh` assurent
l'inventaire et le provisionnement ciblé. Le provisionnement refuse un disque
ayant déjà une partition ou une signature ; **il a déjà été effectué sur cette
carte**. Il ne doit pas être rejoué pour un nouvel essai de boot.

Le reçu et les premiers/derniers Mio avant partitionnement sont conservés sous :

```text
/var/lib/ventuno-nvme/5ccb2c2f-c0f7-44a1-a291-b261a7d060a3/
```

Ces deux zones sont une trace des emplacements GPT initiaux, pas une sauvegarde
complète du NVMe. Le journal local du provisionnement est
`artifacts/20261012T071732413667Z-provision-nvme.log`.

## Montage sans formatage au boot

Le backend `volume-disk` avec `provision` bloc de Pantavisor 030 reformate le
périphérique à chaque cycle de montage. Le prototype utilise donc le backend
**bind mount sans champ `provision`**, dont l'opération de formatage est vide.

Avant d'exécuter Pantavisor, `ventuno-app-storage` :

1. Recherche l'UUID attendu parmi les partitions NVMe et refuse une identité
   ambiguë.
2. Vérifie le numéro de série, le PARTUUID et le type ext4.
3. Monte temporairement en lecture seule avec `noload`, puis vérifie le marqueur
   `.ventuno-app-storage` et le répertoire applicatif préparé.
4. Démonte puis remonte en lecture-écriture sur **`/mnt/appdata`**, avec
   `nosuid,nodev`. Le montage normal peut rejouer le journal ext4 si nécessaire.
5. Publie le périphérique et l'UUID dans `/ventuno-trial/app-storage.status`.

Le script de boot n'appelle jamais `mkfs`. Les identifiants lui sont fournis
par `/etc/ventuno-app-storage.conf`, produit à partir du profil versionné.

## Liaison avec la révision Pantavisor

Le manifeste `device.json` déclare :

```json
"disks": [{"name": "nvme-apps", "type": "volume-disk"}]
```

Le volume `data` de `diagnostic/run.json` sélectionne explicitement ce disque :

```json
"data": {"persistence": "permanent", "disk": "nvme-apps"}
```

Le seed contient le lien :

```text
/storage/pv/volume-disk/nvme-apps → /mnt/appdata
```

Pantavisor bind-monte ce stockage sous
`/run/pantavisor/media/pv/dmcrypt/nvme-apps`, puis monte
`perm/diagnostic/data` comme volume de l'application. Le nom interne `dmcrypt`
est une convention de chemin de Pantavisor ; ce volume ext4 n'est pas chiffré.

```text
NVMe ext4
└── /mnt/appdata
    ├── .ventuno-app-storage
    ├── provisioning.json
    └── perm/diagnostic/data
        ├── boots
        ├── identity
        └── heartbeat.json
```

Dans l'application, ce répertoire est `/data`. `core` le reçoit en lecture
seule sous `/diagnostic-data` pour les contrôles de ce jalon. Le seed ne contient
plus de répertoire de secours `/storage/disks/perm/diagnostic/data` sur eMMC.
Le stockage permanent propre à `core` reste sur eMMC.

Lors de l'arrêt, Pantavisor démonte les volumes et le disque logique ; le
helper de fin d'essai démonte ensuite `/mnt/appdata` et écrit
`APPDATA_CLEANLY_UNMOUNTED=1` avant de libérer le support Ubuntu.

## Absence ou mauvaise identité du NVMe

Le NVMe est obligatoire pour cette variante. Si l'UUID manque, si l'identité
ne correspond pas ou si le marqueur est invalide, le bootstrap ne lance ni
Pantavisor ni l'application et attend le retour borné du gardien. Il n'attache
pas le store de révision et n'écrit pas de données applicatives sur eMMC.

Dans ce mode de refus, le SSH de `core` n'est donc pas disponible ; l'accès
Ubuntu revient après le délai de l'essai. Un mode de maintenance Pantavisor
sans disque applicatif pourra être traité séparément.

## Construction et vérifications

Après le build KAS et le provisionnement des clés SSH déjà décrit dans
[ethernet-dhcp-ssh.md](ethernet-dhcp-ssh.md) :

```bash
bash scripts/build-initramfs.sh
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --trial --runtime --core --pid1 \
  --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --nvme-profile bsp/nvme-app-storage.json \
  --output-dir artifacts/prototype-1084-nvme
python3 scripts/build-first-revision.py --output-dir artifacts/prototype-1084-nvme
python3 scripts/verify-prototype.py --output-dir artifacts/prototype-1084-nvme --emulate
python3 scripts/verify-first-revision.py --output-dir artifacts/prototype-1084-nvme
python3 scripts/test-nvme-boot.py --output-dir artifacts/prototype-1084-nvme
```

Le builder protège les seeds existants ; `--replace-seed` exige que le fichier
soit encore conforme à son empreinte initiale. Ce remplacement local n'agit
pas sur les données du NVMe matériel.

Le scénario QEMU final utilise un **contrôleur NVMe**, une **GPT**, le numéro
de série et le PARTUUID attendus. Il vérifie quatre boots :

- premier boot avec disque : compteur 1, création d'une identité persistante ;
- second boot avec le même disque et un store eMMC neuf : compteur 2 et même identité ;
- disque absent : retour borné et store eMMC inchangé ;
- disque présentant un autre UUID : retour borné, disque présenté et store
  eMMC inchangés, vérifiés par empreinte.

Les systèmes de fichiers sont contrôlés après les boots. Le jeu final est
archivé sous
`artifacts/prototype-1084-nvme/qemu-nvme-test/6150b93c8eff44a4a30347f37e699a61/`.

## Essais matériels du 12 octobre 2026

### Mise au point

Le premier essai `284ba2974ab145bfa32f5d9ce88aa275` a refusé le disque avant
montage : sysfs expose le numéro de série sous la forme
`0012327000631       `, avec des espaces de remplissage. La normalisation
par `read -r` corrige la comparaison. Le retour Ubuntu et la restauration de
GRUB ont fonctionné. Le test QEMU a ensuite été étendu au chemin NVMe/GPT pour
couvrir aussi ces contrôles matériels, initialement contournés par un disque virtio.

La collecte utilise désormais `O_APPEND` : le bootstrap et le processus de
diagnostic peuvent écrire dans le même journal sans écraser leurs marqueurs
respectifs. Ce défaut de collecte a été détecté par le scénario QEMU sans disque.

### Persistance entre deux boots complets

| Essai | Compteur application | Compteur core |
| --- | ---: | ---: |
| `8e1675774b69452e93fec42222fc374c` | 1 | 1 |
| `fec8af8c4272458d83037df71c0ea062` | 2 | 1 |

L'identité applicative est restée **`7877e500-a853-430e-b506-a423eebb1ca1`**.
Les deux essais utilisent le même NVMe mais chacun une copie neuve du seed
eMMC. Le compteur de `core` repart donc à 1, alors que celui de l'application
progresse : la persistance est bien externe au store de révision.

Pour un nouvel essai préparé avec
`transfer-trial.py --output-dir artifacts/prototype-1084-nvme` et le
[cycle GRUB](grub-fallback.md), utiliser :

```bash
python3 scripts/probe-diagnostic-ssh.py --trial-id NOUVEL_ID --core
python3 scripts/check-nvme-over-ssh.py --trial-id NOUVEL_ID \
  --expected-starts COMPTEUR_ATTENDU --previous-trial ESSAI_PRECEDENT
```

Le compteur attendu dépend du nombre de démarrages déjà effectués sur ce disque.
Ne pas utiliser ici le scénario générique qui redémarre volontairement les
conteneurs et suppose un compteur initial à 1.

Pendant un boot, `ventuno-revision-status` affiche l'UUID et le périphérique
réel du volume applicatif. Sous Ubuntu, `finish-trial.sh` vérifie que la partition
est non montée, exécute `e2fsck -f -n` et relit compteur, heartbeat et identité
avec `debugfs`. Il vérifie aussi l'absence de données applicatives de secours
dans le store eMMC. Les journaux SSH sont dans les répertoires des essais sous
`artifacts/trials/`.

### Contrôles finaux après retour Ubuntu

Les deux retours ont réussi avec :

- `appdata_cleanly_unmounted=1` et `runtime_cleanup_unmount_failures=0` ;
- store eMMC et partition NVMe sains sous `e2fsck -f -n`, sans réparation ;
- relecture des données NVMe et absence de répertoire de secours sur eMMC ;
- GRUB restauré et `next_entry` vide ;
- aucun service Ubuntu en échec.

Le dernier heartbeat persistant indique `starts: 2`, `uptime: 163` et la même
identité. La partition NVMe reste non montée sous Ubuntu après les essais ;
aucune entrée permanente n'a été ajoutée au `fstab` Ubuntu.

Boot prototype du second essai : `b38fd41d-13cd-4364-990f-208925e422cf` ;
boot Ubuntu final : `a99ab05b-638f-4561-a543-083a6e0b2b6c`. La carte est sous
Ubuntu et aucun nouvel essai n'est programmé.

Traces locales :

- `artifacts/20261012T072300195627Z-finish-trial.log` : essai refusé sur le numéro de série ;
- `artifacts/20261012T073927608395Z-finish-trial.log` : premier boot réussi ;
- `artifacts/20261012T074514176332Z-finish-trial.log` : second boot et données conservées ;
- `artifacts/20261012T074603208079Z-check-recovered-board.log` : état Ubuntu final.

Empreintes du build validé :

- initramfs (17 716 136 octets) :
  `1041c946af9212b6f7e137c98c4109a90b8bad8d67bcab5d028290905c6b341e` ;
- core 0.1.2 :
  `23e48564e1c9f6f57c742ba104363fa88b0412f1af13dfea319083d29caa1e62` ;
- seed initial eMMC :
  `97ab5f5a2e737907cad2e0166712c79389515bbaa8163088d10217a31677452e`.

## Portée et suite

Ce jalon valide la persistance lors de redémarrages ordonnés. Les essais de
coupure d'alimentation et les migrations de schéma de données restent distincts.
Le jalon suivant, [mise à jour locale et rollback applicatif](local-updates.md),
est maintenant validé.
Les données permanentes NVMe ne seront pas automatiquement ramenées à un état
antérieur par un rollback des images applicatives.

Les chemins de configuration liés à la révision 0 dans ce premier jalon ont
depuis été remplacés par les config overlays natifs de Pantavisor.
Ubuntu et les 71 partitions constructeur eMMC restent préservés. La cible de
release pour `core` reste une image OCI consommée puis préparée pour Pantavisor/LXC.
