#!/bin/bash
# Bobine : ouvre ta page. Lancé par « Ma page » (double-clic), sans Terminal.
#
# Demander activé et service de CE dossier présent : ouvre http://127.0.0.1:8786/
# (le service est relancé au besoin, attente de quelques secondes au plus).
# Sinon, ou en cas d'échec : ouvre la page fichier (vault.html). Jamais d'erreur
# bloquante : le script se termine toujours normalement. Journal technique :
# logs/ouvrir-ma-page.log.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)" || exit 0
ouvrir() {
  if command -v open >/dev/null 2>&1; then open "$1" >/dev/null 2>&1 || true; fi
  exit 0
}
if [ ! -f "$SCRIPT_DIR/page-locale.sh" ]; then ouvrir "$SCRIPT_DIR/vault.html"; fi
# shellcheck source=page-locale.sh
. "$SCRIPT_DIR/page-locale.sh"
cd "$SCRIPT_DIR" 2>/dev/null || ouvrir "$SCRIPT_DIR/vault.html"
mkdir -p "$SCRIPT_DIR/logs" 2>/dev/null
exec 2>>"$SCRIPT_DIR/logs/ouvrir-ma-page.log"

VAULT_EFFECTIF=""
if choisir_python && VAULT_EFFECTIF="$(resoudre_vault_effectif)"; then
  if [ "$(lire_demander)" = oui ] && demarrer_page_locale; then
    ouvrir "$ADRESSE_PAGE_LOCALE"
  fi
else
  VAULT_EFFECTIF=""
fi
ouvrir "$(page_fichier)"
