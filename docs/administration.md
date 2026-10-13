# Administration native

Sur le lab qualifié, SSH arrive dans le conteneur `core`, port 2222, avec
authentification par clé :

```sh
ssh -t -F artifacts/diagnostic-ssh/config ventuno-diagnostic 'exec bash'
```

Le nom d'alias est historique ; le conteneur diagnostic n'est plus déployé.
Le PID 1 visible dans core est celui du conteneur. L'observation du PID 1 hôte
est disponible dans `/trial-status/guard.status`.

Depuis core :

```sh
pvcontrol containers ls
kubectl get nodes -o wide
kubectl get pods -A
k9s
```

Les commandes Kubernetes concernent le profil k0s. Son kubeconfig administrateur
est accessible en lecture seule via `/k0s-access/admin.conf` et le lien
`~/.kube/config`. Le profil base fournit seulement les outils système.

## Redémarrage et secours natifs

La carte utilise maintenant `locals/0.1.0`. Depuis core :

```sh
pvcontrol cmd reboot
```

Pour sélectionner le secours indépendant au prochain reboot :

```sh
printf 'recovery\n' > /boot-control/next
pvcontrol cmd reboot
```

Le secours reste sélectionné jusqu'au réarmement explicite du boot natif.
`lab/resume-native-platform.sh` décrit le contrôle hors ligne et ce réarmement
sur la carte ; son reboot est une opération séparée. Voir le
[compte rendu de migration](history/native-platform-20261013.md).

`pvcontrol steps show-progress current` n'a pas de résultat pour le seed initial
provisionné directement : utiliser la révision active, `steps ls`, l'état des
conteneurs et du gardien pour observer ce premier boot. Le suivi `DONE` concerne
le cycle de mise à jour.

## Ancien contrat du lab

Dans l'ancien contrat uniquement, `pvcontrol cmd reboot` redémarre Pantavisor. Pour sélectionner Ubuntu avant le
reboot, écrire `ubuntu` dans `/boot-control/next`. Ces opérations interrompent
la qualification en cours ; les procédures et leurs preuves sont détaillées
dans [l'administration du jalon 070](history/k0s-os.md#administration-native).

Ce même compte rendu décrit l'accès au namespace k0s avec `kubectl debug` et
`nsenter`. Cet accès dépend de la disponibilité de l'API Kubernetes. La console
série JCTL est en **1,8 V**, 115200 8N1 ; voir
[console et récupération](history/serial-and-recovery.md).
