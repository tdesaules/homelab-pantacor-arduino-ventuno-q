# Architecture

## Base autonome

Le profil `base` assemble le BSP VENTUNO Q, l'initramfs Pantavisor et le conteneur
système `core`. Pantavisor devient PID 1 de l'hôte. Core fournit Bash, Ethernet
DHCP, NTP, SSH par clé et l'accès à l'API locale d'administration Pantavisor.
Il réserve par défaut 512 Mio, avec un poids CPU de 200.

La base n'embarque pas les clients Kubernetes et peut être composée sans NVMe.
Le Wi-Fi est désactivé dans la sélection BSP.

## Couche k0s

Le profil `k0s` ajoute le conteneur système k0s single-node et sélectionne
`core-kubernetes`, la variante du core contenant kubectl, k0sctl et k9s.
La synchronisation NTP précède la création de la PKI. Le runtime utilise cgroup v2.

La couche définit les réserves mémoire de l'hôte, de k0s et le seuil d'éviction,
ainsi que les réseaux pods/services et le nombre maximal de pods. Les valeurs
sont surchargeables et validées avant rendu. La configuration effective du lab
et ses mesures sont dans [le compte rendu k0s](history/k0s-os.md).

## Stockage

| Contenu | Emplacement actuel |
| --- | --- |
| Noyau, initramfs, état GRUB | eMMC, `/boot/pantavisor/` |
| Objets SquashFS et révisions Pantavisor | Store ext4 eMMC, `pvstore.ext4` |
| Données permanentes du core | eMMC |
| PKI, Kine/SQLite, containerd, kubelet, logs et workloads k0s | NVMe ext4 |

Les rootfs système sont immuables ; les overlays de conteneurs sont temporaires.
Le profil privé identifie le NVMe par UUID, PARTUUID et numéro de série. Le rendu
ne formate aucun disque. Le cluster est reconstructible ; les sauvegardes de
cluster et le bootstrap GitOps sont hors du périmètre de ce dépôt.

## Contrat de démarrage

`ubuntu-file-store-v1` est l'ancien contrat de la carte. Il désigne le
boot autonome Pantavisor avec store fichier sur la partition Ubuntu et secours
Ubuntu via GRUB. « Autonome » signifie ici que les reboots Pantavisor fonctionnent
sans intervention du poste ; cela ne signifie pas que la partition Ubuntu peut
être supprimée. Voir [l'installation](installation.md).

Le contrat [eMMC native](native-emmc.md), `emmc-file-store-v1`, est maintenant
installé : secours EFI indépendant et système monté sur `/mnt/pv-system`.
Ses [essais matériels](history/native-platform-20261013.md) couvrent k0s,
reboot, secours et retour au runtime. Les fichiers Ubuntu restent inactifs sur
p71 pour permettre un retour arrière.
