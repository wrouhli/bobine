#!/bin/bash
# Bobine (Linux) : indique comment ouvrir ta page (et l'ouvre s'il y a un écran).
# Usage : dans ton dossier Bobine,  ./ouvrir-ma-page.sh
#
# Demander activé et page de CE dossier installée : la démarre si besoin, puis
# affiche son adresse (publique si PAGE_ORIGIN est renseigné, sinon via ssh -L).
# Sinon : affiche le chemin de vault.html (lisible sans serveur). Le navigateur
# n'est lancé que si un écran est disponible (DISPLAY ou WAYLAND_DISPLAY).
# Le script se termine toujours normalement.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)" || exit 0
ouvrir_si_ecran() {
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1" >/dev/null 2>&1 || true
  fi
}
if [ ! -f "$SCRIPT_DIR/page-locale.sh" ]; then
  printf '  Ta page : %s\n' "$SCRIPT_DIR/vault.html"
  ouvrir_si_ecran "$SCRIPT_DIR/vault.html"
  exit 0
fi
# shellcheck source=page-locale.sh
. "$SCRIPT_DIR/page-locale.sh"
cd "$SCRIPT_DIR" 2>/dev/null || true

VAULT_EFFECTIF=""
if choisir_python; then
  VAULT_EFFECTIF="$(resoudre_vault_effectif 2>/dev/null)" || VAULT_EFFECTIF=""
  if [ "$(lire_demander)" = oui ] && [ -f "$UNITE_PAGE" ] && unite_page_appartient "$UNITE_PAGE"; then
    if ! page_active; then
      systemctl --user start bobine-page.service 2>/dev/null || true
      attendre_page || avis "Ta page met du temps à démarrer : réessaie dans un instant."
    fi
    printf '\n  Ta page Bobine (avec Demander)\n'
    annoncer_adresse
    ouvrir_si_ecran "$ADRESSE_PAGE_LOCALE"
    exit 0
  fi
fi
PAGE="$(page_fichier)"
printf '\n  Ta page Bobine : %s\n' "$PAGE"
note "Pour la lire sur ton ordinateur :  scp $(id -un 2>/dev/null || echo toi)@ton-serveur:$(printf '%q' "$PAGE") ."
ouvrir_si_ecran "$PAGE"
exit 0
