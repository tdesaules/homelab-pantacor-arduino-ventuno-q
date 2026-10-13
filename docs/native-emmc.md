# Boot eMMC indépendant d'Ubuntu

## Contrat `emmc-file-store-v1`

La première implémentation conserve la table de partitions constructeur :

| Partition matérielle | Usage |
| --- | --- |
| `mmcblk0p69`, ESP FAT de 512 Mio | `EFI/ventuno/bootaa64.efi` et `recoveryaa64.efi` |
| `mmcblk0p70` et autres partitions constructeur | Conservées |
| `mmcblk0p71`, ext4 | Arbre système Pantavisor et store fichier |
| NVMe ext4 | Données k0s, inchangées |

Le runtime monte p71 sur `/mnt/pv-system`. Le fichier
`/boot/pantavisor/pvstore.ext4` reste utilisé par Pantavisor via loop32 ; son
format n'est pas changé en même temps que la chaîne de démarrage. Le store
préparé fait 4 Gio par défaut, réglable avec `--store-mib`.

Le chargeur principal contient sa configuration GRUB et **une copie complète du
noyau et de l'initramfs de secours**. L'EFI de secours dédié contient la même
récupération, sans sélection de la partition système. Aucun module GRUB,
noyau, initramfs ni fichier Ubuntu de p71 n'est nécessaire pour le secours.

Le verrou de récupération est armé avant de lancer le noyau normal. La politique
de santé, de tentative unique de révision et de budget de démarrages est réutilisée.
Une erreur de persistance de l'environnement retourne au menu embarqué en mémoire,
plutôt qu'à un `grub.cfg` sur le système potentiellement défaillant.

## Secours

Le secours démarre en RAM avec console locale et SSH par clé. Il charge les
drivers Ethernet et inclut `e2fsck`. Il ne monte automatiquement ni le système
eMMC ni le NVMe ; l'opérateur peut les examiner et réparer explicitement.
L'accès SSH utilise la clé publique et la clé d'hôte du rendu privé.
Les EFI générés sont donc **privés** et ne doivent pas être publiés sur GHCR.

L'indépendance vis-à-vis de p71 ne protège pas d'une ESP ou d'une eMMC entièrement
illisible. Une copie de l'EFI de secours sur un média externe et la procédure
constructeur restent les chemins à qualifier pour ce cas.

## Préparation locale

Construire un nouveau bundle base incluant `ventuno-native-guard` et
`ventuno-native-bootctl`, puis effectuer le rendu :

```sh
python3 -m tools.pvbuild render --profile base --bundle dist/base \
  --override release/overrides/emmc-native.json \
  --device devices/<nom>.local.json --output dist/native-state
python3 -m tools.pvbuild native-package --state dist/native-state \
  --system-uuid <UUID-p71> --grub-modules <répertoire-arm64-efi> \
  --output dist/native-installation
```

Pour k0s, sélectionner `--profile k0s`, fournir les deux bundles et les paramètres
NVMe. Les règles de ressources restent celles de la composition.

`native-package` exige GNU cpio, e2fsprogs, `grub-mkstandalone` et les modules
GRUB ARM64. Le paquet public de référence des modules est verrouillé dans
`release/native-boot-tools.lock.json` ; vérifier son SHA-256 avant extraction.
L'image locale `tools/Containerfile` fournit les outils de construction, auxquels
on passe le répertoire de modules extrait. Elle ne requiert pas de capture GRUB
de la carte.

La sortie contient :

- `system/` : fichiers destinés à p71, store neuf et environnements GRUB ;
- `esp/EFI/ventuno/` : les deux EFI autonomes ;
- `recovery/` : entrées de construction du secours ;
- `installation.json` : UUID attendu, identité d'installation et empreintes.

La commande n'écrit aucun périphérique et ne modifie pas les variables UEFI.
Elle ne copie pas le contenu de l'ancien store : la migration d'une installation
existante doit préserver explicitement les données que l'on veut conserver.

## Qualification VM

Préparer un état avec une clé SSH de test, un UUID fictif et sans NVMe pour le
profil base. Passer `--emulated` à `native-package`, puis :

```sh
python3 -m tools.pvbuild native-test --package dist/native-installation \
  --state dist/native-state --ssh-key <clé-privée-de-test> \
  --output artifacts/native-qualification
```

Le test utilise UEFI et le véritable EFI généré, des disques fichiers neufs,
des ports SSH locaux et des clés d'hôte vérifiées. Scénarios implémentés :
partition système absente, illisible, store absent, environnement GRUB invalide,
boot nominal, reboot avec persistance puis sélection du secours.
Les consoles et résultats sont conservés dans le répertoire de sortie.

Le secours corrigé vérifie aussi l'exécution d'une commande sur la console série.
Le build doit inclure `setsid` ; les images antérieures au correctif ne satisfont
plus les contrôles de packaging. Cette correction a été reconstruite et déployée
avec [la plateforme native](history/native-platform-20261013.md).

### Résultats du 13 octobre 2026

Qualification locale réussie sur QEMU ARM64/UEFI, avec le noyau public 1084,
un store neuf de 1 Gio et la révision `locals/0.1.0` du profil base :

| Scénario | Résultat |
| --- | --- |
| Partition système absente | Secours et SSH accessibles |
| Partition système illisible | Secours et SSH accessibles |
| Store Pantavisor absent | Secours et SSH accessibles |
| Environnement GRUB invalide | Secours et SSH accessibles |
| Démarrage nominal et reboot | Core prêt, boot ID changé, compteur permanent 1 → 2 |
| Sélection explicite du secours | Reboot vers le secours, volumes persistants non montés |
| Coupure brutale avant la validation de stabilité | Au boot suivant, secours sélectionné par le verrou persistant |
| EFI de secours dédié, sans disque système | Secours et SSH accessibles |
| Vérification après reboot normal | `e2fsck -f -n` réussi sur le système et le store interne |

Preuves locales : `artifacts/native-qualification-01/` et
`artifacts/native-qualification-02/`, chacun avec consoles et `results.json`.
Bundle : `dist/base-native/` ; rendu privé : `dist/native-state/` ; paquet de
test : `dist/native-installation/`. Le secours expose e2fsck 1.47.0 et aucun
montage eMMC/NVMe automatique n'a été observé.

Cette qualification concerne le profil base émulé. Elle ne qualifie pas encore
le firmware constructeur, le boot natif matériel avec k0s, la réparation effective
après corruption, ni une coupure pendant le déploiement des fichiers de boot.
`native-test --scenario <nom>` permet de rejouer un scénario ciblé.

## Passage sur matériel

Le [premier secours a été qualifié sur matériel](history/native-recovery-20261013.md) :
boot depuis l'ESP, SSH, identification de p69/p71 et du NVMe, e2fsck en lecture
seule et retour à l'installation initiale. La [migration du runtime natif avec
k0s](history/native-platform-20261013.md) est maintenant effectuée et qualifiée.
Les fichiers Ubuntu sont conservés pour le retour arrière ; ils ne sont plus
utilisés par la chaîne native.

Le firmware n'a pas conservé les entrées ajoutées par `efibootmgr`, même en
position secondaire. Le chemin matériel validé conserve le premier étage
reconnu sous `EFI/ubuntu`, puis lance l'EFI autonome directement depuis l'ESP.
La première redirection de test consommait un indicateur GRUB sur FAT avant le
lancement ; son bootstrap original a été restauré à la fin de cet essai. La
migration suivante a installé le dispatcher natif permanent.

Pour une migration, préparer p71 hors ligne depuis Ubuntu ou le secours. Le chemin
`/boot/pantavisor` est déjà occupé par le lab : conserver l'installation précédente
avant d'y déposer l'arbre natif. Les EFI vont dans leur répertoire dédié,
sans écraser les chargeurs constructeur. L'adaptateur de migration utilise la
redirection ESP validée plutôt que supposer que `BootNext` est utilisable.

Après qualification du boot natif et du retour au secours, les fichiers de
l'userspace Ubuntu peuvent être retirés hors ligne. Aucun repartitionnement ni
reformatage du NVMe n'est nécessaire. Les mises à jour BSP/ESP atomiques et leurs
essais de coupure restent à qualifier ; la qualification du boot initial ne
couvre pas ce cycle de mise à jour.

### Installation de laboratoire réalisée

`native-package --esp-uuid <UUID-FAT>` ajoute `esp-dispatcher.cfg` au paquet privé.
Il référence un répertoire EFI propre à l'identité de l'installation et ne lit
aucun fichier de p71. Le premier étage constructeur charge ce dispatcher.

Les adaptateurs `lab/install-native-platform.sh` et `lab/start-native-platform.sh`
ont réalisé la migration de la carte de qualification : vérification des UUID
et empreintes, vérification ext4 hors ligne, sauvegarde du store et des paramètres
précédents, installation des EFI, bascule du répertoire système puis du bootstrap
ESP. Ils sont spécifiques à cette carte et à son état précédent, pas un
installateur générique. `lab/check-native-platform.py` contrôle ensuite le runtime,
l'identité k0s conservée, les ressources et les reboots.
