#!/bin/bash
# Bobine — relève automatique de la boîte de réception (Linux / serveur).
# Lancé par systemd : tout de suite quand un lien arrive (bobine-watch.path),
# et sinon toutes les 15 minutes (bobine-watch.timer) — install-linux.sh s'en
# charge. Si la machine était éteinte, systemd rattrape au redémarrage
# (Persistent=true).
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
# Lecture de config.env SANS l'exécuter. (Avant : « . config.env », qui lançait
# comme une commande toute valeur non entre guillemets contenant un espace,
# par exemple NOM=Ma Bobine.) Seules les clés connues sont lues ; $HOME,
# ${HOME} et un ~ en tête sont développés, comme avant.
lire_config_env() {  # $1 = fichier, puis la liste des clés autorisées
  local fichier="$1" ligne cle valeur autorisees
  shift
  autorisees=" $* "
  [ -f "$fichier" ] || return 0
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    ligne="${ligne#"${ligne%%[![:space:]]*}"}"
    case "$ligne" in ''|'#'*) continue ;; *=*) ;; *) continue ;; esac
    cle="${ligne%%=*}"
    valeur="${ligne#*=}"
    cle="${cle#export }"
    cle="${cle%"${cle##*[![:space:]]}"}"
    case "$autorisees" in *" $cle "*) ;; *) continue ;; esac
    valeur="${valeur#"${valeur%%[![:space:]]*}"}"
    valeur="${valeur%"${valeur##*[![:space:]]}"}"
    case "$valeur" in
      \'*\')   # guillemets simples : texte littéral, rien n'est développé
        valeur="${valeur#\'}"; valeur="${valeur%\'}"
        printf -v "$cle" '%s' "$valeur"
        continue ;;
      \"*\") valeur="${valeur#\"}"; valeur="${valeur%\"}" ;;
      *) valeur="${valeur%%[[:space:]]#*}"
         valeur="${valeur%"${valeur##*[![:space:]]}"}" ;;
    esac
    valeur="${valeur//\$\{HOME\}/$HOME}"
    valeur="${valeur//\$HOME/$HOME}"
    printf -v "$cle" '%s' "$valeur"
  done < "$fichier"
}
lire_config_env "$CONFIG" VAULT INBOX FFMPEG_DIR COOKIES NOM NOTIF_CMD
VAULT="${VAULT/#\~/$HOME}"
INBOX="${INBOX/#\~/$HOME}"
FFMPEG_DIR="${FFMPEG_DIR/#\~/$HOME}"
NOM="${NOM:-Bobine}"

LOG_DIR="$VAULT/logs"
LOG="$LOG_DIR/watch.log"
LOCK="$VAULT/.watch.lock"
COMPTEUR_IA="$VAULT/.watch-echecs-resume"   # passages consécutifs sans aucun résumé obtenu (alerte)

MAX_PAR_PASSAGE=15    # ≈ 8 minutes de traitement à ~30 s/vidéo
MAX_PAR_JOUR=50       # profil « occasionnel », même pendant les gros rattrapages

mkdir -p "$LOG_DIR"
CHEMIN="$SCRIPT_DIR/.venv/bin:$HOME/.local/bin:/usr/local/bin"
[ -n "$FFMPEG_DIR" ] && CHEMIN="$CHEMIN:$FFMPEG_DIR"
export PATH="$CHEMIN:/usr/bin:/bin:/usr/sbin:/sbin"

PYTHON="$SCRIPT_DIR/.venv/bin/python"

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
# Le compteur persiste chaque essai AVANT le travail, pas seulement les liens
# qui restent en échec. S'il est illisible, on suspend les téléchargements
# mais on continue à mettre à jour les résumés et les pages.
fait_aujourdhui=$("$PYTHON" "$SCRIPT_DIR/ingest.py" --vault "$VAULT" --compter-essais)
if [ $? -ne 0 ] || ! [[ "$fait_aujourdhui" =~ ^[0-9]+$ ]]; then
  fait_aujourdhui=$MAX_PAR_JOUR
  echo "Compteur du jour indisponible : relève en pause, vidéos conservées." >> "$LOG"
fi
reste=$((MAX_PAR_JOUR - fait_aujourdhui))
[ "$reste" -lt 0 ] && reste=0
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
  echo "---- $horodate — réveil (essais aujourd'hui : $fait_aujourdhui/$MAX_PAR_JOUR, limite du passage : $limite)"

  if [ "$limite" -gt 0 ]; then
  if [ ! -f "$INBOX" ]; then
    echo "Aucun nouveau lien reçu. Les vidéos enregistrées restent disponibles."
  else

  cd "$VAULT" || exit 1

  # Copie locale de la boîte : si un lien arrive pendant le passage, il sera
  # pris au suivant — la boîte source n'est jamais modifiée ici.
  copie="$VAULT/.inbox-local.txt"
  if ! cp "$INBOX" "$copie"; then
    echo "boîte illisible — nouvel essai au prochain passage."
  else

  if [ -n "$COOKIES" ]; then
    "$PYTHON" "$SCRIPT_DIR/ingest.py" "$copie" --vault "$VAULT" --cookies "$COOKIES" --limite "$limite" --plafond-journalier "$MAX_PAR_JOUR"
  else
    "$PYTHON" "$SCRIPT_DIR/ingest.py" "$copie" --vault "$VAULT" --limite "$limite" --plafond-journalier "$MAX_PAR_JOUR"
  fi

  fi   # copie lisible
  fi   # boîte présente
  else
    echo "La relève reprendra demain. Les résumés en attente continuent."
  fi

  ok_after=$(grep -c '"statut": "ok"' "$VAULT/journal.json" 2>/dev/null || true)
  [ -z "$ok_after" ] && ok_after=0
  nouvelles=$((ok_after - ok_before))

  if [ "$nouvelles" -gt 0 ]; then
    if [ "$nouvelles" -gt 1 ]; then
      fiches="$nouvelles nouvelles fiches"
      accord=" traitées"
    else
      fiches="$nouvelles nouvelle fiche"
      accord=" traitée"
    fi
    echo "$fiches$accord."
  fi

  # Résumés + pages, à CHAQUE passage : les fiches « résumé en attente » (clé
  # ajoutée plus tard, service d'IA indisponible) sont rattrapées sans attendre
  # une nouvelle vidéo. Sans rien de nouveau, c'est immédiat et gratuit.
  code_resume=0
  "$PYTHON" "$SCRIPT_DIR/enrichir.py" --vault "$VAULT" --limite 30 2>&1 || code_resume=$?
  if [ "$code_resume" -eq 3 ]; then
    # Une clé est configurée, mais aucun résumé n'a pu être obtenu. Alerte si
    # ça dure : ~1 h (4 passages), puis rappel ~toutes les 6 h.
    echecs_ia=$(( $(cat "$COMPTEUR_IA" 2>/dev/null || echo 0) + 1 ))
    echo "$echecs_ia" > "$COMPTEUR_IA"
    if [ "$echecs_ia" -ge 4 ] && [ $(( (echecs_ia - 4) % 24 )) -eq 0 ]; then
      notifier "$NOM : tes vidéos sont enregistrées. Les résumés prennent plus de temps que prévu. Bobine réessaie automatiquement."
    fi
  elif [ "$code_resume" -eq 0 ]; then
    rm -f "$COMPTEUR_IA"
  fi

  if [ "$nouvelles" -gt 0 ]; then
    notifier "$fiches dans $NOM"
  fi
} >> "$LOG" 2>&1
