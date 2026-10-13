# Démarrage autonome et store durable sur eMMC

La [révision courante `locals/k0s-os-070`](k0s-os.md) utilise
core 0.7.0 avec l'administration native et k0s, le runtime corrigé et le défaut Pantavisor avec récupération
Ubuntu persistante. Cette page conserve la qualification initiale du boot
autonome avec core 0.3.0 et Ubuntu par défaut ; consulter le nouveau guide pour
la [politique de récupération](runtime-recovery.md) et les commandes actuelles.

Le mode autonome est installé et validé sur la VENTUNO Q. Il utilise
**Pantavisor PID 1**, **core 0.3.0**, un **store eMMC durable de 1 Gio** et les
données applicatives NVMe existantes. Les redémarrages propres et le rollback
enchaînent directement les boots Pantavisor.

**Ubuntu reste le choix GRUB par défaut pendant cette qualification.** La carte
est actuellement revenue sous Ubuntu, avec l'entrée persistante installée et
aucune sélection ponctuelle en attente.

## Implantation sur la carte

```text
/boot/pantavisor/
├── install-id
├── kernel
├── initramfs
├── build-inputs.json
├── pvstore.ext4                  # 1 Gio, réutilisé à chaque boot
├── state/
│   ├── grubenv                   # pv_rev, pv_try, ventuno_attempt
│   └── boot-budget               # compteur de boots rapides
└── logs/<boot-id>.log
```

Le store reste un fichier ext4 sur la racine Ubuntu eMMC, sans repartitionnement.
Son `/boot` interne est un lien vers le répertoire `state/` ci-dessus. Pantavisor
et GRUB partagent ainsi **le même état de sélection**, sur un fichier ext4
directement accessible à GRUB, hors du loop du store. Le store et `state/`
doivent être conservés ensemble lors d'une sauvegarde ou restauration.

Les données applicatives restent sur le NVMe, UUID
`5ccb2c2f-c0f7-44a1-a291-b261a7d060a3`. Aucun nouveau formatage NVMe n'a été effectué.
Les sources et résultats locaux sont dans `artifacts/prototype-1084-autonomous/`.

L'entrée GRUB porte l'identifiant **`pantavisor-persistent`**, généré par
`scripts/autonomous_boot.py` et installé via `/etc/grub.d/41_ventuno_persistent`.
Le noyau et l'initramfs de cette entrée sont fixes. Un hook refuse une mise à
jour dont les objets BSP diffèrent de ces fichiers ; les mises à jour du BSP
nécessiteront un autre jalon de sélection des images.

## Sélection des révisions et récupération

À l'entrée dans Pantavisor, GRUB :

1. Consomme la sélection ponctuelle de son environnement Ubuntu habituel.
2. Vérifie le budget de boots rapides.
3. Lit `pv_rev`, la révision validée, et l'éventuel `pv_try`.
4. Essaie `pv_try` une seule fois, en enregistrant `ventuno_attempt` avant le
   chargement du noyau.
5. Si cette tentative a déjà eu lieu, charge `pv_rev` et laisse Pantavisor
   terminer le traitement du rollback.

Le hook `20-ventuno-boot-policy` remet le marqueur d'essai à zéro lors d'une
nouvelle installation de révision et après un commit réussi. Une révision
réappliquée explicitement peut donc bénéficier d'une nouvelle tentative.

Le marqueur du dernier essai peut rester présent après un rollback alors que
`pv_try` a été effacé. Il est ignoré, puis effacé au prochain boot sans candidat ;
il ne désigne pas la révision actuellement exécutée.

### Boucle de reboots contrôlée

Un arrêt propre prépare `next_entry=pantavisor-persistent` dans le grubenv
Ubuntu, puis démonte les systèmes de fichiers. Le reboot suivant retourne
directement dans Pantavisor, avec le même store. La sélection ponctuelle est
consommée par GRUB avant de lancer Linux.

Le retour explicite vers Ubuntu laisse cette sélection vide. Une mise sous
tension ou un reset non préparé, sans sélection ponctuelle, suit également
le défaut Ubuntu actuel. La bascule de Pantavisor comme choix par défaut au
démarrage à froid reste à qualifier séparément.

### Watchdog permanent

Le gardien n'impose plus de durée maximale de fonctionnement :

- watchdog matériel : **30 secondes**, alimenté par le gardien ;
- vérification locale de l'API Pantavisor toutes les **5 secondes** ;
- première disponibilité requise dans les **180 secondes** du bootstrap ;
- après disponibilité, récupération si aucune réponse API valide depuis
  **45 secondes**, ou aucun état prêt depuis **120 secondes** ;
- budget GRUB : **3 boots rapides**, remis à zéro après 120 secondes de
  fonctionnement avec un état prêt récent, ou lors d'une activation explicite
  depuis Ubuntu.

Le client de santé ARM64 parse les états JSON réels : `status_goal=READY`
ne suffit pas. Core doit être prêt ; les conteneurs arrêtés explicitement par
l'utilisateur sont pris en compte dans ce contrôle. Il s'agit d'une surveillance
du runtime et de ses états de disponibilité, pas d'un test fonctionnel complet
de chaque application.

Les fichiers de santé sont visibles depuis core sous `/trial-status/` :

```sh
cat /trial-status/guard.status
cat /trial-status/health.status
ventuno-revision-status
```

Le gardien annonce `supervisor_version=5`, `phase=autonomous`, `return_after=0`.
Ses alarmes de démarrage et de récupération restent indépendantes des sessions SSH.

## Utilisation de l'installation actuelle

Identifiant installé : **`6491b61ba229489cb8bacb1719de7c2c`**.

Depuis le poste, alors que la carte est sous Ubuntu :

```bash
python3 scripts/run-board-check.py --sudo \
  --argument 6491b61ba229489cb8bacb1719de7c2c scripts/start-autonomous.sh
```

Ce script vérifie les assets, le store et la configuration GRUB, réinitialise
le budget, puis programme une activation one-shot. Une fois core disponible :

```bash
ssh -F artifacts/diagnostic-ssh/config ventuno-diagnostic
```

Dans core :

```sh
ventuno-reboot             # reboot propre vers Pantavisor
ventuno-reboot ubuntu      # reboot propre vers Ubuntu
```

`pvcontrol cmd reboot` retourne aussi vers Pantavisor, sauf si un retour Ubuntu
a déjà été demandé. Core dispose de Bash 5.3.20, Nushell 0.116.1 et des terminaux
SSH comme au jalon précédent.

Depuis Ubuntu, contrôler l'installation après retour :

```bash
python3 scripts/run-board-check.py --sudo \
  --argument 6491b61ba229489cb8bacb1719de7c2c scripts/check-autonomous-return.sh
```

Pour retirer l'entrée persistante, le helper ci-dessous restaure la configuration
GRUB antérieure uniquement si les fichiers correspondent encore au reçu
d'installation. Il conserve le store, les journaux et le NVMe :

```bash
python3 scripts/run-board-check.py --sudo \
  --argument 6491b61ba229489cb8bacb1719de7c2c scripts/disable-autonomous.sh
```

Les sauvegardes GRUB et reçus sont sous
`/var/lib/ventuno-autonomous/6491b61ba229489cb8bacb1719de7c2c/`.
Le helper de désactivation est fourni comme procédure de retrait ; l'entrée
reste installée à l'issue de cette qualification.

## Construction et installation initiale

```bash
bash scripts/build-initramfs.sh
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --runtime --core --pid1 --autonomous \
  --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --nvme-profile bsp/nvme-app-storage.json \
  --output-dir artifacts/prototype-1084-autonomous
python3 scripts/build-first-revision.py --output-dir artifacts/prototype-1084-autonomous
python3 scripts/build-local-revisions.py --output-dir artifacts/prototype-1084-autonomous
python3 scripts/verify-prototype.py --output-dir artifacts/prototype-1084-autonomous --emulate
python3 scripts/verify-first-revision.py --output-dir artifacts/prototype-1084-autonomous
```

`--autonomous` exclut `--trial`. Le seed autonome mesure 1 Gio et prépare le
lien vers l'état de boot externe. `prepare-autonomous.py` transfère les fichiers
et génère un identifiant ; `install-autonomous.sh` crée le store et l'entrée
stable, sans sélectionner cette entrée ni changer `GRUB_DEFAULT=0`.

Ces opérations initiales ont déjà été effectuées sur la carte. L'installateur
refuse d'écraser `/boot/pantavisor`. Les activations suivantes utilisent
`start-autonomous.sh`, sans recopier de seed.

## Qualification

### UEFI/GRUB en QEMU

Le test utilise le **GRUB ARM64 réellement présent sur la carte**, exporté en
lecture seule avec ses modules, et le firmware UEFI AArch64 du poste. Le test
de récupération représente l'entrée Ubuntu par un arrêt de la VM ; les essais
matériels utilisent, eux, l'Ubuntu installé.

```bash
python3 scripts/fetch-grub-reference.py
python3 scripts/test-autonomous-boot.py --output-dir artifacts/prototype-1084-autonomous
python3 scripts/test-autonomous-boot.py --output-dir artifacts/prototype-1084-autonomous --exhausted-budget
python3 scripts/test-autonomous-boot.py --output-dir artifacts/prototype-1084-autonomous --stalled-bootstrap
```

Les trois scénarios ont réussi :

- quatre boots sur un seul store, révision d'essai sélectionnée une fois,
  rollback automatique et retour explicite à la récupération ;
- budget déjà épuisé : retour à la récupération avant de lancer Linux,
  store inchangé ;
- bootstrap volontairement bloqué : le gardien autonome déclenche le retour
  après son délai de démarrage, store inchangé.

Les **31 tests unitaires** passent également. Le client de santé ARM64 a été
exécuté sous QEMU utilisateur avec des réponses READY et STARTING pour vérifier
qu'il distingue l'état réel de l'objectif de disponibilité.

Les références locales sont respectivement `993f4f204fab40a7b33cebfbdb59af4c`,
`004b76bda0f343f5b9feb7dccfb13569` et `a5af83ec9f90454d996d4bbc62c75ddb`, sous
`artifacts/prototype-1084-autonomous/qemu-autonomous-test/`.

Un retour très rapide avait révélé que le diagnostic gardait son descripteur
de journal ouvert dans le namespace initial. Le watcher arrête désormais ce
groupe de processus et attend la libération du support avant d'annoncer la fin
de l'arrêt. Les vérifications contrôlent aussi les flags ext4
`needs_recovery`/`orphan_present` : le code de retour d'`e2fsck -n` seul pouvait
masquer un journal non rejoué.

### Résultat sur la carte — 12 octobre 2026

Le même fichier `/boot/pantavisor/pvstore.ext4` a servi aux **quatre boots**,
sans intervention Ubuntu ni copie intermédiaire :

1. Démarrage usine, mises à jour v2/v1/v2 et reboot natif.
2. GRUB sélectionne v2, qui devient `DONE`. Fonctionnement observé au-delà de
   205 secondes, sans timer de retour, avec le watchdog matériel armé.
3. Démarrage réel de `locals/app-unready`, qui n'atteint pas READY et échoue
   après le timeout de 45 secondes.
4. GRUB reprend la v2 validée ; Bash, Nushell, SSH et les données NVMe sont
   vérifiés, puis `ventuno-reboot ubuntu` termine la qualification.

| Contrôle final | Résultat |
| --- | --- |
| Store durable | **1 073 741 824 octets**, même inode **1551489** |
| UUID du store | `f41b268e-c936-4345-8459-5e1002bdd012`, inchangé |
| Révision validée | `pv_rev=locals/app-v2`, statut `DONE` |
| Mauvaise révision | `ERROR — Status goal not reached` |
| Compteur core | **4** |
| Compteur applicatif NVMe | **16**, après un état initial à 9 |
| Identité applicative | `7877e500-a853-430e-b506-a423eebb1ca1`, conservée |
| Store et NVMe après arrêt | propres, sans journal à rejouer ni réparation |
| Ubuntu | revenu, aucun service en échec, `next_entry` vide |

Les quatre journaux de boot confirment trois destinations suivantes
`pantavisor`, puis une destination `ubuntu`. Le dernier journal peut être
interrompu avant la fin de la collecte de diagnostic, puisque le retour a été
demandé tôt ; le PID 1 a été vérifié en direct depuis core.

Le boot Ubuntu final est `95525e09-6065-41e4-b9e1-bbb34288ac90`. Le reçu de
validation est conservé sur la carte et dans
`artifacts/20261012T135702607472Z-check-autonomous-return.log`. Les preuves SSH
sont sous `artifacts/autonomous/6491b61ba229489cb8bacb1719de7c2c/`.

Empreintes du build installé :

- initramfs (18 100 701 octets) :
  `bb8b50af808a759b1f06bd3a19a8fb3a8c7e623d221b63e13a5723096c85122d` ;
- core 0.3.0 :
  `3cf0309bb371560cd7d5c0a8209e0cfa4518cb65e1918193f5d4f12d442947da` ;
- seed initial :
  `f13beff26471cf590fc65df05d6c2460d00d603cd1fd91084dcb52d800535c92`.

Le test `check-autonomous-over-ssh.py` réalise les mises à jour de qualification
sur un store initial neuf. Pour une installation déjà utilisée, les commandes
de statut et de reboot ci-dessus permettent l'exploitation courante.

## Suite

La qualification sur plusieurs heures, sous charge et avec arrêts non préparés
reste le prochain jalon. Le choix de Pantavisor comme démarrage par défaut à
froid pourra ensuite être traité avec sa politique de récupération. La cible
de release reste un core consommé sous forme d'image OCI.
