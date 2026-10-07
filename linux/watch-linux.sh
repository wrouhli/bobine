#!/bin/bash
# Bobine — relève automatique de la boîte de réception (Linux / serveur).
# Lancé par systemd (minuteur bobine-watch.timer) toutes les 15 minutes —
# install-linux.sh s'en charge. Si la machine était éteinte, systemd rattrape
# au redémarrage (Persistent=true).
#
# Configuration (facultatif) : fichier config.env à côté de ce script :
#   VAULT       dossier des données (défaut : le dossier de ce projet)
#   INBOX       fichier où déposer les liens (défaut : inbox.txt du vault)
#   FFMPEG_DIR  dossier contenant ffmpeg, s'il n'est pas dans le PATH
#   COOKIES     chemin d'un cookies.txt pour Instagram/TikTok (recommandé sur serveur)
#   NOTIF_CMD   commande appelée après chaque nouveau lot ; reçoit le message
#               dans la variable $NOTIF_MESSAGE
#
# Garde-fous (pour rester doux avec Instagram/YouTube) :
#   - MAX_PAR_PASSAGE : vidéos traitées au maximum par passage
#   - MAX_PAR_JOUR    : plafond quotidien, tous passages confondus
#   - verrou          : jamais deux passages en même temps

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT="$SCRIPT_DIR"
INBOX="$SCRIPT_DIR/inbox.txt"
FFMPEG_DIR=""
COOKIES=""
NOTIF_CMD=""
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

MAX_PAR_PASSAGE=15    # ≈ 8 minutes de traitement à ~30 s/vidéo
MAX_PAR_JOUR=50       # profil « occasionnel », même pendant les gros rattrapages

mkdir -p "$LOG_DIR"
CHEMIN="$SCRIPT_DIR/.venv/bin:$HOME/.local/bin:/usr/local/bin"
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
  echo "---- $horodate — installation incomplète ($PYTHON introuvable). Lance ./install-linux.sh" >> "$LOG"
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

# ---------------------------------------------------------------- notification
notifier() {  # $1 = message ; la commande NOTIF_CMD (facultative) le reçoit dans $NOTIF_MESSAGE
  [ -n "$NOTIF_CMD" ] || return 0
  NOTIF_MESSAGE="$1" sh -c "$NOTIF_CMD" || true
}

# ---------------------------------------------------------------- travail
ok_before=$(grep -c '"statut": "ok"' "$VAULT/journal.json" 2>/dev/null || true)
[ -z "$ok_before" ] && ok_before=0

{
  echo "---- $horodate — réveil (fait aujourd'hui : $fait_aujourdhui/$MAX_PAR_JOUR, limite du passage : $limite)"

  if [ ! -f "$INBOX" ]; then
    echo "boîte de réception absente ($INBOX) — rien à faire."
    echo "Pour y déposer un lien :  echo 'https://youtu.be/jNQXAC9IVRw' >> $INBOX"
    exit 0
  fi

  cd "$VAULT" || exit 1

  # Copie locale de la boîte : si un lien arrive pendant le passage, il sera
  # pris au suivant — la boîte source n'est jamais modifiée ici.
  copie="$VAULT/.inbox-local.txt"
  if ! cp "$INBOX" "$copie"; then
    echo "boîte illisible — nouvel essai au prochain passage."
    exit 0
  fi

  if [ -n "$COOKIES" ]; then
    "$PYTHON" "$SCRIPT_DIR/ingest.py" "$copie" --vault "$VAULT" --cookies "$COOKIES" --limite "$limite"
  else
    "$PYTHON" "$SCRIPT_DIR/ingest.py" "$copie" --vault "$VAULT" --limite "$limite"
  fi

  ok_after=$(grep -c '"statut": "ok"' "$VAULT/journal.json" 2>/dev/null || true)
  [ -z "$ok_after" ] && ok_after=0
  nouvelles=$((ok_after - ok_before))

  if [ "$nouvelles" -gt 0 ]; then
    echo "$nouvelles nouvelle(s) fiche(s) traitée(s)."
    # Résumés + pages (nécessite une clé API dans config.env ; sinon saute).
    "$PYTHON" "$SCRIPT_DIR/enrichir.py" --vault "$VAULT" 2>&1 || true
    notifier "$nouvelles nouvelle(s) fiche(s) dans $NOM"
  fi
} >> "$LOG" 2>&1
