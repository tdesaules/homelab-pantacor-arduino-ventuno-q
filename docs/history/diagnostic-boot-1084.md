# Prototype réduit 1084 et premier boot de diagnostic

Cette page décrit la première variante console. Le
[diagnostic supervisé du 11 octobre](trial-20261011.md) a depuis démarré sur
le matériel avec retour automatique, ainsi que les pilotes HDMI.

## Résultat de construction

Le prototype actuel se trouve dans **`artifacts/prototype-1084/`**. La version
1078 complète reste dans `artifacts/prototype/` pour référence historique.

| Artefact actuel | Octets | Taille approximative |
| --- | ---: | ---: |
| Noyau constructeur 1084 | 17 780 068 | 17,0 Mio |
| Addon modules/firmwares | 23 280 299 | 22,2 Mio |
| Initramfs complet | 29 700 283 | **28,3 Mio** |

L'ancien initramfs complet faisait 879 638 729 octets : réduction d'environ
**96,6 %**. Les octets du noyau 1084 correspondent exactement à la capture de
la carte après mise à jour.

### Sélection explicite

- Source : `bsp/board-reference-20261010-updated.json`.
- Politique : `bsp/ventuno-q-1084-selection.json`.
- **99 modules**, calculés par fermeture des dépendances et softdeps avec
  `modprobe --show-depends`, sur la copie du BSP et sans charger de module hôte.
- **45 firmwares**, conservant les chemins de recherche du noyau, les overrides
  constructeur WCN6855 et les firmwares QCS8300/PCIe nécessaires.
- Les liens symboliques de firmware sont résolus dans la capture, puis aplatis
  aux noms demandés ; ils ne pointent pas vers les fichiers du poste de build.
- La fermeture des dépendances est recalculée après réduction et `depmod` ;
  toute différence fait échouer l'assemblage.

Le BusyBox amont minimal n'incluait pas la commande `ip`. Le fragment
`meta-ventuno/recipes-pv/busybox/files/ventuno-network.cfg` l'active avec les
fonctions adresse, lien, route, voisinage et règles. La présence des commandes
de diagnostic et l'exécution du shell ont été vérifiées après recompilation.

La sélection couvre le diagnostic série, les composants plateforme/thermiques,
Ethernet, Wi-Fi, USB, stockage et prérequis conteneurs. Le GPU, la caméra et
l'audio ne sont pas les objectifs de cette image ; conserver des firmwares DSP
ne constitue pas une validation des fonctions d'accélération.

## Reproduire

La capture BSP post-update doit être présente et correspondre à l'empreinte du
manifeste. La compilation de base reste celle décrite dans `build-prototype.md`.

```bash
bash scripts/build-initramfs.sh
python3 scripts/assemble-prototype.py artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz
python3 scripts/verify-prototype.py --emulate
python3 -m unittest discover -s tests -v
```

L'option `--emulate` nécessite `qemu-aarch64` sur le poste. Elle exécute seulement
`pantavisor --version` et une commande interne au shell BusyBox. Elle ne lance pas le
runtime ni un système complet émulé. Résultat observé :

```text
version: 030-261010 | Pantavisor Inintramfs Distro (030)
```

Les empreintes et la liste exhaustive des fichiers sélectionnés sont dans
`SHA256SUMS` et `build-inputs.json` du répertoire d'artefacts.

Empreinte du résultat vérifié :

```text
8e97e5d253a6b393c1011a6327fdde54b9b6938156c01fe8c61ef94f038b08c9  initramfs-ventuno-q.cpio.gz
```

Les neuf tests de lecture cpio et sélection de firmware passent, ainsi que le
contrôle syntaxique de l'entrée GRUB et les vérifications statiques de l'image.

## Comportement du diagnostic

Configuration effective :

```ini
PV_SYSTEM_INIT_MODE=standalone
PV_BOOTLOADER_TYPE=grub
PV_CONTROL_REMOTE=0
PV_SYSTEM_DRIVERS_LOAD_EARLY_AUTO=1
PV_DEBUG_SHELL=1
PV_DEBUG_SHELL_AUTOLOGIN=1
PV_DEBUG_SSH=0
```

Le code Pantavisor 030 (`init.c`, commit
`48c582334875dde17634973049885c7ab6049116`) montre que le chemin standalone
effectue les montages initiaux proc/dev/sys, le chargement précoce des pilotes,
puis ouvre la console de debug, **sans appeler `pv_start()` ni initialiser le
stockage persistant**. Correction de l'hypothèse initiale : `LABEL=pvstore` peut
rester non provisionné pour ce diagnostic. Il deviendra nécessaire au passage
au runtime embedded, pas pour l'ouverture de cette console.

Le shell local est root sans mot de passe pour ce diagnostic physique. Aucun
serveur SSH n'est démarré et aucune connexion réseau n'est configurée
automatiquement. Il ne faut donc pas attendre le retour de SSH après avoir
sélectionné cette image.

Une règle `mdev` déclenche modprobe à partir de MODALIAS. Le script
`/usr/sbin/ventuno-load-drivers` permet aussi de charger explicitement les
pilotes de diagnostic et de relever les échecs depuis la console. Leur présence
et leurs dépendances sont vérifiées ; leur chargement lors de ce boot custom
reste à tester sur la carte.

## Entrée GRUB préparée, pas installée

La génération suivante a été exécutée avec l'UUID du système Ubuntu de cette
carte. Cet UUID doit être relevé à nouveau pour une autre carte :

```bash
python3 scripts/generate-grub-entry.py \
  --rootfs-uuid e5defb48-4df4-40fc-8f97-7d635b46fcb8
grub2-script-check artifacts/prototype-1084/grub-diagnostic.cfg
```

L'entrée générée a passé la vérification syntaxique GRUB. Elle prévoit les
artefacts sous `/boot/pantavisor-diagnostic/` sur le système Ubuntu et conserve
les paramètres constructeur pertinents (`ttyMSM0`, `earlycon`, `pcie_pme`, vidéo).
Elle utilise `rdinit=/init` et n'indique pas de racine Ubuntu à monter.

**Cette entrée et ces artefacts n'ont pas été installés sur la carte.**
Le boot par défaut et l'environnement GRUB n'ont pas été modifiés.

### Séquence du futur essai

1. Valider la console **1,8 V** et sa saisie sur Ubuntu, avec le brochage confirmé
   dans [serial-and-recovery.md](serial-and-recovery.md).
2. Vérifier le chemin EDL, son alimentation et son câble USB de données.
3. Sauvegarder les éléments supplémentaires nécessaires avant modification du
   boot ; les captures actuelles ne sont pas une sauvegarde eMMC complète.
4. Installer les fichiers de diagnostic et l'entrée GRUB tout en conservant
   Ubuntu comme entrée par défaut.
5. Vérifier réellement le fonctionnement du démarrage ponctuel `next_entry`
   et sa remise à zéro. **Cette vérification a maintenant réussi sur Ubuntu**,
   avec deux redémarrages ; voir [grub-fallback.md](grub-fallback.md).
6. Sélectionner ponctuellement l'entrée `pantavisor-diagnostic-1084`, capturer la
   console, puis contrôler les éléments ci-dessous.

Un `panic=10` est prévu pour redémarrer après une panique noyau ; il ne détecte
pas tous les blocages. Ce mécanisme n'est pas le rollback transactionnel de
Pantavisor, qui sera intégré et testé ultérieurement.

Le retour au défaut au démarrage suivant est vérifié, mais l'image n'a pas
encore de délai de retour logiciel ni d'armement explicite du watchdog pour
un essai automatique borné.

## Contrôles à effectuer depuis la console du prototype

```sh
uname -r
cat /proc/1/comm
/usr/sbin/ventuno-load-drivers
cat /proc/partitions
ip link
cat /proc/mounts
```

Attendus : noyau `6.8.0-1084-qcom`, PID 1 Pantavisor, eMMC/NVMe présents,
contrôleur Ethernet visible et absence de montage automatique des données.
Le nom Ethernet peut être `eth0` plutôt que `end0` : Ubuntu effectuait le renommage
via son userspace. La première vérification réseau porte sur le pilote et le
lien ; l'adressage IPv4/DHCP et SSH seront ajoutés explicitement ensuite.

Lecture du système Ubuntu sans rejeu du journal ext4, après confirmation du
périphérique dans `/proc/partitions` :

```sh
mkdir -p /mnt/ubuntu
mount -t ext4 -o ro,noload /dev/mmcblk0p71 /mnt/ubuntu
cat /mnt/ubuntu/etc/os-release
umount /mnt/ubuntu
dd if=/dev/nvme0n1 of=/dev/null bs=1M count=16
```

Ces commandes sont une procédure future, pas des résultats déjà obtenus sous
l'image custom. Le premier boot dépend encore de la console matérielle.
