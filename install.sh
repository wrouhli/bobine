#!/bin/bash
# Bobine — installation et configuration (interactive, guidée).
# Usage : place-toi dans le dossier téléchargé, puis :  ./install.sh
#
# Principe : on choisit le nom du vault et son emplacement, l'installation
# copie tout là-bas — le dossier téléchargé pourra ensuite être supprimé.

set -u

DEPOT="$(cd "$(dirname "$0")" && pwd)"   # le dossier téléchargé (d'où on lance l'installation)
SCRIPT_DIR="$DEPOT"

# ----------------------------------------------------------- couleurs & aides
if [ -t 1 ]; then
  FONCE=$'\033[2m'; GRAS=$'\033[1m'; ROUGE=$'\033[1;31m'; VERT=$'\033[1;32m'
  JAUNE=$'\033[1;33m'; VIOLET=$'\033[1;35m'; CYAN=$'\033[1;36m'; FIN=$'\033[0m'
else
  FONCE=""; GRAS=""; ROUGE=""; VERT=""; JAUNE=""; VIOLET=""; CYAN=""; FIN=""
fi

ok()    { printf "  ${VERT}✓${FIN} %s\n" "$1"; }
etape() { printf "\n${VIOLET}${GRAS}  ── %s${FIN}\n" "$1"; }
note()  { printf "  ${FONCE}%s${FIN}\n" "$1"; }
avis()  { printf "  ${JAUNE}⚠${FIN}  %s\n" "$1"; }

affiche() { printf '%s' "${1/#$HOME/~}"; }   # affiche les chemins avec un ~

nettoie() {  # retire les espaces au début et à la fin
  local s="$1" t
  while :; do
    t="$s"
    s="${s# }"; s="${s% }"
    [ "$s" = "$t" ] && break
  done
  printf '%s' "$s"
}

question() {  # $1 = texte, $2 = défaut ; la réponse est renvoyée sur stdout
  local reponse
  {
    printf "  ${CYAN}➜${FIN} %s" "$1"
    if [ -n "${2:-}" ]; then printf " ${FONCE}[%s]${FIN}" "$2"; fi
    printf " : "
  } >&2   # le texte de la question sur stderr : seule la réponse doit être capturée
  read -r reponse || true
  if [ -z "$reponse" ]; then reponse="${2:-}"; fi
  printf '%s' "$reponse"
}

confirmer() {  # $1 = texte, $2 = défaut (o/n) ; renvoie vrai si oui
  local defaut="${2:-o}" invite reponse
  if [ "$defaut" = "o" ]; then invite="O/n"; else invite="o/N"; fi
  printf "  ${CYAN}➜${FIN} %s ${FONCE}[%s]${FIN} : " "$1" "$invite" >&2
  read -r reponse || true
  if [ -z "$reponse" ]; then reponse="$defaut"; fi
  case "$reponse" in
    o|O|oui|Oui|OUI|y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

secret() {  # $1 = texte ; lit sans afficher (pour la clé API)
  local reponse
  {
    printf "  ${CYAN}➜${FIN} %s\n" "$1"
    printf "  ${FONCE}(colle ta clé puis Entrée — elle ne s'affichera pas)${FIN}\n  > "
  } >&2
  read -rs reponse || true
  printf "\n" >&2
  printf '%s' "$reponse"
}

# ------------------------------------------------------------------- bannière
printf "\n${CYAN}${GRAS}"
cat <<'BANDEAU'
   ██████╗  ██████╗ ██████╗ ██╗███╗   ██╗███████╗
   ██╔══██╗██╔═══██╗██╔══██╗██║████╗  ██║██╔════╝
   ██████╔╝██║   ██║██████╔╝██║██╔██╗ ██║█████╗
   ██╔══██╗██║   ██║██╔══██╗██║██║╚██╗██║██╔══╝
   ██████╔╝╚██████╔╝██████╔╝██║██║ ╚████║███████║
   ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝╚═╝  ╚═══╝╚══════╝
BANDEAU
printf "${FIN}${FONCE}                  par Wahid Rouhli${FIN}\n\n"
printf "${FIN}   tes vidéos sauvegardées deviennent une base locale, cherchable,\n"
printf "   à toi. On installe tout ensemble — ça prend quelques minutes.\n"
printf "   ${FONCE}(accepte les propositions par défaut en appuyant sur Entrée)${FIN}\n"

# ---------------------------------------------------------------- 1. Python
etape "1/7 — Vérification de Python"
PY=""
for candidat in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidat" >/dev/null 2>&1; then
    version=$("$candidat" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")
    maj=${version%%.*}; min=${version#*.}
    if [ "${maj:-0}" -ge 3 ] && [ "${min:-0}" -ge 10 ]; then PY="$candidat"; break; fi
  fi
done
if [ -z "$PY" ]; then
  avis "Il faut Python 3.10 ou plus récent."
  note "Installe-le avec :   brew install python@3.12"
  exit 1
fi
ok "Python : $PY ($("$PY" -V 2>&1))"

# ---------------------------------------------------------------- 2. nom du vault
etape "2/7 — Le nom de ton vault"
NOM_DEFAUT="Bobine"
if [ -f "$DEPOT/config.env" ]; then
  ANCIEN_NOM="$(grep -m1 '^NOM=' "$DEPOT/config.env" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)"
  if [ -n "${ANCIEN_NOM:-}" ]; then NOM_DEFAUT="$ANCIEN_NOM"; fi
fi
note "Il apparaîtra sur ta page et dans tes notifications — et donnera son nom au dossier par défaut."
NOM_VAULT="$(question "Comment veux-tu l'appeler ?" "$NOM_DEFAUT")"
NOM_VAULT="$(nettoie "$(printf '%s' "$NOM_VAULT" | tr -d '/"\\')")"
if [ -z "$NOM_VAULT" ]; then NOM_VAULT="Bobine"; fi
ok "Nom choisi : $NOM_VAULT"

# ---------------------------------------------------------------- 3. emplacement
etape "3/7 — Où installer ton vault ?"
note "Ton vault, c'est TON dossier : tes fiches, tes pages, ta configuration."
note "Choisis un endroit que tu gardes — pas le dossier téléchargé (il ne servira plus)."

DEFAUT_CIBLE="$HOME/$NOM_VAULT"
if [ -f "$DEPOT/config.env" ] || [ -d "$DEPOT/.venv" ]; then
  DEFAUT_CIBLE="$DEPOT"   # on relance l'installation depuis un Bobine existant
fi

CIBLE=""; GARDE=""; COLLISION=0; essais=0
REP="$(question "Emplacement de ton vault" "$(affiche "$DEFAUT_CIBLE")")"
while [ -z "$CIBLE" ]; do
  essais=$((essais + 1))
  if [ "$essais" -gt 6 ]; then
    avis "Trop de tentatives — relance l'installation quand tu veux."
    exit 1
  fi
  case "$REP" in
    "~")   CIBLE="$HOME" ;;
    "~/"*) CIBLE="$HOME/${REP#\~/}" ;;
    *)     CIBLE="$REP" ;;
  esac
  CIBLE="${CIBLE%/}"
  CIBLE="$(nettoie "$CIBLE")"
  if [ -z "$CIBLE" ]; then
    if [ "$COLLISION" = "1" ]; then
      CIBLE="$DEPOT"; GARDE="oui"          # l'utilisateur confirme : on garde ce dossier tel quel
      break
    fi
    CIBLE="$DEFAUT_CIBLE"
  fi
  case "$CIBLE" in
    /*) ;;
    *)  avis "Indique un dossier complet — par exemple :  ~/MonBobine"
        COLLISION=0
        REP="$(question "Emplacement de ton vault" "$(affiche "$DEFAUT_CIBLE")")"
        CIBLE=""; continue ;;
  esac
  if [ "$CIBLE" = "$HOME" ]; then
    avis "Ça, c'est tout ton dossier personnel — choisis un dossier dédié (ex. ~/MonBobine)."
    COLLISION=0
    REP="$(question "Emplacement de ton vault" "$(affiche "$DEFAUT_CIBLE")")"
    CIBLE=""; continue
  fi
  if [ "$CIBLE" -ef "$DEPOT" ]; then
    if [ -f "$DEPOT/config.env" ] || [ -d "$DEPOT/.venv" ]; then
      GARDE="reinstall"
      break
    fi
    if [ "$COLLISION" = "0" ]; then
      COLLISION=1
      avis "« $(affiche "$CIBLE") » c'est le dossier que tu viens de télécharger — à la fin, tu pourras le supprimer."
      note "Choisis un autre emplacement (ex. ~/MonBobine), ou appuie sur Entrée pour le garder ici tel quel."
      REP="$(question "Emplacement de ton vault" "")"
      CIBLE=""; continue
    else
      CIBLE="$DEPOT"; GARDE="oui"
      break
    fi
  fi
  COLLISION=0
  case "$CIBLE/" in
    "$DEPOT"/*)
      avis "Ce dossier est à l'intérieur du dossier téléchargé — il serait supprimé avec lui."
      REP="$(question "Emplacement de ton vault" "$(affiche "$DEFAUT_CIBLE")")"
      CIBLE=""; continue ;;
  esac
  if ! mkdir -p "$CIBLE" 2>/dev/null; then
    avis "Impossible de créer « $(affiche "$CIBLE") »."
    REP="$(question "Emplacement de ton vault" "$(affiche "$DEFAUT_CIBLE")")"
    CIBLE=""; continue
  fi
  if [ -n "$(/bin/ls -A "$CIBLE" 2>/dev/null)" ]; then
    avis "« $(affiche "$CIBLE") » existe déjà et n'est pas vide."
    if ! confirmer "Installer dedans quand même (les fichiers de Bobine y seront copiés, rien n'est supprimé) ?" "n"; then
      REP="$(question "Emplacement de ton vault" "$(affiche "$DEFAUT_CIBLE")")"
      CIBLE=""; continue
    fi
  fi
done

if [ "$GARDE" = "reinstall" ]; then
  ok "Réinstallation dans ton dossier Bobine : $(affiche "$CIBLE")"
elif [ "$GARDE" = "oui" ]; then
  ok "D'accord — ce dossier devient ton dossier Bobine (il ne sera pas supprimé)."
else
  for f in ingest.py enrichir.py generate_page.py graphe.py filtre.py watch.sh install.sh \
           desinstaller.sh requirements.txt config.example.env filtres.exemple.yaml \
           LICENSE README.md .gitignore; do
    [ -f "$DEPOT/$f" ] && cp "$DEPOT/$f" "$CIBLE/$f"
  done
  [ -d "$DEPOT/exemples" ] && cp -R "$DEPOT/exemples" "$CIBLE/" 2>/dev/null
  [ -f "$DEPOT/👉 2. Installer Bobine.command" ] && cp "$DEPOT/👉 2. Installer Bobine.command" "$CIBLE/"
  ok "Fichiers installés dans : $(affiche "$CIBLE")"
fi
cd "$CIBLE" || exit 1
SCRIPT_DIR="$(pwd)"

# ----------------------------------------------------- petits plus (macOS)
# Double-clic pour désinstaller : ce fichier naît ici même — macOS ne le bloquera jamais.
cat > "Désinstaller Bobine.command" <<'CMD'
#!/bin/bash
cd "$(dirname "$0")" || exit 1
exec bash ./desinstaller.sh
CMD
chmod +x "Désinstaller Bobine.command"

# Une petite page d'accueil (elle sera remplacée toute seule au premier vrai passage).
if [ ! -f "vault.html" ]; then
  cat > "vault.html" <<'PAGE'
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Bobine</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#201a3d;color:#f3ecff;font-family:-apple-system,"SF Pro Text",Helvetica,sans-serif}
  .carte{background:#2c2452;border:1px solid #4a3f7d;border-radius:18px;padding:40px 46px;
         max-width:540px;text-align:center;box-shadow:0 18px 60px rgba(0,0,0,.35)}
  h1{margin:0 0 12px;font-size:26px}
  p{margin:8px 0;color:#c9bdf0;line-height:1.55}
  .petit{font-size:13px;color:#8f83bd;margin-top:18px}
</style>
</head>
<body>
  <div class="carte">
    <h1>🎞️ Bobine</h1>
    <p>Ta page est prête — elle se remplira automatiquement<br>après ta première vidéo partagée.</p>
    <p class="petit">Cette page vit sur ton Mac.<br>(Elle se retrouve aussi dans iCloud si tu as activé la copie.)</p>
  </div>
</body>
</html>
PAGE
fi

# Raccourci « Ma page » : double-clic = ta page s'ouvre dans le navigateur.
URL_PAGE="$("$PY" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().as_uri())' "vault.html" 2>/dev/null || true)"
if [ -n "$URL_PAGE" ]; then
  cat > "Ma page.webloc" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>URL</key>
	<string>$URL_PAGE</string>
</dict>
</plist>
EOF
fi

# ---------------------------------------------------------------- 4. clé API
etape "4/7 — Les résumés automatiques (clé API)"
note "Facultatif mais recommandé : un résumé + des thèmes pour chaque vidéo."
note "C'est TA clé (quelques centimes pour des centaines de vidéos) ; elle reste ici, sur ta machine."
API_BLOC=""
ANCIENNE_CONFIG=""
if [ -f config.env ]; then
  ANCIENNE_CONFIG="config.env.bak-$(date '+%Y%m%d-%H%M%S')"
  cp config.env "$ANCIENNE_CONFIG"
  note "Ancienne configuration sauvegardée dans $ANCIENNE_CONFIG"
fi
VIEILLE_CLE=""
if [ -n "$ANCIENNE_CONFIG" ]; then
  VIEILLE_CLE="$(grep -m1 -E '^(DEEPSEEK|OPENAI|OPENROUTER|GEMINI)_API_KEY=|^API_KEY=' "$ANCIENNE_CONFIG" 2>/dev/null || true)"
fi
if [ -n "$VIEILLE_CLE" ]; then
  if confirmer "Une clé API était déjà configurée — la garder ?" "o"; then
    API_BLOC="$VIEILLE_CLE"
    VIEUX_MODELE="$(grep -m1 -E '^API_MODEL=' "$ANCIENNE_CONFIG" 2>/dev/null || true)"
    [ -n "$VIEUX_MODELE" ] && API_BLOC="$API_BLOC
$VIEUX_MODELE"
    ok "Clé conservée"
  else
    VIEILLE_CLE=""
  fi
fi
if [ -z "$API_BLOC" ] && confirmer "Activer les résumés automatiques ?" "o"; then
  echo "   1) DeepSeek    — le moins cher (recommandé)"
  echo "   2) OpenAI"
  echo "   3) OpenRouter  — des modèles gratuits existent"
  echo "   4) Un autre service compatible OpenAI"
  echo "   5) Plus tard"
  CHOIX="$(question "Ton choix" "1")"
  case "$CHOIX" in
    1)
      CLE="$(secret "Colle ta clé DeepSeek (platform.deepseek.com)")"
      CLE="$(printf '%s' "$CLE" | tr -d '[:space:]')"
      if [ -n "$CLE" ]; then API_BLOC="DEEPSEEK_API_KEY=$CLE"; ok "Clé DeepSeek enregistrée (masquée)"; fi ;;
    2)
      CLE="$(secret "Colle ta clé OpenAI (platform.openai.com/api-keys)")"
      CLE="$(printf '%s' "$CLE" | tr -d '[:space:]')"
      if [ -n "$CLE" ]; then API_BLOC="OPENAI_API_KEY=$CLE"; ok "Clé OpenAI enregistrée (masquée)"; fi ;;
    3)
      CLE="$(secret "Colle ta clé OpenRouter (openrouter.ai)")"
      CLE="$(printf '%s' "$CLE" | tr -d '[:space:]')"
      if [ -n "$CLE" ]; then
        MODELE="$(question "Identifiant du modèle (bouton « copier » sur la page du modèle)" "")"
        API_BLOC="OPENROUTER_API_KEY=$CLE"
        [ -n "$MODELE" ] && API_BLOC="$API_BLOC
API_MODEL=$MODELE"
        ok "Clé OpenRouter enregistrée (masquée)"
      fi ;;
    4)
      CLE="$(secret "Colle ta clé API")"
      CLE="$(printf '%s' "$CLE" | tr -d '[:space:]')"
      BASE="$(question "Adresse (base_url) du service, ex. https://api.exemple.com/v1" "")"
      MODELE="$(question "Identifiant du modèle" "")"
      if [ -n "$CLE" ] && [ -n "$BASE" ]; then
        API_BLOC="API_KEY=$CLE
API_BASE_URL=$BASE"
        [ -n "$MODELE" ] && API_BLOC="$API_BLOC
API_MODEL=$MODELE"
        ok "Clé enregistrée (masquée)"
      fi ;;
    *)
      note "D'accord — tu pourras ajouter ta clé plus tard dans config.env." ;;
  esac
  if [ -z "$API_BLOC" ]; then
    note "(pas de clé pour l'instant : tu pourras en ajouter une plus tard dans config.env)"
  fi
fi

# ---------------------------------------------------------------- 5. options
etape "5/7 — Les options"
REVEIL="non"; CARTE="oui"; SYNC="oui"
if confirmer "Installer le réveil automatique (toutes les 15 minutes) ?" "o"; then
  REVEIL="oui"
fi
if confirmer "Générer aussi la carte des thèmes (graph.html) ?" "o"; then
  CARTE="oui"; else CARTE="non"
fi
if confirmer "Copier la page vers iCloud pour la consulter sur ton iPhone ?" "o"; then
  SYNC="oui"; else SYNC="non"
fi

# écrire config.env (nouveau, en gardant l'éventuelle clé récupérée)
{
  echo "# Bobine — configuration (généré par install.sh le $(date '+%d/%m/%Y'))"
  echo "# Détails et réglages avancés : voir config.example.env"
  echo
  echo "NOM=\"$NOM_VAULT\""
  echo "CARTE=\"$CARTE\""
  echo "SYNC_ICLOUD=\"$SYNC\""
  if [ -n "$API_BLOC" ]; then
    echo
    echo "$API_BLOC"
  fi
} > config.env
chmod 600 config.env
ok "config.env écrit (clé comprise, lisible par toi seul)"

# ---------------------------------------------------------------- réveil (launchd)
if [ "$REVEIL" = "oui" ]; then
  PLIST="$HOME/Library/LaunchAgents/com.bobine.watch.plist"
  if [ -f "$PLIST" ] && ! grep -qF "$SCRIPT_DIR/watch.sh" "$PLIST" 2>/dev/null; then
    note "Un réveil existait déjà pour un autre dossier — remplacé (Bobine n'en fait tourner qu'un à la fois)."
  fi
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.bobine.watch</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$SCRIPT_DIR/watch.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Minute</key><integer>0</integer></dict>
    <dict><key>Minute</key><integer>15</integer></dict>
    <dict><key>Minute</key><integer>30</integer></dict>
    <dict><key>Minute</key><integer>45</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$SCRIPT_DIR/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$SCRIPT_DIR/logs/launchd.err.log</string>
</dict>
</plist>
EOF
  launchctl bootout "gui/$(id -u)/com.bobine.watch" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST" 2>/dev/null || true
  ok "Réveil installé (com.bobine.watch) — premier passage imminent"
fi

# ---------------------------------------------------------------- 6. dépendances
etape "6/7 — Environnement Python et dépendances"
mkdir -p logs
if [ ! -d .venv ]; then
  note "Création de l'environnement Python…"
  "$PY" -m venv .venv || { avis "Impossible de créer l'environnement."; exit 1; }
fi
if [ -x .venv/bin/python ]; then
  (
    .venv/bin/pip install --upgrade pip -q &&
    .venv/bin/pip install -q -r requirements.txt
  ) > logs/install.log 2>&1 &
  pid=$!
  tours=0
  while kill -0 "$pid" 2>/dev/null; do
    case $((tours % 4)) in
      0) points="." ;; 1) points=".." ;; 2) points="..." ;; 3) points="...." ;;
    esac
    printf "\r  ${FONCE}⏳ Installation des dépendances%-4s  (1 à 3 minutes)${FIN}" "$points"
    tours=$((tours + 1))
    sleep 1
  done
  wait "$pid"
  rc=$?
  printf "\r%*s\r" 70 ""
  if [ "$rc" -ne 0 ]; then
    avis "L'installation des dépendances a échoué — détails dans logs/install.log"
    exit 1
  fi
  ok "Dépendances installées (yt-dlp, faster-whisper, gallery-dl, numpy)"
else
  avis "L'environnement .venv est introuvable."
  exit 1
fi

if command -v ffmpeg >/dev/null 2>&1; then
  ok "ffmpeg trouvé"
else
  avis "ffmpeg est introuvable dans le PATH."
  note "Installe-le avec :   brew install ffmpeg   (nécessaire pour la transcription)"
fi

# ---------------------------------------------------------------- 7. bonus : Crush
etape "7/7 — Bonus : interroge ton vault (Crush)"
note "Crush, c'est un assistant IA qui vit dans le Terminal : léger, open source, sans compte à créer."
note "Il utilise la même clé API que tes résumés — et lancé dans ton vault, il lit tes fiches pour répondre."
note "Exemple : « Quelles vidéos parlent de cuisine ? »"

CRUSH_PRET="non"
if command -v crush >/dev/null 2>&1; then
  ok "Crush est déjà installé ✓"
  CRUSH_PRET="oui"
elif command -v brew >/dev/null 2>&1; then
  if confirmer "Veux-tu que je l'installe maintenant (recommandé, via Homebrew) ?" "o"; then
    note "Installation de Crush… (une minute)"
    if brew install charmbracelet/tap/crush > logs/crush-install.log 2>&1; then
      ok "Crush installé"
      CRUSH_PRET="oui"
    else
      avis "L'installation de Crush a échoué — détails : logs/crush-install.log"
      note "Tu pourras réessayer plus tard :   brew install charmbracelet/tap/crush"
    fi
  else
    note "D'accord — pour l'avoir plus tard :   brew install charmbracelet/tap/crush"
  fi
else
  note "Pour l'avoir plus tard (il faut Homebrew — voir brew.sh), puis :"
  note "   brew install charmbracelet/tap/crush"
fi

# On prépare .crushrc : lu automatiquement quand on lance « crush » dans ce dossier.
if [ -f .crushrc ]; then
  cp .crushrc ".crushrc.bak-$(date '+%Y%m%d-%H%M%S')" 2>/dev/null && note "Ancien .crushrc sauvegardé (.crushrc.bak-…)"
fi
{
  echo "# Bobine — réglages de Crush pour ce dossier (lus automatiquement par « crush »)."
  case "${API_BLOC:-}" in
    *DEEPSEEK_API_KEY=*)
      CLE_CRUSH="$(printf '%s\n' "$API_BLOC" | grep -m1 '^DEEPSEEK_API_KEY=' | cut -d= -f2-)"
      echo "# Ta clé (la même que pour tes résumés — aussi dans config.env) :"
      echo "export DEEPSEEK_API_KEY=\"$CLE_CRUSH\""
      echo
      echo "# Le fournisseur et le modèle (rapide et économique) :"
      echo 'provider add deepseek --type openai-compat --base-url "https://api.deepseek.com/v1" --api-key "$DEEPSEEK_API_KEY"'
      echo "model large deepseek/deepseek-v4-flash"
      echo "model small deepseek/deepseek-v4-flash"
      ;;
    *OPENAI_API_KEY=*)
      CLE_CRUSH="$(printf '%s\n' "$API_BLOC" | grep -m1 '^OPENAI_API_KEY=' | cut -d= -f2-)"
      echo "# Ta clé (la même que pour tes résumés — aussi dans config.env) :"
      echo "export OPENAI_API_KEY=\"$CLE_CRUSH\""
      echo
      echo "# Le fournisseur :"
      echo 'provider add openai --type openai --base-url "https://api.openai.com/v1" --api-key "$OPENAI_API_KEY"'
      ;;
    *OPENROUTER_API_KEY=*)
      CLE_CRUSH="$(printf '%s\n' "$API_BLOC" | grep -m1 '^OPENROUTER_API_KEY=' | cut -d= -f2-)"
      echo "# Ta clé (la même que pour tes résumés — aussi dans config.env) :"
      echo "export OPENROUTER_API_KEY=\"$CLE_CRUSH\""
      echo
      echo "# Le fournisseur :"
      echo 'provider add openrouter --type openrouter --base-url "https://openrouter.ai/api/v1" --api-key "$OPENROUTER_API_KEY"'
      ;;
    *)
      echo "# Pas de clé API pour l'instant — la même clé que tes résumés ira ici."
      echo "# Quand tu l'auras, décommente ces lignes :"
      echo '# export DEEPSEEK_API_KEY="sk-…"'
      echo '# provider add deepseek --type openai-compat --base-url "https://api.deepseek.com/v1" --api-key "$DEEPSEEK_API_KEY"'
      echo "# model large deepseek/deepseek-v4-flash"
      echo "# model small deepseek/deepseek-v4-flash"
      ;;
  esac
  echo
  echo "# Lecture seule : Crush lit et cherche tes fiches, ne modifie rien et ne lance pas de commandes."
  echo "permissions allow view ls grep"
  echo "permissions deny bash"
  echo
  echo "# Pas de statistiques anonymes."
  echo "option metrics false"
} > .crushrc
chmod 600 .crushrc
if [ -n "${CLE_CRUSH:-}" ]; then
  ok "Crush pré-réglé (.crushrc — il prendra ta clé tout seul)"
else
  note "Crush pré-réglé (.crushrc — il te manquera juste une clé API, une ligne t'y attend)"
fi
if [ "$CRUSH_PRET" = "oui" ]; then
  note "Pour t'en servir : dans le Terminal, va dans ton vault ($(affiche "$CIBLE")) puis tape :  crush"
fi

# ---------------------------------------------------------------- résumé final
echo
printf "${VERT}${GRAS}  ✨ C'est prêt !${FIN}\n\n"
printf "   Dossier         : %s\n" "$SCRIPT_DIR"
printf "   Nom du vault    : %s\n" "$NOM_VAULT"
if [ -n "$API_BLOC" ]; then
  printf "   Résumés auto    : oui\n"
else
  printf "   Résumés auto    : non (ajoute une clé dans config.env quand tu veux)\n"
fi
printf "   Réveil 15 min   : %s\n" "$REVEIL"
printf "   Carte (graphe)  : %s\n" "$CARTE"
printf "   Copie iPhone    : %s\n" "$SYNC"
printf "   Assistant Crush : %s\n" "$CRUSH_PRET"
echo
printf "   ${GRAS}Et maintenant ?${FIN}\n"
printf "   1. Crée le raccourci iPhone « Send to Bobine » — recette pas-à-pas dans le README\n"
printf "   2. Partage une vidéo de test, puis surveille :  %s/logs/watch.log\n" "$SCRIPT_DIR"
printf "   3. Ta page : %s/vault.html\n" "$SCRIPT_DIR"
printf "   4. Un jour, pour tout retirer :  ./desinstaller.sh  (dans le dossier de ton vault)\n"
if [ "$SYNC" = "oui" ]; then
  printf "      (sur l'iPhone : Fichiers → iCloud Drive → %s → vault.html)\n" "$NOM_VAULT"
fi
if [ -z "$GARDE" ]; then
  echo
  printf "   ${GRAS}Un dernier réflexe — le ménage :${FIN}\n"
  printf "   • ton vault vit ici :       %s\n" "$(affiche "$CIBLE")"
  printf "   • le dossier téléchargé :   %s\n" "$(affiche "$DEPOT")"
  printf "     ne sert plus à rien — tu peux le glisser dans la corbeille.\n"
fi
# ---------------------------------------------------------- générique de fin
echo
if [ -t 1 ]; then
  DELAI="0.09"
  printf "   ${FONCE}🎞️  Mise en bobine…${FIN}"
  for c in ⣾ ⣽ ⣻ ⢿ ⡿ ⣟ ⣯ ⣷ ⣾ ⣽; do
    printf "\r   ${FONCE}🎞️  Mise en bobine…${FIN} ${VIOLET}${c}${FIN}"
    sleep 0.07
  done
  printf "\r%*s\r" 40 ""
else
  DELAI="0"
fi
TIRET="$(printf '─%.0s' $(seq 1 45))"
VIDE45="$(printf ' %.0s' $(seq 1 45))"
PAD17="$(printf ' %.0s' $(seq 1 17))"
PAD9="$(printf ' %.0s' $(seq 1 9))"
PAD3="   "
printf "   ${FONCE}╭${TIRET}╮${FIN}\n"; sleep "$DELAI"
printf "   ${FONCE}│${VIDE45}│${FIN}\n"; sleep "$DELAI"
printf "   ${FONCE}│${FIN}${PAD17}${VIOLET}${GRAS}B O B I N E${FIN}${FONCE}${PAD17}│${FIN}\n"; sleep "$DELAI"
printf "   ${FONCE}│${VIDE45}│${FIN}\n"; sleep "$DELAI"
printf "   ${FONCE}│${FIN}${PAD3}chaque vidéo partagée devient une fiche${PAD3}${FONCE}│${FIN}\n"; sleep "$DELAI"
printf "   ${FONCE}│${FIN}${PAD9}à retrouver, à questionner.${PAD9}${FONCE}│${FIN}\n"; sleep "$DELAI"
printf "   ${FONCE}╰${TIRET}╯${FIN}\n"; sleep "$DELAI"
echo
printf "   ${FONCE}🎞️  écrit et réalisé par Wahid Rouhli · github.com/wrouhli/bobine${FIN}\n\n"
