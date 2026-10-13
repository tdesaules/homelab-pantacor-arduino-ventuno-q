# Build local et CI

## Outils

Le build utilise Podman rootless et l'image KAS épinglée dans
`tools/pvbuild/build.py`. Les recettes et sources Yocto sont fixées dans `kas/`.
Python 3.12 est utilisé dans la CI. Le packaging BSP utilise `ar`, GNU tar et
`depmod` ; le rendu ajoute `cpio`, `unsquashfs` et `qemu-aarch64`.
Les contrôles rapides nécessitent `grub-script-check`.
ORAS 1.3.4 et Skopeo servent à la distribution.

## Construire et vérifier

```sh
python3 -m tools.pvbuild build --profile base
python3 -m tools.pvbuild build --profile k0s
python3 -m tools.pvbuild package --profile base --output dist/base
python3 -m tools.pvbuild package --profile k0s --output dist/k0s
python3 -m tools.pvbuild verify dist/base
python3 -m tools.pvbuild verify dist/k0s
python3 -m tools.pvbuild smoke --bundle dist/base
python3 -m tools.pvbuild smoke --bundle dist/k0s
python3 -m tools.pvbuild check
```

Les bundles incluent rootfs, manifestes de paquets, SBOM Yocto, provenance et
empreintes. Le BSP est assemblé depuis les paquets publics verrouillés dans
`release/platform.lock.json`, sans capture d'une carte. `verify` refuse les
fichiers modifiés et les fichiers supplémentaires.

`--ci` sélectionne `kas/ci.yml` et un répertoire `artifacts/yocto-ci/<profil>`.
Il faut aussi passer `--ci` à `package` si l'on utilise ce répertoire directement.
La CI conserve d'abord les sorties avec `stage-build` puis libère l'arbre de
build avant packaging. Le mode CI limite BitBake à 2 tâches et make à 2 jobs ;
son cache sstate est propre au build et ses archives sont supprimées après
création. Le cache local partagé n'est pas destiné à ce mode.

### Outils locaux en conteneur

Si le poste ne fournit pas SquashFS ou les outils d'émulation :

```sh
podman build -t localhost/ventuno-build-tools:dev -f tools/Containerfile tools
podman run --rm --security-opt label=disable -v "$PWD:/work" \
  localhost/ventuno-build-tools:dev smoke --bundle dist/base
podman run --rm --security-opt label=disable -v "$PWD:/work" \
  localhost/ventuno-build-tools:dev oci \
  --component dist/base/components/core --output dist/oci-core
skopeo inspect oci:dist/oci-core
```

La même image peut exécuter `render`. C'est une image d'outillage Ubuntu avec
shell et outils de packaging, distincte des images déployées. Elle utilise UID 0
dans l'espace utilisateur de Podman rootless pour préserver les propriétaires
des fichiers extraits. L'option SELinux évite de réétiqueter tout l'arbre Yocto.
Elle ne contient pas les outils de publication ni ceux de la VM complète.

## GitHub Actions

- `ci.yml` : tests, syntaxe, liens documentaires et actionlint sur PR/main.
- `release.yml` : contrôles, builds base/k0s sur deux jobs `ubuntu-24.04`,
  transfert des bundles via GHCR, tests de binaires et VM complète sur
  `ubuntu-24.04-arm`, puis publication si tag `v*` ou `publish=true`.
- Le job base utilise le contrat natif : secours indépendant, console série,
  reboots et cas de panne. Le job k0s conserve le scénario complet de cluster
  historique ; le boot natif k0s est actuellement qualifié sur la carte.
- Même un lancement manuel avec `publish=false` utilise GHCR pour les transferts
  intermédiaires `build-<profil>:ci-<run>-<attempt>`.
- L'intégration complète exige un workspace vierge : elle génère des clés
  éphémères et un serveur NTP local. Elle refuse les chemins de lab déjà présents.

Les actions sont épinglées par SHA ; les droits packages sont limités aux jobs
concernés. Les accès SSH matériels ne font pas partie du pipeline.
Le publisher refuse un arbre Git non commité et le remplacement d'un tag par
un digest différent.

## Qualification restante

Les builds locaux réussis ne valident pas encore les contraintes d'un runner
GitHub standard. Le premier build froid doit mesurer temps, espace disque minimal
et disponibilité des dépendances ARM64. Les métriques sont écrites dans
`artifacts/metrics/` et reprises dans le résumé du job. La configuration CI
corrigée a été vérifiée par `bitbake-getvar` ; le précédent build froid utilisait
encore 12 jobs, donc ne constitue pas une mesure du profil limité à 2 jobs.

La nouvelle chaîne complète VM/GHCR n'a pas encore été exécutée. Les preuves VM
historiques restent consultables dans [l'historique](history/README.md).
