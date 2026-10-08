#!/bin/bash
# Bobine — désinstallation guidée (Linux).
# Usage : place-toi dans le dossier de ton vault, puis :  ./desinstaller-linux.sh
#
# Retire, proprement : le réveil systemd, le serveur de liens (s'il tourne),
# et — si tu le souhaites — le dossier du vault lui-même.

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

NOM="Bobine"
if [ -f "$VAULT/config.env" ]; then
  ANCIEN_NOM="$(grep -m1 '^NOM=' "$VAULT/config.env" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)"
  if [ -n "${ANCIEN_NOM:-}" ]; then NOM="$ANCIEN_NOM"; fi
fi

note "Au programme : le réveil automatique, le serveur de liens, et le dossier"
note "(pour le dossier, c'est toi qui choisis à la fin)."

# ------------------------------------------------- 1. le réveil automatique
etape "1/3 — Le réveil automatique (systemd)"
UNIT_DIR="$HOME/.config/systemd/user"
if [ -f "$UNIT_DIR/bobine-watch.service" ] && grep -qF "$VAULT" "$UNIT_DIR/bobine-watch.service" 2>/dev/null; then
  systemctl --user disable --now bobine-watch.timer 2>/dev/null || true
  systemctl --user disable --now bobine-watch.path 2>/dev/null || true
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
if [ -f "$UNIT_DIR/bobine-inbox.service" ] && grep -qF "$VAULT" "$UNIT_DIR/bobine-inbox.service" 2>/dev/null; then
  systemctl --user disable --now bobine-inbox.service 2>/dev/null || true
  rm -f "$UNIT_DIR/bobine-inbox.service"
  systemctl --user daemon-reload 2>/dev/null || true
  ok "Serveur de liens retiré."
else
  note "Pas de serveur de liens pour ce dossier — rien à retirer."
fi

# ------------------------------------------ 2bis. la page web (page_server)
if [ -f "$UNIT_DIR/bobine-page.service" ] && grep -qF "$VAULT" "$UNIT_DIR/bobine-page.service" 2>/dev/null; then
  systemctl --user disable --now bobine-page.service bobine-tunnel.service 2>/dev/null || true
  rm -f "$UNIT_DIR/bobine-page.service" "$UNIT_DIR/bobine-tunnel.service"
  systemctl --user daemon-reload 2>/dev/null || true
  ok "Page web retirée."
  note "Le tunnel « bobine-page » reste côté Cloudflare : pour l'effacer aussi,  cloudflared tunnel delete bobine-page"
else
  note "Pas de page web pour ce dossier — rien à retirer."
fi

# --------------------------------------------------- 3. le dossier du vault
etape "3/3 — Le dossier de Bobine (fiches comprises)"
note "Dedans : tes fiches (raw/), ta configuration, l'environnement… tout Bobine."
SUPPRIME="non"
if confirmer "Le supprimer ? (définitif — pas de corbeille sur un serveur)" "n"; then
  printf "  ${CYAN}➜${FIN} Pour confirmer, écris « supprimer » : " >&2
  read -r reponse || true
  case "$reponse" in
    supprimer|SUPPRIMER|Supprimer)
      cd "$HOME" || true
      rm -rf "$VAULT"
      SUPPRIME="oui"
      ok "Supprimé : $(affiche "$VAULT")"
      note "Ton shell est peut-être dans un dossier qui n'existe plus : tape  cd ~  si besoin."
      ;;
    *)
      note "D'accord — je le laisse tel quel, en place."
      ;;
  esac
else
  note "D'accord — je le laisse tel quel, en place."
  note "Tu pourras le supprimer toi-même quand tu veux."
fi

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
if [ "$SUPPRIME" = "oui" ]; then
  printf "${VERT}${GRAS}  ✨ Bobine est désinstallé — merci d'avoir essayé !${FIN}\n"
  printf "   ${FONCE}(si un jour tu veux revenir : https://github.com/wrouhli/bobine)${FIN}\n\n"
else
  printf "${VERT}${GRAS}  ✓ C'est fait : réveil et serveur de liens retirés.${FIN}\n"
  printf "   ${FONCE}(le dossier est resté en place, sans effet — supprime-le quand tu veux.)${FIN}\n\n"
fi
