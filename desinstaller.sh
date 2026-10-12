#!/bin/bash
# Bobine — désinstallation guidée.
# Usage : place-toi dans le dossier de ton vault, puis :  ./desinstaller.sh
#
# Arrête le réveil automatique et propose de retirer la copie iCloud.
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

# ------------------------------------------------------------------ accueil
printf "\n${VIOLET}${GRAS}  Bobine — désinstallation${FIN}\n"
printf "  ${FONCE}Ce dossier : %s${FIN}\n" "$(affiche "$VAULT")"

if [ ! -f "$VAULT/watch.sh" ] || [ ! -f "$VAULT/ingest.py" ]; then
  avis "Ce dossier n'a pas l'air d'être un dossier Bobine (watch.sh / ingest.py introuvables)."
  if ! confirmer "Continuer quand même ?" "n"; then
    echo "  Rien n'a été touché."
    exit 1
  fi
fi

NOM="Bobine"
if [ -f "$VAULT/config.env" ]; then
  ANCIEN_NOM="$(grep -m1 '^NOM=' "$VAULT/config.env" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)"
  if [ -n "${ANCIEN_NOM:-}" ]; then NOM="$ANCIEN_NOM"; fi
fi

note "Au programme : arrêter le réveil automatique, puis choisir si la copie iCloud reste."
note "Tes vidéos locales et tous tes autres fichiers restent en place."

# ------------------------------------------------- 1. le réveil automatique
etape "1/3 — Le réveil automatique"
PLIST="$HOME/Library/LaunchAgents/com.bobine.watch.plist"
if [ -f "$PLIST" ] && { grep -qF "<string>$VAULT/watch.sh</string>" "$PLIST" || grep -qxF "$VAULT/watch.sh" "$PLIST"; }; then
  launchctl bootout "gui/$(id -u)/com.bobine.watch" 2>/dev/null || launchctl remove com.bobine.watch 2>/dev/null || true
  rm -f "$PLIST"
  ok "Réveil retiré (il ne tournera plus toutes les 15 minutes)."
elif [ -f "$PLIST" ]; then
  note "Un réveil existe, mais il surveille un autre dossier (le dernier Bobine installé) — je n'y touche pas."
else
  note "Pas de réveil installé — rien à retirer."
fi

# La page locale est indépendante du réveil. Ne jamais arrêter celle d'un autre vault.
PAGE_PLIST="$HOME/Library/LaunchAgents/com.bobine.page.plist"
PY_PAGE=""
for candidat in "$VAULT/.venv/bin/python" python3 python3.13 python3.12 python3.11 python3.10; do
  if command -v "$candidat" >/dev/null 2>&1; then PY_PAGE="$candidat"; break; fi
done
if [ -e "$PAGE_PLIST" ] || [ -L "$PAGE_PLIST" ]; then
  if [ -n "$PY_PAGE" ] && [ ! -L "$PAGE_PLIST" ] && "$PY_PAGE" -B - "$PAGE_PLIST" "$VAULT" <<'PYTHON'
import os
import plistlib
from xml.parsers.expat import ExpatError
import sys
from pathlib import Path
try:
    with open(sys.argv[1], "rb") as stream:
        data = plistlib.load(stream)
    vault = Path(sys.argv[2])
    config = vault / "config.env"
    if config.is_symlink() or (config.exists() and not config.is_file()):
        raise ValueError("configuration non ordinaire")
    sys.path.insert(0, str(vault))
    from enrichir import charger_config
    configured = charger_config(vault).get("VAULT")
    effective = Path(os.path.expandvars(configured)).expanduser() if configured else vault
    if not effective.is_absolute() or any(ord(c) < 32 or ord(c) == 127 for c in str(effective)):
        raise ValueError("chemin ambigu")
    expected = [str(vault / ".venv/bin/python"), str(vault / "page_server.py"),
                "--vault", str(effective), "--local"]
    valid = data.get("Label") == "com.bobine.page" and data.get("ProgramArguments") == expected
except (OSError, ValueError, TypeError, AttributeError, ExpatError, RuntimeError, ImportError):
    valid = False
sys.exit(0 if valid else 1)
PYTHON
  then
    launchctl bootout "gui/$(id -u)/com.bobine.page" 2>/dev/null || launchctl remove com.bobine.page 2>/dev/null || true
    rm -f "$PAGE_PLIST"
    ok "Service de page locale retiré ; les fichiers du vault sont conservés."
  else
    note "Un service de page existe, mais il n'appartient pas exactement à ce dossier : il est conservé."
  fi
fi

# ------------------------------------------ 2. la copie iCloud (iPhone)
etape "2/3 — La copie iCloud (ta page sur l'iPhone)"
ICOPIE="$HOME/Library/Mobile Documents/com~apple~CloudDocs/$NOM"
if [ -f "$ICOPIE/vault.html" ]; then
  note "(si tu as un autre vault du même nom, il partage cette page.)"
  if confirmer "Page trouvée : iCloud Drive → « $NOM » → vault.html. La retirer aussi ?" "o"; then
    rm -f "$ICOPIE/vault.html"
    if rmdir "$ICOPIE" 2>/dev/null; then
      ok "Copie iCloud retirée."
    else
      note "La page est retirée ; le dossier iCloud contenait d'autres fichiers — je l'ai laissé."
    fi
  else
    note "D'accord — la copie iCloud reste en place."
  fi
else
  note "Pas de copie iCloud trouvée — rien à retirer."
fi

# --------------------------------------------------- 3. les fichiers conservés
etape "3/3 : Tes fichiers restent en place"
note "Bobine est arrêté pour ce dossier."
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
printf "${VERT}${GRAS}  ✓ C'est fait : Bobine est arrêté, tes fichiers locaux sont conservés.${FIN}\n"
printf "   ${FONCE}(si un jour tu veux revenir : https://github.com/wrouhli/bobine)${FIN}\n\n"
