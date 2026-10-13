# Guide du dépôt

## À quoi sert ce projet ?

Ce dépôt construit et qualifie un système Pantavisor pour l'Arduino VENTUNO Q.
Il fournit une base de gestion autonome, une couche k0s optionnelle, un secours
indépendant et les outils de composition, de distribution et de provisionnement.

La carte utilise `locals/0.1.0`, core 0.8.0 et k0s 1.36.4. Cette installation
locale ne signifie pas encore qu'une release publique a été publiée.

Flux, les accès GitOps et les workloads d'infrastructure relèvent d'un autre
dépôt. La petite API Python présente ici sert seulement de fixture de qualification.

## Vue d'ensemble

```text
.
├── .github/          Automatisation GitHub et suivi des dépendances
├── bsp/              Références matérielles et sélection du BSP
├── docs/             Documentation courante et comptes rendus historiques
├── examples/         Application de test Kubernetes
├── kas/              Configurations de construction Yocto
├── lab/              Qualification et maintenance de la carte du laboratoire
├── meta-ventuno/      Recettes Yocto, services et correctifs du système
├── release/          Modèle de composition et entrées publiques verrouillées
├── tests/            Tests automatisés rapides
├── tools/            CLI de build, packaging, distribution et rendu
├── .gitignore        Exclusions des données privées et générées
├── .gitattributes    Traitement des fichiers patch par Git
├── README.md         Présentation, état actuel et points d'entrée
└── VERSION           Version OS prévue pour la publication
```

Les répertoires locaux `artifacts/`, `dist/` et les fichiers privés sous
`devices/` ne font pas partie du contenu public versionné.

## Chemin d'un changement

```text
recettes meta-ventuno/ + paramètres kas/
                 │ build
                 ▼
       images Yocto et métadonnées
                 │ package + verify
                 ▼
       bundles publics de composants
          │                    │
          │ publish            │ render + paramètres privés de carte
          ▼                    ▼
  images et catalogue GHCR   état Pantavisor privé
          │ fetch              │ native-package
          └────────────────────┤
                               ▼
                       fichiers système et EFI privés
                               │ qualification / installation
                               ▼
                          VENTUNO Q
```

Le profil `base` contient le BSP et `core`. Le profil `k0s` sélectionne
`core-kubernetes`, avec les clients Kubernetes, et ajoute le service système k0s.
Une couche de composition décrit des composants système ; ce n'est pas une
couche de fichiers Docker ni un déploiement GitOps.

## Fichiers à la racine

| Fichier | Rôle |
| --- | --- |
| `README.md` | Vue rapide et état matériel courant |
| `VERSION` | Version OS, actuellement `0.1.0`, indépendante de celle du core |
| `.gitignore` | Exclut les secrets locaux, les sorties de build et caches Python |
| `.gitattributes` | Préserve les espaces de contexte nécessaires aux fichiers patch |

## `.github/` — automatisation

| Fichier | Rôle |
| --- | --- |
| `workflows/ci.yml` | Tests, syntaxe, liens et actionlint sur PR et `main` |
| `workflows/release.yml` | Build base/k0s, échanges GHCR, intégration ARM64 et publication conditionnelle |
| `dependabot.yml` | Suivi des versions des actions GitHub |

Le pipeline complet utilise GHCR pour ses bundles intermédiaires, même avec
`publish=false`. Le job base qualifie le boot natif et le secours ; le job k0s
utilise le scénario complet de cluster historique. L'automatisation n'accède pas
à la carte physique. Voir [build et CI](build-ci.md).

## `release/` — composition publique

| Fichier | Rôle |
| --- | --- |
| `base.json` | Contrat de base, architecture, BSP, core et paramètres par défaut |
| `layers/k0s.json` | Ajout de k0s, sélection du core avec clients et politique de ressources |
| `profiles/base.json`, `profiles/k0s.json` | Sélection des couches d'un profil |
| `overrides/emmc-native.json` | Sélection explicite du contrat de boot natif |
| `overrides/k0s-example.json` | Exemple de personnalisation des réseaux et du nombre de pods |
| `device.example.json` | Modèle à compléter dans un fichier privé pour une carte |
| `platform.lock.json` | URLs et empreintes des paquets publics du noyau et des firmwares |
| `native-boot-tools.lock.json` | Référence publique et empreinte des modules GRUB ARM64 |
| `project.json` | Identité du dépôt utilisée dans la provenance des artefacts |

La composition publique et les secrets d'une carte restent distincts. Le rendu
privé contient notamment la clé d'hôte SSH : il ne doit pas être publié.

## `kas/` — paramètres Yocto

| Fichier | Rôle |
| --- | --- |
| `base.yml` | Sources/layers épinglées, machine VENTUNO Q et images de base |
| `k0s.yml` | Variante de build avec k0s et clients Kubernetes |
| `ci.yml` | Limites de parallélisme et stratégie de stockage pour les runners |
| `ventuno-initramfs.yml` | Configuration de compatibilité pour les prototypes historiques |

KAS orchestre BitBake dans une image conteneur épinglée. Il ne pilote pas les
installations matérielles.

## `meta-ventuno/` — système embarqué

Une extension `.bb` est une recette Yocto ; `.bbappend` complète une recette
amont ; `.inc` partage des paramètres ; `.bbclass` ajoute un comportement de build.
Les fichiers sans extension dans `files/` sont généralement les scripts installés
dans l'image cible.

| Chemin | Rôle |
| --- | --- |
| `conf/layer.conf` | Déclaration de la layer Yocto |
| `conf/machine/ventuno-q.conf` | Définition de la machine cible |
| `conf/ventuno-core.inc` | Version du core et sélection des outils Kubernetes |
| `classes/ventuno-ci.bbclass` | Réduction du stockage temporaire sstate en CI |
| `recipes-core/images/ventuno-core-image.bb` | Image de gestion core, rootfs et métadonnées de release |
| `recipes-core/images/ventuno-k0s-image.bb` | Image du service système k0s |
| `recipes-core/shells/ventuno-bash_5.3.20.bb` | Bash embarqué |
| `recipes-core/shells/ventuno-nushell_0.116.1.bb` | Recette historique ; Nushell n'est plus sélectionné |
| `recipes-core/kubernetes-tools/ventuno-kubernetes-tools_1.0.bb` | kubectl, k0sctl et k9s épinglés |
| `recipes-core/kubernetes-tools/files/ventuno-enter` | Ancien helper de diagnostic des namespaces |
| `recipes-core/ventuno-core-service/ventuno-core-service.bb` | Installation des services internes du core |
| `recipes-core/ventuno-core-service/files/ventuno-core-service` | Initialisation du conteneur de gestion |
| `recipes-core/ventuno-core-service/files/ventuno-time` | Synchronisation NTP avant k0s |
| `recipes-core/ventuno-core-service/files/ventuno-reboot`, `ventuno-revision-status` | Helpers d'administration historiques, remplacés dans l'image courante par les commandes natives |
| `recipes-containers/k0s/ventuno-k0s_1.36.4.bb` | Binaire k0s épinglé et intégration dans l'image |
| `recipes-containers/k0s/files/ventuno-k0s-service` | Initialisation de k0s, réserves de ressources et attente de l'heure |
| `recipes-core/ventuno-diagnostic/ventuno-diagnostic.bb`, `files/diagnostic.c` | Ancien conteneur de test des premiers jalons |
| `recipes-core/ventuno-trial-guard/ventuno-trial-guard.bb` | Construction et installation des composants de démarrage/contrôle |
| `recipes-core/ventuno-trial-guard/files/ventuno-return-guard.c` | Bootstrap PID 1 puis gardien de santé/watchdog ; variantes lab et native |
| `recipes-core/ventuno-trial-guard/files/ventuno-bootctl.c` | Édition contrôlée des environnements GRUB et requêtes de santé |
| `recipes-core/ventuno-trial-guard/files/runtime-layout` | Chemins du support système selon le contrat de boot |
| `recipes-core/ventuno-trial-guard/files/20-ventuno-boot-policy` | Hooks Pantavisor de boot et politique de mise à jour BSP |
| `recipes-core/ventuno-trial-guard/files/ventuno-runtime` | Attachement du store et lancement de Pantavisor |
| `recipes-core/ventuno-trial-guard/files/ventuno-app-storage` | Identification et montage du NVMe attendu |
| `recipes-core/ventuno-trial-guard/files/ventuno-health-watch` | Observation de la disponibilité des conteneurs |
| `recipes-core/ventuno-trial-guard/files/ventuno-storage-watch` | Surveillance du démontage et choix du prochain boot |
| `recipes-core/ventuno-trial-guard/files/ventuno-pid1-shutdown`, `ventuno-runtime-cleanup` | Arrêt et libération du stockage des essais |
| `recipes-core/ventuno-trial-guard/files/ventuno-runtime-status`, `ventuno-trial-diagnostics` | Collecte de diagnostics runtime |
| `recipes-core/ventuno-trial-guard/files/ventuno-network`, `udhcpc.script` | Ethernet DHCP et SSH, utilisables par le core ou le secours |
| `recipes-pv/busybox/busybox_%.bbappend`, `files/ventuno-network.cfg` | Applets BusyBox requis, dont `setsid` |
| `recipes-pv/dropbear/dropbear-pv_%.bbappend`, `files/ventuno-localoptions.h` | Configuration du serveur SSH embarqué |
| `recipes-pv/pantavisor/pantavisor_git.bbappend` | Source Pantavisor et application des correctifs locaux |
| `recipes-pv/pantavisor/files/0001-…patch` | Correction de la course entre les états STARTED et READY |
| `recipes-pv/pantavisor/files/0002-…patch` | Activation opt-in des cgroups v2 |
| `recipes-pv/pantavisor/files/0003-…patch` | Retry borné des démontages occupés |
| `recipes-pv/pantavisor/files/0004-…patch` | Utilisation de curl pour les requêtes pvcontrol concurrentes |

## `tools/` — interface de travail courante

Point d'entrée : `python3 -m tools.pvbuild --help`.

| Fichier | Rôle |
| --- | --- |
| `Containerfile`, `.containerignore` | Image locale d'outillage pour packaging et tests, avec contexte minimal |
| `__init__.py`, `pvbuild/__init__.py` | Déclaration des packages Python |
| `pvbuild/__main__.py` | CLI et arguments des commandes |
| `pvbuild/model.py` | Chargement, fusion et validation des compositions, versions et digests |
| `pvbuild/build.py` | Exécution KAS, collecte des sorties, packaging BSP et vérification des bundles |
| `pvbuild/oci.py` | Conversion SquashFS → image OCI, transferts ORAS et publication |
| `pvbuild/fetch.py` | Récupération des composants à partir d'un catalogue ou d'une composition verrouillée |
| `pvbuild/render.py` | Création d'un état Pantavisor privé à partir des composants et paramètres de carte |
| `pvbuild/native.py` | Store natif, EFI principal/secours et dispatcher ESP |
| `pvbuild/native_test.py` | Qualification UEFI/QEMU : fautes, reboot, secours et console série |
| `pvbuild/integration.py` | Orchestration des scénarios CI avec clés éphémères et NTP local |
| `pvbuild/checks.py` | Tests rapides, syntaxe, liens documentaires et exécution de binaires ARM64 |
| `pvbuild/host.py` | Adaptation aux outils et firmwares de l'hôte de test |
| `pvbuild/cpio.py` | Lecture des archives initramfs newc et résolution interne des liens |
| `pvbuild/vendor.py` | Sélection des modules et firmwares nécessaires au BSP |
| `pvbuild/discover_packages.py` | Recherche de paquets et de leurs empreintes dans les index Ubuntu |

## `bsp/` — références matérielles

BSP signifie *Board Support Package* : noyau, modules, firmwares et paramètres
nécessaires à la carte. Les archives binaires sont dans `artifacts/`, pas ici.

| Fichier | Rôle |
| --- | --- |
| `board-reference.json` | Référence du premier snapshot matériel |
| `board-reference-20261010-updated.json` | Référence du snapshot après mise à jour noyau 1084 |
| `vendor-packages.json` | Inventaire historique des paquets constructeur |
| `recovery-downloads.json` | Références de l'image et du flasher de restauration constructeur |
| `nvme-app-storage.json` | Identifiants du NVMe du laboratoire, pas un profil générique |
| `ventuno-q-1084-selection.json` | Politique de sélection des modules/firmwares, sans Wi-Fi |
| `ventuno-q-1084-k0s-selection.json` | Politique de sélection destinée aux essais k0s |

Les nouvelles constructions publiques utilisent `release/platform.lock.json` ;
les snapshots de la carte restent des références historiques.

## `lab/` — qualification et maintenance

Ce dossier conserve les outils des étapes de portage. Plusieurs scripts sont
spécifiques aux UUID, chemins et identités de cette carte. Les préfixes indiquent
l'intention, mais il faut lire le script avant exécution : un `test-*` peut
installer un essai ou redémarrer le matériel.

### Noyau partagé et qualification

| Fichiers | Rôle |
| --- | --- |
| `autonomous_boot.py`, `revision_names.py` | Génération GRUB et validation des noms de révision |
| `core_only.py`, `k0s_revision.py`, `resource_policy.py` | Construction des configurations de conteneurs et budgets |
| `initramfs_archive.py`, `vendor_selection.py` | Adaptateurs de compatibilité vers les fonctions partagées dans `tools/pvbuild/` |
| `diagnostic_ssh.py`, `local_updates.py` | Sessions SSH et opérations de révision |
| `runtime_validation.py`, `nvme_validation.py`, `soak_validation.py` | Interprétation des preuves de qualification |
| `persistent_session.py`, `core_only_session.py`, `k0s_session.py`, `management_tools_session.py`, `recovery_session.py` | Scénarios de boot, cluster, clients et récupération |
| `soak_monitor.py`, `monitor-prolonged-boot.py` | Observation des essais prolongés |
| `run-board-check.py`, `ssh-askpass.py` | Diagnostics SSH archivés et lecture des accès privés locaux |

### Build, provisionnement et essais

| Fichiers ou familles | Rôle |
| --- | --- |
| `assemble-prototype.py`, `build-first-revision.py` | Assemblage du bootstrap BSP et du premier store ; encore réutilisés par certains adaptateurs |
| `build-initramfs.sh`, `build-core-only-revision.py`, `build-local-revisions.py` | Entrées de construction des jalons historiques |
| `prepare-vendor.py`, `prepare-os-seed.py`, `prepare-autonomous.py`, `prepare-runtime-upgrade.py`, `prepare-resume-store.sh` | Préparation des entrées et états de maintenance |
| `fetch-bsp.py`, `fetch-recovery.py`, `prepare-recovery-tools.py` | Téléchargement et préparation des ressources constructeur |
| `fetch-grub-reference.py`, `fetch-autonomous-record.py`, `fetch-runtime-history.py` | Récupération de références et preuves du lab |
| `export-boot-reference.py`, `export-grub-reference.sh`, `capture-core-state.py` | Export de références de démarrage et d'état |
| `generate-grub-entry.py`, `transfer-trial.py`, `install-trial.sh`, `finish-trial.sh` | Cycle d'un essai borné historique |
| `install-autonomous.sh`, `start-autonomous.sh`, `disable-autonomous.sh`, `start-bounded-trial.sh` | Ancien contrat autonome avec secours Ubuntu |
| `install-runtime-upgrade.sh`, `resume-runtime-upgrade.sh`, `refresh-runtime-grub.sh` | Maintenance de l'ancien runtime |
| `deploy-core-only.py`, `start-k0s-qemu.py` | Déploiement du jalon core seul et lancement de sa VM k0s |
| `provision-diagnostic-ssh.py`, `restore-diagnostic-ssh.py`, `probe-diagnostic-ssh.py` | Création, restauration et vérification des accès SSH de lab |
| `provision-nvme.py`, `provision-nvme.sh` | Provisionnement historique du NVMe ; à distinguer de sa réutilisation actuelle |
| `start-os-update.sh`, `reboot-updated-os.sh`, `disable-board-wifi.sh` | Opérations historiques sur Ubuntu et le Wi-Fi |
| `recover-autonomous-filesystems.sh`, `recover-runtime-store.sh` | Récupération des systèmes de fichiers du lab |
| `test-ready-race.py`, `test-storage-unmount.py`, `test-native-pvcontrol.py` | Régressions ciblées des correctifs Pantavisor |
| `test-grub-fallback.sh`, `test-grub-revision-names.py`, `test-pid1-guard.py` | Sélection GRUB, noms et supervision |
| `test-autonomous-boot.py`, `test-supervised-boot.py`, `test-network-boot.py`, `test-nvme-boot.py`, `test-prolonged-boot.py`, `test-local-updates.py` | Scénarios d'émulation historiques |
| `verify-first-revision.py`, `verify-prototype.py` | Vérification des sorties de prototype |

### Migration native actuelle

| Fichiers | Rôle |
| --- | --- |
| `inspect-native-recovery-host.sh`, `inspect-efi-bootstrap.sh` | Inventaire du boot avant modification |
| `install-native-recovery-trial.sh`, `start-native-recovery-trial.sh` | Premier essai du secours via une nouvelle entrée UEFI |
| `retry-native-recovery-ordered.sh`, `chainload-native-recovery-trial.sh` | Diagnostic du comportement du firmware et lancement depuis GRUB |
| `test-esp-native-recovery.sh`, `finish-native-recovery-trial.sh` | Essai ESP ponctuel et restauration du bootstrap |
| `check-native-recovery.py`, `check-native-recovery-return.py` | Observation du secours et du retour au runtime historique |
| `install-native-platform.sh`, `start-native-platform.sh` | Migration vers le store natif, sauvegarde de l'ancien état et activation |
| `check-native-platform.py` | Révision active, stabilité, ressources, identité k0s et reboots |
| `resume-native-platform.sh` | Vérification hors ligne depuis le secours et réarmement du boot natif |

### Collectes et diagnostics complémentaires

`collect-board-info.sh`, `collect-network-profile.sh`, `collect-prototype-inputs.sh`,
`collect-runtime-status.sh` et `collect-cluster-evidence.py` archivent les observations.
`inspect-nvme.sh`, `inspect-os-storage.sh` et `inspect-autonomous-failure.sh`
inspectent des points précis ; `read-last-runtime-log.sh` récupère le dernier log.

Les fichiers `check-*` restants sont des contrôles ciblés :

- BSP et matériel : `check-bsp.sh`, `check-display-support.sh`, `check-firmware-origin.sh`, `check-installed-bsp.sh` ;
- Ubuntu : `check-after-os-update.sh`, `check-os-update-progress.sh`, `check-os-updates.sh`, `check-update-summary.sh`, `check-login-notices.sh`, `check-release-candidates.sh` ;
- boot et récupération : `check-grub-fallback.sh`, `check-recovered-board.sh`, `check-autonomous-return.sh`, `check-autonomous-over-ssh.py` ;
- runtime : `check-runtime.sh`, `check-runtime-over-ssh.py`, `check-runtime-recovery.sh`, `check-runtime-upgrade.py`, `check-local-updates.py` ;
- NVMe : `check-nvme-container.sh`, `check-nvme-over-ssh.py` ;
- Kubernetes et clients : `check-k0s.py`, `check-k0s-os.py`, `check-management-tools.py`.

## `tests/` — régressions rapides

Les tests Python sont lancés par `python3 -m tools.pvbuild check`.

| Fichiers | Couverture |
| --- | --- |
| `test_release_model.py`, `test_release_bundle.py` | Compositions, versions, empreintes et publication |
| `test_native_boot.py` | Contrat natif, dispatcher ESP, secours et outils requis |
| `test_autonomous_boot.py`, `test_grub_duration.py`, `test_revision_names.py` | GRUB, durées, sélection et noms sûrs |
| `test_initramfs_archive.py`, `test_vendor_selection.py` | Archives cpio, sélection BSP et résolution des liens |
| `test_core_only.py`, `test_k0s_revision.py`, `test_resource_policy.py` | Configurations système et réserves de ressources |
| `test_local_updates.py` | Attente des transitions et des reboots, sans répéter les commandes |
| `test_nvme_validation.py`, `test_runtime_validation.py`, `test_soak_validation.py` | Validation des observations matérielles |
| `test_hello_api.py` | Comportement HTTP de la fixture Python |

Ces tests ne remplacent ni un boot QEMU complet ni une qualification matérielle.

## `examples/hello-api/` — fixture applicative

| Fichier | Rôle |
| --- | --- |
| `app.py` | Petit serveur Python, `/hello` et `/healthz` |
| `namespace.yaml` | Namespace `ventuno-poc` |
| `deployment.yaml` | Pod de test, image épinglée, sondes et ressources |
| `service.yaml` | Exposition NodePort pour vérifier le réseau depuis le poste |
| `kustomization.yaml` | Assemblage des manifestes et du code de l'application |

## `docs/` — où chercher une réponse

| Document | Question traitée |
| --- | --- |
| `README.md` | Où commencer ? |
| `repository.md` | À quoi sert chaque partie du dépôt ? |
| `architecture.md` | Comment sont organisés core, k0s et le stockage ? |
| `layers.md` | Comment composer et personnaliser une installation ? |
| `build-ci.md` | Comment construire et vérifier les images ? |
| `releases.md` | Que signifient version, tag, révision et digest ? |
| `installation.md`, `native-emmc.md` | Comment fonctionnent l'installation et le secours ? |
| `administration.md` | Quelles commandes utiliser sur le système courant ? |
| `history/README.md` | Où retrouver les jalons du portage ? |
| `history/native-platform-20261013.md` | Quelle installation native est réellement active ? |
| `history/native-recovery-20261013.md` | Comment le secours et la contrainte firmware ont-ils été validés ? |

Les autres documents de `history/` détaillent les étapes : inventaire/préflight,
BSP et mises à jour Ubuntu, essais de boot datés, réseau/SSH, core/PID 1,
persistance NVMe, mises à jour locales, récupération, k0s, accès aux conteneurs
et incidents. Leur nom décrit le jalon ; leurs anciennes commandes ne sont pas
nécessairement celles de l'installation courante.

## Données locales exclues de Git

| Emplacement | Contenu |
| --- | --- |
| `artifacts/` | Caches Yocto, téléchargements, VM, traces, captures et accès de lab |
| `dist/` | Bundles, images OCI, états privés et paquets d'installation |
| `devices/*.local.json` | Paramètres propres aux cartes |
| `docs/access.local.md` | Accès privés du laboratoire |
| `.venv/`, `__pycache__/` | Environnement Python et caches |

**Pour un changement courant**, commencer par `release/`, `meta-ventuno/` ou
`tools/pvbuild/`, puis les tests associés. Consulter `lab/` pour une qualification
ou une maintenance précise, avec son compte rendu.
