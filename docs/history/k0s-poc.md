# Faisabilité d'un POC k0s single-node

## Conclusion

Le matériel convient à un petit cluster Kubernetes single-node. Le
[POC est maintenant intégré et validé](k0s-integration.md) dans Pantavisor,
avec k0s v1.36.4+k0s.1 et désormais [core 0.7.0 et une administration native](k0s-os.md).
Cette page conserve l'étude initiale et
les prérequis qui ont guidé cette intégration.

Observations sur la carte le 12 octobre 2026 :

- architecture `aarch64`, huit CPU en ligne (`0-7`) ;
- `MemTotal: 15651824 kB`, soit environ 14,9 Gio utilisables ;
- noyau constructeur `6.8.0-1084-qcom`, ext4 et overlayfs disponibles ;
- NVMe 128 Go provisionné, à partager par répertoires dédiés, sans reformatage ;
- pas de swap actif ;
- contrôleurs CPU, mémoire, pids, etc. actuellement montés en **cgroup v1**.

La documentation k0s annonce le support ARM64 et environ 1 Go de RAM minimum
pour controller + worker, hors applications. Il reste préférable de réserver
plusieurs Gio au POC. Core conserve sa limite de 256 Mio et son rôle réseau/SSH.

## Architecture proposée

```text
Pantavisor PID 1
├── core : DHCP, SSH, administration
└── k0s : controller --single
    ├── API Kubernetes et stockage du cluster
    ├── kubelet + containerd
    └── pods ARM64
        └── données persistantes sur NVMe
```

Pantavisor gère le conteneur système k0s ; containerd gère les pods à l'intérieur.
Il faut des permissions et des montages adaptés à cette imbrication : cgroups
délégués en écriture, namespaces, montages/propagation, périphériques et réseau.
Ce conteneur aura davantage de privilèges qu'une application ordinaire.

Le guide `k0s install controller --single` installe un service systemd/OpenRC.
Notre PID 1 étant Pantavisor, l'intégration utilisera plutôt le lancement direct
`k0s controller --single`, supervisé dans son conteneur, avec configuration et
répertoires persistants explicitement définis.

## Prérequis à traiter

1. **Cgroup v2** : les versions récentes de k0s le demandent par défaut. Valider
   la migration du montage hôte et des limites LXC avant le déploiement k0s.
   La présence du type `cgroup2` dans `/proc/filesystems` ne signifie pas que
   les contrôleurs sont actuellement disponibles en v2.
2. **Modules réseau** : vérifier et inclure dans le BSP réduit les dépendances
   du CNI choisi (bridge, veth, br_netfilter, conntrack, NAT, netfilter/IPVS selon
   configuration). Le noyau constructeur complet et notre sélection de modules
   ne sont pas équivalents.
3. **Stockage** : réserver les chemins k0s, containerd, kubelet et volumes des
   workloads sur le NVMe. Refuser le démarrage du worker sans ce stockage.
   Un rollback de l'image ne restaure pas automatiquement la base Kubernetes.
4. **Réseau** : choisir des CIDR pods/services distincts du LAN et exposer l'API
   sur le port 6443. Vérifier DNS, accès entre pods et exposition d'un service.
5. **Image** : fixer une version k0s ARM64 et son empreinte, préparer utilisateurs,
   outils mount/umount et configuration. Exécuter `k0s sysinfo` dans le contexte
   réel du futur conteneur avant de démarrer le cluster.

## Validation du POC

- nœud `Ready`, pods système sains ;
- déploiement ARM64 de test joignable depuis le LAN ;
- volume persistant conservé après redémarrage ;
- arrêt propre du cluster et de Pantavisor ;
- core toujours accessible lors d'une panne k0s ;
- ressources et écritures NVMe mesurées.

`--single` désactive des fonctions nécessaires à l'extension multi-nœuds. Si
cette extension devient un objectif, utiliser un controller avec
`--enable-worker --no-taints` dès la création du cluster.

## Références consultées

- <https://docs.k0sproject.io/stable/install/>
- <https://docs.k0sproject.io/stable/system-requirements/>
- <https://docs.k0sproject.io/stable/external-runtime-deps/>

Les URL `stable` sont évolutives : fixer la version au moment du POC. Les pages
consultées indiquent que cgroup v1 nécessite des dérogations explicites depuis
Kubernetes 1.35 ; la migration v2 est préférable à ce contournement.
