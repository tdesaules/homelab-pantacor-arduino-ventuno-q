# Première révision Pantavisor et conteneur persistant

Le jalon suivant, [réseau et SSH gérés par la révision](revision-network.md),
est également validé sur la carte. Cette page décrit le premier runtime, où
le superviseur fournissait encore DHCP et SSH.

## Résultat du 11 octobre 2026

La révision **0** atteint `DONE` et le conteneur LXC **diagnostic** atteint
`READY` sur la VENTUNO Q, avec le noyau constructeur `6.8.0-1084-qcom`.
Le redémarrage du conteneur conserve son compteur. Après le retour automatique
à Ubuntu, le fichier de stockage passe `e2fsck -f -n` sans réparation.

Ubuntu et les 71 partitions constructeur sont conservés. Le NVMe n'est pas
encore provisionné : la persistance de ce jalon utilise uniquement l'eMMC.

## Architecture du test

- `ventuno-init`, superviseur statique, est PID 1. Il lance Pantavisor 030 en
  mode embedded dans un namespace de montage privé.
- Ethernet DHCP et SSH par clé restent des services du superviseur, accessibles
  pendant la fenêtre de test via
  `ssh -F artifacts/diagnostic-ssh/config ventuno-diagnostic`.
- `pvstore.ext4` est un **fichier de 256 Mio** situé dans le répertoire de l'essai
  sous `/boot/pantavisor-diagnostic/` sur la racine Ubuntu. Il est attaché à
  `/dev/loop32` et monté sur `/storage` dans le runtime.
- Le store contient les objets SHA-256, leurs hardlinks sous `trails/0/`,
  le manifeste `trails/0/.pvr/json` et un `boot/grubenv` privé, distinct de celui
  qui sélectionne le démarrage Ubuntu.
- Le conteneur utilise un rootfs SquashFS Zstd et un overlay temporaire. Son
  programme C statique est PID 1 du conteneur et annonce `READY` au socket de
  contrôle Pantavisor. Il écrit `/data/boots` et un heartbeat JSON sur le volume
  permanent `/storage/disks/perm/diagnostic/data`.
- LXC limite la mémoire à 64 Mio et utilise un réseau `empty`. Ce conteneur de
  lab utilise encore AppArmor `unconfined` et apparaît avec le rôle `mgmt`.
- Le nettoyage commence à 160 secondes, le retour est prévu à 180 secondes,
  avec une alarme logicielle à 190 secondes et un watchdog matériel de 30 secondes
  alimenté par le superviseur. Pantavisor ne prend pas possession du watchdog.

## Essais matériels

### Premier essai runtime : défaut de démontage corrigé

Essai `27a41e2e5f394fd49e1fb7b83e7af015` : `READY`/`DONE`, compteur de 1 à 2 et
retour Ubuntu obtenus, mais un démontage échoue. `e2fsck -fn` retourne le code 4.
La configuration GRUB est restaurée avant que cette erreur soit signalée.

Le script `recover-runtime-store.sh` sauvegarde le fichier dans
`pvstore.before-journal-replay.ext4`, puis rejoue son journal avec `e2fsck -p`.
Le contrôle final est sain et le compteur 2 est conservé. Cette récupération
porte sur le seul fichier de test.

La correction détache explicitement les périphériques loop LXC liés aux objets
du store après l'arrêt des processus du namespace, avant le démontage du store
et de son support. Ces loops n'étaient pas automatiquement détachés à la fermeture.

### Second essai runtime : stockage propre

Essai **`0ec1c090206c49e6abdf285a48d04d92`** :

| Contrôle | Résultat |
| --- | --- |
| Révision / conteneur | `DONE` / `READY` |
| Redémarrage et arrêt du conteneur | Validés, état `STOPPED` observé |
| Compteur final persistant | **3**, après un redémarrage manuel supplémentaire |
| Contrôle runtime | `runtime_status_exit=0` |
| Nettoyage | `runtime_cleanup_unmount_failures=0` |
| Vérification ext4 sous Ubuntu | Saine, sans réparation |
| Dernier heartbeat persistant | `starts:3`, `uptime:142` |
| Retour Ubuntu | Automatique, configuration GRUB restaurée, `next_entry` vide |
| Wi-Fi | Aucune interface, modules radio exclus |

Le boot prototype est `a8da258b-8855-4609-b000-058378cd2d4d` ; le boot Ubuntu
de retour est `6bc842d0-62b7-4682-90a0-3d1bcfcf9e3c`. Aucun service systemd en
échec n'a été relevé lors du contrôle final.

Les assertions SSH ont ensuite été corrigées pour lire le champ JSON `status`
réel : la présence de `status_goal: READY` ne prouve pas que le conteneur est
déjà prêt. Le `READY` matériel a été confirmé manuellement ; le scénario QEMU
complet a été rejoué avec ces assertions corrigées.

## Reproduction locale

Après le build décrit dans [build-prototype.md](build-prototype.md) et le
provisionnement des clés décrit dans [ethernet-dhcp-ssh.md](ethernet-dhcp-ssh.md) :

```bash
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --trial --runtime \
  --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --output-dir artifacts/prototype-1084-runtime
python3 scripts/build-first-revision.py --output-dir artifacts/prototype-1084-runtime
python3 scripts/verify-prototype.py --output-dir artifacts/prototype-1084-runtime
python3 scripts/verify-first-revision.py --output-dir artifacts/prototype-1084-runtime
python3 scripts/test-network-boot.py --output-dir artifacts/prototype-1084-runtime
```

La création du store refuse d'écraser un fichier existant. `--replace-seed`
n'autorise que le remplacement d'un seed local encore conforme à son empreinte
enregistrée, pas celui d'un store ayant déjà servi.

Le test QEMU valide DHCP/SSH, le refus d'une mauvaise clé, `DONE`, `READY`,
le passage du compteur de 1 à 2 après redémarrage du conteneur, `STOPPED`, le
nettoyage sans échec et la lecture du compteur 2 après reboot. Les contrôles
ext4 du store et du disque support passent sans réparation.

Pour préparer un **nouvel** essai matériel, le transfert doit également préciser
`--output-dir artifacts/prototype-1084-runtime` : sa valeur par défaut désigne
encore la variante réseau seule. Le cycle utilise `transfer-trial.py`,
`install-trial.sh`, `start-bounded-trial.sh`, puis `finish-trial.sh`, avec
l'identifiant propre au nouvel essai et les contrôles de la procédure
[GRUB](grub-fallback.md). `finish-trial.sh` a déjà été exécuté pour les essais
ci-dessus et n'est pas idempotent.

## Traces et artefacts locaux

Les fichiers suivants sont conservés dans `artifacts/`, exclu de Git :

- `20261011T153231495242Z-finish-trial.log` : premier essai, défaut de nettoyage ;
- `20261011T153544527094Z-recover-runtime-store.log` : sauvegarde et récupération ;
- `20261011T154900309608Z-finish-trial.log` : second essai réussi ;
- `trials/0ec1c090206c49e6abdf285a48d04d92/` : manifestes et journaux SSH ;
- `prototype-1084-runtime/qemu-network-test/` : états runtime, console et store
  après le dernier scénario QEMU.

L'initramfs testé mesure **17 689 766 octets**, avec 105 modules et 29 firmwares.
Son SHA-256 est
`f21fa871ac7571fc6e78b1cd9bfc8b2bb9309681ff7f47114c8cdf193ae5a777`.
Le seed de 268 435 456 octets a pour SHA-256
`0a4ae66c3fd8594925769ea1e7b064e07567ccd2ecc2731c2f99b284c63b6752`.
Cette dernière empreinte identifie le seed initial, pas le store modifié pendant
un essai.

## Suite du portage

Ce jalon valide l'exécution d'une révision et la persistance d'un conteneur sous
supervision. L'intégration des services réseau/SSH à une révision est désormais
[validée](revision-network.md). Les prochaines étapes sont le passage progressif
à Pantavisor PID 1, le provisionnement des
données applicatives sur NVMe, puis les mises à jour locales et le rollback
transactionnel. Le retour ponctuel GRUB à Ubuntu ne valide pas ce rollback.
