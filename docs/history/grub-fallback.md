# Retour au système Ubuntu pour les essais Pantavisor

## Mécanisme vérifié sur la carte

Ubuntu reste la première entrée et `GRUB_DEFAULT=0`. Le code généré de GRUB
charge `grubenv`, sélectionne `next_entry` si elle existe, puis l'efface et
exécute `save_env next_entry` **avant de démarrer cette entrée**. Au démarrage
suivant, en l'absence de nouvelle sélection, GRUB reprend l'entrée 0.

Le fichier `/boot/grub/grubenv` fait 1024 octets, est alloué dans un seul extent
sur ext4 et a pu être écrit par `grub-reboot`. Sa consommation a été vérifiée
après un démarrage réel, pas seulement par lecture de la configuration.

### Tests du 10 octobre 2026

1. Environnement initial sans variables, syntaxe GRUB vérifiée, absence de
   transaction dpkg inachevée.
2. Sélection ponctuelle de l'entrée **Ubuntu déjà fonctionnelle**, avec
   `grub-reboot`. La présence de `next_entry` a été contrôlée avant redémarrage.
3. Après redémarrage : Ubuntu 1084 actif, nouvel identifiant de boot,
   `next_entry` effacé, SSH accessible.
4. Deuxième redémarrage, **sans écrire de sélection ponctuelle** : Ubuntu 1084
   de nouveau actif, nouvel identifiant de boot et SSH accessible.
5. Empreintes de `/boot/grub/grub.cfg` et `/etc/default/grub` identiques avant et
   après les deux essais. Aucun changement du choix par défaut ni des entrées EFI.

| Étape | Boot ID |
| --- | --- |
| Avant test | `3ab018b7-7e6e-4ee3-9c65-4d4646aad81a` |
| Après démarrage ponctuel Ubuntu | `28607203-7fcb-4433-8ed5-c09ff22cd61d` |
| Après démarrage au défaut | `636419d2-0f51-481c-8eb7-d220aee7d5ab` |

L'essai portait sur Ubuntu, **pas sur le prototype ni sur une panne injectée**.
Il valide la consommation de la sélection ponctuelle et le démarrage suivant
au défaut. Il ne valide pas encore un chargement de l'initramfs custom.

La trace sur la carte est `/var/tmp/ventuno-grub-fallback-test.json`. Les sorties
SSH sont archivées dans `artifacts/*-test-grub-fallback.log`.

## Procédure reproductible de validation Ubuntu

Ces commandes redémarrent réellement la carte. Attendre le retour de SSH entre
chaque phase ; `check` vérifie aussi que le boot ID a changé.

```bash
python3 scripts/run-board-check.py --sudo --argument start scripts/test-grub-fallback.sh
# Attendre le redémarrage et le retour SSH.
python3 scripts/run-board-check.py --sudo --argument check scripts/test-grub-fallback.sh
python3 scripts/run-board-check.py --sudo --argument default scripts/test-grub-fallback.sh
# Attendre le deuxième redémarrage et le retour SSH.
python3 scripts/run-board-check.py --sudo --argument check scripts/test-grub-fallback.sh
```

Le script refuse de démarrer un nouvel essai si une trace existe déjà : inspecter
et archiver cette trace avant de recommencer. Il refuse également une sélection
GRUB préexistante, un autre défaut ou un noyau par défaut différent du noyau actif.

## Déclencher le retour après un échec

**GRUB choisit où repartir ; il ne peut pas redémarrer à lui seul un noyau figé.**

| Situation | Couverture actuelle / mécanisme prévu |
| --- | --- |
| Reboot ou remise sous tension après consommation de `next_entry` | Retour Ubuntu vérifié avec les essais ci-dessus |
| Panique du noyau custom | `panic=10` dans l'entrée générée ; comportement à valider avec le prototype |
| Prototype fonctionnel mais sans accès réseau | Prévoir une fenêtre de diagnostic bornée, puis reboot vers Ubuntu |
| Userspace bloqué après activation d'un watchdog | Watchdog matériel à intégrer et tester |
| Blocage GRUB ou noyau avant activation du watchdog | Une remise sous tension peut rester nécessaire |
| Dégradation d'Ubuntu, de l'eMMC ou du bootloader | Hors couverture du one-shot ; récupération EDL et sauvegardes |

Le matériel expose un watchdog `qcom_wdt`, observé **inactive**, avec un délai
de 30 secondes et `nowayout=0`. Il n'a pas été armé ni soumis à un test
d'expiration pendant cette validation.

### Prochaine évolution proposée du prototype

Pour les premiers essais sans accès de secours confirmé :

1. Garder Ubuntu par défaut et sélectionner Pantavisor une seule fois.
2. Ajouter une fenêtre de diagnostic, par exemple **180 secondes**, après
   laquelle le prototype revient volontairement vers Ubuntu, même s'il a démarré.
3. Compléter ce délai logiciel par un watchdog matériel alimenté seulement
   pendant la fenêtre de test, afin de couvrir davantage de blocages.
4. Vérifier un premier aller-retour borné avant d'autoriser un fonctionnement
   prolongé et avant le rollback transactionnel des révisions Pantavisor.

Le délai logiciel et l'armement du watchdog ont depuis été intégrés dans une
image d'essai distincte. Son [premier essai matériel](trial-20261010.md) n'a pas
produit le retour SSH automatique attendu. La remise sous tension manuelle a
ensuite rétabli Ubuntu et la consommation de `next_entry` a été confirmée.
L'exécution effective du garde et du watchdog pendant l'essai reste à établir.
Le mode standalone court-circuite une partie du démarrage
normal de Pantavisor : un simple changement de `PV_WDT_MODE` ne suffit pas à
prouver que le watchdog sera armé dans ce mode.

Cette stratégie réduit le risque de rester sur une entrée expérimentale.
Elle ne remplace pas la console pour comprendre un échec précoce, ni la
validation du chemin EDL décrite dans `serial-and-recovery.md`.

## Mise à jour : superviseur indépendant validé le 11 octobre

Le [second essai](trial-20261011.md) utilise un exécutable statique en PID 1,
qui monte les pseudo-systèmes de fichiers lui-même et écrit un jalon avant
de démarrer Pantavisor comme enfant. Le retour automatique Ubuntu et la trace
persistante ont été observés. Le watchdog était armé à 30 secondes ; l'expiration
matérielle n'a pas fait l'objet d'une injection de panne séparée.

Trois boots QEMU couvrent le fonctionnement nominal, l'absence du disque de
trace et le blocage volontaire du superviseur avant ses enfants. La phase
matérielle a confirmé le démarrage et le retour, sans mise hors tension manuelle.
