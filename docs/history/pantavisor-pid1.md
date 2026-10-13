# Pantavisor PID 1 avec core et retour borné

La [qualification prolongée de 15 minutes](prolonged-boot.md) complète désormais
ce premier jalon. Elle utilise le gardien version 4 avec une durée explicitement
configurable ; cette page conserve le premier essai PID 1 de 180 secondes.

Le prototype `artifacts/prototype-1084-pid1/` exécute Pantavisor 030 comme
**PID 1 de l'hôte**, avec `core` **0.1.1** et l'application `diagnostic` dans
la révision 0. Le noyau reste le BSP constructeur `6.8.0-1084-qcom`.

## Architecture

```text
GRUB one-shot → noyau → bootstrap statique /init
                        ├── fork : gardien ventuno-guard, délai + watchdog
                        └── exec : Pantavisor, conserve le PID 1
                            └── pv-main-loop
                                ├── root : core (mgmt)
                                └── app  : diagnostic (nobody)
```

Le bootstrap crée les montages nécessaires à la collecte, vérifie le marqueur
de l'essai sur l'eMMC et attend que le gardien indépendant soit armé. Il prépare
le fichier `pvstore.ext4` sur `/dev/loop32`, puis se remplace par Pantavisor via
`exec`. Pantavisor est donc réellement PID 1, pas un enfant du superviseur.

Le gardien reste un processus enfant dans le namespace de montage initial.
Pantavisor et son runtime utilisent un namespace de montage privé, dans le
même namespace PID hôte. Cette séparation protège les fichiers de suivi du
gardien lorsque Pantavisor recrée `/run` et les autres montages précoces.

Le gardien alimente le watchdog matériel (30 secondes sur la carte), demande
l'arrêt à 160 secondes, et conserve le retour de secours à 180 secondes avec
une alarme indépendante à 190 secondes. `PV_WDT_MODE=disabled` évite que
Pantavisor entre en concurrence avec le gardien pour le watchdog pendant l'essai.

### Configuration et montages précoces

Pantavisor ignore l'option `--config` lorsqu'il est PID 1. L'assemblage `--pid1`
installe donc la configuration embedded dans **`/etc/pantavisor.config`**,
avec le stockage `/dev/loop32`, la gestion locale et le debug SSH hôte désactivé.

Le bootstrap libère ses copies de `/run`, `/dev/pts`, `/dev`, `/sys` et `/proc`
avant l'exécution de Pantavisor. Ses descripteurs console passent par un nœud
temporaire dans l'initramfs. Cela laisse Pantavisor créer ses propres montages,
notamment devtmpfs ; un premier essai QEMU avait révélé un échec `Resource busy`
sur `/dev` lorsque ces montages étaient conservés.

### Vérifier le PID 1 depuis core

Dans une session SSH, `/proc/1` désigne toujours le PID 1 **du conteneur**, soit
`init.lxc.static`. Le gardien relève le nom et l'exécutable du PID 1 **hôte**
et publie ses observations dans un tmpfs partagé, monté en lecture seule dans
`core` sous `/trial-status` :

```sh
cat /trial-status/guard.status
ventuno-revision-status
```

Les contrôles attendent notamment :

```text
supervisor_version=3
pantavisor_pid=1
host_pid1_name=pantavisor
host_pid1_exe=/usr/bin/pantavisor
```

Le `guardian_pid` doit être distinct de 1. `core` 0.1.1 ajoute cette section
optionnelle à l'outil de statut ; sa version et ses empreintes restent
consultables dans `/etc/ventuno-core-release`.

## Arrêt normal et secours

`ventuno-pid1-shutdown` prépare l'arrêt du stockage de test :

1. Arrêter `diagnostic` puis `core` via l'API Pantavisor.
2. Attendre le démontage des volumes et libérer uniquement les loops réservés
   qui référencent les objets de ce store.
3. Marquer loop32 en AUTOCLEAR alors que `/storage` est encore monté.
4. Demander **`pvcontrol cmd reboot`** à Pantavisor.
5. Observer le détachement de loop32 après le démontage natif de `/storage`,
   enregistrer la preuve persistante et libérer le support Ubuntu.

Pantavisor arrête ses services internes, démonte son stockage, synchronise et
demande le redémarrage au noyau. Le gardien reste disponible si ce chemin se
bloque. Le helper de nettoyage de l'ancien prototype, qui terminait les processus
du runtime enfant, n'est pas utilisé sur le PID 1.

Cette préparation des loops est liée au **store de test dans un fichier** sur
la racine Ubuntu. Elle ne constitue pas encore le schéma de stockage final.

## Construction et tests locaux

Avec les [clés du lab](ethernet-dhcp-ssh.md) déjà provisionnées :

```bash
bash scripts/build-initramfs.sh
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --trial --runtime --core --pid1 \
  --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --output-dir artifacts/prototype-1084-pid1
python3 scripts/build-first-revision.py --output-dir artifacts/prototype-1084-pid1
python3 scripts/verify-prototype.py --output-dir artifacts/prototype-1084-pid1 --emulate
python3 scripts/verify-first-revision.py --output-dir artifacts/prototype-1084-pid1
python3 scripts/test-pid1-guard.py --output-dir artifacts/prototype-1084-pid1
python3 scripts/test-network-boot.py --output-dir artifacts/prototype-1084-pid1
```

Le store existant reste protégé : `--replace-seed` ne remplace qu'un seed local
conforme à son empreinte initiale.

Deux scénarios QEMU ont réussi sur l'image finale :

- **Cycle normal** : PID 1 observé, DHCP/SSH, mauvaise clé refusée, `core READY`
  avant l'application, révision `DONE`, droits distincts (HTTP 403 côté app),
  redémarrages, persistance, arrêt natif et contrôles ext4 du store et du support
  sans réparation. Le marqueur de nettoyage natif est présent et le marqueur
  de retour de secours du gardien est absent.
- **Bootstrap bloqué** : `ventuno_pid1_test_stall=1` bloque le bootstrap après
  armement du gardien et annule son alarme PID 1. Le gardien seul provoque le
  retour, observé après environ **30,5 secondes** pour un délai configuré de
  25 secondes, temps de boot QEMU compris. Le support ext4 reste sain.

Ce test de panne porte sur le bootstrap avant `exec`, pas sur toutes les
catégories possibles de blocage du noyau ou du matériel.

## Essai sur la VENTUNO Q

Essai **`f9e2ef69a473455db6d71a7d71ce0e63`**, le 11 octobre 2026. SSH est devenu
accessible à **17:49:09 UTC** (horloge du poste), avec `192.168.1.20/24`.

Le gardien observé est PID **181**, distinct de Pantavisor PID **1**, avec le
watchdog matériel armé à 30 secondes. Les contrôles SSH ont confirmé :

- `core` dans `root`, rôle `mgmt`, et `diagnostic` dans `app`, rôle `nobody` ;
- les deux conteneurs `READY` et la révision `DONE` ;
- la version embarquée `core` 0.1.1 et le vrai exécutable du PID 1 hôte ;
- le refus HTTP 403 de l'administration depuis l'application ;
- le redémarrage de `core`, la reconnexion SSH et la continuité de l'application ;
- le redémarrage applicatif, puis son arrêt explicite ; les compteurs valent 2.

Pour préparer un nouvel essai, transférer avec
`transfer-trial.py --output-dir artifacts/prototype-1084-pid1`, suivre le
[cycle GRUB borné](grub-fallback.md), puis utiliser les outils SSH avec `--core`.
Le contrôle runtime lit `pid1_runtime` dans le manifeste local de l'essai et
exige automatiquement les preuves du PID 1 hôte.

Les traces SSH sont dans `artifacts/trials/f9e2ef69a473455db6d71a7d71ce0e63/`.
Les scénarios QEMU sont archivés dans `qemu-network-test/` et
`qemu-pid1-guard-test/` sous le répertoire de ce prototype.

### Retour Ubuntu et empreintes

Le retour automatique a réussi. Le contrôle final a confirmé :

| Contrôle | Résultat |
| --- | --- |
| PID 1 hôte | `pantavisor`, `/usr/bin/pantavisor` |
| Demande de reboot via Pantavisor | `pantavisor_reboot_requested=1` |
| Démontage natif du store | `pantavisor_storage_unmounted=1` |
| Nettoyage | `runtime_cleanup_unmount_failures=0` |
| Store ext4 après retour | sain, sans réparation (`e2fsck -f -n`) |
| Compteurs persistants | core **2**, application **2** |
| GRUB | configuration antérieure restaurée, `next_entry` vide |
| Ubuntu | aucun service en échec |

Boot prototype : `c0eb4210-f76d-4df7-a55b-3b39030b6c3b` ; boot Ubuntu de retour :
`9a121e37-5db0-4606-9570-07f766660391`. La carte est revenue sous Ubuntu et
aucun nouvel essai n'est programmé.

Traces de retour :

- `artifacts/20261011T175216149030Z-finish-trial.log` ;
- `artifacts/20261011T175234629739Z-check-recovered-board.log`.

Les noms de fichiers sont horodatés par le poste ; l'horloge de la carte est
resynchronisée par NTP après le retour. Le marqueur initial `PID1_NAME=ventuno-init`
décrit le bootstrap avant `exec`. Les champs `HOST_PID1_NAME`/`HOST_PID1_EXE`
enregistrés ensuite décrivent le PID 1 réellement en service.

Empreintes de l'image testée :

- initramfs (17 691 350 octets) :
  `cef7988ff2a24abacaa2e7a8ab1435ac75914e15e4d8131d9b3e1280162fb641` ;
- rootfs core 0.1.1 :
  `89912d72735fffa7c88f8258ded0eb1a247f44c3fd3bbf157ea8577622b5c44d` ;
- seed initial de 256 Mio :
  `ef606b741edbb8abcd674674a796cc653d2aafe2e5477e9ad451e2318d5535f4`.

## Suite

Le jalon valide Pantavisor PID 1 avec une révision fonctionnelle, dans une fenêtre
de test bornée. Ubuntu reste le système par défaut. Une première qualification
prolongée est maintenant [validée](prolonged-boot.md), ainsi que
[l'intégration des données NVMe](nvme-persistence.md). Les mises à jour/rollback
locaux applicatifs sont également [validés](local-updates.md). Les partitions
constructeur sont préservées.

La cible de release reste **une image OCI consommée pour core**. Le choix du
registre, la distribution et l'automatisation seront repris après qualification
du boot autonome ; ce jalon conserve la construction Yocto/SquashFS.
