# Ethernet et SSH gérés par une révision Pantavisor

Ce jalon est désormais suivi par le [conteneur core versionné](core.md), avec
les groupes `root`/`app` et des rôles distincts. Les noms de recettes et commandes
ci-dessous décrivent l'ancien jalon ; utiliser `core.md` pour le build courant.

Le prototype `artifacts/prototype-1084-revision-network/` ajoute un conteneur
**network** à la révision 0, aux côtés de **diagnostic**. DHCP et SSH sont désormais
des services de cette révision. Le superviseur `ventuno-init` reste PID 1 et
conserve la minuterie de retour Ubuntu et le watchdog matériel.

## Architecture

Le build KAS produit deux images :

- `pantavisor-initramfs-ventuno-q.cpio.gz` : runtime, superviseur et pilotes BSP ;
- `ventuno-network-image-ventuno-q.squashfs` : BusyBox, Dropbear, `pvcontrol`,
  `pvcurl`, LXC 6 et les scripts du service réseau.

Le conteneur `network` utilise `init.lxc.static --name network` comme PID 1 pour
transmettre les signaux et récolter les processus enfants. Le service configure
Ethernet, lance Dropbear et `udhcpc`, puis annonce `READY` après l'obtention du
bail DHCP. Il partage le namespace réseau de l'hôte (`lxc.net.0.type = none`) ;
ses processus et son système de fichiers sont dans leurs namespaces LXC.

Le compte SSH est `root`, par clé uniquement, sur le port **2222**. L'identité
d'hôte et le profil MAC/DHCP du lab sont conservés. La session SSH arrive
maintenant **dans le conteneur**, où `/proc/1/comm` indique `init.lxc.static`.
Le shell BusyBox et les outils d'administration y sont disponibles.

L'option d'assemblage `--revision-network` exclut du système hôte la configuration
qui démarrait son service réseau, ainsi que les clés SSH. Le superviseur n'y
lance donc ni client DHCP ni serveur SSH. La configuration et les clés sont
des objets de la révision, montés en lecture seule dans le conteneur. La clé
privée cliente reste uniquement sur le poste ; la clé privée d'hôte est présente
dans le store local de test.

Le volume permanent `/data` du conteneur correspond à
`/storage/disks/perm/network/data`. Il contient son compteur de démarrages et une
copie du bail utilisée pour le diagnostic depuis l'hôte. L'overlay système est
temporaire. Le conteneur dispose de 128 Mio de mémoire au maximum et d'un accès
en lecture seule aux données de `diagnostic` pour les contrôles du jalon.

## Commandes pendant un essai

```bash
ssh -F artifacts/diagnostic-ssh/config ventuno-diagnostic
```

Dans cette session :

```sh
cat /proc/1/comm
cat /run/ventuno-dhcp.state
echo "Shell du conteneur réseau"
ventuno-revision-status
ventuno-revision-status restart diagnostic
ventuno-revision-status stop diagnostic
```

Pour redémarrer le service réseau via Pantavisor :

```sh
ventuno-revision-status restart network
```

Cette commande peut couper la connexion avant son retour. Reconnecter ensuite
SSH avec la même configuration et vérifier `NETWORK_STARTS=2` et le statut réel
`READY`. `ventuno-revision-status` sérialise ses appels et le signal de disponibilité
car `pvcurl` utilise un fichier temporaire partagé dans le conteneur.

L'outil `pvcontrol` est également disponible, par exemple :

```sh
pvcontrol containers ls
pvcontrol steps show-progress current
```

## Construction et vérification

Les clés/profils du lab doivent avoir été provisionnés selon
[ethernet-dhcp-ssh.md](ethernet-dhcp-ssh.md). Après le build KAS :

```bash
bash scripts/build-initramfs.sh
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --trial --runtime --revision-network \
  --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --output-dir artifacts/prototype-1084-revision-network
python3 scripts/build-first-revision.py \
  --output-dir artifacts/prototype-1084-revision-network
python3 scripts/verify-prototype.py \
  --output-dir artifacts/prototype-1084-revision-network --emulate
python3 scripts/verify-first-revision.py \
  --output-dir artifacts/prototype-1084-revision-network
python3 scripts/test-network-boot.py \
  --output-dir artifacts/prototype-1084-revision-network
```

Un seed existant n'est pas écrasé par défaut. `--replace-seed` exige qu'il soit
encore conforme à son empreinte initiale. Les résultats de QEMU sont conservés
séparément dans `qemu-network-test/`, notamment le store après reboot.

Le scénario complet vérifie :

1. DHCP, SSH et clé d'hôte épinglée ; refus d'une clé cliente non autorisée.
2. Révision `DONE`, conteneurs `network` et `diagnostic` réellement `READY`.
3. Redémarrage de `network`, reconnexion SSH, compteur réseau 1 → 2 et compteur
   applicatif toujours à 1.
4. Redémarrage de `diagnostic`, compteur applicatif 1 → 2, puis état `STOPPED`.
5. Retour automatique, démontages sans échec et contrôles ext4 sans réparation.
6. Lecture des deux compteurs persistants à 2 après reboot.

La mise au point en QEMU a corrigé deux problèmes avant l'essai matériel :
`init.lxc.static` exige `--name network`, et `mkfs.ext4 -d` conserve l'UID du
constructeur rootless. Les inodes de `authorized_keys` et de la clé d'hôte sont
donc explicitement attribués à root dans le seed ; cette propriété est vérifiée
avant transfert pour satisfaire les contrôles de Dropbear.

## Essai matériel du 11 octobre 2026

Essai **`523740db571345e48a5cfbb0fe67866a`**. La connexion SSH depuis le poste
a réussi à **16:25:20 UTC**, avec DHCP `192.168.1.20/24` sur `eth0` et passerelle
`192.168.1.254`. La session confirme `NETWORK_OWNER=revision` et le PID 1 du
conteneur `init.lxc.static`.

Les contrôles SSH ont validé les deux conteneurs `READY`, la révision `DONE`,
le redémarrage de `network` avec reconnexion et compteur applicatif inchangé,
puis le redémarrage et l'arrêt de `diagnostic`. Les deux compteurs finaux sont 2.

Le retour automatique Ubuntu et la restauration de GRUB ont ensuite réussi :

| Contrôle final | Résultat |
| --- | --- |
| Propriétaire du réseau | `network_owner=revision`, `host_network_pid=0` |
| Contrôle runtime | `runtime_status_exit=0` |
| Nettoyage | `runtime_cleanup_unmount_failures=0` |
| Store ext4 | `e2fsck -f -n` sain, sans réparation |
| Compteurs relus sous Ubuntu | application **2**, réseau **2** |
| GRUB | empreinte antérieure restaurée, `next_entry` vide |
| Services Ubuntu | aucun en échec |

Boot prototype : `a8db3da8-ea4f-49c6-9ca0-e259f7207b7a` ; boot Ubuntu de retour :
`f07aeb79-33f4-4f3d-99f5-dba21061a234`. La carte est revenue sous Ubuntu 24.04.5
LTS, noyau `6.8.0-1084-qcom` ; aucun nouvel essai n'est programmé.

L'initramfs testé mesure **17 689 267 octets**, SHA-256
`a25660df674a0c3c6120d5da4f83292a880336b50bb5a7850b6f5599c98dbf74`.
Le rootfs réseau a pour SHA-256
`b4ba34ba77d27931a19b1cc93d1a81dc6b8a1663a80a5a8d2b5f4a16bd3ed9a2`.
Le seed initial du store a pour SHA-256
`ea096f7bf61187c55bd9e5c1edf6fc2067f4bc7631b4cb617cd13ef776097cb9`.

Pour reproduire les contrôles sur un **nouvel** essai préparé avec
`transfer-trial.py --output-dir artifacts/prototype-1084-revision-network`
et le [cycle GRUB borné](grub-fallback.md) :

```bash
python3 scripts/probe-diagnostic-ssh.py --trial-id NOUVEL_ID --revision-network
python3 scripts/check-runtime-over-ssh.py --trial-id NOUVEL_ID --revision-network
```

Les journaux de cet essai sont dans
`artifacts/trials/523740db571345e48a5cfbb0fe67866a/`, notamment
`ssh-check.log`, `network-restarted.log`, `runtime-restarted.log` et
`runtime-stopped.log`.
Les contrôles de retour sont conservés dans
`artifacts/20261011T162839559339Z-finish-trial.log` et
`artifacts/20261011T162901648713Z-check-recovered-board.log`.
Les horodatages des noms de fichiers sont ceux du poste ; la carte resynchronise
son horloge par NTP après le retour Ubuntu.

## Portée du jalon

La révision 0 est un nouveau seed de test, pas une mise à jour transactionnelle
de la révision précédente. Le store reste un fichier de 256 Mio sur l'eMMC Ubuntu.
Le conteneur d'administration utilise encore le rôle `mgmt`, AppArmor
`unconfined` et le réseau partagé. Le réseau du système dépend maintenant de la
révision ; le retour automatique du superviseur reste indépendant de SSH.

La suite du portage est le passage progressif à **Pantavisor PID 1**, puis la
persistance NVMe et les mises à jour locales avec rollback. Les commandes de
montage du prototype restent liées à la révision 0 et devront évoluer pour
supporter le changement de révision.
