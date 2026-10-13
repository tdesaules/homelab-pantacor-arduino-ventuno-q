# Core : connectivité, shell et administration

`core` remplace le conteneur expérimental `network`. Son premier jalon, version
**0.1.0**, fournit Ethernet DHCP, SSH Dropbear, BusyBox et les outils Pantavisor
`pvcontrol`/`pvcurl` ; il est archivé dans `artifacts/prototype-1084-core/`.
La variante courante utilise **0.7.0**, le [mode autonome](autonomous-boot.md) et
la [persistance NVMe](nvme-persistence.md). Elle inclut **Bash 5.3.20**,
avec terminaux SSH, redémarrage natif par `pvcontrol` et
[mises à jour locales applicatives](local-updates.md) validés.

Le propriétaire a retenu **Bash seul**. Le retrait de Nushell, préparé pour
0.3.1, a été livré dans **0.4.0**, avec une révision contenant uniquement core.
Le [conteneur diagnostic est décommissionné](container-access.md), ses données
et les anciennes révisions restant conservées.
La révision actuelle [`locals/k0s-os-070`](k0s-os.md) fournit
kubectl, k0sctl, k9s et l'administration native, avec 512 Mio
pour core. Les raccourcis `ventuno-*` ne sont plus installés dans son PATH.
Elle conserve cgroup v2 et la synchronisation NTP introduits pour
le cluster k0s avec core 0.5.0. L'image précédente
0.4.0 est conservée avec les résultats du [jalon de récupération](runtime-recovery.md).

## Vérifier Pantavisor depuis SSH

La session SSH arrive dans le conteneur `core`. Pour voir le runtime, la
révision et le PID 1 **hôte** observé par le gardien :

```sh
pvcontrol containers ls
pvcontrol steps show-progress current
# Vue courte du gardien :
cat /trial-status/guard.status
```

Les champs attendus sont `host_pid1_name=pantavisor`,
`host_pid1_exe=/usr/bin/pantavisor` et `pantavisor_pid=1`. Le mode autonome
affiche aussi `phase=autonomous` et `return_after=0`.

`cat /proc/1/comm` dans cette session affiche `init.lxc.static`, le PID 1 du
conteneur. `uname -r` identifie le noyau constructeur commun aux deux systèmes
et ne suffit pas à distinguer Ubuntu de Pantavisor.

## Architecture du premier jalon et ordre de démarrage

```text
Noyau constructeur + superviseur ventuno-init PID 1
└── Pantavisor embedded (namespace de montage privé)
    ├── groupe root : core, rôle mgmt, objectif READY
    └── groupe app  : diagnostic, rôle nobody, objectif READY
```

Le groupe `root` précède `app`. Sur le chemin de démarrage nominal, `core`
annonce `READY` après l'obtention du bail DHCP ; Pantavisor peut alors lancer
l'application. Chaque groupe dispose d'un timeout de 45 secondes. Ce mécanisme
est un ordonnancement de démarrage, pas une garantie de disponibilité permanente
du réseau : Pantavisor peut débloquer les groupes après un timeout au boot.

`core` conserve un namespace réseau partagé avec l'hôte pour configurer Ethernet.
Son rootfs SquashFS est accompagné d'un overlay temporaire, et son volume `/data`
est permanent. Le test utilise une limite mémoire de 128 Mio pour `core`,
64 Mio pour `diagnostic`.

Les deux conteneurs ont explicitement `restart_policy=container`, y compris
`core` dans le groupe `root`, afin de tester leur redémarrage indépendant.
Le choix de la politique de transition système finale reste à valider avec
les mises à jour de révision.

### Droits Pantavisor

- `core` possède le rôle `mgmt` et peut administrer les conteneurs via `pvcontrol`.
- `diagnostic` déclare le rôle `nobody` : il peut annoncer `READY`, mais un
  `GET /containers` depuis l'application reçoit **HTTP 403**.
- Pantavisor 030 affiche `nobody` sous la forme `roles: []` dans la réponse de
  statut ; le manifeste conserve bien `roles: ["nobody"]`.

Ce sont des rôles d'accès à l'API Pantavisor, pas des utilisateurs Unix. Le
programme applicatif reste exécuté comme root dans son conteneur de test.

Le bind en lecture seule `/diagnostic-data` dans `core` sert uniquement aux
vérifications du compteur et du heartbeat du lab. Le seed prépare ce répertoire
avant le démarrage de `core`, puisque l'application démarre ensuite.

## Sources, version et artefacts

| Élément | Emplacement |
| --- | --- |
| Version du composant | `meta-ventuno/conf/ventuno-core.inc` |
| Composition de l'image | `meta-ventuno/recipes-core/images/ventuno-core-image.bb` |
| Scripts du service et outils | `meta-ventuno/recipes-core/ventuno-core-service/` |
| Scripts DHCP/réseau partagés avec le diagnostic hôte | `meta-ventuno/recipes-core/ventuno-trial-guard/files/` |
| Cibles de build et versions des couches | `kas/ventuno-initramfs.yml` |
| Assemblage de la révision, groupes, rôles et volumes | `scripts/build-first-revision.py` |

La compilation ARM64 se fait sur le poste avec Podman/KAS/Yocto. Les résultats
sont déposés sous `artifacts/build/tmp/deploy/images/ventuno-q/` :

- `ventuno-core-image-ventuno-q.squashfs` ;
- `ventuno-core-image-ventuno-q.core-release.json` ;
- `ventuno-core-image-ventuno-q.manifest` : paquets et versions.

L'image contient `/etc/ventuno-core-release`, un document JSON comprenant le
nom, la version, le système de build et les empreintes des quatre scripts du
service. Le fichier `core-release.json` exporté en est une copie.

L'assemblage conserve également `core-build.json` et une entrée `core_image`
dans `build-inputs.json`, contenant le SHA-256 du SquashFS, l'identification
embarquée et l'empreinte du manifeste des paquets. Les versions des couches et
la configuration KAS sont déjà consignées dans `build-inputs.json`.

La version `0.1.0` identifie le composant en développement ; **le SHA-256 de
l'image identifie le build exact**. Les empreintes de scripts ne prétendent pas
identifier à elles seules toutes les entrées Yocto. L'historique Git du travail
local reste à enregistrer ; aucun tag de release n'a été créé pour ce jalon.

Les clés SSH et le profil MAC/DHCP sont fournis lors de l'assemblage de la
révision, montés en lecture seule depuis ses objets. Le rootfs générique `core`
est construit sans ces secrets ni identité matérielle. Les données permanentes
du test sont dans `/storage/disks/perm/core/data` sur le store eMMC de 256 Mio.

## Construire et vérifier

Après le [provisionnement des clés du lab](ethernet-dhcp-ssh.md) :

```bash
bash scripts/build-initramfs.sh
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --trial --runtime --core \
  --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --output-dir artifacts/prototype-1084-core
python3 scripts/build-first-revision.py --output-dir artifacts/prototype-1084-core
python3 scripts/verify-prototype.py --output-dir artifacts/prototype-1084-core --emulate
python3 scripts/verify-first-revision.py --output-dir artifacts/prototype-1084-core
python3 scripts/test-network-boot.py --output-dir artifacts/prototype-1084-core
```

Le builder refuse d'écraser un store existant. `--replace-seed` permet seulement
de remplacer un seed local dont l'empreinte initiale est encore intacte.
L'ancien argument d'assemblage `--revision-network` est un alias de `--core` ;
il produit désormais le composant `core`, pas l'ancien conteneur `network`.
Les anciennes images restent archivées dans leurs répertoires d'artefacts.

Pour un nouvel essai matériel, utiliser le
[cycle GRUB borné](grub-fallback.md), avec :

```bash
python3 scripts/transfer-trial.py --output-dir artifacts/prototype-1084-core
# Après installation et lancement de l'essai avec son nouvel identifiant :
python3 scripts/probe-diagnostic-ssh.py --trial-id NOUVEL_ID --core
python3 scripts/check-runtime-over-ssh.py --trial-id NOUVEL_ID --core
```

## Utiliser core pendant la fenêtre de test

Cette section décrit le jalon historique avec diagnostic. Pour l'image actuelle
et les commandes natives remplaçant les raccourcis, voir [OS k0s-ready](k0s-os.md).

```bash
ssh -F artifacts/diagnostic-ssh/config ventuno-diagnostic
```

Puis, dans le conteneur :

```sh
cat /etc/ventuno-core-release
cat /run/ventuno-dhcp.state
ventuno-revision-status
pvcontrol containers ls
ventuno-revision-status restart diagnostic
ventuno-revision-status restart core
```

La dernière commande coupe temporairement SSH. Reconnecter avec la même
configuration et vérifier `CORE_STARTS=2` et les statuts réels `READY`.
`ventuno-revision-status` affiche aussi la version embarquée. Avant la première
écriture de l'application, il affiche `APPLICATION_NOT_READY` à la place des
données applicatives ; cela ne bloque pas le signal de disponibilité de `core`.

## Validation du 11 octobre 2026

Le scénario QEMU complet valide :

- SSH authentifié et refus d'une mauvaise clé ;
- `core READY` avant le lancement de `diagnostic` ;
- révision `DONE`, deux conteneurs `READY`, groupes et rôles attendus ;
- refus HTTP 403 de l'API d'administration depuis `diagnostic` ;
- concordance entre l'identification embarquée et le manifeste de build ;
- redémarrage de `core` avec reconnexion SSH et compteur applicatif restant à 1 ;
- redémarrage de l'application, compteur 2, puis arrêt explicite ;
- retour automatique, stockage propre et compteurs relus à 2 après reboot.

L'essai matériel **`cf5e3670e0a1428ea52e43f85f1b6178`** a validé les contrôles SSH
à partir de **17:26:35 UTC** (horloge du poste), avec `192.168.1.20/24`. Le
heartbeat applicatif enregistre `management_http_status: 403`, tandis que
`core` peut effectivement redémarrer et arrêter les conteneurs.

Le journal matériel confirme `core READY` avant le premier lancement de
`diagnostic`. Le retour automatique Ubuntu a réussi avec :

| Contrôle | Résultat |
| --- | --- |
| Runtime | `runtime_status_exit=0` |
| Réseau hôte | `network_owner=core`, `host_network_pid=0` |
| Nettoyage | `runtime_cleanup_unmount_failures=0` |
| Store ext4 | `e2fsck -f -n` sain, sans réparation |
| Compteurs persistants relus | core **2**, application **2** |
| GRUB | empreinte initiale restaurée, `next_entry` vide |
| Ubuntu | aucun service en échec |

Boot prototype : `4810bc20-8d95-4d76-aef1-e47585c5be7e` ; boot Ubuntu de retour :
`265602c3-7fb6-48c6-978d-f7533f7ae30c`. La carte est revenue sous Ubuntu et aucun
nouvel essai n'est programmé.

Empreintes du build testé :

- initramfs (17 687 727 octets) :
  `f6644485954027b97b876dee957519ded70233f84202165ff2f7c58279df0908` ;
- rootfs `core` :
  `df13b4a529315e62982a06c3568e67cb557a0f0e8848cb9e60fed6a2e5b2af18` ;
- seed initial du store :
  `0dea6c56ff574f5a1121aa5847990583e59f14f65247b6c72f7a0f03e5ff345b`.

Les journaux SSH sont dans `artifacts/trials/cf5e3670e0a1428ea52e43f85f1b6178/`.
Les résultats QEMU sont dans `artifacts/prototype-1084-core/qemu-network-test/`.
Les contrôles de retour sont dans
`artifacts/20261011T172952235301Z-finish-trial.log` et
`artifacts/20261011T173012810368Z-check-recovered-board.log`.
Les horodatages de ces noms de fichiers sont ceux du poste ; la carte remet
son horloge à l'heure par NTP après le retour Ubuntu.

## Release finale : image OCI consommée

**Décision de cible : la release finale devra consommer une image OCI pour
`core`**, identifiée par son digest, puis préparée/importée pour l'exécution
Pantavisor/LXC. Le build direct Yocto → SquashFS sert au portage actuel.

La méthode de publication, le registre, l'import OCI et l'automatisation seront
revus après l'obtention d'un boot autonome viable. Ils ne sont pas implémentés
par ce jalon. Le découpage `core`/applications, les rôles et l'identification
des artefacts restent applicables quelle que soit la future chaîne de livraison.

Le [passage à Pantavisor PID 1](pantavisor-pid1.md) est maintenant validé dans
un essai borné, suivi d'une [qualification prolongée](prolonged-boot.md).
Le [provisionnement et la persistance NVMe](nvme-persistence.md) sont également
validés, ainsi que les [transitions locales et leur rollback](local-updates.md).
La configuration de core utilise désormais les config overlays de Pantavisor,
sans bind mounts fixés à la révision 0. Un [store durable et une entrée GRUB
stable](autonomous-boot.md) sont maintenant installés. La qualification longue
et les mises à jour du BSP/core restent à traiter.
