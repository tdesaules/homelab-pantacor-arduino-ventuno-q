# Core seul et accès aux applications

## État déployé

La révision **`locals/core-only-040`** a livré le retrait décrit ici. Elle est
remplacée par [`locals/k0s-os-070`](k0s-os.md), avec
**core 0.7.0**, Bash 5.3.20, Dropbear, NTP, les clients Kubernetes et
les outils d'administration Pantavisor. Nushell est absent de cette image.

Le conteneur `diagnostic`, son groupe applicatif et son disque logique ont été
retirés de cette révision. Le montage `/diagnostic-data` n'est plus exposé à
core. Les anciennes révisions, les fixtures de tests et les fichiers NVMe
`perm/diagnostic/data` sont conservés ; aucune suppression de données n'a été
effectuée. Le nouveau bootstrap contrôle le marqueur de provisionnement NVMe
mais ne dépend plus du répertoire historique diagnostic ; il permet le boot
du core seul sans NVMe.

Pour vérifier la révision active depuis SSH :

```sh
pvcontrol containers ls
pvcontrol steps show-progress current
cat /etc/ventuno-core-release
command -v bash
command -v dropbear
```

La liste actuelle contient `core` au statut `READY` et `k0s` au statut `STARTED` ;
la révision active est `locals/k0s-os-070`, statut `DONE`. La disponibilité Kubernetes
se vérifie séparément avec `kubectl`. Les opérations `pvcontrol containers restart`
et `pvcontrol containers stop` prennent le nom du conteneur.

## Où se trouvent SSH et Bash ?

```text
Poste de travail : client OpenSSH
             │ TCP 2222
             ▼
core : serveur Dropbear → shell POSIX ou Bash → outils installés dans core
```

Dropbear et Bash sont dans **le même conteneur core**. Bash n'écoute pas sur
un port réseau : Dropbear lui fournit une session et, avec `ssh -t`, un terminal.
Le réseau de core est partagé avec celui de l'hôte ; son port 2222 est donc
accessible à l'adresse de la carte.

Chaque conteneur possède son propre système de fichiers et son propre `PATH`.
Installer `/usr/bin/mon-outil` dans un conteneur applicatif ne l'ajoute pas au
`PATH` de core ou du système hôte.

## Trois façons d'utiliser un binaire

### Outil d'administration utilisé dans la session SSH

Pour un outil destiné à l'administration de la carte, le placer dans core
permet de l'appeler directement depuis cette session, comme Bash ou les
utilitaires BusyBox. Ses dépendances font partie de l'image core.

### Service applicatif

Pantavisor lance le service à partir de la configuration du conteneur, par
exemple avec `lxc.init.cmd`. Les utilisateurs accèdent à l'interface du service :

- HTTP/HTTPS pour une API ou une interface web ;
- protocole MQTT, SQL ou autre sur le port prévu ;
- socket Unix partagé explicitement pour une communication locale.

L'adresse et le port accessibles dépendent de la configuration réseau : réseau
hôte partagé, interface/bridge propre au conteneur, proxy ou redirection. Le
port n'est pas publié automatiquement par la seule présence d'un binaire.

### Commande CLI isolée dans un autre conteneur

La commande doit être exécutée **dans ce conteneur en cours d'exécution**, avec
son environnement et ses bibliothèques. Pantavisor fournit notamment l'outil
`pventer` depuis l'hôte disposant de l'accès au runtime LXC :

```sh
# Exemple depuis ce contexte d'administration, pour un futur conteneur :
pventer -c mon-app /usr/bin/mon-outil --help
```

Cet accès au runtime hôte n'est pas actuellement raccordé à la session SSH
de core. `pvcontrol` y expose les opérations de cycle de vie, mais n'ajoute
pas une commande d'exécution arbitraire dans les autres conteneurs.

Pour k0s, [une voie de maintenance assistée par Kubernetes](k0s-os.md)
utilise les commandes natives `kubectl debug` et `nsenter`. Kubectl et k9s sont également installés
directement dans core et utilisent le kubeconfig partagé.

Pour une utilisation courante, on peut fournir un petit client ou wrapper dans
core qui appelle une API/socket de l'application. Le mécanisme exact sera
configuré avec la première application réelle ; un serveur SSH par application
n'est pas nécessaire.

Les répertoires partagés par bind mount ou export servent à échanger des
fichiers. Partager uniquement un exécutable ne lui fournit pas automatiquement
le système de fichiers, les bibliothèques ni les namespaces de son conteneur.

## Préparation et validation du retrait

- `capture-core-state.py` a capturé le manifeste actif et arrêté explicitement
  le conteneur de test. Les fichiers à conserver ont été relevés après son arrêt.
- `build-core-only-revision.py` a créé le manifeste à partir de cet état, en
  conservant exactement les objets BSP et la configuration SSH.
- `deploy-core-only.py` a importé les deux objets modifiés, demandé la transition
  et vérifié le nouveau boot, `DONE`, core seul `READY`, Bash et les terminaux SSH.
- Le scénario UEFI/GRUB sous QEMU a vérifié un second boot et plus de
  180 secondes de disponibilité, puis contrôlé les trois systèmes de fichiers
  et les données conservées : compteur, identité et heartbeat sont restés
  identiques octet pour octet.

Preuves locales :

- `artifacts/decommission/ceff110a80184c44a266739d9e87ceb1/` ;
- bundle et reçu de déploiement sous son répertoire `bundle/` ;
- simulation sous
  `artifacts/prototype-1084-autonomous/qemu-autonomous-test/d3cd9554118543f4af32d964f4d157c0/`.

Le rootfs core 0.4.0 a pour SHA-256
`1897639c9fbcb368d87d8c90ba50b3d558ff9ef66464cb2a379dfe227a156ce9`.
Le noyau et l'initramfs du boot autonome installé n'ont pas été remplacés.
La carte a été laissée sous Pantavisor, avec SSH accessible.

## Prochaine étape

La course READY/STARTED et le démarrage par défaut sont traités dans le
[jalon suivant](runtime-recovery.md). La qualification longue et l'investigation
de l'arrêt non propre initial restent ouvertes, ainsi que la chaîne OCI.
Une première application système est maintenant déployée :
[le POC k0s single-node](k0s-integration.md).
