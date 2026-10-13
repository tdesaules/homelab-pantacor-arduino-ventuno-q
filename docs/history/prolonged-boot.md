# Qualification d'un boot prolongé

Ce scénario étend le [boot Pantavisor PID 1](pantavisor-pid1.md) à une fenêtre
de **900 secondes (15 minutes)** sur la VENTUNO Q. L'objectif est de vérifier
un fonctionnement continu de `core` et de l'application, puis un retour
ordonné sous Ubuntu. Aucun redémarrage volontaire des conteneurs n'est effectué
pendant cette observation.

## Durées bornées

Le gardien PID 1 version **4** accepte des délais de 15 à 1800 secondes ; les
outils d'installation matérielle limitent les essais à **180..1800 secondes**.
Le défaut reste **180 secondes**. Les anciennes images de gardien ne peuvent
pas recevoir une durée matérielle supérieure à 180 secondes par ces outils.

La durée est transmise explicitement dans `ventuno_return_seconds`, inscrite
dans les manifestes de transfert, d'installation et de lancement, puis
comparée à la durée réellement rapportée par le gardien pendant l'observation.

Pour l'essai de 900 secondes :

- fin d'observation visée : environ **850 secondes** depuis le démarrage du gardien ;
- observation stable requise : au moins **750 secondes** ;
- préparation de l'arrêt natif : **880 secondes** ;
- retour forcé de secours : **900 secondes**, alarme indépendante à **910 secondes** ;
- watchdog matériel alimenté par le gardien : **30 secondes**.

L'alarme initiale avant lecture de la ligne de commande reste courte, à
190 secondes. Elle est réarmée à la durée explicite après validation des
paramètres. Les deadlines inférieures à 180 secondes servent aux tests QEMU.

## Mesures et critères

Le moniteur du poste interroge `core` avec la clé SSH et l'identité d'hôte
épinglées. Il attend 15 secondes entre deux requêtes ; le temps de la requête
s'ajoute à cet intervalle. Chaque échantillon accepté doit confirmer :

- le même identifiant de boot vu depuis `core` et le même PID de gardien ;
- Pantavisor effectivement PID 1, gardien version 4, durée attendue ;
- watchdog matériel armé à 30 secondes sur la carte ;
- révision `DONE`, `core` et `diagnostic` `READY` ;
- version de core et rôles inchangés, accès d'administration refusé à l'application ;
- compteurs de démarrage restant à **1** pour les deux conteneurs ;
- horloge du gardien qui avance, heartbeat applicatif non régressif et âgé de
  moins de **10 secondes** ;
- mémoire hôte disponible supérieure à **128 Mio** ;
- espace libre du store supérieur à **32 Mio** ;
- absence des signatures d'erreurs noyau recherchées : panic, BUG/Oops, OOM,
  erreurs ext4/E/S et température critique signalée.

Les températures exposées par sysfs, la charge et la durée des requêtes SSH
sont également enregistrées. Les températures sont des mesures, sans seuil
arbitraire ajouté au moniteur. Le contrôle des signatures noyau n'est pas une
analyse exhaustive de tous les messages du journal.

Les données sont conservées dans le répertoire local de l'essai :

- `soak-samples.jsonl` : échantillons successifs, synchronisés sur disque ;
- `soak-latest.log` : dernière réponse détaillée ;
- `soak-monitor.log` : progression du moniteur détaché ;
- `soak-result.json` : résultat final, durée réellement observée et extrema.

Un résultat du moniteur ne suffit pas à conclure : il faut ensuite vérifier
le retour Ubuntu, le store ext4 et les compteurs persistants avec le cycle
habituel de fin d'essai.

## Construire et valider en QEMU

Les clés du lab doivent déjà être provisionnées selon
[ethernet-dhcp-ssh.md](ethernet-dhcp-ssh.md).

```bash
bash scripts/build-initramfs.sh
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --trial --runtime --core --pid1 \
  --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --output-dir artifacts/prototype-1084-soak
python3 scripts/build-first-revision.py --output-dir artifacts/prototype-1084-soak
python3 scripts/verify-prototype.py --output-dir artifacts/prototype-1084-soak --emulate
python3 scripts/verify-first-revision.py --output-dir artifacts/prototype-1084-soak
python3 scripts/test-prolonged-boot.py --output-dir artifacts/prototype-1084-soak
python3 scripts/test-pid1-guard.py --output-dir artifacts/prototype-1084-soak
```

Le scénario QEMU utilise un délai de **240 secondes** et le même moniteur.
Il exige au moins 150 secondes d'observation, le nettoyage natif sans retour
forcé du gardien et des systèmes de fichiers store/support sains après reboot.
Le test de bootstrap bloqué vérifie séparément le retour par le gardien.

Le contrôle positif et les contrôles négatifs du parseur (heartbeat périmé,
redémarrage, mémoire/espace insuffisants, watchdog absent, durée incorrecte,
erreur noyau) font partie des tests unitaires. La génération de GRUB est aussi
testée : défaut 180 secondes, extension explicite, refus des durées incompatibles.

## Lancer un nouvel essai matériel

```bash
python3 scripts/transfer-trial.py \
  --output-dir artifacts/prototype-1084-soak --return-seconds 900
```

Utiliser l'identifiant retourné pour le [cycle d'installation GRUB](grub-fallback.md) :

```bash
python3 scripts/run-board-check.py --sudo --argument NOUVEL_ID scripts/install-trial.sh
python3 scripts/run-board-check.py --sudo --argument NOUVEL_ID scripts/start-bounded-trial.sh
python3 scripts/probe-diagnostic-ssh.py --trial-id NOUVEL_ID --core
python3 scripts/monitor-prolonged-boot.py --trial-id NOUVEL_ID --detach
python3 scripts/monitor-prolonged-boot.py --trial-id NOUVEL_ID --wait
```

Ce scénario utilise le moniteur de continuité, pas `check-runtime-over-ssh.py`,
car ce dernier redémarre puis arrête les conteneurs. Après le retour sous Ubuntu :

```bash
python3 scripts/run-board-check.py --sudo --argument NOUVEL_ID scripts/finish-trial.sh
python3 scripts/run-board-check.py --sudo --argument NOUVEL_ID scripts/check-recovered-board.sh
```

`finish-trial.sh` restaure GRUB et n'est pas idempotent. Le moniteur refuse
d'écraser des échantillons existants. Le garde-fou temporel fonctionne sur la
carte même si le poste ou le moniteur devient indisponible.

## Résultats

Le test QEMU `85c06da91d75480a9729e229aa9713ab` a enregistré **12 échantillons**
sur **182 secondes**, sans redémarrage des conteneurs. L'arrêt natif, les
contrôles ext4 du store et du support, et la relecture des deux compteurs à 1
ont réussi. Le test de bootstrap bloqué a provoqué le retour en environ
30,4 secondes pour un délai de 25 secondes.

L'essai matériel du 11 octobre 2026 porte l'identifiant
**`00cef8abd54b4eea979b72ea7e99bdc3`**. Il utilise le store neuf de 256 Mio
sur eMMC et core 0.1.1. Les relevés sont conservés dans
`artifacts/trials/00cef8abd54b4eea979b72ea7e99bdc3/`.

### Résultat matériel : réussi

Le moniteur a accepté **54 échantillons**, entre les secondes **30 et 851** du
gardien, soit **821 secondes (13 min 41 s)** de continuité vérifiée. Les mesures
du poste vont de **18:11:22 à 18:25:03 UTC**.

| Mesure | Résultat |
| --- | --- |
| Core / application | `READY`, compteurs **1 / 1** sur tous les relevés |
| Révision / hôte | `DONE`, Pantavisor PID 1, gardien PID 175 inchangé |
| Watchdog | armé à 30 secondes sur tous les relevés |
| Retard maximal du heartbeat | **2,67 s** |
| Mémoire disponible minimale | **15 225 944 Kio**, environ **14,52 Gio** |
| Espace libre minimal du store | **181 633 Kio**, environ **177,4 Mio** |
| Durée maximale d'une requête SSH | **0,653 s** |
| Température maximale observée, tous capteurs relevés | **42 °C** |
| Température maximale parmi les capteurs au dernier relevé | **38,6 °C** |
| Signatures d'erreurs noyau recherchées | aucune détectée |

L'espace libre a diminué de 96 Kio entre le premier et le dernier relevé,
pendant l'écriture des journaux et heartbeats. Les valeurs de mémoire incluent
les effets des caches ; ces mesures ne démontrent pas à elles seules l'absence
de fuite mémoire sur une longue période.

Après l'arrêt natif et le retour sous Ubuntu :

- demande de reboot Pantavisor et démontage natif du store confirmés ;
- `runtime_cleanup_unmount_failures=0` ;
- `e2fsck -f -n` du store sain, sans réparation ;
- compteurs persistants relus à **1 / 1**, heartbeat final `uptime: 881` ;
- configuration GRUB initiale restaurée, `next_entry` vide ;
- aucun service Ubuntu en échec.

Le boot **hôte** prototype est `e39f0c50-da87-4d62-a9cd-67bcb6666bd9`.
Le champ `boot_id` du moniteur est celui visible depuis le conteneur LXC
`core` (`6fdf2bd1-97bd-48db-b9d8-dc751a3efb45`) : ces deux identifiants ne
doivent pas être confondus. Le boot Ubuntu de retour est
`4dc21134-2ce1-452e-ac6b-38ae191c312e`.

Traces de retour :

- `artifacts/20261011T182626954574Z-finish-trial.log` ;
- `artifacts/20261011T182712418610Z-check-recovered-board.log`.

Les horodatages des noms de fichiers sont ceux du poste. L'horloge de la carte
se resynchronise par NTP après le retour Ubuntu.

Empreintes du build testé :

- initramfs (17 691 469 octets) :
  `6c7677bcdbbfce909207cd0681db82f68ab292de339d032d868f86eb60daf723` ;
- core 0.1.1 :
  `89912d72735fffa7c88f8258ded0eb1a247f44c3fd3bbf157ea8577622b5c44d` ;
- seed initial de 256 Mio :
  `927823d8dfe1baa6251c6428130864fd0680ca8649f7bac217bd94c0bbc12d65`.

## Suite vers le NVMe

Le [jalon NVMe](nvme-persistence.md) a depuis été réalisé : provisionnement
unique et persistance entre deux boots complets, avec contrôles de disque
absent ou incorrect en émulation.

Cette qualification est un premier contrôle de continuité, sous faible charge.
Elle ne remplace pas un essai d'endurance de plusieurs heures, un test sous
charge ni des essais de coupure d'alimentation.

Le système et les révisions restent sur eMMC, Ubuntu et les partitions
constructeur restent préservés. Les [mises à jour locales et leur rollback
applicatif](local-updates.md) ont également été validés depuis.

La release finale doit toujours consommer une image OCI pour `core` ; la
distribution et l'automatisation feront l'objet du jalon prévu après le boot.
