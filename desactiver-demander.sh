#!/bin/bash
# Bobine : désactive « Demander ». Ta page reste lisible, sans chat ni profil modifiable.
# Usage : dans ton dossier Bobine,  ./desactiver-demander.sh  (ou double-clic sur
# « Désactiver Demander.command »). Relançable à tout moment.
#
# Ce que fait le script : DEMANDER=non dans config.env, arrêt du service de page
# seulement s'il appartient exactement à ce dossier, raccourci « Ma page » vers la
# page fichier. Aucune donnée n'est supprimée. Logique partagée : page-locale.sh.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)" || exit 1
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
