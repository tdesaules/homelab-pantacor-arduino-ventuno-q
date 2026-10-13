# Reset natif et qualification des mises à jour — 13 octobre 2026

## Incident : cause encore ouverte

La carte a été trouvée dans le secours alors que son propriétaire confirme
n'avoir ni redémarré ni coupé son alimentation. L'alimentation déclarée est un
chargeur USB-C PD direct ; sa puissance et la qualité du contrat PD n'ont pas
été établies par ces observations.

Les traces conservées montrent deux arrêts sans séquence de démontage normale :
le journal Pantavisor d'un boot s'arrête vers 634 secondes, puis celui du boot
suivant vers 91 secondes. Les conteneurs avaient atteint leurs objectifs de
disponibilité. Le store nécessite une reprise de journal ext4. Le verrou
`ventuno_recovery=1` est resté armé sur le second boot, conduisant au secours.

**Cela ne démontre pas la cause du reset.** Aucune panique exploitable n'a été
retrouvée dans pstore. Les logs disponibles ne permettent pas de départager un
reset matériel, un watchdog ou un blocage noyau. Les erreurs de progression
absente pour le seed initial ne constituent pas une preuve de causalité.

Une copie brute de 4 Gio du store a été préservée avant réparation. Le journal
a d'abord été rejoué sur une copie locale, puis les journaux eMMC/store/NVMe ont
été récupérés avec `e2fsck -p` avant remise en service. Aucun reformatage ni
changement de l'image BSP n'a été effectué pendant ce diagnostic.

Une nouvelle observation externe de 30 minutes, puis un court intervalle sans
sondes SSH, n'ont pas reproduit le reset. Le gardien et le watchdog étaient actifs,
la santé du runtime bonne, et l'autosleep observé était désactivé. Cette fenêtre
ne suffit pas à conclure à une correction : **aucune cause n'est encore isolée**.

Une capture noyau passive, bornée à une heure, a été laissée dans le core après
les essais sous `/data/native-kernel-after-updates.log`. Elle ne redémarre pas la
carte et ne réarme pas automatiquement le secours. Elle s'arrête aussi si le
conteneur core ou la carte redémarre.

## Mise à jour réelle et retours arrière : réussis

Les essais suivants ont été exécutés volontairement et leurs intentions sont
enregistrées séparément de l'incident spontané.

| Étape | Résultat observé |
| --- | --- |
| `locals/0.1.0` → `locals/0.2.0` | Nouvelle image core 0.8.1, transition puis reboot, statut `DONE` |
| Validation de `0.2.0` | Message « Update finished, revision set as rollback point », retries 0 |
| `locals/0.2.0` → `locals/0.1.0` | Retour explicite, reboot, core 0.8.0 et statut `DONE` |
| Essai de `locals/0.2.0-unready` | Core lancé avec `sleep` et ne signalant jamais `READY` |
| Rejet automatique | `ERROR`, « Status goal not reached » ; timeout de l'objectif core après 45 s |
| Retour automatique | Journal « Rolling back... », retour à `locals/0.1.0`, sans intervention de réarmement |

L'état final de la carte est **`locals/0.1.0` en `DONE`**, core 0.8.0, nœud k0s
`Ready` et API Hello world accessible. L'UID du nœud est resté
`3f36e144-59b3-440e-856f-e664534b08fe`. Les manifestes actifs correspondent aux
états attendus ; le NVMe et les données du cluster ont été conservés.

La candidate `0.2.0` contenait une image core différente, avec `setsid` dans
son BusyBox, un marqueur de version et un bind en lecture seule de l'état GRUB.
Ce n'était pas seulement un renommage de révision.

### Périmètre exact

Ces essais valident la mise à jour **des images de conteneurs système et de leur
configuration**, à BSP constant. Le noyau, l'initramfs et les EFI n'ont pas été
modifiés par cette mise à jour. Le hook actuel refuse un changement du BSP.
Le cycle atomique de mise à jour noyau/initramfs/ESP et son rollback restent à
implémenter et qualifier séparément. Aucune release publique `0.2.0` n'a été créée.

Le seed initial `0.1.0` n'avait pas d'historique de mise à jour. Après le retour
explicite via le moteur Pantavisor, il possède désormais un véritable statut
`DONE`. Cela remplace, pour l'état courant, la qualification précédente
`INITIAL_SEED` ; cela ne prouve pas que l'incident était causé par cet historique.

## Retrait d'Ubuntu : encore bloqué par l'incident

Le runtime natif et le secours ne nécessitent déjà plus l'userspace Ubuntu.
Ses fichiers restent un moyen de retour pendant la qualification.

Avant leur retrait définitif :

1. Isoler la cause des resets ou obtenir les traces manquantes au prochain incident.
2. Valider la correction dans le scénario qui déclenche l'échec, au repos et en
   charge, puis vérifier un démarrage matériel depuis une alimentation coupée.
3. Conserver le secours EFI indépendant et une procédure de réinstallation
   reproductible ; préserver l'ESP et les partitions constructeur.
4. Définir le traitement des mises à jour BSP, qui ne sont pas couvertes par les
   essais d'images système ci-dessus.

La mise à jour applicative/système à BSP constant et ses retours arrière sont
maintenant démontrés. La cause du reset demeure le blocage principal : aucune
date de suppression d'Ubuntu n'est annoncée sur la seule base d'un essai sans incident.

## Preuves et outils

- Capture initiale : `artifacts/native-incidents/3b32ee1208a042399dd8dd58745b5477/`.
- Store brut et copie rejouée : `artifacts/native-incidents/3067239586a84554a0cccbbf4db9c28d/`.
- Observation externe : `artifacts/native-live/76fe1fe7f12d4fb189c8e1bc7007f26d/`.
- Flux noyau externe : `artifacts/native-kernel-stream.log`.
- Essais d'update : `artifacts/native-update-tests/38d3796a8b1c468abc72c3fb4ff0e9e2/`,
  avec `evidence-stage`, `evidence-upgrade`, `evidence-downgrade` et `evidence-fault`.
- `lab/capture-native-incident.py` : collecte depuis le secours avec montages en lecture seule.
- `lab/monitor-native-incident.py` : capture externe bornée, sans commande de reboot.
- `lab/prepare-native-update-test.py` : préparation des candidates, sans activation.
- `lab/test-native-updates.py` : étapes explicites de transfert, upgrade, downgrade et faute.

## CI observée en parallèle

Les premiers builds hébergés et leurs packagings ont réussi : environ 1 h 32
pour la base, 1 h 48 pour k0s. Les runners disposaient initialement de 84–85 Gio
libres ; cela ne démontre pas une capacité à construire avec seulement 14 Gio.
Les transferts GHCR ont échoué sur un mauvais flag ORAS : `cp` nécessite
`--to-registry-config` au lieu de `--registry-config`. Le correctif et sa régression
sont dans le commit `af43873`. Un nouveau run sans publication finale a été lancé :
[38478742335](https://github.com/tdesaules/homelab-pantacor-arduino-ventuno-q/actions/runs/38478742335).
