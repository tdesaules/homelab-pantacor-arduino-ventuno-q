# Outils du laboratoire et historique de portage

Ce répertoire conserve les anciens outils `scripts/`, à la même profondeur
dans le dépôt pour préserver leurs références aux artefacts et au BSP.
Il contient les diagnostics matériels, essais bornés, simulations complètes
et procédures de maintenance de la carte de qualification.

Ces outils ne sont pas exécutés par les jobs GitHub hébergés contre la carte.
Les identifiants d'installation et chemins des essais historiques y sont
conservés : ce ne sont pas des installateurs génériques de production.

Entrées utiles pour l'installation de laboratoire existante :

- `run-board-check.py` : exécuter un diagnostic explicite via SSH et archiver sa sortie ;
- `collect-cluster-evidence.py` : relevé de santé ;
- `test-autonomous-boot.py` : qualification matérielle émulée, avec les entrées locales requises ;
- `prepare-runtime-upgrade.py` / `install-runtime-upgrade.sh` : maintenance sous Ubuntu ;
- `check-runtime-recovery.sh` : contrôle hors ligne après retour Ubuntu.
- `install-native-recovery-trial.sh`, `test-esp-native-recovery.sh` et
  `finish-native-recovery-trial.sh` : essais ponctuels du secours et restauration
  du bootstrap ESP ; voir le [compte rendu matériel](../docs/history/native-recovery-20261013.md).
- `check-native-recovery.py` / `check-native-recovery-return.py` : preuves du
  secours et du retour au runtime qualifié.

Les accès restent dans `docs/access.local.md`, ignoré par Git. Les nouvelles
commandes de composition, build et publication sont dans `tools/pvbuild/`.
