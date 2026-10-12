#!/bin/bash
# Bobine (Linux) : désactive « Demander ». Ta page reste lisible, sans chat ni profil modifiable.
# Usage : dans ton dossier Bobine,  ./desactiver-demander.sh
# Relançable à tout moment.
#
# Ce que fait le script : DEMANDER=non dans config.env, puis :
#   - page locale créée par activer-demander.sh, sans accès web : arrêtée et retirée ;
#   - page web publique (activer-page-web.sh) : redémarrée, elle reste lisible.
# Une page d'un autre dossier n'est jamais touchée. Aucune donnée n'est supprimée.
# Logique partagée : page-locale.sh.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)" || exit 1
if [ ! -f "$SCRIPT_DIR/page-locale.sh" ]; then
  printf "  ⚠  Il manque le fichier page-locale.sh dans ce dossier : relance l'installation de Bobine.\n"
  exit 1
fi
# shellcheck source=page-locale.sh
. "$SCRIPT_DIR/page-locale.sh"
cd "$SCRIPT_DIR" || exit 1

printf '\n  Bobine : désactivation de Demander\n'
if ! choisir_python; then
  avis "Python est introuvable : relance l'installation de Bobine."
  exit 1
fi
desactiver_demander
rc=$?
annoncer_desactivation "$rc"
[ "$rc" -ne 2 ]
