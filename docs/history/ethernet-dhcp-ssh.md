# Ethernet DHCP et SSH dans le prototype supervisé

Le prototype courant utilise [le conteneur core](core.md).
Cette page conserve l'historique du service réseau lancé par le superviseur et
la procédure de provisionnement des clés, toujours utilisée.

Le périmètre courant est **Ethernet seul, Wi-Fi désactivé**. Voir
[wifi-disabled.md](wifi-disabled.md). Les résultats matériels ci-dessous
décrivent l'essai réseau antérieur à cette exclusion ; la nouvelle variante
Ethernet seule a passé les contrôles en émulation, puis sur la carte avec
la [première révision embedded](first-revision.md).

## État : testé sur la carte le 11 octobre 2026

Essai **`f16def9b9f884367a49da24000cc0fa4`** : démarrage automatique du client
DHCP et de SSH, connexion authentifiée depuis le poste, puis retour automatique
Ubuntu et restauration de GRUB réussis.

| Paramètre du prototype | Valeur observée |
| --- | --- |
| Interface Ethernet | `eth0`, choisie par le pilote `qcom-ethqos` |
| Configuration IPv4 | DHCP |
| Adresse obtenue | `192.168.1.20/24` |
| Passerelle et DNS du bail | `192.168.1.254` |
| Lien Ethernet | 2,5 Gbit/s full duplex dans le journal noyau |
| Serveur SSH | Dropbear du BSP Pantavisor, port **2222** |
| Compte | **root**, authentification par clé uniquement |
| Fenêtre de diagnostic | 180 secondes, même lorsqu'une session SSH est ouverte |

La connexion a réussi à **12:37:47 UTC**, avec vérification de la clé d'hôte et
du marqueur de l'essai dans `/proc/cmdline`. Le shell a retourné `uid=0(root)`,
le noyau 1084, le PID 1 `ventuno-init` et le bail DHCP attendu.

La carte est ensuite revenue sous Ubuntu ; aucun service systemd en échec,
configuration GRUB antérieure restaurée et aucune sélection ponctuelle restante.
Le port 2222 n'est donc ouvert que pendant un boot de ce prototype, pas sous
l'Ubuntu actuellement actif.

## Connexion depuis ce poste

Pendant une fenêtre de diagnostic :

```bash
ssh -F artifacts/diagnostic-ssh/config ventuno-diagnostic
```

La configuration générée fixe l'adresse, le port 2222, l'utilisateur root, la
clé cliente et le fichier de clés d'hôtes dédié. Elle ne modifie pas la
configuration SSH personnelle du poste ni la clé d'hôte Ubuntu du port 22.

Le client OpenSSH récent peut afficher un avertissement d'absence d'échange
post-quantique avec cette version de Dropbear. L'authentification par clé et
la vérification de l'identité du serveur ont néanmoins été effectuées et testées.

## Fonctionnement

- Le superviseur lance `ventuno-network` indépendamment de Pantavisor dès que
  le premier jalon persistant est disponible.
- Le service attend l'interface du contrôleur Ethernet, la met en service et
  lance BusyBox `udhcpc` en continu pour obtenir/renouveler le bail.
- Le script DHCP configure adresse, masque, route par défaut et DNS dans le
  système en RAM. Il enregistre le bail dans `/run/ventuno-dhcp.state`.
- Dropbear écoute sur 2222, avec mots de passe et redirections de ports désactivés.
- Le superviseur conserve sa minuterie et son watchdog, indépendamment des
  processus réseau et des sessions SSH.

Les utilitaires BusyBox `udhcpc`, `readlink` et `id` ont été ajoutés, et le PATH
des sessions Dropbear inclut `/usr/sbin` et `/sbin` pour permettre l'utilisation
directe de `ip` et des outils de diagnostic.

### Identité réseau de cette carte

Le profil local reprend l'adresse MAC réellement utilisée sous Ubuntu et
vérifie que son identifiant DHCP est `01:<MAC>`. Cette identité est réappliquée
au contrôleur `qcom-ethqos` avant DHCP. Le bail actuel a ainsi été conservé.

Ce profil est propre à la carte du lab : ne pas réutiliser sa MAC sur plusieurs
cartes simultanément. Le provisionnement d'une identité stable pour une image
générique multi-cartes reste une étape ultérieure. Le transfert refuse une image
dont la MAC du profil ne correspond plus à l'Ubuntu cible.

## Clés et génération de l'image

Les fichiers locaux sont dans `artifacts/diagnostic-ssh/`, exclu de Git :

- `client_ed25519` : clé privée cliente, reste sur le poste ;
- `client_ed25519.pub` : clé publique autorisée dans l'image ;
- `dropbear_ed25519_host_key` : clé privée d'hôte du serveur de diagnostic,
  générée avec l'outil Dropbear correspondant au build et embarquée dans l'image ;
- `host_ed25519.pub` et `known_hosts` : identité d'hôte épinglée avant connexion ;
- `network-profile.json` et `config` : profil de cette carte et configuration SSH.

```bash
bash scripts/build-initramfs.sh
python3 scripts/provision-diagnostic-ssh.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz
python3 scripts/assemble-prototype.py \
  artifacts/build/tmp/deploy/images/ventuno-q/pantavisor-initramfs-ventuno-q.cpio.gz \
  --trial --network-profile artifacts/diagnostic-ssh/network-profile.json \
  --output-dir artifacts/prototype-1084-ethernet-only
python3 scripts/verify-prototype.py --output-dir artifacts/prototype-1084-ethernet-only --emulate
python3 scripts/test-network-boot.py
```

La génération des clés réutilise les clés existantes, mais actualise le profil
Ethernet depuis Ubuntu. La clé privée cliente n'est jamais copiée dans l'image.

L'image matériellement testée faisait **35 650 666 octets**, avec l'empreinte :

```text
4baffa1205705abbad335d8187f54a2ae0c2bda37840c8304ca64e4ef4691556  initramfs-ventuno-q.cpio.gz
```

## Vérifications exécutées

En QEMU avec le vrai noyau/initramfs :

1. Obtention d'un bail DHCP sur une carte virtio isolée du LAN.
2. Connexion SSH, clé d'hôte épinglée, vérification de l'identifiant du boot.
3. Refus d'une clé cliente non autorisée, sans proposition d'authentification par mot de passe.
4. Journalisation persistante du réseau et retour temporisé.

Sur la carte :

- même authentification et contrôle du marqueur de boot via
  `scripts/probe-diagnostic-ssh.py` ;
- adresse `192.168.1.20`, route et exécution de commandes distantes confirmées ;
- retour automatique sous Ubuntu et retrait de l'entrée d'essai.

Traces :

- `artifacts/prototype-1084-network/qemu-network-test/` ;
- `artifacts/trials/f16def9b9f884367a49da24000cc0fa4/ssh-check.log` ;
- `artifacts/20261011T124127816971Z-finish-trial.log`.

Le prototype reste un diagnostic supervisé : Pantavisor est un enfant en mode
standalone, pas encore le PID 1 du système embedded avec ses conteneurs.

## Historique : observation Wi-Fi pendant la session SSH

Le firmware QCA2066 est maintenant disponible, mais `wlan0` n'apparaissait pas
au relevé initial. Pendant la session, `modprobe qrtr_mhi` a débloqué
l'initialisation : `wlan0` est apparu, avec identification du chipset et du build
firmware dans `dmesg` vers 148 secondes d'uptime.

Le module était déjà embarqué ; il manquait au chargement explicite. La liste
`early_modules` a été corrigée pour les prochains assemblages. **Cette correction
automatique n'a pas encore fait l'objet d'un nouveau boot**. La trace persistante
prise plus tôt indique donc encore `WIFI_INTERFACE_COUNT=0`. Aucune association
à un point d'accès n'a été testée.

Cette piste a ensuite été abandonnée pour la V1 à la demande du propriétaire :
les composants Wi-Fi sont maintenant exclus de la sélection courante.
