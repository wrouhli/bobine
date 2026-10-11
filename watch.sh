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
lire_config_env "$CONFIG" VAULT INBOX FFMPEG_DIR COOKIES NOM
VAULT="${VAULT/#\~/$HOME}"
INBOX="${INBOX/#\~/$HOME}"
FFMPEG_DIR="${FFMPEG_DIR/#\~/$HOME}"
NOM="${NOM:-Bobine}"

LOG_DIR="$VAULT/logs"
LOG="$LOG_DIR/watch.log"
LOCK="$VAULT/.watch.lock"
COMPTEUR="$VAULT/.watch-echecs-lecture"   # échecs consécutifs de lecture de la boîte (alerte)
COMPTEUR_IA="$VAULT/.watch-echecs-resume"   # passages consécutifs sans aucun résumé obtenu (alerte)

MAX_PAR_PASSAGE=15    # ≈ 8 minutes de traitement à ~30 s/vidéo
MAX_PAR_JOUR=50       # profil « occasionnel », même pendant les gros rattrapages

mkdir -p "$LOG_DIR"
CHEMIN="$SCRIPT_DIR/.venv/bin:/usr/local/bin:/opt/homebrew/bin"
[ -n "$FFMPEG_DIR" ] && CHEMIN="$CHEMIN:$FFMPEG_DIR"
export PATH="$CHEMIN:/usr/bin:/bin:/usr/sbin:/sbin"

PYTHON="$SCRIPT_DIR/.venv/bin/python"

# Notification macOS. Les textes passent en ARGUMENTS d'AppleScript (jamais
# collés dans le script) : un guillemet dans un nom ne peut rien casser.
notifier() {  # $1 = message, $2 = titre, $3 = son (facultatif)
  osascript - "$1" "$2" "${3:-}" >/dev/null 2>&1 <<'APPLESCRIPT' || true
on run argv
  if (item 3 of argv) is "" then
    display notification (item 1 of argv) with title (item 2 of argv)
  else
    display notification (item 1 of argv) with title (item 2 of argv) sound name (item 3 of argv)
  end if
end run
APPLESCRIPT
}

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

  # iCloud : quand le Mac se réveille, le fichier peut être encore en cours de
  # téléchargement — une lecture directe peut échouer. On demande le
  # téléchargement, puis on travaille sur une copie locale (relue à chaque
  # passage, donc rien n'est perdu si l'iCloud traîne).
  brctl download "$INBOX" 2>/dev/null || true
  copie="$VAULT/.inbox-local.txt"
  ok_copie=""
  derniere_erreur_cp=""
  for _ in 1 2 3 4 5; do
    derniere_erreur_cp=$(cp "$INBOX" "$copie" 2>&1) && { ok_copie=1; derniere_erreur_cp=""; break; }
    # macOS refuse la lecture d'iCloud aux processus d'arrière-plan
    # (« Operation not permitted ») : on demande au Finder, qui vit dans la
    # session utilisateur et a le droit, de faire la copie à notre place.
    # Les chemins passent en arguments (un guillemet dans un chemin ne casse rien).
    osascript - "$INBOX" "$VAULT" >/dev/null 2>&1 <<'APPLESCRIPT'
on run argv
  tell application "Finder"
    set src to (POSIX file (item 1 of argv)) as alias
    set dst to (POSIX file (item 2 of argv)) as alias
    duplicate src to dst with replacing
  end tell
end run
APPLESCRIPT
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
      notifier "Impossible de lire la boîte iCloud depuis ~1 h (passage $echecs_lecture). Un diagnostic est conseillé." "⚠️ $NOM — tube bouché" "Basso"
    fi
  else
  rm -f "$COMPTEUR"   # lecture de la boîte OK : compteur d'alerte remis à zéro

  "$PYTHON" "$SCRIPT_DIR/ingest.py" "$copie" --vault "$VAULT" --cookies "$COOKIES" --limite "$limite" --plafond-journalier "$MAX_PAR_JOUR"

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
      notifier "Tes vidéos sont enregistrées. Les résumés prennent plus de temps que prévu. Bobine réessaie automatiquement." "$NOM : résumés retardés" "Basso"
    fi
  elif [ "$code_resume" -eq 0 ]; then
    rm -f "$COMPTEUR_IA"
  fi

  if [ "$nouvelles" -gt 0 ]; then
    notifier "$fiches dans $NOM" "$NOM"
  fi
} >> "$LOG" 2>&1
