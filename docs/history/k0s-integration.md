# Intégration k0s single-node dans Pantavisor

**Révision courante : [`locals/k0s-os-070`](k0s-os.md), statut `DONE`.**
Le nouveau guide fait référence pour les ressources et l'administration native.
Cette page conserve aussi la qualification initiale du cluster `locals/k0s-051`.

## Architecture

```text
Noyau constructeur + Pantavisor PID 1, cgroup v2
├── core 0.7.0 : DHCP, NTP, SSH/Bash, clients Kubernetes, administration Pantavisor
└── k0s v1.36.4+k0s.1 : controller --single
    ├── API Kubernetes : TCP 6443
    ├── Kine/SQLite, kubelet, containerd
    ├── kube-router, kube-proxy, CoreDNS
    └── application de test : TCP 30080, données NVMe
```

Le nœud se nomme `ventuno-k0s`. Le mode `--single` n'est pas destiné à être
étendu en cluster multi-nœuds. Autopilot, metrics-server et la télémétrie k0s
sont désactivés pour ce POC.

Pantavisor et k0s partagent le noyau. Le conteneur système k0s dispose du réseau
hôte, de cgroups délégués en écriture et des privilèges nécessaires aux montages,
aux règles réseau et aux conteneurs imbriqués. Ce n'est pas une frontière de
sécurité équivalente à une VM. Core dispose désormais de 512 Mio ; k0s est
limité à environ 13,93 Gio et 8192 tâches, avec 40 pods maximum configurés dans kubelet.

L'objectif Pantavisor de k0s est **STARTED** : il confirme le lancement du
conteneur système, pas la disponibilité Kubernetes. Celle-ci se vérifie avec
`kubectl get nodes` et `kubectl get pods -A`. Le superviseur conserve un
conteneur inspectable si k0s échoue, afin de garder l'administration disponible.

## Construction

- `0002-ventuno-unified-cgroups.patch` ajoute le mode unifié opt-in, activé par
  `/etc/ventuno-cgroup-v2` dans l'initramfs. Les builds sans ce marqueur conservent
  leur comportement précédent.
- `bsp/ventuno-q-1084-k0s-selection.json` ajoute les modules nécessaires au CNI
  et à kube-proxy, notamment les cibles DNAT et la comptabilité nfacct.
- `ventuno-k0s_1.36.4.bb` installe le binaire ARM64 officiel, vérifié par SHA-256 :
  `04f685c8c9c29262da64acf26fd928452f19d449ac58729592f686f915882319`.
- `ventuno-k0s-image.bb` produit le rootfs SquashFS, avec les outils système
  nécessaires et des comptes dédiés aux composants de contrôle.
- `scripts/k0s_revision.py` construit les configurations LXC et les binds NVMe.

La configuration LXC force explicitement le montage cgroup dans les conteneurs.
Le service exporte un PATH complet, rend `/etc/hosts` et `/etc/resolv.conf`
lisibles par les composants non-root et fournit `/dev/kmsg` au kubelet.
K0s et containerd héritent d'un umask 022 : un umask 077 rendrait les racines
des snapshots inaccessibles aux pods non-root, dont CoreDNS.
Les fichiers de configuration administrateur et les journaux d'accès restent
privés.

```sh
bash scripts/build-initramfs.sh --detach
# Attendre la réussite du build avant l'assemblage.
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --output-dir artifacts/prototype-1084-k0s \
  --selection bsp/ventuno-q-1084-k0s-selection.json \
  --autonomous --pid1 --runtime --core --cgroup-v2 \
  --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --nvme-profile bsp/nvme-app-storage.json
python3 scripts/build-first-revision.py \
  --output-dir artifacts/prototype-1084-k0s --core-only --k0s
python3 scripts/test-autonomous-boot.py \
  --output-dir artifacts/prototype-1084-k0s --default-boot
```

`--core-only --k0s` retire la fixture historique du seed puis ajoute k0s.
Le seed sert à la simulation ; il ne remplace pas le store matériel existant.

## Persistance et réseau

### Horloge avant la PKI

La carte démarre sans horloge RTC exploitable dans ce bootstrap, donc en 1970.
Core 0.5.0 synchronise l'heure avec BusyBox ntpd, puis publie `time-ready` sous
`/boot-control`. K0s attend ce marqueur et une date plausible avant de créer
ses certificats. Le client NTP reste actif ensuite ; il ne sert pas de temps
aux autres machines. SSH reste disponible pendant l'attente de synchronisation.

```sh
# Dans core :
date -u
cat /run/ventuno-time.status
```

Le premier essai matériel sans cette barrière avait généré une PKI datée de
1970. Son répertoire est conservé avant l'initialisation d'un nouveau cluster.
Le scénario QEMU avec `--unsynced-clock` reproduit désormais cette condition.

### Répertoires

Les répertoires hôte sont sous `/mnt/appdata/perm/k0s/` :

| Répertoire | Dans le conteneur k0s | Usage |
| --- | --- | --- |
| `data` | `/var/lib/k0s` | Base Kubernetes, PKI, containerd et kubelet |
| `workloads` | `/data` | Données des applications de test |
| `log` | `/var/log` | Journaux de conteneurs |
| `access` | `/access` | Statut, diagnostics et kubeconfig administrateur |

Core expose `access` en lecture seule sous `/k0s-access`. Son bind est optionnel
pour ne pas rendre le core dépendant de ce répertoire. Les binds du conteneur
k0s sont obligatoires et son service vérifie le stockage ext4 avant de démarrer.
Le disque est celui déjà provisionné ; aucun formatage n'est ajouté.

Le réseau pods est `10.244.0.0/16`, celui des services `10.96.0.0/12`.
Le POC utilise les résolveurs `1.1.1.1` et `9.9.9.9` sur la carte, et celui de
QEMU dans la simulation. Les images des composants sont celles de la version
k0s fixée ; l'image BusyBox de test est fixée par digest.

## Accès depuis le poste

Après validation matérielle, `check-k0s.py` conserve le kubeconfig administrateur
dans un fichier ignoré par Git, mode 0600, sous un répertoire privé :

```sh
export KUBECONFIG="$PWD/artifacts/k0s/kubeconfig"
kubectl get nodes -o wide
kubectl get pods -A
kubectl -n ventuno-poc get deployment,service
curl http://192.168.1.20:30080/
```

Le service de test initial renvoyait un UUID stocké sur NVMe. Le test exigeait le même UUID
après un redémarrage complet. Il utilisait un `hostPath` dédié, pas un provisionneur
CSI ni une StorageClass destinée aux applications futures.
Depuis 070, ce service est remplacé par l'API Python `/hello` et `/healthz`,
sans suppression des anciennes données de test.

Depuis la session SSH core :

```sh
cat /k0s-access/status
cat /k0s-access/sysinfo.log
pvcontrol containers ls
pvcontrol containers stop k0s
pvcontrol containers restart k0s
```

`kubectl` est aussi disponible dans core depuis la version 0.6.0, avec k9s,
k0sctl. L'accès au conteneur utilise maintenant `kubectl debug` et `nsenter`,
voir [le guide courant](k0s-os.md). Core n'embarque pas le binaire k0s. Ne pas publier
le kubeconfig administrateur ni l'inclure dans les fichiers suivis du dépôt.

## Maintenance et récupération

Le changement de BSP/cgroups est installé depuis Ubuntu, avec sauvegarde du
store et des fichiers de démarrage, via `prepare-runtime-upgrade.py` et
`install-runtime-upgrade.sh`. La nouvelle révision est essayée par `pv_try` et
validée nativement par Pantavisor. Les données de l'ancienne fixture sont
conservées.

La sélection `ubuntu` dans `/boot-control/next`, suivie de `pvcontrol cmd reboot`,
conserve le retour Ubuntu persistant. Le rollback BSP
reste une opération de maintenance : sélectionner une ancienne révision seule
ne restaure pas l'initramfs installé. Ne pas supprimer `perm/k0s` pour revenir
au core ; conserver d'abord les données et la PKI du cluster.

## Validation attendue

Le scénario vérifie cgroup v2, la limite mémoire du core, `k0s sysinfo`, le
nœud Ready, les pods système, une résolution DNS interne, le service NodePort,
la persistance après reboot et le maintien de SSH. Il termine la simulation
par un retour Ubuntu et des contrôles ext4 hors ligne.

La simulation complète a réussi, y compris avec une horloge initiale en 1970 :
`artifacts/prototype-1084-k0s/qemu-autonomous-test/9692f87c0f694f23a0a57e58859f5e72/`.
Les trois systèmes de fichiers de la fixture sont propres après retour Ubuntu.
La qualification matérielle est archivée sous
`artifacts/k0s/13511a23c485416383c00c799be1576f/` :

- heure UTC synchronisée avant génération de la PKI ;
- nœud `ventuno-k0s` Ready, CoreDNS/kube-proxy/kube-router opérationnels ;
- application `ventuno-poc/web` et résolution DNS interne validées ;
- même UUID `a565c9ca-1cbb-4a8c-b946-9069bdaefa84` avant/après reboot ;
- SSH et Bash/PTY fonctionnels après reboot ;
- retour Ubuntu puis store/NVMe propres, identité historique conservée,
  même inode du store et 71 partitions eMMC présentes.

Le dernier contrôle hors ligne est dans
`artifacts/20261012T215848290662Z-check-runtime-recovery.log`.

L'essai initial avec PKI datée de 1970 est archivé sur NVMe sous
`perm/k0s-before-1c0e218684cb4536a9590ec1671a54f6/`.
La sauvegarde du store et du démarrage avant correction se trouve sous :

```text
/var/lib/ventuno-autonomous/6491b61ba229489cb8bacb1719de7c2c/
  runtime-upgrade-1c0e218684cb4536a9590ec1671a54f6/
```

Empreintes des artefacts du jalon initial `locals/k0s-051` :

Le BSP cgroup v2 a été conservé lors de la correction NTP, qui porte sur les
images core et k0s. Un nouvel assemblage complet à partir des sources courantes
peut donc produire un initramfs différent de cet artefact archivé.

| Artefact | SHA-256 |
| --- | --- |
| Initramfs cgroup v2 | `17635dc2e2f6a37726ae21e27315ea1155e332c7e5efdd548f2ed782a962af92` |
| Core 0.5.0 | `7d0115b5a901c955e011851b1072b0bbb698ce11726693f1d385468f1cd403b5` |
| Image k0s | `4f28938884070c5516d6a94938bb049f26f4d0fa9ecad3bbaa175c02822a89b5` |

Le [jalon 070](k0s-os.md) aligne les réservations de kubelet, confirme la nuit
précédente et remplace le serveur BusyBox de test par l'API Python. La
qualification complète de 24 heures de cette nouvelle révision reste à mener.
