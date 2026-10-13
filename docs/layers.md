# Composition et configuration privée

## Ordre de composition

`release/base.json` est chargé en premier, puis les couches du profil, les
`--layer` supplémentaires et enfin les `--override`, dans leur ordre d'apparition.
Les objets JSON sont fusionnés récursivement, les listes remplacées et `null`
supprime une clé. Le résultat doit toujours satisfaire le contrat de plateforme.

```sh
python3 -m tools.pvbuild compose --profile base --output dist/base-composition.json
python3 -m tools.pvbuild compose --profile k0s \
  --override release/overrides/k0s-example.json --output dist/k0s-composition.json
```

La couche k0s sélectionne `core-kubernetes` et ajoute `k0s`. Les paramètres
publics incluent les réserves de ressources, NTP, le port SSH, les CIDR et
`maxPods`. Les clés SSH, identités de disques et credentials ne sont pas des
paramètres de release publique.

Les surcharges peuvent également sélectionner `bootContract`. La surcharge
`release/overrides/emmc-native.json` active le nouveau contrat de
[boot eMMC indépendant](native-emmc.md), avec un BSP reconstruit qui l'annonce.

Une composition déployable se verrouille avec `compose --artifacts <map.json>` :
la carte des artefacts fournit les références GHCR par digest. Les images
personnalisées doivent respecter les contrats `core-v1` ou `k0s-v1` attendus
par les adaptateurs de rendu. Ce mécanisme ne transforme pas un conteneur
applicatif arbitraire en service système Pantavisor.

## Paramètres d'une carte

Créer un fichier privé `devices/<nom>.local.json` à partir de
[`device.example.json`](../release/device.example.json), en remplaçant les valeurs
d'exemple par les identifiants réels et une clé publique SSH. `appStorage` est
optionnel pour la base et obligatoire pour k0s. Ne pas publier ce fichier.

Après [construction des bundles](build-ci.md) :

```sh
python3 -m tools.pvbuild render --profile base --bundle dist/base \
  --device devices/<nom>.local.json --output dist/device-base
python3 -m tools.pvbuild render --profile k0s --bundle dist/base --bundle dist/k0s \
  --override release/overrides/k0s-example.json \
  --device devices/<nom>.local.json --output dist/device-k0s
```

Les sorties comprennent `state.json`, les objets adressés par SHA-256, le
bootstrap et `device-state.json`. Une clé d'hôte SSH est générée, sauf si
`sshHostKeyFile` désigne une clé Dropbear existante. **Ces sorties sont privées** :
elles contiennent la clé d'hôte et ne sont pas des bundles publiables.
Le répertoire de sortie doit être nouveau.

Le rendu prépare un état ; il ne l'installe pas. Le UUID eMMC fourni ne suffit
pas à générer ou installer les entrées GRUB du dispositif actuel. Suivre les
limites du [contrat d'installation](installation.md).
