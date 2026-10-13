# Qualification matérielle du secours indépendant — 13 octobre 2026

## Résultat

**Le secours EFI a démarré sur la VENTUNO Q depuis l'ESP, avant toute lecture
de la partition système p71.** Ethernet DHCP, SSH par clé, détection des disques,
lecture de l'ESP et e2fsck fonctionnent. Aucun volume eMMC/NVMe n'est monté
automatiquement par le secours.

La carte a ensuite retrouvé `locals/k0s-os-070` en `DONE`, son nœud Kubernetes
`Ready` et l'API Python fonctionnelle. Ubuntu et l'installation Pantavisor
existante sont conservés ; aucune partition ni aucun volume NVMe n'a été formaté.

## Particularité du firmware

Deux tentatives ont échoué à sélectionner le secours par `BootNext` :

1. entrée créée avec `efibootmgr --create-only`, hors de `BootOrder` ;
2. entrée ajoutée en seconde position dans `BootOrder`, Ubuntu restant premier.

Dans les deux cas, le système est revenu sous Ubuntu et les variables observées
ne contenaient plus que `Boot0000` et `BootOrder=0000`. La cause exacte de cette
réécriture n'est pas établie. Il ne faut pas baser l'installateur sur la
persistance de nouvelles entrées UEFI tant que ce comportement n'est pas résolu.

Le même fichier EFI a ensuite démarré avec succès depuis le GRUB existant.
Cela a permis d'isoler la sélection du firmware de l'image de secours elle-même.

Enfin, une redirection ponctuelle a été placée dans
`/boot/efi/EFI/ubuntu/grub.cfg`, avec le bootstrap original conservé en repli :

- recherche de l'ESP par UUID `78B2-3FE4` ;
- lecture puis consommation de `native_trial=1` dans un environnement GRUB sur FAT ;
- lancement de l'EFI autonome depuis l'ESP ;
- au boot suivant, indicateur à zéro, reprise du bootstrap original vers Ubuntu.

Ce troisième chemin a réussi. La cible sans userspace Ubuntu peut donc conserver
le premier étage reconnu par le firmware (`shimaa64.efi` et GRUB sur l'ESP), puis
lancer la plateforme native. Le nom de répertoire `EFI/ubuntu` ne signifie pas
que le système Ubuntu de p71 est encore requis par ce chemin.

## Observations du secours

- Noyau `6.8.0-1084-qcom`, chargé depuis `(memdisk)/recovery/kernel`.
- PID 1 : init du secours, `/bin/busybox.nosuid`.
- Racine en RAM ; proc, sysfs, devtmpfs et tmpfs uniquement au début du contrôle.
- Ethernet `eth0`, adresse DHCP `192.168.1.20`, SSH sur 2222.
- 71 partitions eMMC reconnues ; p69, p71 et NVMe identifiés par leurs UUID attendus.
- e2fsck 1.47.0 : vérifications `-f -n` réussies sur p71 et le NVMe, non montés.
- ESP montée manuellement en lecture seule : EFI conforme au SHA-256 attendu,
  indicateur `native_trial=0`, puis démontage réussi.

EFI testé :
`e40b081ab8a665abe68ddf4a74c39f0ba671a6136c2d5a779c8ce42b2f9dede7`.
Identifiant d'essai : `728220a01d9e4193af0fc552d099aee0`.

## Restauration et état final

- Le `grub.cfg` de p71 a été restauré exactement après l'essai de chainloading.
- Le bootstrap ESP de 117 octets a été restauré exactement après l'essai ESP.
- `BootOrder=0000`, sans `BootNext` en attente au retour Ubuntu.
- Noyau, initramfs et inode du store de l'installation existante préservés.
- Réactivation du démarrage Pantavisor par défaut avec les contrôles habituels.
- `locals/k0s-os-070` `DONE`, nœud `Ready`, passage de la fenêtre de stabilité,
  réponse Hello world de l'API vérifiée.

Une copie **privée et inactive** du secours reste sur l'ESP sous
`EFI/ventuno-trial-728220a01d9e4193af0fc552d099aee0/`. Elle contient la clé d'hôte
SSH du lab. Les enregistrements de maintenance sont sous
`/var/lib/ventuno-native-recovery/728220a01d9e4193af0fc552d099aee0/`.

## Preuves locales

- État initial : `artifacts/cluster-audit/30ab0bb1264b4111a3bac758336896f9/`.
- Échec BootNext seul : `artifacts/native-hardware/4010084304364cc19010e74234410dc7/`.
- Secours via GRUB : `artifacts/native-hardware/f47e2718b80c4468bc2750e6ab6a5e9c/`.
- Échec BootNext avec ordre secondaire : `artifacts/native-hardware/2d48d0b881c54e0fb0a5ad6c6d542d36/`.
- Secours depuis l'ESP seule : `artifacts/native-hardware/271a29e22af44bc7bdfd7607fea0d729/`.
- Restauration : `artifacts/20261013T193121443554Z-finish-native-recovery-trial.log`.
- Runtime restauré : `artifacts/native-hardware-return/347237a84cbe402d91ab42ff6fc919b7/`.

## Ce que ce jalon ne qualifie pas encore

Après l'essai, l'opérateur a signalé `setsid: not found` sur l'écran. Le script
de console du secours appelait un applet BusyBox absent. La qualification SSH
ci-dessus reste acquise, mais **la console interactive locale n'était pas validée**.
La configuration BusyBox active désormais `CONFIG_SETSID=y`, le packaging refuse
un initramfs sans cet outil et le test VM exige l'exécution d'une commande sur la
console série. L'EFI matériel testé conserve ce défaut tant qu'il n'est pas
reconstruit et remplacé.

Ce correctif a ensuite été reconstruit et installé avec
[la plateforme native `locals/0.1.0`](native-platform-20261013.md).

L'installation native complète du runtime sur matériel, le maintien de k0s
pendant cette migration, les mises à jour atomiques du BSP/ESP et la suppression
de l'userspace Ubuntu restent à réaliser. Le secours a été lancé sans accéder à
p71 dans le chemin d'amorçage testé ; aucune corruption volontaire du disque réel
n'a été effectuée. Les essais de partition absente/illisible restent des essais VM.
