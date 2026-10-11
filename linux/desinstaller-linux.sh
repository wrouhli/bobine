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

# Reconnaître le chemin COMPLET du script lancé, pas un simple préfixe de
# dossier (Bobine et Bobine-autre peuvent coexister). On ne lit que ExecStart.
service_de_ce_dossier() {  # $1 = fichier unité, $2 = script attendu
  local ligne candidat
  [ -f "$1" ] || return 1
  candidat="$VAULT/$2"
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    case "$ligne" in ExecStart=*) ;; *) continue ;; esac
    ligne="${ligne//%h/$HOME}"
    case "$ligne" in
      *"$candidat"|*"$candidat "*|*"$candidat\""*|*"$candidat'"*) return 0 ;;
    esac
  done < "$1"
  return 1
}

# ------------------------------------------------- 1. le réveil automatique
etape "1/3 — Le réveil automatique (systemd)"
UNIT_DIR="$HOME/.config/systemd/user"
if service_de_ce_dossier "$UNIT_DIR/bobine-watch.service" watch-linux.sh; then
  systemctl --user disable --now bobine-watch.timer 2>/dev/null || true
  systemctl --user disable --now bobine-watch.path 2>/dev/null || true
  systemctl --user stop bobine-watch.service 2>/dev/null || true
  rm -f "$UNIT_DIR/bobine-watch.service" "$UNIT_DIR/bobine-watch.timer" "$UNIT_DIR/bobine-watch.path"
  systemctl --user daemon-reload 2>/dev/null || true
  ok "Réveil retiré (plus de passage automatique ni instantané)."
elif [ -f "$UNIT_DIR/bobine-watch.service" ]; then
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
  note "Pas de serveur de liens pour ce dossier — rien à retirer."
fi

# ------------------------------------------ 2bis. la page web (page_server)
if service_de_ce_dossier "$UNIT_DIR/bobine-page.service" page_server.py; then
  systemctl --user disable --now bobine-page.service bobine-tunnel.service 2>/dev/null || true
  rm -f "$UNIT_DIR/bobine-page.service" "$UNIT_DIR/bobine-tunnel.service"
  systemctl --user daemon-reload 2>/dev/null || true
  ok "Page web retirée."
  note "Le tunnel « bobine-page » reste côté Cloudflare : pour l'effacer aussi,  cloudflared tunnel delete bobine-page"
else
  note "Pas de page web pour ce dossier — rien à retirer."
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
