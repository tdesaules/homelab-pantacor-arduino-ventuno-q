# Prototype ARM64 : initramfs Pantavisor et BSP constructeur

Le prototype courant valide [le démarrage autonome et le store durable](autonomous-boot.md),
construite sur le [diagnostic réduit 1084](diagnostic-boot-1084.md).
Les commandes d'assemblage avec `--runtime --core --pid1 --autonomous --nvme-profile` et les résultats
sont sur cette page. KAS construit désormais aussi `ventuno-core-image`, le
rootfs SquashFS du conteneur d'administration.
Le résultat du premier build 1078 est conservé à la fin de cette page comme
historique ; ses artefacts restent disponibles séparément.

## Choix de construction

- Pantavisor **030**, commit `48c582334875dde17634973049885c7ab6049116`.
- meta-pantavisor **030**, commit `cac393c28b0e44c5229fef6f1c516c3ec6bc87bb`.
- Yocto **Scarthgap**, couches figées dans `kas/ventuno-initramfs.yml`.
- Environnement KAS **4.8.2** sous Podman rootless, image figée par digest dans
  `scripts/build-initramfs.sh`. Le mapping UID/GID 30000 correspond à `builder`
  dans cette image et conserve la propriété des fichiers sur le poste.
- Machine `ventuno-q` : ARMv8-A générique, sans compiler de noyau Yocto ; le noyau
  et ses modules sont assemblés séparément à partir d'une capture de la carte.

La compilation se fait sur le poste x86_64, avec cross-compilation ARM64 et musl.
La carte n'est pas utilisée pour compiler.

## Composants BSP

```bash
python3 scripts/fetch-bsp.py
python3 scripts/prepare-vendor.py
```

Les téléchargements vérifiés restent dans `artifacts/vendor/`, les extractions
dans `artifacts/vendor-extracted/`. L'extraction n'exécute aucun script Debian.
Elle refuse d'écraser une extraction existante.

Le firmware Dragonwing `20260612` n'est plus disponible dans le pool APT du PPA.
L'URL d'archive Launchpad est issue de l'API `binaryFileUrls` de la publication
source `18497276`. Son contenu correspond au SHA-256 précédemment relevé sur
la carte. Les overrides Wi-Fi WCN6855 sont inclus dans ce paquet.

### Différence entre les paquets disponibles et la carte

La configuration noyau est identique, mais le noyau et les modules téléchargés
diffèrent des fichiers installés malgré leur même version `6.8.0-1078.83`.
Ce n'est pas uniquement une différence de compression : les noyaux décompressés
diffèrent aussi. L'origine précise de cette reconstruction reste à déterminer.

| Noyau compressé | SHA-256 |
| --- | --- |
| Carte | `5d62cbadebd18daef88d96fe5e1c9bb4151174425aaff3aaf58ecce5260f285c` |
| Pool Ubuntu | `0933182c81547ee65f1cf46ad7c7b09f5dfc770ee8824ff14bdd6782b5e64109` |

`dpkg --verify` ne signale pas de différence du noyau/modules par rapport à la
base dpkg locale, mais signale quatre fichiers firmware modifiés (QCA2066 et
Bluetooth). La capture préserve l'ensemble installé, modifications comprises.
Le premier prototype utilise donc **la capture de la carte**, pas les paquets
Ubuntu téléchargés. Ces paquets restent une référence distincte.

## Référence du démarrage Ubuntu

```bash
python3 scripts/export-boot-reference.py
python3 scripts/export-boot-reference.py --bsp
```

Cette collecte SSH archive `/boot`, la configuration GRUB, le FDT actif, le
descriptif GPT et les entrées EFI dans `artifacts/board-reference/`. Elle ne
modifie pas la carte. **Ce n'est pas une sauvegarde complète de l'eMMC**, de
`persist`, ni des partitions de firmware Qualcomm. Le FDT actif contient les
modifications apportées au boot ; il sert à l'analyse et n'est pas installé
comme DTB statique dans le prototype.

L'option `--bsp` produit `board-bsp-reference.tar.gz` avec en plus les modules,
les firmwares et la configuration modprobe installés. La première capture est
figée dans `bsp/board-reference.json`, la capture courante dans
`bsp/board-reference-20261010-updated.json`. L'option `--output-dir` permet de
conserver une nouvelle capture séparément. Une nouvelle capture n'est
pas automatiquement équivalente : son empreinte devra être examinée et mise
à jour explicitement. Le script refuse d'écraser une capture existante.

## Compilation

```bash
bash scripts/build-initramfs.sh
```

Pour une compilation détachée :

```bash
bash scripts/build-initramfs.sh --detach
podman logs -f ventuno-kas
podman inspect ventuno-kas --format '{{.State.Status}} {{.State.ExitCode}}'
```

Le nom du conteneur évite deux builds simultanés sur le même répertoire.
Après un build détaché terminé, retirer son conteneur avant de relancer :

```bash
podman rm ventuno-kas
bash scripts/build-initramfs.sh --detach
```

Les caches et résultats restent dans `artifacts/` ; le premier build compile
aussi les outils natifs et la toolchain. La configuration utilise 12 tâches
BitBake et `make -j12`.

L'isolation SELinux du conteneur de build est désactivée pour le bind mount
du workspace ; le conteneur reste rootless et ne reçoit aucun périphérique de
la carte ni socket du moteur de conteneurs.

## Assemblage

Après succès du build, utiliser le fichier `pantavisor-initramfs-*.cpio.gz`
du répertoire `artifacts/build/tmp/deploy/images/ventuno-q/` :

```bash
python3 scripts/assemble-prototype.py CHEMIN_DU_FICHIER_INITRAMFS.cpio.gz
python3 scripts/verify-prototype.py
```

L'assemblage courant crée dans `artifacts/prototype-1084/` :

- le noyau `vmlinuz-6.8.0-1084-qcom` ;
- `vendor-addon.cpio.gz` contenant les modules, leurs index depmod et les firmwares ;
- `initramfs-ventuno-q.cpio.gz`, concaténation des deux archives gzip/cpio ;
- `SHA256SUMS` et `build-inputs.json`.

Linux accepte plusieurs archives cpio compressées concaténées dans un initramfs.
L'addon reprend une sélection explicite de modules et firmwares depuis la
capture locale vérifiée par SHA-256. La sélection et ses dépendances sont
documentées dans `diagnostic-boot-1084.md`. Kmod est construit avec Zstd pour lire les
modules `.ko.zst` Ubuntu. Les licences des paquets restent dans les extractions
et devront accompagner une éventuelle distribution des artefacts.

Le vérificateur contrôle les empreintes, les deux archives concaténées, les
exécutables ARM64, les chargeurs et bibliothèques dynamiques nécessaires,
la configuration standalone et la présence des modules/firmwares requis.
Le parseur cpio est testé contre des archives produites par GNU cpio :

```bash
python3 -m unittest discover -s tests -v
```

## Limites du premier prototype

La configuration sélectionne **standalone**, le mode diagnostic de Pantavisor,
avec le backend GRUB, `PV_CONTROL_REMOTE=0` et un stockage cible `LABEL=pvstore`.
Cette partition n'est pas provisionnée sur la carte et n'est pas requise par
le chemin standalone, qui s'arrête au diagnostic avant l'initialisation du
stockage. Le prototype n'est pas une image de production ni un fichier à
flasher directement.

Le partage du bus D-Bus système entre conteneurs (`xconnect-dbus-systembus`)
est désactivé pour ce prototype : son ajout implicite faisait échouer la
création du rootfs minimal sur la dépendance `shadow-base`, exclue par poky-tiny.
Les fonctionnalités autogrow, runc et tailscale sont également retirées.

Le boot expérimental, le retour Ubuntu et une révision embedded sur stockage
de test sont désormais validés : voir [le compte rendu runtime](first-revision.md).
L'intégration du réseau/SSH à une révision est également
[validée](revision-network.md), ainsi que [Pantavisor PID 1](pantavisor-pid1.md).
Une [qualification prolongée](prolonged-boot.md) et la
[persistance NVMe](nvme-persistence.md) ont réussi, ainsi que les
[mises à jour locales applicatives et leur rollback](local-updates.md).
Le [store durable et le démarrage autonome](autonomous-boot.md) sont également
validés, avec Ubuntu par défaut. Les mises à jour du BSP/core et la qualification
longue de ce mode restent à traiter.

Les commits, paquets et image de build sont figés. La reproductibilité binaire
bit à bit doit encore être mesurée par deux builds indépendants ; les outils
hôte d'assemblage (tar, cpio, depmod, Python) ne sont pas encore isolés par digest.

## Historique : premier résultat 1078 du 10 octobre 2026

La compilation Yocto s'est terminée avec un code zéro. L'artefact de base est
`pantavisor-initramfs-ventuno-q-20261010104755.cpio.gz` (6 404 667 octets).
Le lien stable désigne désormais le build courant. Pour assembler et vérifier
le nouveau prototype, utiliser :

```bash
python3 scripts/assemble-prototype.py artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz
python3 scripts/verify-prototype.py
```

| Artefact | Taille en octets |
| --- | ---: |
| `vmlinuz-6.8.0-1078-qcom` | 17 764 826 |
| `vendor-addon.cpio.gz` | 873 234 062 |
| `initramfs-ventuno-q.cpio.gz` | 879 638 729 |

Cette taille importante vient de l'inclusion de tous les firmwares et modules
installés. Elle n'est pas la cible de taille de la V1. Le rootfs de base est
accompagné d'un manifeste des paquets et d'un SBOM SPDX produits par Yocto.

Les contrôles ont confirmé :

- `/init` pointe vers le binaire ARM64 `/usr/bin/pantavisor` ;
- BusyBox et modprobe/kmod sont ARM64 ;
- les chargeurs et dépendances dynamiques examinés sont présents (11 ELF),
  avec Zstd dans la chaîne de dépendances ;
- la configuration standalone/GRUB est effectivement présente dans l'archive ;
- les index depmod, modules essentiels et firmware WCN6855 sont présents ;
- les trois tests du lecteur cpio passent (concaténation gzip, données tronquées,
  en-tête invalide).

Deux assemblages successifs à partir du même rootfs et de la même capture ont
produit les mêmes empreintes :

```text
7426ddb2e2f51568d00dcbeea70ccecdb64982780cfc436ea1e5f80783386728  vendor-addon.cpio.gz
618b2d135e1eef1b907a7d4c58057080031747f84e684c3a96d8bd8f4642f201  initramfs-ventuno-q.cpio.gz
```

Cela valide la répétabilité de l'assemblage sur ce poste, pas encore celle de
deux compilations Yocto indépendantes.

Ces contrôles sont statiques. Ils ne valident ni le chargement de cet initramfs
par GRUB, ni le boot de la carte, ni l'exécution de LXC/Pantavisor sur le matériel.
