#!/bin/bash
# Bobine — double-clique sur ce fichier pour installer (macOS).
#
# 👉 Tout est expliqué, clic par clic, dans « 👉 1. LIS-MOI D'ABORD (installation) »
#    (le fichier juste à côté, dans ce dossier).
#
# Si macOS refuse de l'ouvrir (fichier téléchargé — c'est normal) :
#   1. clique « Terminé » (surtout pas « Placer dans la corbeille ») ;
#   2. Réglages Système → Confidentialité et sécurité → « Ouvrir quand même » ;
#   3. re-double-clique ce fichier.
#
# Équivalent en Terminal :  ./install.sh

cd "$(dirname "$0")" || exit 1
exec bash ./install.sh
