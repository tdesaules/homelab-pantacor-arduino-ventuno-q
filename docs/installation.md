# Installation et trajectoire eMMC

## Contrat natif installé

La carte utilise maintenant `emmc-file-store-v1`, avec la révision locale
`locals/0.1.0` et k0s. Voir la [qualification matérielle](history/native-platform-20261013.md).
Les fichiers Ubuntu restent conservés sur p71 pour le retour arrière, mais le boot
et le secours natifs ne dépendent plus de cet userspace.

## Ancien contrat du lab

Le rendu produit une révision privée pour `ubuntu-file-store-v1`. Sur la carte
de qualification, le store est un fichier ext4 de 1 Gio sous
`/boot/pantavisor/`, sur la partition racine Ubuntu. GRUB sélectionne Pantavisor
et garde Ubuntu comme secours. Le gardien et l'état de boot bornent les tentatives
infructueuses. Les procédures effectivement utilisées sont conservées dans
[boot autonome](history/autonomous-boot.md) et
[récupération](history/runtime-recovery.md).

Les adaptateurs `lab/` reposent sur ce montage et sur des accès locaux précis.
Il n'existe pas encore d'installateur générique eMMC ni de commande `pvbuild`
qui formate, installe ou redémarre une carte. Le rendu ne remplace pas cette étape.

Avant d'installer une release SemVer, le GRUB de la carte doit également accepter
les noms à points : les générateurs sont adaptés, le GRUB actuellement installé
ne l'a pas encore été. La capacité et la rétention du store doivent être adaptées
à l'accumulation des images système.

## Cible sans Ubuntu

La suppression d'Ubuntu dépend d'un nouveau contrat de boot et de récupération :

1. Qualifier un secours EFI/initramfs indépendant d'Ubuntu et du store actif,
   capable d'inspecter et réparer l'eMMC.
2. Définir les emplacements durables du noyau, de l'initramfs, des révisions et
   de l'état de sélection/rollback, avec bascule résistante aux interruptions.
3. Remplacer les dépendances `/mnt/ubuntu-trial` et les scripts de récupération
   actuels ; tester boot nominal, révision invalide, échec du store et coupure.
4. Valider ce contrat en VM puis sur matériel avec récupération indépendante,
   avant de retirer le système Ubuntu.

Les 71 partitions constructeur et le firmware de démarrage sont à conserver.
Le NVMe ext4 existant est réutilisé sans reformatage. Le runtime cible reste
Pantavisor sur eMMC, avec k0s et données applicatives sur NVMe.

La préparation du contrat `emmc-file-store-v1` et le banc d'essai UEFI/QEMU sont
implémentés et la migration physique est effectuée ; voir
[le guide eMMC native](native-emmc.md). La suppression des fichiers Ubuntu
conservés pour le retour arrière reste à réaliser.
