# Incident SSH du 12 octobre 2026

Après l'activation du mode autonome pour un essai SSH utilisateur, le port 2222
est devenu indisponible. Le port 22 identifiait de nouveau Ubuntu.

## Constats

- Le boot Pantavisor `7a11069d-2709-43cd-9377-36818e0278a6` n'a pas enregistré
  les marqueurs d'arrêt propre. Le dernier heartbeat retrouvé après relecture
  du journal NVMe indique `starts: 17`, `uptime: 3152` et la même identité
  applicative. La cause exacte de cet arrêt initial n'est pas établie.
- Le store et le NVMe portaient `needs_recovery`. Le store a été copié et les
  blocs alloués du NVMe sauvegardés par `e2image -Q -a` avant `e2fsck -p`.
  Les contrôles ultérieurs `e2fsck -f -n` ont réussi, avec identité conservée.
- Le premier redémarrage de récupération (`e02831dc-b869-460e-97d5-8a1b1fec7ed4`)
  a révélé une course de disponibilité : le journal montre le signal `ready`,
  le passage de `diagnostic` à `READY`, puis une notification tardive le
  replaçant à `STARTED`. L'application continuait à écrire ses heartbeats,
  mais la disponibilité globale n'était pas acquise. Le retour de démarrage
  du gardien a suivi, avec un heartbeat final à 182 secondes.

Aucune correction du binaire Pantavisor n'avait été déployée pendant cette
remise en service. La course READY/STARTED a ensuite été reproduite, corrigée
et livrée dans [`locals/runtime-041`](runtime-recovery.md). La cause de l'arrêt
initial demeure distincte et non établie.

## Remise en service

Une seconde sauvegarde et relecture des journaux a conservé le compteur 18 et
l'identité `7877e500-a853-430e-b506-a423eebb1ca1`. Le boot suivant a atteint
`READY` pour les deux conteneurs, sans redémarrage manuel du conteneur de test.

`restore-diagnostic-ssh.py` a vérifié l'accès jusqu'à 217 secondes puis testé
Bash et Nushell avec un terminal SSH. Son résultat est conservé dans
`artifacts/autonomous/6491b61ba229489cb8bacb1719de7c2c/ssh-recovery-result.json`.
La carte a été laissée sous Pantavisor pour l'essai utilisateur.

Sauvegardes sur la carte :

- `/var/lib/ventuno-autonomous/6491b61ba229489cb8bacb1719de7c2c/recovery-20261012T161039Z/` ;
- `/var/lib/ventuno-autonomous/6491b61ba229489cb8bacb1719de7c2c/recovery-20261012T162646Z/`.

Les scripts `inspect-autonomous-failure.sh` et `read-last-runtime-log.sh`
collectent les éléments en lecture seule. `recover-autonomous-filesystems.sh`
vérifie l'identité et l'absence de montage avant sauvegarde et récupération ;
il ne reformate aucun système de fichiers.
