# Plateforme native `locals/0.1.0` — 13 octobre 2026

## État matériel final

La VENTUNO Q utilise maintenant **`locals/0.1.0`**, core **0.8.0** et
k0s **v1.36.4+k0s.1**, avec le contrat `emmc-file-store-v1`.

Identité d'installation : `e864eba0e2c84ac1a03738743e4c67d7`.
Le noyau reste `6.8.0-1084-qcom`. Pantavisor est PID 1 ; son gardien utilise
le watchdog matériel de 30 secondes. Le store neuf fait **4 Gio**.

Le firmware conserve sa chaîne reconnue sous `EFI/ubuntu`, mais le bootstrap
ESP lance désormais directement les EFI natifs depuis
`EFI/ventuno-native-e864eba0e2c84ac1a03738743e4c67d7/`. Il ne lit plus le
`/boot/grub/grub.cfg` de p71 pour sélectionner Pantavisor ou son secours.

Le système de fichiers p71 est monté sur `/mnt/pv-system` par le runtime natif.
**L'userspace Ubuntu n'intervient plus dans le démarrage ni dans la récupération.**
Ses fichiers restent néanmoins présents sur p71 pour permettre un retour arrière.
Ils n'ont pas été supprimés et aucune partition n'a été reformatée.

## Console du secours corrigée

L'applet BusyBox `setsid` était absent du premier secours matériel. Après
activation de `CONFIG_SETSID=y`, reconstruction et remplacement de l'image :

- le packaging vérifie la présence des outils `setsid` et `e2fsck` ;
- la VM exécute réellement une commande sur sa console série ;
- sur matériel, `/bin/setsid` est présent et a exécuté un shell avec succès.

La console série interactive a été testée en VM. Sur carte, l'exécution de
`setsid` a été vérifiée via SSH ; aucune nouvelle validation clavier/UART physique
n'est revendiquée.

## Qualification

| Contrôle | Résultat |
| --- | --- |
| Révision sélectionnée | `locals/0.1.0` |
| Core | 0.8.0, prêt, interface d'administration native |
| k0s | Nœud `Ready`, UID conservé |
| Ressources | 7 500 mCPU et environ 12,43 Gio planifiables |
| Reboot normal | Boot ID changé et compteur permanent du core 1 → 2 |
| Secours depuis le nouveau boot | EFI autonome, SSH disponible, aucun volume persistant automonté |
| Systèmes de fichiers | `e2fsck -f -n` réussi sur p71, NVMe et store natif |
| Retour du secours | Nouveau boot natif réussi, compteur core 3 |
| Workload existant | API Hello world accessible après chaque cycle |

L'UID du nœud reste `3f36e144-59b3-440e-856f-e664534b08fe`. Les données k0s,
sa PKI et les workloads sur NVMe ont été réutilisés, sans reconstruction du cluster.

### Révision initiale et historique de mise à jour

Le store a été provisionné directement avec la révision `locals/0.1.0` comme
révision initiale. Pantavisor expose cette révision active, mais aucun historique
de mise à jour : `steps ls` indique `progress: {}` et `show-progress current`
répond que la ressource n'existe pas. Il ne faut pas annoncer un statut `DONE`
pour ce provisionnement initial.

Le banc de qualification avait initialement confondu ce cas avec un échec du
cluster. Il contrôle désormais séparément la révision initiale, la santé observée,
le délai de stabilité, l'identité du nœud, les ressources et l'API. Les mises à jour
ultérieures devront suivre et valider le cycle de mise à jour Pantavisor normal.

La version locale `0.1.0` n'est pas une publication GHCR : les sources restent
non commitées, aucun tag Git ni artefact de release n'a été publié.

## Retour à l'installation précédente

L'ancien store et ses fichiers de boot sont conservés, avec leur inode, sous :

```text
/var/lib/ventuno-native-migrations/e864eba0e2c84ac1a03738743e4c67d7/previous-pantavisor/
```

Le même répertoire contient le bootstrap ESP précédent, l'environnement GRUB
précédent, `migration.json` et `rollback.sh`. Ce script s'exécute **depuis le
secours**, après copie en RAM et avec p71/ESP initialement démontées. Il replace
l'ancien répertoire, restaure les environnements et le bootstrap, puis laisse le
reboot à l'opérateur. Il conserve aussi le store natif déplacé sous
`/boot/pantavisor-failed-<identité>` ; il ne modifie pas le NVMe.

La procédure est préparée, mais ce retour complet à 070 n'a pas été rejoué après
la migration. Le passage au secours et le retour au runtime natif ont été testés.

## Preuves locales

- Console VM : `artifacts/native-console-qualification/`.
- Bundle corrigé : `dist/base-native-console/`.
- Rendu k0s privé : `dist/native-k0s-hardware-state/`.
- Installation privée : `dist/native-k0s-hardware-installation/`.
- État du cluster avant migration : `artifacts/cluster-audit/117967775edc42818ff6f958045bf4a6/`.
- Installation : `artifacts/20261013T200510444880Z-install-native-platform.log`.
- Boot et reboot natifs : `artifacts/native-platform/ffdded2e40c04851a9a2101fee3a2441/`.
- Secours matériel corrigé : `artifacts/native-hardware/6e192035b401476885ce8194955f6268/`.
- Retour final au runtime : `artifacts/native-platform/15bc424a3d214a83a7c3935810689246/`.

## Suites

Restent le retrait contrôlé des fichiers Ubuntu devenus inutiles, les mises à jour
atomiques BSP/ESP avec tests de coupure pendant installation et la publication
de release. Les tests de corruption/absence de partition sont des tests VM ;
aucune corruption volontaire des volumes matériels n'a été effectuée.
