# Administrer Kubernetes depuis SSH dans core

> Historique de core 0.6.0. Depuis [core 0.7.0](k0s-os.md), les raccourcis
> `ventuno-enter`, `ventuno-reboot` et `ventuno-revision-status` ont été retirés
> de l'image. Utiliser les commandes natives du nouveau guide.

**Jalon validé : `locals/core-tools-060`, statut `DONE`.**

Core **0.6.0** fournit les clients ARM64 suivants, dont les binaires officiels
sont fixés par version et SHA-256 dans la recette Yocto :

| Outil | Version | Usage |
| --- | --- | --- |
| `kubectl` | 1.36.4 | Administrer le cluster via son API |
| `k9s` | 0.51.0 | Interface interactive dans le terminal |
| `k0sctl` | 0.33.1 | Outil de provisionnement k0s par SSH |

## Utilisation

Depuis le poste :

```sh
ssh -t -F artifacts/diagnostic-ssh/config ventuno-diagnostic 'exec bash'
```

Puis, **dans core** :

```sh
kubectl get nodes -o wide
kubectl get pods -A
k9s
k0sctl version
```

Dans k9s, `:q` permet de quitter. Il faut une session SSH avec terminal (`-t`).

`k0sctl` n'est pas un client de l'API Kubernetes : il utilise une configuration
de machines et SSH pour installer/gérer les services k0s. Notre conteneur k0s
est supervisé par Pantavisor et n'est pas une installation systemd/OpenRC à
provisionner avec `k0sctl apply`. Pour ce cluster, utiliser kubectl/k9s pour les
ressources Kubernetes et les commandes Pantavisor pour le cycle de vie du
conteneur.

## Kubeconfig partagé

Le chemin standard de root est un lien :

```text
/home/root/.kube/config → /k0s-access/admin.conf
```

Le répertoire `/k0s-access` est le bind en lecture seule du répertoire `access`
du conteneur k0s, sur NVMe. K0s y publie atomiquement son kubeconfig administrateur.
Les clients de core suivent donc le fichier actualisé sans copie manuelle.
Le fichier reste privé (0600) et n'entre pas dans l'image ni dans Git.

Le kubeconfig partagé est destiné à être lu. Pour en modifier les contextes,
utiliser une copie privée et la sélectionner avec `KUBECONFIG` ou `--kubeconfig`.
Les caches et préférences standard sont persistants dans le volume core :

- `~/.kube/cache` → `/data/kube-cache` ;
- `~/.config` → `/data/config` ;
- `~/.cache` → `/data/cache` ;
- `~/.local/state` → `/data/state` ;
- `~/.local/share` → `/data/share`.

La limite mémoire de core est portée à **512 Mio** pour ces clients.

## Ouvrir un shell dans le conteneur k0s

```sh
ventuno-enter k0s
```

Dans ce shell :

```sh
k0s version
k0s kubectl get nodes
exit
```

On peut aussi exécuter directement une commande :

```sh
ventuno-enter k0s k0s kubectl get nodes
ventuno-enter k0s sh -c 'ls /var/lib/k0s'
```

Les arguments, l'entrée standard, les sorties et le code retour sont transmis.
Un terminal est demandé automatiquement lorsque l'appel est interactif.
Les chemins utilisés par la commande se rapportent au système de fichiers de k0s.

### Mécanisme et disponibilité

Dans cette architecture, le « nœud hôte » vu par Kubernetes est le conteneur
LXC k0s. Le helper crée un pod de maintenance temporaire dans `kube-system`,
avec accès privilégié et au namespace PID du nœud. Depuis ce pod, `nsenter`
rejoint les namespaces de montage, PID, réseau, UTS et IPC du PID 1 de k0s,
ainsi que sa racine et son répertoire de travail.

Le shell retrouve donc `/usr/bin/k0s`, `/var/lib/k0s`, sa configuration et ses
sockets locaux. Le pod est supprimé à la sortie, y compris après un code retour
non nul. Sa durée maximale est d'une heure. Le helper utilise par défaut le
kubeconfig local partagé ; `KUBECONFIG` permet de sélectionner explicitement
un autre fichier.

Cet accès **nécessite l'API Kubernetes disponible**. Si elle ne répond plus,
les diagnostics partagés et le cycle de vie Pantavisor restent accessibles :

```sh
cat /k0s-access/status
cat /k0s-access/service.log
pvcontrol containers ls
ventuno-revision-status restart k0s
```

## Mise à jour

La révision est installée en maintenance depuis Ubuntu, avec sauvegarde du
store et du démarrage. Elle met à jour core, sa limite mémoire et l'initramfs.
Les autres conteneurs, leurs données et les objets de configuration SSH sont
préservés. L'historique Bash présent avant la transition est sauvegardé sous
`/data/core-tools-backup/`.

Le test d'arrêt a révélé un `EBUSY` au démontage du store après l'utilisation
des nouveaux outils. Le runtime synchronise désormais le store avant démontage
et réessaie les erreurs `EBUSY` pendant au plus deux secondes, sans démontage
paresseux. Cette correction est testée séparément en C et dans le scénario
UEFI complet, y compris les contrôles ext4 après retour Ubuntu.

La validation couvre les versions des clients, l'accès à l'API sans option
kubeconfig, l'affichage réel de k9s via SSH/PTY, l'entrée dans k0s, les arguments
avec espaces, stdin, le code retour, le terminal et le nettoyage des pods.

Preuves :

- QEMU, reboot et systèmes de fichiers propres :
  `artifacts/prototype-1084-core-tools/qemu-autonomous-test/b507f892d62844f19da9d48c85bd5965/` ;
- clients et shell validés sur la carte :
  `artifacts/management-tools/5f4740e0ff97439d916fa16874b53dcf/` ;
- retour Ubuntu après ces usages, store et NVMe propres, données historiques
  conservées et 71 partitions eMMC présentes :
  `artifacts/20261013T075317909435Z-check-runtime-recovery.log` ;
- sauvegarde de maintenance :
  `/var/lib/ventuno-autonomous/6491b61ba229489cb8bacb1719de7c2c/runtime-upgrade-2a41e5d3f8a44df78040c3000b0254b5/`.

SHA-256 core 0.6.0 :
`507660892b734429ed7465a26458b0e1c13150fd0395ede02908a7f055e4cce9`.
SHA-256 initramfs avec reprise du démontage :
`16c1fe32cb74b33e88a344bd7bca15624d3ae931e403a0cee9c92b503d7627e4`.
