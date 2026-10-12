#!/bin/bash
# Bobine — désinstallation guidée (Linux).
# Usage : place-toi dans le dossier de ton vault, puis :  ./desinstaller-linux.sh
#
# Arrête le réveil systemd, le serveur de liens et la page web de ce dossier.
# Tous les fichiers locaux sont conservés, y compris les vidéos.

set -u

VAULT="$(cd "$(dirname "$0")" && pwd)"

# ----------------------------------------------------------- couleurs & aides
if [ -t 1 ]; then
  FONCE=$'\033[2m'; GRAS=$'\033[1m'; VERT=$'\033[1;32m'
  JAUNE=$'\033[1;33m'; VIOLET=$'\033[1;35m'; CYAN=$'\033[1;36m'; FIN=$'\033[0m'
else
  FONCE=""; GRAS=""; VERT=""; JAUNE=""; VIOLET=""; CYAN=""; FIN=""
fi

ok()    { printf "  ${VERT}✓${FIN} %s\n" "$1"; }
etape() { printf "\n${VIOLET}${GRAS}  ── %s${FIN}\n" "$1"; }
note()  { printf "  ${FONCE}%s${FIN}\n" "$1"; }
avis()  { printf "  ${JAUNE}⚠${FIN}  %s\n" "$1"; }

confirmer() {  # $1 = texte, $2 = défaut (o/n) ; renvoie vrai si oui
  local defaut="${2:-o}" invite reponse
  if [ "$defaut" = "o" ]; then invite="O/n"; else invite="o/N"; fi
  printf "  ${CYAN}➜${FIN} %s ${FONCE}[%s]${FIN} : " "$1" "$invite" >&2
  read -r reponse || true
  if [ -z "$reponse" ]; then reponse="$defaut"; fi
  case "$reponse" in
    o|O|oui|Oui|OUI|y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

affiche() { printf '%s' "${1/#$HOME/~}"; }

case "$VAULT" in
  "$HOME"|/) avis "Chemin inattendu ($VAULT) — abandon."; exit 1 ;;
esac

# ------------------------------------------------------------------ accueil
printf "\n${VIOLET}${GRAS}  Bobine — désinstallation${FIN}\n"
printf "  ${FONCE}Ce dossier : %s${FIN}\n" "$(affiche "$VAULT")"

if [ ! -f "$VAULT/watch-linux.sh" ] || [ ! -f "$VAULT/ingest.py" ]; then
  avis "Ce dossier n'a pas l'air d'être un dossier Bobine (watch-linux.sh / ingest.py introuvables)."
  if ! confirmer "Continuer quand même ?" "n"; then
    echo "  Rien n'a été touché."
    exit 1
  fi
fi

note "Au programme : arrêter le réveil automatique, le serveur de liens et la page web."
note "Tes vidéos locales et tous tes autres fichiers restent en place."

# Reconnaître des arguments complets, après décodage systemd (pas du shell).
# Tout format ambigu/personnalisé, lien ou surcharge reste volontairement intact.
PY_SERVICE=""
for candidat in "$VAULT/.venv/bin/python" python3 python3.13 python3.12 python3.11 python3.10; do
  if command -v "$candidat" >/dev/null 2>&1; then PY_SERVICE="$candidat"; break; fi
done
service_de_ce_dossier() {  # $1 = fichier unité, $2 = script attendu (ou tunnel)
  [ -n "$PY_SERVICE" ] && "$PY_SERVICE" -B - "$1" "$VAULT" "$2" "$HOME" <<'PYTHON'
import json
import re
import sys
from pathlib import Path
import os
unit, vault, script, home = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
# Un même dossier peut apparaître sous son chemin affiché ou son chemin réel
# (lien symbolique, ou /var -> /private/var sur macOS). L'activation de la page
# enregistre le chemin réel ; le réveil, le chemin affiché. Seul ce dossier est
# reconnu : la comparaison se fait sur le chemin réel, rien de plus large.
reel = os.path.realpath(str(vault))

def meme(arg, attendu):
    """Vrai si arg désigne exactement le chemin attendu de CE dossier."""
    return os.path.realpath(arg) == os.path.realpath(str(attendu))

def arguments(text):
    # Sous-ensemble non ambigu : mots nus ou entièrement entre guillemets,
    # \\ et \" émis par activer-page-web.sh. Pas d'expansion shell/variable.
    words, i = [], 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        quote = text[i] if text[i] in "\"'" else None
        if quote:
            i += 1
        word = ""
        closed = not quote
        while i < len(text):
            c = text[i]
            if quote and c == quote:
                i += 1
                closed = True
                if i < len(text) and not text[i].isspace():
                    raise ValueError("guillemets ambigus")
                break
            if not quote and c.isspace():
                break
            if c == "\\":
                i += 1
                if i >= len(text) or text[i] not in ('\\', '"'):
                    raise ValueError("échappement inconnu")
                c = text[i]
            elif c in "\"'" and not quote:
                raise ValueError("guillemets dans un mot")
            word += c
            i += 1
        if not closed:
            raise ValueError("guillemets non fermés")
        # Une seule passe : %%h est un %h littéral, jamais le HOME.
        def expand(match):
            token = match.group()
            if token == "%%":
                return "%"
            if token == "$$":
                return "$"
            if token == "%h":
                return str(home)
            raise ValueError("expansion non reconnue")
        words.append(re.sub(r"%%|\$\$|%h|[%$]", expand, word))
    return words

try:
    if unit.is_symlink() or not unit.is_file() or unit.with_name(unit.name + ".d").exists():
        raise ValueError("unité non ordinaire ou surchargée")
    commands = []
    section = None
    for line in unit.read_text().splitlines():
        line = line.strip()
        if line.startswith(("#", ";")) or not line:
            continue
        if line.startswith("["):
            section = line
        elif line.startswith("ExecStart="):
            if section != "[Service]":
                raise ValueError("commande hors service")
            commands.append(line.split("=", 1)[1].strip())
    if len(commands) != 1:
        raise ValueError("commande ambiguë")
    args = arguments(commands[0])
    if not args or not Path(args[0]).is_absolute():
        raise ValueError("exécutable ambigu")
    if script == "watch-linux.sh":
        valid = len(args) == 2 and args[0] == "/bin/bash" and meme(args[1], vault / script)
    elif script == "tunnel":
        # Ce test n'est appelé que si la page appartient à ce vault. Le tunnel
        # doit aussi utiliser un fichier dédié qui dessert sa PAGE_ORIGIN.
        valid = (Path(args[0]).name == "cloudflared" and len(args) == 6 and
                 args[1:4] == ["--no-autoupdate", "tunnel", "--config"] and args[5] == "run")
        if valid:
            yml, config = Path(args[4]), vault / "config.env"
            if (yml.parent != home / ".cloudflared" or
                    not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}\.yml", yml.name) or
                    yml.is_symlink() or config.is_symlink()):
                raise ValueError("configuration inconnue")
            origins = [line.split("=", 1)[1].strip().strip('"').strip("'")
                       for line in config.read_text().splitlines()
                       if re.match(r"^\s*PAGE_ORIGIN\s*=", line)]
            content = yml.read_text()
            hosts = [line.split("hostname:", 1)[1].strip() for line in content.splitlines()
                     if re.match(r"^\s*-\s*hostname:", line)]
            host = json.loads(hosts[0]) if len(hosts) == 1 and hosts[0].startswith('"') else (hosts[0] if len(hosts) == 1 else "")
            services = [line.split("service:", 1)[1].strip() for line in content.splitlines()
                        if re.match(r"^\s*(?:-\s*)?service:", line)]
            valid = origins == ["https://" + host] and services == ["http://127.0.0.1:8786", "http_status:404"]
    else:
        valid = (re.fullmatch(r"python(?:3(?:\.\d+)*)?", Path(args[0]).name) is not None and
                 len(args) == 4 and meme(args[1], vault / script) and args[2] == "--vault"
                 and meme(args[3], vault) and os.path.realpath(args[3]) == reel)
except (OSError, ValueError, IndexError, TypeError):
    valid = False
sys.exit(0 if valid else 1)
PYTHON
}

# ------------------------------------------------- 1. le réveil automatique
etape "1/3 — Le réveil automatique (systemd)"
UNIT_DIR="$HOME/.config/systemd/user"
SERVICES_CONSERVES="non"
if service_de_ce_dossier "$UNIT_DIR/bobine-watch.service" watch-linux.sh; then
  systemctl --user disable --now bobine-watch.timer 2>/dev/null || true
  systemctl --user disable --now bobine-watch.path 2>/dev/null || true
  systemctl --user stop bobine-watch.service 2>/dev/null || true
  rm -f "$UNIT_DIR/bobine-watch.service" "$UNIT_DIR/bobine-watch.timer" "$UNIT_DIR/bobine-watch.path"
  systemctl --user daemon-reload 2>/dev/null || true
  ok "Réveil retiré (plus de passage automatique ni instantané)."
elif [ -e "$UNIT_DIR/bobine-watch.service" ] || [ -L "$UNIT_DIR/bobine-watch.service" ]; then
  SERVICES_CONSERVES="oui"
  note "Un réveil existe, mais il surveille un autre dossier — je n'y touche pas."
else
  note "Pas de réveil installé — rien à retirer."
fi

# --------------------------------------------------- 2. le serveur de liens
etape "2/3 — Le serveur de liens (facultatif)"
if service_de_ce_dossier "$UNIT_DIR/bobine-inbox.service" inbox_server.py; then
  systemctl --user disable --now bobine-inbox.service 2>/dev/null || true
  rm -f "$UNIT_DIR/bobine-inbox.service"
  systemctl --user daemon-reload 2>/dev/null || true
  ok "Serveur de liens retiré."
else
  if [ -e "$UNIT_DIR/bobine-inbox.service" ] || [ -L "$UNIT_DIR/bobine-inbox.service" ]; then
    SERVICES_CONSERVES="oui"
  fi
  note "Pas de serveur de liens pour ce dossier — rien à retirer."
fi

# ------------------------------------------ 2bis. la page web (page_server)
if service_de_ce_dossier "$UNIT_DIR/bobine-page.service" page_server.py; then
  if service_de_ce_dossier "$UNIT_DIR/bobine-tunnel.service" tunnel; then
    systemctl --user disable --now bobine-page.service bobine-tunnel.service 2>/dev/null || true
    rm -f "$UNIT_DIR/bobine-tunnel.service"
  else
    systemctl --user disable --now bobine-page.service 2>/dev/null || true
    if [ -e "$UNIT_DIR/bobine-tunnel.service" ] || [ -L "$UNIT_DIR/bobine-tunnel.service" ]; then
      SERVICES_CONSERVES="oui"
      note "Tunnel non reconnu pour ce dossier : il est conservé."
    fi
  fi
  rm -f "$UNIT_DIR/bobine-page.service"
  systemctl --user daemon-reload 2>/dev/null || true
  ok "Page web retirée."
  note "Le tunnel « bobine-page » reste côté Cloudflare : pour l'effacer aussi,  cloudflared tunnel delete bobine-page"
else
  for unite in bobine-page.service bobine-tunnel.service; do
    if [ -e "$UNIT_DIR/$unite" ] || [ -L "$UNIT_DIR/$unite" ]; then SERVICES_CONSERVES="oui"; fi
  done
  note "Pas de page web pour ce dossier — rien à retirer."
fi

# --------------------------------------------------- 3. les fichiers conservés
etape "3/3 : Tes fichiers restent en place"
if [ "$SERVICES_CONSERVES" = oui ]; then
  note "Des services non reconnus ont été conservés : leur arrêt n’est pas confirmé."
else
  note "Bobine est arrêté pour ce dossier."
fi
note "Toutes tes vidéos locales et tes autres fichiers sont conservés."
note "Après avoir vérifié son contenu, tu peux supprimer toi-même ce dossier :"
note "$(affiche "$VAULT")"

# ------------------------------------------------------------------- au revoir
echo
if [ -t 1 ]; then
  printf "   ${FONCE}🎞️  Rembobinage…${FIN}"
  for c in ⣾ ⣽ ⣻ ⢿ ⡿ ⣟ ⣯ ⣷; do
    printf "\r   ${FONCE}🎞️  Rembobinage…${FIN} ${VIOLET}${c}${FIN}"
    sleep 0.07
  done
  printf "\r%*s\r" 36 ""
fi
if [ "$SERVICES_CONSERVES" = oui ]; then
  ok "Services reconnus retirés ; services non reconnus et fichiers locaux conservés."
else
  printf "${VERT}${GRAS}  ✓ C'est fait : Bobine est arrêté, tes fichiers locaux sont conservés.${FIN}\n"
fi
printf "   ${FONCE}(si un jour tu veux revenir : https://github.com/wrouhli/bobine)${FIN}\n\n"
