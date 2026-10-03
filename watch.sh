#!/bin/bash
# Bobine — relève automatique de la boîte aux lettres iCloud.
# Lancé par launchd (com.bobine.watch) toutes les 15 minutes — install.sh s'en charge.
# Si le Mac dormait, macOS rattrape au réveil.
#
# Configuration (facultatif) : fichier config.env à côté de ce script :
#   VAULT       dossier des données (défaut : le dossier de ce projet)
#   INBOX       fichier de liens (défaut : la boîte du raccourci iPhone)
#   FFMPEG_DIR  dossier contenant ffmpeg, s'il n'est pas dans le PATH
#   COOKIES     navigateur pour les cookies Instagram/TikTok (défaut : chrome)
#
# Garde-fous (pour rester doux avec Instagram/YouTube) :
#   - MAX_PAR_PASSAGE : vidéos traitées au maximum par passage
#   - MAX_PAR_JOUR    : plafond quotidien, tous passages confondus
#   - verrou          : jamais deux passages en même temps

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT="$SCRIPT_DIR"
INBOX="$HOME/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/inbox.txt"
FFMPEG_DIR=""
COOKIES="chrome"
CONFIG="$SCRIPT_DIR/config.env"
if [ -f "$CONFIG" ]; then
  # shellcheck source=/dev/null
  . "$CONFIG"
fi
VAULT="${VAULT/#\~/$HOME}"
INBOX="${INBOX/#\~/$HOME}"
FFMPEG_DIR="${FFMPEG_DIR/#\~/$HOME}"
NOM="${NOM:-Bobine}"

LOG_DIR="$VAULT/logs"
LOG="$LOG_DIR/watch.log"
LOCK="$VAULT/.watch.lock"
COMPTEUR="$VAULT/.watch-echecs-lecture"   # échecs consécutifs de lecture de la boîte (alerte)

MAX_PAR_PASSAGE=15    # ≈ 8 minutes de traitement à ~30 s/vidéo
MAX_PAR_JOUR=50       # profil « occasionnel », même pendant les gros rattrapages

mkdir -p "$LOG_DIR"
CHEMIN="$SCRIPT_DIR/.venv/bin:/usr/local/bin:/opt/homebrew/bin"
[ -n "$FFMPEG_DIR" ] && CHEMIN="$CHEMIN:$FFMPEG_DIR"
export PATH="$CHEMIN:/usr/bin:/bin:/usr/sbin:/sbin"

PYTHON="$SCRIPT_DIR/.venv/bin/python"

jour=$(date '+%Y-%m-%d')
horodate=$(date '+%Y-%m-%d %H:%M:%S')

# ---------------------------------------------------------------- verrou
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -f "$LOCK/pid" ] && kill -0 "$(cat "$LOCK/pid")" 2>/dev/null; then
    echo "---- $horodate — passage déjà en cours (pid $(cat "$LOCK/pid")), celui-ci est ignoré." >> "$LOG"
    exit 0
  fi
  rm -rf "$LOCK"
  mkdir "$LOCK" || exit 0
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

# ------------------------------------------------- installation complète ?
if [ ! -x "$PYTHON" ]; then
  echo "---- $horodate — installation incomplète ($PYTHON introuvable). Lance ./install.sh" >> "$LOG"
  exit 0
fi

# ------------------------------------------------- plafond quotidien
fait_aujourdhui=$(grep -l "traite_le: $jour" "$VAULT"/raw/*.md 2>/dev/null | wc -l | tr -d ' ')
if [ "$fait_aujourdhui" -ge "$MAX_PAR_JOUR" ]; then
  echo "---- $horodate — plafond quotidien atteint ($fait_aujourdhui/$MAX_PAR_JOUR), pause jusqu'à demain." >> "$LOG"
  exit 0
fi
reste=$((MAX_PAR_JOUR - fait_aujourdhui))
limite=$MAX_PAR_PASSAGE
[ "$reste" -lt "$limite" ] && limite=$reste

# ---------------------------------------------------------------- travail
ok_before=$(grep -c '"statut": "ok"' "$VAULT/journal.json" 2>/dev/null || true)
[ -z "$ok_before" ] && ok_before=0

{
  echo "---- $horodate — réveil (fait aujourd'hui : $fait_aujourdhui/$MAX_PAR_JOUR, limite du passage : $limite)"

  if [ ! -f "$INBOX" ]; then
    echo "boîte de réception absente ($INBOX) — rien à faire. (Le raccourci iPhone est-il créé ?)"
    exit 0
  fi

  cd "$VAULT" || exit 1

  # iCloud : quand le Mac se réveille, le fichier peut être encore en cours de
  # téléchargement — une lecture directe peut échouer. On demande le
  # téléchargement, puis on travaille sur une copie locale (relue à chaque
  # passage, donc rien n'est perdu si l'iCloud traîne).
  brctl download "$INBOX" 2>/dev/null || true
  copie="$VAULT/.inbox-local.txt"
  ok_copie=""
  derniere_erreur_cp=""
  for tentative in 1 2 3 4 5; do
    derniere_erreur_cp=$(cp "$INBOX" "$copie" 2>&1) && { ok_copie=1; derniere_erreur_cp=""; break; }
    # macOS refuse la lecture d'iCloud aux processus d'arrière-plan
    # (« Operation not permitted ») : on demande au Finder, qui vit dans la
    # session utilisateur et a le droit, de faire la copie à notre place.
    osascript -e 'tell application "Finder"' \
      -e 'set src to (POSIX file "'"$INBOX"'") as alias' \
      -e 'set dst to (POSIX file "'"$VAULT"'") as alias' \
      -e 'duplicate src to dst with replacing' -e 'end tell' >/dev/null 2>&1
    if [ -f "$VAULT/inbox.txt" ]; then
      mv -f "$VAULT/inbox.txt" "$copie" && { ok_copie=1; derniere_erreur_cp=""; break; }
    fi
    sleep 12
  done
  if [ -z "$ok_copie" ]; then
    echo "boîte iCloud pas encore lisible — nouvel essai au prochain passage. (cp: ${derniere_erreur_cp:-échec sans message})"
    # Alerte si ça dure : ~1 h (4 passages en échec), puis rappel ~toutes les 6 h.
    echecs_lecture=$(( $(cat "$COMPTEUR" 2>/dev/null || echo 0) + 1 ))
    echo "$echecs_lecture" > "$COMPTEUR"
    if [ "$echecs_lecture" -ge 4 ] && [ $(( (echecs_lecture - 4) % 24 )) -eq 0 ]; then
      osascript -e "display notification \"Impossible de lire la boîte iCloud depuis ~1 h (passage $echecs_lecture). Un diagnostic est conseillé.\" with title \"⚠️ $NOM — tube bouché\" sound name \"Basso\"" 2>/dev/null || true
    fi
    exit 0
  fi
  rm -f "$COMPTEUR"   # lecture de la boîte OK : compteur d'alerte remis à zéro

  "$PYTHON" "$SCRIPT_DIR/ingest.py" "$copie" --vault "$VAULT" --cookies "$COOKIES" --limite "$limite"

  ok_after=$(grep -c '"statut": "ok"' "$VAULT/journal.json" 2>/dev/null || true)
  [ -z "$ok_after" ] && ok_after=0
  nouvelles=$((ok_after - ok_before))

  if [ "$nouvelles" -gt 0 ]; then
    echo "$nouvelles nouvelle(s) fiche(s) traitée(s)."
    # Résumés + pages (nécessite une clé API dans config.env ; sinon saute).
    "$PYTHON" "$SCRIPT_DIR/enrichir.py" --vault "$VAULT" 2>&1 || true
    osascript -e "display notification \"$nouvelles nouvelle(s) fiche(s) dans $NOM\" with title \"$NOM\"" 2>/dev/null || true
  fi
} >> "$LOG" 2>&1
