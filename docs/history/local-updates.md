# Mises à jour locales, rollback et shells de core

Le [jalon autonome](autonomous-boot.md) prolonge désormais ce scénario avec le
vrai GRUB, un store durable et des reboots directs. Cette page conserve le
premier cycle de validation, avec passage intermédiaire par Ubuntu.

Le prototype `artifacts/prototype-1084-updates/` utilise Pantavisor PID 1,
**core 0.2.0**, un store eMMC de test et les données applicatives sur NVMe.
Ce jalon ajoute les shells demandés et teste les révisions locales avec un
point de retour effectivement validé après reboot.

## Bash et Nushell

| Composant | Version | Construction |
| --- | --- | --- |
| Bash | **5.3.20** | GNU Bash 5.3 + correctifs officiels 001..020, compilation ARM64/musl par Yocto |
| Nushell | **0.116.1** | binaire officiel `aarch64-unknown-linux-musl`, archive vérifiée par SHA-256 |

Les versions ont été vérifiées sur les publications amont le 12 octobre 2026.
Références : [correctifs GNU Bash 5.3](https://ftp.gnu.org/gnu/bash/bash-5.3-patches/)
et [release Nushell 0.116.1](https://github.com/nushell/nushell/releases/tag/0.116.1).
Les recettes sont dans `meta-ventuno/recipes-core/shells/`, avec les empreintes
du tarball GNU, des 20 correctifs et de l'archive Nushell. Les licences sont
prises en compte par Yocto : GPL-3.0-or-later pour Bash, MIT pour Nushell.

L'archive Nushell officielle a pour SHA-256 :
`b103770c00bf322c409caa007aad44882d1cc5d24d82f719f877812ac33d6ad1`.
Le paquet installe le shell `nu` ; les plugins optionnels de l'archive ne font
pas partie du paquet de ce jalon.

Les exécutables sont `/usr/bin/bash` (également `/bin/bash`) et `/usr/bin/nu`.
Le shell POSIX des scripts système et de connexion reste BusyBox. Pendant un
boot de test, pour ouvrir les nouveaux shells :

```bash
ssh -t -F artifacts/diagnostic-ssh/config ventuno-diagnostic 'exec bash --noprofile --norc'
ssh -t -F artifacts/diagnostic-ssh/config ventuno-diagnostic 'exec nu --no-config-file'
```

Ou depuis le shell de connexion :

```sh
bash --version
nu --version
exec bash
# Ou : exec nu
```

Les tests vérifient les versions exactes, les tableaux associatifs et la
substitution de processus Bash, un pipeline JSON Nushell et l'allocation
d'un terminal SSH. `lxc.pty.max=16` a été ajouté à core pour permettre les
sessions interactives. Sa limite mémoire est maintenant **256 Mio**.

## Révisions préparées

`build-local-revisions.py` génère trois manifests et leurs objets :

| Révision | Binaire diagnostic | Comportement |
| --- | --- | --- |
| `locals/app-v1` | 1.0.0 | version initiale, annonce READY |
| `locals/app-v2` | 2.0.0 | nouvelle image SquashFS, annonce READY |
| `locals/app-unready` | 2.0.0-unready | s'exécute et écrit un heartbeat, mais n'annonce jamais READY |

Les variantes sont compilées par la recette `ventuno-diagnostic`. Chaque
révision locale ne change que l'objet `diagnostic/root.squashfs` ; le BSP,
core, les groupes, les rôles et le volume NVMe sont identiques. Les nouveaux
objets sont envoyés par `pvcontrol objects put`, puis les manifests par
`pvcontrol steps put`. Le runtime vérifie les empreintes lors de l'import.

Le heartbeat rapporte maintenant `application_version`, en plus du compteur
et de l'identité persistante. La révision système réellement active est
affichée séparément par `ventuno-revision-status` à partir des métadonnées
Pantavisor.

### Configuration indépendante de la révision 0

Les clés SSH et le profil réseau sont désormais des objets sous
`_config/core/...`. Pantavisor les matérialise dans le config overlay du
conteneur. Les bind mounts vers `/storage/trails/0/core/...` sont supprimés.
Le seed attribue à root les fichiers d'authentification et les répertoires
copiés dans cet overlay, même lorsque le build est rootless.

`ventuno-revision-status control ...` sérialise les commandes d'administration
avec les autres requêtes `pvcurl`, qui partagent des fichiers temporaires dans
core. Exemples pendant une fenêtre d'essai :

```sh
ventuno-revision-status control steps ls
ventuno-revision-status control steps show-progress locals/app-v2
ventuno-revision-status control cmd run locals/app-v2
ventuno-revision-status control cmd run locals/app-v1
```

## UPDATED, DONE et rollback

Le scénario distingue les états suivants :

1. **Mise à jour sans reboot** : `0 → locals/app-v2`. L'application devient
   2.0.0, le statut atteint `UPDATED`. Core et SSH restent en service.
2. **Retour manuel sans reboot** : `locals/app-v2 → locals/app-v1`. L'application
   redevient 1.0.0 et les données NVMe sont conservées.
3. **Préparation du point de retour** : réappliquer v2, attendre `UPDATED`,
   puis demander un reboot natif.
4. **Validation après reboot** : booter sur la révision indiquée par `pv_try`,
   attendre `DONE`. Pantavisor écrit `pv_rev=locals/app-v2` dans son grubenv
   privé ; v2 devient le point de rollback.
5. **Échec volontaire** : lancer `locals/app-unready`. Après le timeout de
   disponibilité de 45 secondes, Pantavisor enregistre `ERROR`,
   `Status goal not reached`, et déclenche son reboot de rollback.
6. **Reprise** : booter la révision validée indiquée par `pv_rev`. La v2 est
   `DONE` et `READY`, tandis que la mauvaise révision reste `ERROR`.

Une mise à jour à chaud `UPDATED` ne suffit donc pas à déclarer un nouveau
point de retour durable : le scénario vérifie bien le passage à `DONE` après
reboot et le grubenv privé.

### Articulation avec Ubuntu dans le lab

Ubuntu reste le choix GRUB par défaut. Chaque reboot du prototype revient sous
Ubuntu, où le store est vérifié et GRUB restauré. Un nouvel essai borné reprend
ensuite une **copie du store modifié**, sans effacer l'original.

`--resume-trial` et `--boot-revision` contrôlent cette reprise. Le helper exige :

- un essai précédent terminé avec démontages propres et un store ext4 sain ;
- le même noyau/initramfs et le même profil NVMe ;
- une révision sélectionnée `UPDATED` correspondant à `pv_try`, ou `DONE`
  correspondant à `pv_rev` ;
- uniquement des différences applicatives par rapport au manifeste usine.

La décision de réussite, le point de retour et le rejet de la mauvaise révision
proviennent de Pantavisor. Le choix de l'entrée one-shot suivante est effectué
par les outils de lab à partir de cet état. Ce n'est pas encore une installation
Pantavisor permanente qui enchaîne automatiquement tous ses boots sans passer
par Ubuntu. Le remplacement du BSP/core lors d'une mise à jour reste hors du
scénario applicatif testé ici.

### Arrêt propre lors d'un reboot imprévu par le minuteur

Le gardien marque AUTOCLEAR sur le loop du store une fois monté et sur les
loops d'images appartenant au runtime. `ventuno-storage-watch` observe leur
libération, puis démonte le NVMe et le support Ubuntu. Il agit aussi lorsque
Pantavisor redémarre pour un échec de mise à jour, avant le délai du gardien.
Le helper d'arrêt temporisé se limite à demander l'arrêt via l'API.

## Construction et test QEMU

```bash
bash scripts/build-initramfs.sh
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --trial --runtime --core --pid1 \
  --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --nvme-profile bsp/nvme-app-storage.json \
  --output-dir artifacts/prototype-1084-updates
python3 scripts/build-first-revision.py --output-dir artifacts/prototype-1084-updates
python3 scripts/build-local-revisions.py --output-dir artifacts/prototype-1084-updates
python3 scripts/verify-prototype.py --output-dir artifacts/prototype-1084-updates --emulate
python3 scripts/verify-first-revision.py --output-dir artifacts/prototype-1084-updates
python3 scripts/test-local-updates.py --output-dir artifacts/prototype-1084-updates
```

Comme pour les jalons précédents, `--replace-seed` ne peut remplacer qu'un seed
local encore conforme à son empreinte initiale. Le NVMe matériel est déjà
provisionné et ne doit pas être reformaté pour ce scénario.

Le cycle QEMU complet est archivé sous
`artifacts/prototype-1084-updates/qemu-updates-test/11d36226e3634458b3122b3e11ca210f/`.
Il couvre les trois boots, les shells, la continuité de core pendant les
transitions à chaud, la conservation de l'identité NVMe et les contrôles ext4
après chaque retour. Les compteurs applicatifs terminent à 4, 6 puis 7 sur
le disque neuf de la simulation.

## Reproduction matérielle

Pour le premier essai, préparer une fenêtre de 600 secondes et suivre le
[cycle GRUB borné](grub-fallback.md) :

```bash
python3 scripts/transfer-trial.py --output-dir artifacts/prototype-1084-updates --return-seconds 600
# Installer et lancer l'essai avec ID1, puis :
python3 scripts/probe-diagnostic-ssh.py --trial-id ID1 --core
python3 scripts/check-local-updates.py --trial-id ID1
# Après retour Ubuntu : finish-trial.sh avec ID1.
```

Le script déclenche le reboot après la préparation de v2. Le second essai
valide v2 puis lance la version non prête :

```bash
python3 scripts/transfer-trial.py --output-dir artifacts/prototype-1084-updates \
  --return-seconds 600 --resume-trial ID1 --boot-revision locals/app-v2
# Installer et lancer ID2, puis :
python3 scripts/probe-diagnostic-ssh.py --trial-id ID2 --core
python3 scripts/check-local-updates.py --trial-id ID2 --commit-from ID1
# Après le reboot automatique d'échec : finish-trial.sh avec ID2.
```

Enfin, vérifier le retour à la v2 validée :

```bash
python3 scripts/transfer-trial.py --output-dir artifacts/prototype-1084-updates \
  --resume-trial ID2 --boot-revision locals/app-v2
# Installer et lancer ID3, puis :
python3 scripts/probe-diagnostic-ssh.py --trial-id ID3 --core
python3 scripts/check-local-updates.py --trial-id ID3 --recover-from ID1
# Après retour Ubuntu : finish-trial.sh puis check-recovered-board.sh avec ID3.
```

Les compteurs attendus sont dérivés du premier relevé : le NVMe contient déjà
les données des essais précédents. Le fichier `updates-result.json` d'ID1
conserve ces attentes et l'identité de référence pour les trois phases.

Le suivi tolère les lectures de progression temporairement indisponibles
pendant une transition. Ce cas a interrompu deux relevés lors de la mise au
point matérielle ; les états persistants ont confirmé les transitions. Les
boucles ont été corrigées pour réessayer dans un délai borné. L'option
`--finish-prepared` permet de terminer une préparation de v2 interrompue côté
poste, après contrôle des preuves initiale/v2/v1 déjà enregistrées.

## Essais matériels du 12 octobre 2026

| Phase | Essai | Compteur application en fin de phase |
| --- | --- | ---: |
| v2, retour v1, v2 préparée | `b55f5cbfbc9c4c0d9dd8bbaa2ba7eea7` | 6 |
| v2 validée DONE, puis mauvaise révision | `d6cbb3ba8b394e9e905a6f8cd016150e` | 8 |
| Reprise de la v2 validée | `59d23adb92ef44229e32daccb6bb46bd` | 9 |

Le compteur initial était 3, après les deux boots du jalon NVMe. L'identité
**`7877e500-a853-430e-b506-a423eebb1ca1`** a été conservée. Les compteurs de core
progressent à 1, 2 puis 3, car les trois essais reprennent le même état logique
du store. Les versions Bash/Nushell et les sessions PTY ont été vérifiées sur
les trois boots.

Les preuves SSH et `shell-check.json` sont sous `artifacts/trials/<ID>/`.
La mauvaise révision est enregistrée `ERROR`, avec le message
`Status goal not reached` et le journal du timeout de 45 secondes.

### État final et traces de retour

Les trois retours ont conservé des systèmes de fichiers sains, vérifiés avec
`e2fsck -f -n` sur le store eMMC et le NVMe. Le dernier état persistant contient :

```text
pv_rev=locals/app-v2
locals/app-v2       DONE
locals/app-unready  ERROR: Status goal not reached
application_version=2.0.0
application_starts=9
core_starts=3
```

L'identité NVMe est inchangée, les démontages sont confirmés et
`runtime_cleanup_unmount_failures=0`. GRUB retrouve son empreinte initiale,
`next_entry` est vide et aucun service Ubuntu n'est en échec. La carte est
revenue sous Ubuntu, sans nouvel essai programmé.

Boot prototype final : `be1424e6-20a0-4fc1-bd13-5cd620c7e8dc` ; boot Ubuntu final :
`be20ff5f-96d8-4c10-a719-c60797c6dfa3`.

Journaux de fin d'essai :

- `artifacts/20261012T085953990347Z-finish-trial.log` : v2 `UPDATED`, `pv_try=locals/app-v2` ;
- `artifacts/20261012T090448519772Z-finish-trial.log` : v2 `DONE`, mauvaise révision `ERROR` ;
- `artifacts/20261012T091406150828Z-finish-trial.log` : reprise de v2, données conservées ;
- `artifacts/20261012T091507194150Z-check-recovered-board.log` : état Ubuntu final.

Les copies de reprise sont tracées dans `resume-store.json` pour chaque nouvel
essai. La première sélection provient de `pv_try`, la seconde de `pv_rev` ;
les stores précédents sont conservés dans leurs répertoires de boot.
Les **26 tests unitaires** passent, notamment les contrôles de sélection GRUB,
de version/révision réellement stable et les reprises après réponse transitoire.

Empreintes des artefacts initiaux utilisés pour ce cycle :

- initramfs (18 093 831 octets) :
  `3c37280e6f43dd3e46e629e64ad95ed687d5d9f099d6d736d579137395d3c527` ;
- rootfs core 0.2.0 :
  `1ece0d158d5292fec90353f82bcdacead2a3adfe0cc90ea746adadbe8491cbb3` ;
- seed initial de 256 Mio :
  `97d564946b4bffb9772bad3dda09dbd2fb60141577d538a85f15e635db95b543`.

Les stores de reprise ont naturellement d'autres empreintes, car ils contiennent
les révisions importées, leur progression et les données de core.

## Suite

Les données NVMe sont permanentes : le rollback restaure les images, pas un
ancien contenu de `/data`. La compatibilité des données lors de changements
de schéma devra être traitée pour chaque application.

La consommation d'une image OCI pour core reste la cible de release. La
distribution, l'automatisation et le démarrage permanent avec sélection native
des révisions pourront s'appuyer sur ce jalon applicatif validé.
