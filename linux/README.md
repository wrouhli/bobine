# Bobine : version Linux (serveur ou VPS)

<sub>🌍 <b>Français</b> · <a href="README.en.md">English</a></sub>

**Tes Reels, et n'importe quelle vidéo TikTok/YouTube, sauvegardés deviennent
une base de connaissances locale, cherchable et interrogeable. Sur ta machine,
chez toi.**

L'édition Linux/VPS du projet [Bobine](https://github.com/wrouhli/bobine).
Elle vit dans le dossier `linux/` du dépôt et partage son cœur (ingestion,
transcription, résumés, pages) avec l'édition Mac. Ici, Bobine vit sur un serveur : un petit VPS, une
machine à la maison, un vieux portable sous Linux. Pas d'iCloud, pas de
double-clic : un minuteur systemd et une boîte de réception locale.

> **Statut : premier portage.** Le cœur (ingestion, transcription, résumés,
> pages, carte) est le même code que la version Mac ; seuls l'installation et
> le réveil changent. Testé en priorité sur Debian (aarch64 inclus).

## Comment ça marche

    liens → inbox.txt → réveil (15 min) → fiches (raw/) → résumés → vault.html

1. Tu déposes un lien dans `inbox.txt` (à la main, par `ssh`, ou via le petit
   serveur HTTP optionnel) ;
2. Toutes les 15 minutes, Bobine relève la boîte : télécharge, transcrit,
   écrit une fiche dans `raw/` ;
3. S'il y a une clé API : résumé + thèmes → `index.md` ;
4. `vault.html` (liste) et `graph.html` (carte des thèmes) sont régénérés.

*Sans clé API : les fiches arrivent quand même dans `raw/` (lisibles en Markdown), et l'index et les pages se remplissent dès que tu ajoutes une clé ; Bobine rattrape tout ce qui attend.*

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

## Crush (bonus)

[Crush](https://charm.sh/crush) est un assistant IA pour le terminal : lancé
dans le dossier du vault, il lit tes fiches pour répondre (« Quelles vidéos
parlent de cuisine ? »). L'installateur prépare son fichier de réglages
(`.crushrc`, lecture seule, avec ta clé) ; il ne reste qu'à l'installer, via
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
- **systemd --user indisponible** → utilise la ligne cron ci-dessus.
- **Installation des dépendances en échec** → `logs/install.log` ; sur les
  petites machines, la compilation de certains paquets peut manquer d'un
  paquet système (`sudo apt install build-essential python3-dev`).

## Désinstaller

    ./desinstaller-linux.sh     # retire le réveil, le serveur de liens, et (si tu veux) le dossier

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
