# OS k0s-ready : ressources, administration et stockage

Révision **`locals/k0s-os-070`**, core **0.7.0**, k0s **v1.36.4+k0s.1**.
L'application système est k0s ; l'API Python sert uniquement de charge de POC.
La distribution OCI et l'industrialisation restent différées.

## Ressources disponibles

La carte fournit environ **14,93 Gio de RAM utilisables** et huit CPU.
La limite de k0s est calculée à partir de cette mémoire, arrondie vers le bas :

| Usage | Budget |
| --- | --- |
| Hôte, noyau, Pantavisor et core | Au moins 1 Gio hors du conteneur k0s |
| Core | Plafond de 512 Mio, inclus dans la réserve hôte |
| Conteneur k0s complet | Environ 13,93 Gio |
| Composants k0s hors des pods | 1 Gio réservé |
| Marge d'éviction mémoire des pods | 512 Mio |
| Mémoire planifiable pour les pods | **Environ 12,43 Gio** |
| CPU planifiables | **7,5 CPU** ; 250m réservés au système et 250m à k0s |

Ces réserves ne préallouent pas de mémoire. La limite cgroup de k0s protège
l'hôte, celle de `kubepods` conserve une marge aux composants du cluster, et
kubelet peut évincer les pods en pression mémoire avant leur plafond dur.
`memory.high` commence à freiner k0s 256 Mio avant son maximum. Core reçoit
un poids CPU supérieur ; aucune limite CPU dure ne bloque l'utilisation des
huit cœurs lorsqu'ils sont disponibles.

La réserve du kubelet doit être explicite : dans ce montage LXC, sa capacité
annoncée est celle de la machine physique. La limite LXC seule ne suffit donc
pas à obtenir un `Allocatable` correct.

Sources : `scripts/resource_policy.py`, configuration LXC générée par
`scripts/k0s_revision.py` et profil kubelet généré par le service k0s.
Pour une autre capacité RAM, le seed accepte `--memory-kib`.

Sur un cluster existant, le nouveau profil peut être publié après que le nœud
est déjà Ready, lorsque le réconciliateur k0s acquiert son lease. Le kubelet
doit ensuite être redémarré pour prendre les nouveaux paramètres. La migration
070 a utilisé un redémarrage ciblé du conteneur k0s après publication du profil.

Vérification depuis core :

```sh
kubectl get node ventuno-k0s -o yaml
kubectl get --raw /api/v1/nodes/ventuno-k0s/proxy/configz
cat /k0s-access/resources.status
```

## Administration native

Les raccourcis `ventuno-revision-status`, `ventuno-reboot` et `ventuno-enter`
ne sont plus installés dans core. Les services nécessaires à DHCP/SSH, NTP et
au lancement de core/k0s sont sous `/usr/libexec/ventuno/`, hors du PATH.
Le bootstrap, le watchdog, le montage du stockage et la récupération GRUB du
BSP restent nécessaires ; leurs sources et les anciennes fixtures sont conservées.

```sh
pvcontrol containers ls
pvcontrol steps show-progress current
pvcontrol containers restart k0s
kubectl get nodes
kubectl get pods -A
k9s
```

Le kubeconfig reste disponible automatiquement via
`~/.kube/config -> /k0s-access/admin.conf`. `pvcontrol` préfère désormais curl
lorsqu'il est installé, ce qui supprime le besoin du verrou personnalisé autour
des fichiers temporaires partagés de pvcurl. Le fallback pvcurl reste disponible
dans les environnements minimaux sans curl.

### Redémarrage et récupération

```sh
# Redémarrer le système Pantavisor :
printf 'pantavisor\n' > /boot-control/next
pvcontrol cmd reboot

# Revenir sous Ubuntu et y rester jusqu'à réactivation explicite :
printf 'ubuntu\n' > /boot-control/next
pvcontrol cmd reboot
```

### Shell de maintenance k0s

Depuis une session SSH avec terminal :

```sh
kubectl -n kube-system debug node/ventuno-k0s -it \
  --profile=sysadmin \
  --image=docker.io/library/busybox:1.37.0@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e \
  -- nsenter -t 1 -m -u -i -n -p -r -w -- /bin/sh
```

Puis `k0s kubectl get nodes`, par exemple. Après `exit`, supprimer le pod
`node-debugger-...` dont kubectl a affiché le nom :

```sh
kubectl -n kube-system delete pod NOM_DU_POD
```

Cet accès requiert l'API Kubernetes. En cas de panne de l'API, les fichiers
`/k0s-access/status`, `/k0s-access/service.log` et `pvcontrol` restent les moyens
de diagnostic et de récupération depuis core.

## API Python de POC

Le Deployment `ventuno-poc/web` utilise désormais Python 3.14.8 au lieu du
serveur BusyBox de persistance. Les anciennes données `/data/poc/identity`
sur NVMe sont conservées. L'API est sans état et sans dépendance Python externe.

```sh
curl http://192.168.1.20:30080/hello
# {"message":"Hello world","service":"hello-api"}
curl http://192.168.1.20:30080/healthz
# {"status":"ok"}
```

Source et manifeste : `examples/hello-api/`. L'image Python officielle est
fixée par digest ; le code est monté via ConfigMap. Le pod utilise un UID
non-root, un rootfs en lecture seule et des limites de 128 Mio / 250m CPU.
Le ConfigMap et les couches d'image containerd sont stockés sur NVMe.

```sh
kubectl apply -k examples/hello-api
```

## Bilan de la nuit précédente

Le journal de `locals/k0s-051` confirme un boot atteignant **34 891 secondes**
(**9 h 41 min 31 s**) avant la commande de reboot de maintenance. Core démarre
à 14 s et k0s à 24 s ; leurs arrêts suivants n'apparaissent qu'à 34 892/34 894 s.
Aucune erreur Pantavisor n'est enregistrée dans cet intervalle.

Ce résultat confirme la continuité de cette nuit pour la révision précédente.
L'âge Kubernetes des objets n'est pas utilisé comme uptime. Les redémarrages
de maintenance du matin expliquent l'uptime plus court observé ensuite.
Ce n'est pas une qualification de 24 heures de la nouvelle révision.

Le journal `core-tools-060.log` montre aussi un reset après 5 879 secondes
d'uptime, vers **09 h 32 UTC le 13 octobre**, sans arrêt propre. Le propriétaire
a confirmé qu'il s'agissait de son intervention manuelle. Ce reset est donc
distingué des maintenances de l'agent et n'est pas classé comme incident autonome.

Le relevé ponctuel avant modification montre aussi :

- aucun OOM enregistré dans les cgroups core/k0s du boot observé ;
- environ 68 Mio utilisés dans core et 1,12 Gio dans k0s, caches compris ;
- sondes thermiques entre **38 et 39,7 °C** ;
- NVMe utilisé à environ 1 %, nœud Ready et pods de POC sains.

Preuves : `artifacts/cluster-audit/e21820391d8e4483aa66872528552065/` et
`artifacts/cluster-audit/667764ec22754f9ea04a1bead99b2e33/k0s-051.log`.

## Où sont les données ?

| Élément | Emplacement | Format |
| --- | --- | --- |
| Ubuntu et fichiers de démarrage | eMMC, `/dev/mmcblk0p71` | ext4 |
| Store Pantavisor | `/boot/pantavisor/pvstore.ext4`, sur cette partition eMMC | ext4 dans un fichier de 1 Gio |
| Images système core et k0s | Objets/révisions du store eMMC | SquashFS en lecture seule |
| Données persistantes de core | Volume `/data` du store | ext4 sur eMMC |
| Base k0s, PKI, containerd, kubelet, logs et workloads | `/mnt/appdata/perm/k0s/`, sur `/dev/nvme0n1p1` | ext4 sur NVMe |
| `/run` et overlays de boot | RAM | tmpfs/overlayfs |

Les images immuables core/k0s font partie de l'OS. Les images des pods téléchargées
par containerd et toutes les données persistantes du cluster sont sur le NVMe.
Les 71 partitions constructeur eMMC sont conservées ; cela ne signifie pas
qu'elles ont toutes le même format. Les lignes ci-dessus décrivent celles
effectivement utilisées par notre installation.

Vérification matérielle : `artifacts/20261013T104956270873Z-inspect-os-storage.log`.

## ext4, XFS ou Btrfs ?

- **ext4** : choix actuel, simple et déjà validé avec SQLite, containerd et les
  redémarrages. Il convient à ce POC et à de nombreuses installations Kubernetes.
- **XFS** : également adapté aux conteneurs, avec `ftype=1`, notamment pour
  certaines charges volumineuses ou parallèles. Il ne fournit pas de snapshots
  autonomes du système de fichiers et n'est pas automatiquement plus rapide ici.
- **Btrfs** : apporte checksums, compression, sous-volumes et snapshots. Ces
  fonctions seraient utiles si nous organisions explicitement les points de
  restauration, mais demandent une politique de snapshots, une validation des
  performances et une coordination avec la base du cluster.

**Recommandation actuelle : conserver ext4.** Aucun formatage ni migration n'a
été réalisé. Changer de format nécessiterait aussi d'adapter les contrôles du
bootstrap, les modules du BSP et la vérification de stockage du service k0s.

## Pourquoi une sauvegarde reste nécessaire

Séparer l'OS sur eMMC des données sur NVMe permet de mettre à jour le système
sans écraser les données. Cela ne crée pas de seconde copie de ces données.
Une panne du NVMe ou une suppression logique dans Kubernetes peut donc toujours
faire perdre le cluster ou ses volumes.

Le cluster single-node utilise **Kine/SQLite** (`state.db`, `state.db-wal`,
`state.db-shm`) et sa PKI sur NVMe. `k0s backup` sait sauvegarder l'état géré du
cluster, y compris Kine/SQLite et les certificats. Les volumes des applications
doivent être sauvegardés séparément. Le code et les manifestes de l'API de POC
sont déjà dans le dépôt.

Une stratégie complète comporte donc une sauvegarde cohérente du cluster,
celle des volumes persistants, puis une copie hors du NVMe — par exemple sur
un NAS. Un snapshot Btrfs sur le même disque aide à revenir en arrière, mais
ne protège pas contre la perte du disque. Un rollback Pantavisor restaure une
révision système, pas automatiquement l'état du cluster et de ses volumes.

La persistance et les contrôles de systèmes de fichiers sont validés ; une
restauration complète depuis une sauvegarde externe n'a pas encore été testée.
Référence : <https://docs.k0sproject.io/stable/backup/>.

## Validation de cette révision

- 40 tests Python et test du transport natif pvcontrol/curl concurrent ;
- QEMU avec une capacité RAM réduite, horloge initiale en 1970, reboot,
  clients, administration native et API Python ;
- injection de pression mémoire uniquement en VM : le pod de test est
  **Evicted** au seuil 512 Mio, core/l'API/le workload restent disponibles ;
- contrôles ext4 propres au retour Ubuntu dans la simulation.

Traces QEMU :
`artifacts/prototype-k0s-os-vm/qemu-autonomous-test/9fd8ce2c149940ba9b3e593755d4bf27/`.
Résultats matériels : `artifacts/k0s-os/2b149c519fba4bd9909d8c4990beebc9/`.
Le retour Ubuntu après migration et déploiement de l'API a confirmé des systèmes
de fichiers propres et les deux identités de test conservées :
`artifacts/20261013T112046452421Z-check-runtime-recovery.log`.
La sauvegarde système préalable se trouve sous
`/var/lib/ventuno-autonomous/6491b61ba229489cb8bacb1719de7c2c/runtime-upgrade-1348d59f046c4b1baa53244188aa4d69/`.
