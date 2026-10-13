# Pantavisor sur Arduino VENTUNO Q

Plateforme ARM64 composée d'une **base Pantavisor autonome** et d'une **couche
k0s optionnelle**, construite avec KAS/Yocto. Les compositions et leurs surcharges
sont versionnées ; la distribution prévue utilise exclusivement GHCR.

## État du projet

- La carte utilise **`locals/0.1.0`**, core **0.8.0** et k0s **v1.36.4+k0s.1**
  avec le boot natif. Voir le [compte rendu matériel](docs/history/native-platform-20261013.md).
- La révision locale est installée ; la release OS **0.1.0** n'est pas encore
  publiée sur GHCR ni associée à un tag Git.
- Les builds locaux base/k0s, les bundles, les tests de binaires ARM64 et les
  rendus privés ont été vérifiés. La chaîne GitHub Actions/GHCR et son intégration
  complète sur runners hébergés restent à exécuter.
- Le [boot eMMC indépendant et son secours](docs/native-emmc.md) sont installés
  et qualifiés sur matériel, avec reboot et conservation du cluster. Les fichiers
  Ubuntu et l'ancien store sont conservés pour le retour arrière, mais ne sont
  plus utilisés par la chaîne native.

## Commencer

Depuis la racine du dépôt :

```sh
python3 -m tools.pvbuild --help
python3 -m tools.pvbuild compose --profile base
python3 -m tools.pvbuild compose --profile k0s \
  --override release/overrides/k0s-example.json
python3 -m tools.pvbuild check
```

Le contrôle local utilise Python 3 et `grub-script-check`. Pour les dépendances
de build, d'émulation et de packaging, suivre le [guide build et CI](docs/build-ci.md).

## Organisation

| Chemin | Rôle |
| --- | --- |
| `release/` | Base, couches, profils, surcharges et paquets BSP verrouillés |
| `kas/` | Configurations de build base, k0s et CI |
| `meta-ventuno/` | Recettes Yocto et correctifs Pantavisor |
| `tools/pvbuild/` | Composition, packaging, OCI, récupération et rendu privé |
| `.github/workflows/` | Contrôles et chaîne de release |
| `tests/` | Tests automatisés |
| `lab/` | Adaptateurs et outils de qualification historique |
| `docs/history/` | Observations et preuves des jalons matériels |
| `examples/hello-api/` | Fixture applicative optionnelle |

Les sorties `artifacts/` et `dist/`, les paramètres de carte et les accès locaux
sont ignorés par Git. Flux, les credentials GitOps et les workloads
d'infrastructure appartiennent au dépôt d'infrastructure.

## Documentation

- [Guide des dossiers et fichiers](docs/repository.md)
- [Index](docs/README.md)
- [Architecture et stockage](docs/architecture.md)
- [Composition, couches et configuration privée](docs/layers.md)
- [Build local et GitHub Actions](docs/build-ci.md)
- [Versions et distribution GHCR](docs/releases.md)
- [Installation et trajectoire eMMC](docs/installation.md)
- [Administration](docs/administration.md)
- [Historique des qualifications](docs/history/README.md)

## Références

- [Arduino VENTUNO Q](https://docs.arduino.cc/hardware/ventuno-q/)
- [Restauration constructeur](https://docs.arduino.cc/tutorials/ventuno-q/flash-image/)
- [BSP Pantavisor](https://docs.pantavisor.io/pantavisor/overview/bsp)
