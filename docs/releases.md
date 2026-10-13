# Convention de release

## Convention retenue

| Élément | Convention | Exemple |
| --- | --- | --- |
| Version de release | SemVer sans préfixe | `0.1.0` |
| Tag Git | `v` suivi de la version | `v0.1.0` |
| Révision Pantavisor installée localement | `locals/` suivi de la version | `locals/0.1.0` |
| Identité de l'artefact publié | Digest SHA-256 | `sha256:<64 caractères hexadécimaux>` |

Cette convention est adoptée pour les futures publications. Elle ne constitue
pas une publication de `0.1.0` : la révision locale `locals/0.1.0` est maintenant
déployée sur la carte, sans release GHCR. Les numéros internes de core et les identifiants des
essais historiques ne sont pas rétroactivement des releases de l'OS.

## Signification des identifiants

`locals/` est l'espace des révisions importées via l'API locale Pantavisor.
Il décrit le mode d'installation, même si les artefacts proviennent d'un registre.
Pantavisor traite le suffixe comme un nom ; il n'en interprète pas la sémantique
SemVer et n'en déduit pas la compatibilité d'une mise à jour.

La version publiée désigne la plateforme Pantavisor et ses profils base et k0s
(BSP, core, couche k0s et configuration système versionnée). Les composants conservent
leurs propres versions, consignées dans la composition de la release.

Le digest identifie exactement les octets de l'artefact publié. Un digest OCI
désigne son manifeste OCI ; le SHA-256 d'une archive désigne cette archive.
Le catalogue de release référence séparément ces artefacts. Ce n'est
pas automatiquement le digest du `state.json` final d'une carte, qui peut
inclure des paramètres propres à celle-ci, ni celui d'une seule image composante.

## Politique SemVer avant la stabilité

- Rester en `0.x.x` jusqu'à une première version stable publiée et ouverte.
- Incrémenter PATCH pour les corrections compatibles.
- Incrémenter MINOR pour les évolutions ; des changements incompatibles restent
  possibles avant `1.0.0`, avec leurs implications documentées.
- Publier `1.0.0` lorsqu'un contrat de stabilité et de compatibilité est assumé.

Une première publication peut être `0.1.0`, sans prérelease obligatoire.
Le préfixe `v` est réservé au tag Git, pas au numéro de version ni au nom choisi
pour les révisions de release Pantavisor.

## Immutabilité des publications

Une version publiée doit rester associée au même contenu : pas de déplacement
du tag Git ni de remplacement des artefacts sous une version existante. Toute
modification destinée à être publiée reçoit une nouvelle version. Les digests
doivent être enregistrés et vérifiés par la chaîne de publication et
de déploiement ; le nom SemVer seul ne garantit pas cette immutabilité.

La configuration propre à une carte (identité du disque, réseau, clés d'accès)
doit être distinguée des artefacts génériques. Un même OS peut ainsi produire
des états de déploiement différents selon les cartes, avec leur propre trace
de configuration et leurs empreintes.

## Validation locale et démarrage

Les outils du dépôt et les générateurs GRUB acceptent maintenant les noms à
points, dont `locals/0.1.0`, ainsi que les identifiants historiques de POC.
La validation technique est volontairement plus générale que la convention
de publication ; accepter `locals/v0.1.0` ne signifie pas que nous le publierons
sous ce nom.

La version Pantavisor utilisée limite le suffixe à 64 caractères et interdit
un second `/`. Notre sous-ensemble commence par un caractère alphanumérique,
puis autorise lettres ASCII, chiffres, points, tirets et underscores. Il exclut
ainsi les chemins `.`/`..`, les espaces et les caractères d'interprétation shell.
`0` reste autorisé pour la révision usine.

Le nouveau GRUB embarqué dans l'EFI natif accepte les noms à points et a démarré
`locals/0.1.0` sur matériel. L'ancien GRUB du lab reste conservé pour le retour
arrière ; il ne constitue plus le chemin de sélection des révisions natives.

## Périmètre de ce dépôt

Ce dépôt couvre Pantavisor et son intégration k0s-ready : BSP, images système,
ressources, stockage, démarrage, récupération, tests et futures releases.

Le bootstrap Flux, ses identifiants d'accès, la configuration Kubernetes pilotée
par GitOps et les workloads d'infrastructure appartiennent à un autre dépôt
d'infrastructure. Aucune installation de Flux ne fait partie de la release
standard de ce dépôt. `examples/hello-api/` est une fixture de POC optionnelle.

## Distribution GHCR

Le pipeline préparé publie sous `ghcr.io/<propriétaire>/<dépôt>/` :

| Nom | Contenu |
| --- | --- |
| `core`, `core-kubernetes`, `k0s` | Images OCI standard ARM64 |
| `core-rootfs`, `core-kubernetes-rootfs`, `k0s-rootfs` | Artefacts SquashFS et métadonnées |
| `bsp` | Noyau, initramfs, modules/firmware sélectionnés et provenance |
| `release` | Catalogue et compositions verrouillées par digest |

Le tag de publication est `0.1.0` pour le tag Git `v0.1.0`. Les candidats issus
d'un lancement manuel utilisent `build-<SHA Git>`. Les transferts intermédiaires
utilisent les packages `build-base` et `build-k0s` avec des tags propres au run.
Le catalogue est publié après les composants ; les consommateurs utilisent son
digest plutôt qu'un tag flottant.

Après publication effective, récupérer un catalogue avec :

```sh
python3 -m tools.pvbuild fetch --profile k0s \
  --reference 'ghcr.io/<propriétaire>/<dépôt>/release@sha256:<digest>' \
  --output dist/fetched
```

Une composition personnalisée verrouillée se récupère avec
`fetch --composition <lock.json> --output <répertoire>`. Le rendu des états privés
est décrit dans [les couches](layers.md). Les contraintes et l'état de validation
du pipeline sont dans [build et CI](build-ci.md). Aucun artefact de release n'est
encore publié ; signature et attestation ne sont pas encore intégrées.
