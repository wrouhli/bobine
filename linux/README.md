# Bobine : version Linux (serveur ou VPS)

<sub>🌍 <b>Français</b> · <a href="README.en.md">English</a></sub>

**Tes Reels, et n'importe quelle vidéo TikTok/YouTube, sauvegardés deviennent
une base de connaissances locale, cherchable et interrogeable. Sur ta machine,
chez toi.**

L'édition Linux/VPS du projet [Bobine](https://github.com/wrouhli/bobine).
Elle vit dans le dossier `linux/` du dépôt et partage son cœur (ingestion,
transcription, résumés, pages) avec l'édition Mac. Ici, Bobine vit sur un serveur : un petit VPS, une
machine à la maison, un vieux portable sous Linux. Pas d'iCloud, pas de
double-clic : un minuteur systemd, une relève immédiate dès qu'un lien arrive, et une boîte de réception locale.

> **Statut : premier portage.** Le cœur (ingestion, transcription, résumés,
> pages, carte) est le même code que la version Mac ; seuls l'installation et
> le réveil changent. Testé en priorité sur Debian (aarch64 inclus).

## Comment ça marche

    liens → inbox.txt → relève (tout de suite, sinon 15 min) → fiches (raw/) → résumés → vault.html

1. Tu déposes un lien dans `inbox.txt` (à la main, par `ssh`, ou via le petit
   serveur HTTP optionnel) ;
2. Dès qu'un lien arrive dans la boîte (sinon au plus tard 15 minutes plus
   tard, en filet de sécurité), Bobine relève : télécharge, transcrit,
   écrit une fiche dans `raw/` ;
3. S'il y a une clé API : résumé + thèmes → `index.md`, et un mémo par vidéo
   → `memos/` (avec un bloc « Pour toi » si tu as rempli `Mon profil.txt`,
   facultatif ; l'installation propose de l'écrire) ;
4. `vault.html` (liste) et `graph.html` (carte des thèmes) sont régénérés.

*Sans clé API : les fiches apparaissent quand même dans la page, marquées « résumé en attente », et Bobine les remplacera par les vrais résumés dès que tu ajoutes une clé.*

## Prérequis

- Linux avec systemd (Debian 12+/Ubuntu 22.04+ et cousins ; aarch64 ok) ;
- Python 3.10+ avec venv : `sudo apt install python3 python3-venv` (Debian récent : le paquet versionné, ex. `python3.13-venv`) ;
- ffmpeg : `sudo apt install ffmpeg` ;
- ~2 Go libres (le modèle de transcription se télécharge au premier passage).

## Installation

Copie le dossier sur le serveur, puis lance l'installateur :

    rsync -av ~/bobine-linux/ mon-serveur:~/bobine-linux/     # ou scp -r
    ssh mon-serveur
    cd ~/bobine-linux && ./install-linux.sh

L'installateur te guide : nom du vault, emplacement, clé API (facultative),
réveil systemd. Il ne demande jamais de droits root, sauf si tu acceptes
d'installer ffmpeg via apt.

## Envoyer un lien

Trois façons, toutes écrivent dans la même boîte (`inbox.txt`) :

**1. Directement sur le serveur :**

    echo 'https://www.instagram.com/reel/Cxyz123AbCd/' >> ~/Bobine/inbox.txt

**2. Depuis ton ordinateur, en ssh :**

    ssh mon-serveur "echo 'https://youtu.be/jNQXAC9IVRw' >> ~/Bobine/inbox.txt"

**3. Par HTTP, depuis n'importe où (serveur de liens optionnel)** : voir la
section suivante.

Tout ce qui a déjà été traité est ignoré automatiquement : les vieux liens
peuvent rester dans la boîte.

## Le réveil

    systemctl --user list-timers bobine-watch.timer   # prochain passage
    systemctl --user start bobine-watch.service       # déclencher tout de suite
    tail -f ~/Bobine/logs/watch.log                   # ce qui se passe

Pas besoin d'attendre le prochain quart d'heure : dès qu'un lien est poussé
ou déposé dans la boîte, la relève part tout de suite (unité systemd
`bobine-watch.path`, activée à l'installation). Le minuteur de 15 minutes
reste en filet de sécurité (dépôt pendant un passage en cours, redémarrage…).
État de la relève instantanée :  `systemctl --user status bobine-watch.path`

Sans systemd (ou en cas de souci), l'équivalent en cron :

    */15 * * * * /bin/bash ~/Bobine/watch-linux.sh >/dev/null 2>&1

## Le serveur de liens (optionnel)

Un micro-serveur HTTP (bibliothèque standard Python, zéro dépendance) qui
accepte tes liens par POST, pratique depuis un raccourci de téléphone :

    cd ~/Bobine
    openssl rand -hex 16                     # fabrique un jeton…
    # … mets-le dans config.env :  INBOX_TOKEN="…"
    .venv/bin/python inbox_server.py --vault ~/Bobine

Test (le serveur écoute sur 127.0.0.1:8785 par défaut) :

    curl -X POST -H "Authorization: Bearer TONJETON" \
         -d 'https://youtu.be/jNQXAC9IVRw' http://127.0.0.1:8785/push

Pour l'utiliser à distance, expose-le proprement via ton tunnel (Cloudflare
Tunnel, Tailscale) ou un proxy avec mot de passe (Caddy, nginx) : **jamais ce
port en clair sur internet**. Un modèle de service systemd est fourni dans
`systemd/bobine-inbox.service`.

Préfère l'en-tête `Authorization: Bearer …`. Le serveur accepte aussi le jeton
dans l'adresse (`/push/JETON` ou `?token=…`) pour les raccourcis qui ne savent
pas ajouter d'en-tête ; Bobine le masque dans son propre journal, mais un
proxy ou un tunnel placé devant peut encore enregistrer les adresses complètes.

## Consulter la page

`vault.html` (et `graph.html`) vivent dans le dossier du vault. Quelques options :

    # la lire depuis ton poste, via un tunnel ssh
    ssh -L 8080:127.0.0.1:8080 mon-serveur
    # (sur le serveur : cd ~/Bobine && .venv/bin/python -m http.server 8080 --bind 127.0.0.1)
    # → puis http://127.0.0.1:8080/vault.html

Ou ramène simplement le fichier : `scp mon-serveur:~/Bobine/vault.html .`

**À distance, avec un mot de passe** : `page_server.py` sert UNIQUEMENT
`vault.html` et `graph.html` (jamais tes fiches ni ta config), protégés par un
mot de passe :

    cd ~/Bobine
    openssl rand -hex 16                     # fabrique un mot de passe…
    # … mets-le dans config.env :  PAGE_PASSWORD="…"
    .venv/bin/python page_server.py          # écoute 127.0.0.1:8786

Combiné à un tunnel (Cloudflare Tunnel, Tailscale…), la page devient une
adresse consultable de partout, téléphone compris. Modèles de services systemd
fournis : `systemd/bobine-page.service` (la page) et
`systemd/bobine-tunnel.service` (le tunnel Cloudflare dédié). Le script
`activer-page-web.sh mon-domaine.tld` automatise toute la mise en place
(mot de passe, tunnel dédié, services), sans sudo.

Protégée par Cloudflare Access (ou un autre videur en amont) ? Lance la page
avec `--sans-mot-de-passe` : Cloudflare fait la porte, la page ne demande plus
rien (ajoute l'option à la ligne ExecStart de ton service).

## Demander depuis la page

Avec ta clé de résumé déjà configurée, ouvre **Demander** à l'adresse habituelle de Bobine. Les réponses s'appuient sur jusqu'à cinq fiches et leurs extraits, avec des liens pour les vérifier. Depuis une fiche, la question reste limitée à cette vidéo. La conversation ne reste que dans l'onglet.

Pour une installation existante, ajoute `PAGE_ORIGIN=https://ton-adresse-bobine` dans `config.env` (origine exacte, sans chemin ni slash final), puis redémarre le service de page après mise à jour et régénération. `activer-page-web.sh` le configure lors d'une nouvelle activation. Le tunnel doit conserver l'en-tête Host public. Garde le mot de passe ou ta protection en amont : l'origine n'est pas une authentification.

Le fichier ouvert directement, la copie téléchargée et un simple serveur de fichiers restent en lecture seule. Les limites de demandes s'appliquent aussi à l'adresse publique et survivent au redémarrage. Aucun accès direct à `raw/`, à la configuration ou aux compteurs privés n'est ajouté. Le profil reste modifiable dans `Mon profil.txt`, pas dans la page.

Voir [le guide de vérification et de migration](../docs/demander-verification.md). Le déploiement doit être précédé d'une sauvegarde.

## Crush (bonus)

[Crush](https://charm.sh/crush) est un assistant IA pour le terminal : lancé
dans le dossier du vault, il lit tes fiches pour répondre (« Quelles vidéos
parlent de cuisine ? »). L'installateur prépare son fichier de réglages
(`.crushrc`, lecture seule, avec ta clé : Crush lit et cherche dans tes
fiches, mais ses outils pour modifier des fichiers, lancer des commandes ou
aller sur internet sont retirés) ; il ne reste qu'à l'installer, via
le dépôt Charm :

    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://repo.charm.sh/apt/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/charm.gpg
    echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" | sudo tee /etc/apt/sources.list.d/charm.list
    sudo apt update && sudo apt install crush
    # puis, dans le dossier du vault :  crush

## Entretien

- **Mettre yt-dlp à jour** (Instagram casse souvent) :
  `.venv/bin/pip install -U yt-dlp`
- **Cookies Instagram** : en cas d'échec de téléchargement, exporte un
  `cookies.txt` (extension « Get cookies.txt LOCALLY ») depuis ton navigateur
  de bureau, copie-le sur le serveur, et pointe `COOKIES=` dessus dans
  `config.env`. YouTube fonctionne sans cookies.
- **Transcription lente ?** C'est normal sur un petit serveur : chaque vidéo
  passe par Whisper (modèle « small »), de quelques dizaines de secondes à
  quelques minutes selon la machine. Les plafonds (15 vidéos par passage,
  50 par jour) lissent la charge.

## Dépannage

- **Rien ne se passe** → `tail -50 ~/Bobine/logs/watch.log` ; vérifie la boîte
  (`ls -la ~/Bobine/inbox.txt`) et le minuteur (`systemctl --user list-timers`).
- **Les résumés ne viennent pas** → pas de clé API dans `config.env`
  (facultatif ; vérifier avec `.venv/bin/python enrichir.py --dry-run`).
  Avec une clé, les fiches restent « (résumé en attente) » et `logs/watch.log`
  affiche le message du fournisseur (clé refusée, crédit épuisé, modèle retiré :
  mets `API_MODEL=…`). Bobine réessaie à chaque passage et appelle `NOTIF_CMD`
  si ça dure environ une heure.
- **Résumés en anglais** → ajoute `LANGUE_RESUMES=en` dans `config.env` (les
  pages et les messages restent en français).
- **systemd --user indisponible** → utilise la ligne cron ci-dessus.
- **Installation des dépendances en échec** → `logs/install.log` ; sur les
  petites machines, la compilation de certains paquets peut manquer d'un
  paquet système (`sudo apt install build-essential python3-dev`).

## Désinstaller

Tes fichiers locaux ne sont jamais supprimés automatiquement. Après avoir vérifié le contenu du dossier, tu peux le supprimer toi-même si tu n'en as plus besoin.

    ./desinstaller-linux.sh     # arrête les services ; conserve ta bibliothèque et tous tes fichiers locaux

## Différences avec la version Mac

| | Mac | Linux (ici) |
|---|---|---|
| Réveil | launchd | systemd (ou cron) |
| Boîte de réception | Raccourci iPhone + iCloud | `inbox.txt` (ssh, echo, HTTP) |
| Notifications | Centre de notifications macOS | option `NOTIF_CMD` (ntfy, etc.) |
| Page sur téléphone | copie iCloud | URL servie par ta machine (tunnel/proxy) |
| Installation | double-clic `.command` | `./install-linux.sh` |

Le reste (ingestion, filtre d'import Instagram, transcription, résumés,
pages, carte) est le même code que Bobine pour Mac.

---

Bobine, écrit et réalisé par Wahid Rouhli · [github.com/wrouhli/bobine](https://github.com/wrouhli/bobine)
