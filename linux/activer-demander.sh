#!/bin/bash
# Bobine (Linux) : active « Demander » (questions à l'IA et profil modifiable depuis ta page).
# Usage : dans ton dossier Bobine,  ./activer-demander.sh
# Relançable à tout moment, sans réinstaller.
#
# Ce que fait le script : DEMANDER=oui dans config.env, page régénérée localement
# (sans appel d'IA), puis :
#   - page déjà installée pour CE dossier (activer-page-web.sh ou ce script) :
#     elle est redémarrée ;
#   - sinon : une page locale (127.0.0.1:8786, avec mot de passe) est installée.
# Une page d'un autre dossier ou personnalisée n'est jamais remplacée.
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

printf '\n  Bobine : activation de Demander\n'
if ! choisir_python; then
  avis "Python est introuvable : relance l'installation de Bobine."
  exit 1
fi
activer_demander
rc=$?
annoncer_activation "$rc"
[ "$rc" -eq 0 ]
