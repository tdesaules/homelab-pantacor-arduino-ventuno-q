# Runtime corrigé, démarrage par défaut et récupération

Ce jalon est conservé comme qualification du runtime et de la récupération.
La révision courante est désormais [`locals/k0s-os-070`](k0s-os.md),
avec core 0.7.0, cgroup v2, le POC Kubernetes et l'administration native.

## État livré

La révision `locals/runtime-041` utilise core **0.4.0** inchangé et un nouvel
initramfs contenant le correctif Pantavisor et le bootstrap de récupération.
Le noyau constructeur reste `6.8.0-1084-qcom`.

SHA-256 de l'initramfs :
`91cbd7ace3af3f670d432e9671ed97a5ab1b645e063b62ca142f767ac89338f1`.

## Course READY / STARTED

Le socket de contrôle pouvait livrer le signal READY avant la notification
du PID sur le pipe LXC. Le callback du pipe exécutait ensuite une transition
inconditionnelle vers STARTED, faisant régresser le statut et échouer le contrôle
de santé.

Le patch de la couche `meta-ventuno` :

- termine toujours la lecture du PID et la préparation des logs ;
- passe à STARTED uniquement si le statut est encore STARTING ;
- conserve READY et n'annule pas un arrêt déjà demandé ;
- refuse les signaux READY hors des états STARTING, STARTED et READY.

`python3 scripts/test-ready-race.py` compile les vrais callbacks de la révision
amont fixée, avec des dépendances simulées. L'ancien code reproduit la régression ;
le code patché passe les deux ordres d'événements, les doublons READY, l'échec
de démarrage, l'arrêt et un nouveau cycle de démarrage.

Ce correctif résout la course identifiée lors de la récupération. Il ne démontre
pas la cause de l'arrêt non propre initial vers 52 minutes.

## Politique de démarrage

`09_ventuno_default` sélectionne Pantavisor lorsque l'installation, l'environnement
de révision et le budget sont valides. `GRUB_DEFAULT=0` reste dans la configuration
Ubuntu ; le sélecteur ajouté choisit l'entrée effective. Les demandes ponctuelles
`grub-reboot` gardent la priorité.

Avant de lancer le noyau, GRUB arme `ventuno_recovery=1`. Un démarrage sain
d'au moins 120 secondes remet ce verrou à zéro et réinitialise le budget.
Ainsi, un bootstrap bloqué avant même de monter le support revient vers Ubuntu
au boot suivant. Le budget de trois démarrages rapides reste une protection
supplémentaire contre les boucles de reboots propres trop précoces.

Si GRUB ne peut pas écrire l'environnement, il recharge directement le menu
en forçant Ubuntu, au lieu de boucler sur des redémarrages impossibles à compter.

Depuis core :

```sh
ventuno-reboot         # redémarrer Pantavisor
ventuno-reboot ubuntu  # revenir sous Ubuntu et y rester aux boots suivants
```

En cas d'échec de santé, le gardien arme la récupération et demande un reboot
natif, laissant jusqu'à dix secondes au démontage propre. Le délai forcé et le
watchdog restent disponibles si le runtime ne répond plus. Un arrêt forcé peut
toujours nécessiter une récupération de journal ; il ne faut pas l'assimiler à
un démontage propre garanti.

Pour réactiver depuis Ubuntu, depuis le poste :

```sh
python3 scripts/run-board-check.py --sudo \
  --argument 6491b61ba229489cb8bacb1719de7c2c --argument=--default \
  scripts/start-autonomous.sh
```

Cette commande contrôle l'installation, lève le verrou de récupération puis
redémarre **sans `next_entry`**, pour utiliser le choix par défaut.

## NVMe absent ou inutilisable

Le bootstrap ne dépend plus du répertoire historique `diagnostic`. Il vérifie
toujours l'identité du disque, le marqueur de provisionnement et le répertoire
`perm`. Aucun formatage n'est effectué au démarrage.

Si le montage échoue, `/mnt/appdata` reçoit un tmpfs vide **en lecture seule**.
Le core seul peut démarrer et fournir SSH. Une application qui requiert le NVMe
ne doit pas écrire silencieusement sur eMMC : son montage échoue et la politique
de santé/récupération s'applique. Ce mode ne signifie pas qu'une révision avec
applications dépendantes du NVMe restera entièrement opérationnelle.

Depuis core, l'état est lisible dans `/trial-status/app-storage.status` :
`APPDATA_MOUNTED=1` ou `APPDATA_MOUNTED=0`.

## Installation et sauvegarde

Le BSP a été mis à jour en maintenance **depuis Ubuntu**, après sauvegarde
complète du store et des fichiers de démarrage. Le store existant est conservé
(même inode, taille et UUID) ; une nouvelle révision référence le nouvel initramfs.
L'activation utilise `pv_try`, puis Pantavisor produit lui-même le statut `DONE`.

La première activation de maintenance avait sélectionné directement `pv_rev`,
ce qui donnait un core READY sans historique de progression. Le script a été
corrigé pour passer par `pv_try` ; la validation native a ensuite réussi.

Scripts : `prepare-runtime-upgrade.py`, `install-runtime-upgrade.sh`,
`check-runtime-upgrade.py`, `check-runtime-recovery.sh`.
`resume-runtime-upgrade.sh` conserve la procédure de reprise du premier essai.
`refresh-runtime-grub.sh` permet la mise à jour contrôlée des seuls sélecteurs
GRUB, depuis Ubuntu avec récupération verrouillée.

Sauvegarde matérielle :

```text
/var/lib/ventuno-autonomous/6491b61ba229489cb8bacb1719de7c2c/
  runtime-upgrade-e044acc58d5a4945a7cfc505aff09f42/
```

Elle contient le store complet avant modification, l'ancien initramfs, les
environnements GRUB, la configuration GRUB et le reçu d'installation.
Le rollback d'un **BSP** reste une restauration de maintenance depuis Ubuntu ;
le mécanisme de mise à jour applicative conserve son refus des changements BSP.
Les anciennes révisions faisant référence à l'ancien BSP ne doivent pas être
présentées comme un rollback automatique de cet initramfs installé.

## Validations

Tests UEFI avec le vrai GRUB ARM64, sous
`artifacts/prototype-1084-recovery/qemu-autonomous-test/` :

| Scénario | Résultat | Répertoire |
| --- | --- | --- |
| Défaut Pantavisor, reboot, retour Ubuntu | Réussi | `548199a56c024cb3b311add3256231d3` |
| NVMe absent, SSH et core disponibles | Réussi | `f75123d28ce141a898e1252ce010340b` |
| Arrêt de core, récupération automatique | Réussi | `f8bb0c7977f44e16a35de61426129d3b` |
| Bootstrap bloqué avant montage | Réussi | `47529da827e54888bbe0813f8475f640` |
| Budget épuisé | Réussi | `c13b8b7bbaf74ea4a1a22d059564611a` |
| Échec d'écriture de l'environnement GRUB | Réussi | `32fc667a5b7e48b3aa94063914be56ab` |

Chaque scénario vérifie également un nouveau démarrage à froid de la VM :
Ubuntu reste sélectionné après récupération. Les vérifications ext4 comprennent
les flags de journal, car le seul code retour d'`e2fsck -n` ne suffit pas.

Sur la carte : démarrage sans `next_entry`, core READY, révision `DONE`, watchdog
armé et Bash/PTY SSH validés au-delà de 180 secondes. Le retour Ubuntu a permis
de contrôler le store et le NVMe hors ligne : systèmes de fichiers propres,
identité applicative conservée et **71 partitions eMMC** toujours présentes.
Le dernier contrôle matériel, laissé sous Pantavisor avec SSH accessible, est
archivé dans
`artifacts/prototype-1084-recovery/hardware/391f5a9b3e43423fad11b09b2e187384/`.
Le retrait physique du NVMe et une coupure d'alimentation n'ont pas été réalisés
sur la carte ; ces scénarios de boot sont couverts par la simulation.

La qualification longue reste à mener. Pour l'étape Kubernetes, voir
[la faisabilité k0s](k0s-poc.md).
