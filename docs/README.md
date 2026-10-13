# Documentation

## Plateforme et outillage courant

Le [guide du dépôt](repository.md) explique les dossiers, fichiers et flux de travail.

1. [Architecture](architecture.md) : base, k0s, ressources et stockage.
2. [Couches](layers.md) : composition et personnalisation d'une carte.
3. [Build et CI](build-ci.md) : outils, contrôles et runners hébergés.
4. [Releases](releases.md) : SemVer, digests et distribution GHCR.
5. [Installation](installation.md) : contrat actuel et migration eMMC.
6. [Administration](administration.md) : commandes natives.
7. [eMMC native](native-emmc.md) : préparation du boot et secours indépendant.

Les [comptes rendus historiques](history/README.md) décrivent les essais réellement
effectués sur le matériel. Leurs anciennes commandes ne constituent pas une
procédure d'installation générique. Les scripts correspondants sont dans
[`lab/`](../lab/README.md).

La carte utilise désormais [le runtime natif `locals/0.1.0`](history/native-platform-20261013.md).
Cette installation locale ne constitue pas encore une publication de release ;
`VERSION` désigne toujours la version prévue pour celle-ci.
