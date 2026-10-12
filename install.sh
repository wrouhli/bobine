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
  FONCE=$'\033[2m'; GRAS=$'\033[1m'; VERT=$'\033[1;32m'
  JAUNE=$'\033[1;33m'; VIOLET=$'\033[1;35m'; CYAN=$'\033[1;36m'; FIN=$'\033[0m'
else
  FONCE=""; GRAS=""; VERT=""; JAUNE=""; VIOLET=""; CYAN=""; FIN=""
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

# Même dossier de données pour la génération et le serveur ; jamais de source/eval.
resoudre_vault_effectif() {
  "$PY" -B - "$SCRIPT_DIR" <<'PYTHON'
import os
import sys
from pathlib import Path
code = Path(sys.argv[1])
try:
    config = code / "config.env"
    if config.is_symlink() or (config.exists() and not config.is_file()):
        raise ValueError("configuration non ordinaire")
    sys.path.insert(0, str(code))
    from enrichir import charger_config
    configured = charger_config(code).get("VAULT")
    vault = Path(os.path.expandvars(configured)).expanduser() if configured else code
    if not vault.is_absolute() or any(ord(c) < 32 or ord(c) == 127 for c in str(vault)):
        raise ValueError("chemin de données non absolu ou ambigu")
    print(vault)
except (OSError, ValueError, RuntimeError, ImportError):
    sys.exit(1)
PYTHON
}

# Une mise à jour du générateur doit aussi actualiser une page déjà existante.
# Génération locale uniquement : ni ingestion, ni enrichissement, ni appel d'IA.
preparer_page() {
  VAULT_EFFECTIF="$(resoudre_vault_effectif)" || {
    avis "VAULT illisible ou ambigu dans config.env : la page et son service sont conservés."
    return 1
  }
  mkdir -p "$SCRIPT_DIR/logs" || return 1
  if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/generate_page.py" --vault "$VAULT_EFFECTIF" > "$SCRIPT_DIR/logs/page-generation.log" 2>&1; then
    ok "Page régénérée localement (sans appel d'IA)."
  else
    avis "La génération de la page a échoué — détails dans logs/page-generation.log."
    return 1
  fi
}

# La page est un service distinct du réveil. Aucune configuration n'est exécutée.
page_plist_appartient() {
  [ ! -L "$1" ] && "$PY" - "$1" "$SCRIPT_DIR" "$VAULT_EFFECTIF" <<'PYTHON'
import plistlib
from xml.parsers.expat import ExpatError
import sys
from pathlib import Path
try:
    with open(sys.argv[1], "rb") as stream:
        data = plistlib.load(stream)
    vault = Path(sys.argv[2])
    expected = [str(vault / ".venv/bin/python"), str(vault / "page_server.py"),
                "--vault", sys.argv[3], "--local"]
    valid = data.get("Label") == "com.bobine.page" and data.get("ProgramArguments") == expected
except (OSError, ValueError, TypeError, AttributeError, ExpatError):
    valid = False
sys.exit(0 if valid else 1)
PYTHON
}

ecrire_raccourci_page() {
  "$PY" - "$SCRIPT_DIR" "$1" "${VAULT_EFFECTIF:-$SCRIPT_DIR}" <<'PYTHON'
import os
import plistlib
from xml.parsers.expat import ExpatError
import sys
import tempfile
from pathlib import Path
vault = Path(sys.argv[1])
shortcut = vault / "Ma page.webloc"
fallback = (Path(sys.argv[3]) / "vault.html").as_uri()
legacy = (vault / "vault.html").as_uri()
local = "http://127.0.0.1:8786/"
data = {"URL": local if sys.argv[2] == "serveur" else fallback}
try:
    if shortcut.is_symlink():
        sys.exit(1)
    if shortcut.exists():
        with shortcut.open("rb") as stream:
            old = plistlib.load(stream)
        if old not in ({"URL": fallback}, {"URL": legacy}, {"URL": local}):
            sys.exit(1)
        if old == data:
            sys.exit(0)
    fd, temp = tempfile.mkstemp(prefix=".ma-page-", dir=vault)
    try:
        with os.fdopen(fd, "wb") as stream:
            plistlib.dump(data, stream)
        os.replace(temp, shortcut)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
except (OSError, ValueError, TypeError, ExpatError):
    sys.exit(1)
PYTHON
}

port_page_libre() {
  "$PY" - <<'PYTHON'
import socket
import sys
try:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 8786))
except OSError:
    sys.exit(1)
PYTHON
}

page_locale_repond() {
  # Connexion directe locale : aucun proxy d'environnement ni accès au LAN.
  "$PY" - <<'PYTHON'
import http.client
import sys
connection = http.client.HTTPConnection("127.0.0.1", 8786, timeout=0.5)
try:
    connection.request("GET", "/health")
    response = connection.getresponse()
    valid = response.status == 200 and response.read(16).strip() == b"ok"
except (OSError, http.client.HTTPException):
    valid = False
finally:
    connection.close()
sys.exit(0 if valid else 1)
PYTHON
}

installer_page_locale() {
  local plist="$HOME/Library/LaunchAgents/com.bobine.page.plist"
  local service existant=non etat tentative
  service="gui/$(id -u)/com.bobine.page"
  [ -x "$SCRIPT_DIR/.venv/bin/python" ] && [ -f "$SCRIPT_DIR/page_server.py" ] &&
    [ -f "$SCRIPT_DIR/demander.py" ] || return 1
  if [ -e "$plist" ] || [ -L "$plist" ]; then
    if ! page_plist_appartient "$plist"; then
      avis "Un service de page existe pour un autre dossier ou a été personnalisé : il est conservé."
      return 1
    fi
    existant=oui
  elif launchctl print "$service" >/dev/null 2>&1; then
    avis "Un service de page est déjà chargé sans fichier reconnu : il est conservé."
    return 1
  fi
  if [ "$existant" = oui ]; then
    launchctl bootout "$service" 2>/dev/null || true
  fi
  if ! port_page_libre; then
    avis "Le port local 8786 est déjà utilisé : aucun autre serveur n'est remplacé."
    return 1
  fi
  mkdir -p "$HOME/Library/LaunchAgents" "$SCRIPT_DIR/logs" || return 1
  # plistlib échappe le XML ; chaque argument reste distinct, même avec des espaces.
  "$PY" - "$plist" "$SCRIPT_DIR" "$VAULT_EFFECTIF" <<'PYTHON' || return 1
import os
import plistlib
import sys
import tempfile
from pathlib import Path
path, vault = Path(sys.argv[1]), Path(sys.argv[2])
data = {
    "Label": "com.bobine.page",
    "ProgramArguments": [str(vault / ".venv/bin/python"), str(vault / "page_server.py"),
                         "--vault", sys.argv[3], "--local"],
    "WorkingDirectory": str(vault),
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 10,
    "StandardOutPath": str(vault / "logs/page.out.log"),
    "StandardErrorPath": str(vault / "logs/page.err.log"),
}
fd, temp = tempfile.mkstemp(prefix=".bobine-page-", dir=path.parent)
try:
    with os.fdopen(fd, "wb") as stream:
        plistlib.dump(data, stream)
    os.replace(temp, path)
finally:
    if os.path.exists(temp):
        os.unlink(temp)
PYTHON
  if ! launchctl bootstrap "gui/$(id -u)" "$plist" 2>/dev/null; then
    return 1
  fi
  for ((tentative=0; tentative<10; tentative++)); do
    etat="$(launchctl print "$service" 2>/dev/null || true)"
    if printf '%s\n' "$etat" | grep -qE '^[[:space:]]*state = running[[:space:]]*$' &&
       printf '%s\n' "$etat" | grep -qE '^[[:space:]]*pid = [1-9][0-9]*[[:space:]]*$' && page_locale_repond; then
      return 0
    fi
    sleep 0.5
  done
  # Un chargement réussi n'est pas une preuve de démarrage. Ne pas laisser boucler.
  launchctl bootout "$service" 2>/dev/null || true
  return 1
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
  # shellcheck disable=SC2088  # « ~ » littéral tapé par l'utilisateur, développé à la main
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
  if ! CONTENU="$(/bin/ls -Aq "$CIBLE" 2>/dev/null)" || [ -n "$CONTENU" ]; then
    avis "Ce dossier contient déjà des fichiers. Choisis un dossier vide pour les protéger."
    REP="$(question "Emplacement de ton vault" "$(affiche "$DEFAUT_CIBLE")")"
    CIBLE=""; continue
  fi
done

if [ "$GARDE" = "reinstall" ]; then
  ok "Réinstallation dans ton dossier Bobine : $(affiche "$CIBLE")"
elif [ "$GARDE" = "oui" ]; then
  ok "D'accord — ce dossier devient ton dossier Bobine (il ne sera pas supprimé)."
else
  for f in ingest.py enrichir.py generate_page.py graphe.py filtre.py page_server.py demander.py watch.sh install.sh \
           desinstaller.sh requirements.txt config.example.env filtres.exemple.yaml \
           LICENSE .gitignore; do
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
if [ ! -e "Désinstaller Bobine.command" ] && [ ! -L "Désinstaller Bobine.command" ]; then
cat > "Désinstaller Bobine.command" <<'CMD'
#!/bin/bash
cd "$(dirname "$0")" || exit 1
exec bash ./desinstaller.sh
CMD
chmod +x "Désinstaller Bobine.command"
fi

# Un petit README pour le vault — le guide complet reste sur la page du projet.
if [ ! -f "README.md" ]; then
  cat > "README.md" <<EOF
# 🎞️ $NOM_VAULT

Ton vault, chez toi : chaque vidéo partagée depuis ton iPhone devient une fiche
ici — téléchargée, transcrite et résumée automatiquement.

## Au quotidien

- **Partager** : Instagram, TikTok ou YouTube → Partager → le raccourci « Send to Bobine ».
- **La page** : double-clique « Ma page » (recherche, pastilles de thèmes, fiches).
- **Le réveil** : relève la boîte toutes les 15 minutes — journal : logs/watch.log
- **À la main** : launchctl kickstart -k gui/\$(id -u)/com.bobine.watch

## Les fichiers

- raw/ — tes fiches (Markdown, ouvrables avec n'importe quel outil)
- index.md — l'index condensé (résumés + thèmes)
- memos/ : le mémo de chaque vidéo (avec une clé API)
- Mon profil.txt : quelques lignes sur toi, pour le bloc « Pour toi » (facultatif)
- vault.html et graph.html — la page et la carte
- config.env — ta configuration (clé API, nom, options)
- logs/ — les journaux, en cas de souci

## Les docs

- Guide complet, dépannage, recette du Raccourci : https://github.com/wrouhli/bobine
- Arrêter Bobine sans supprimer tes fichiers : double-clique « Désinstaller Bobine.command ».
EOF
fi

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

# Raccourci local de secours, conservé si le serveur ne démarre pas.
# Un raccourci personnel (autre URL ou lien symbolique) n'est jamais remplacé.
ecrire_raccourci_page fichier || note "Ton raccourci Ma page est conservé."

# ---------------------------------------------------------------- 4. clé API
etape "4/7 — Les résumés automatiques (clé API)"
note "Facultatif mais recommandé : un résumé + des thèmes pour chaque vidéo."
note "C'est TA clé (quelques centimes pour des centaines de vidéos) ; elle reste ici, sur ta machine."
API_BLOC=""
ANCIENNE_CONFIG=""
if [ -f config.env ]; then
  ANCIENNE_CONFIG="config.env.bak-$(date '+%Y%m%d-%H%M%S')"
  cp config.env "$ANCIENNE_CONFIG"
  chmod 600 "$ANCIENNE_CONFIG"   # elle contient la clé API : lisible par toi seul
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
      if [ -n "$CLE" ]; then
        API_BLOC="OPENAI_API_KEY=$CLE
API_MODEL=gpt-4o-mini"
        ok "Clé OpenAI enregistrée (masquée)"
      fi ;;
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

# Profil (facultatif) : quelques lignes sur toi pour le bloc « Pour toi ».
# Jamais écrasé : s'il existe déjà, on le garde tel quel.
if [ ! -f "Mon profil.txt" ]; then
  note "Bobine peut te dire ce que chaque vidéo t'apporte. Pour ça, décris-toi en une ou deux phrases."
  note "(facultatif : appuie sur Entrée pour passer ; tu pourras le faire plus tard dans « Mon profil.txt »)"
  PROFIL="$(question "Qui es-tu, et que cherches-tu dans tes vidéos ?" "")"
  {
    echo "# Ton profil Bobine (facultatif)."
    echo "# Écris quelques lignes sur toi : ce que tu fais, ce que tu cherches dans tes vidéos."
    echo "# Bobine s'en sert pour le bloc « Pour toi » de chaque fiche."
    echo "# Les lignes qui commencent par # sont des explications : elles ne sont jamais lues."
    echo "# Ce texte est envoyé à ton service d'IA avec les demandes de résumé : évite les informations sensibles."
    echo
    if [ -n "$PROFIL" ]; then printf '%s\n' "$PROFIL"; fi
  } > "Mon profil.txt"
  chmod 600 "Mon profil.txt"
  if [ -n "$PROFIL" ]; then ok "Profil enregistré (Mon profil.txt)"; else note "Pas de profil pour l'instant : « Mon profil.txt » t'attend."; fi
else
  ok "Profil conservé (Mon profil.txt)"
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
    case "$API_BLOC" in
      *API_MODEL=*) ;;
      *DEEPSEEK_API_KEY=*)
        echo "# Modèle des résumés (facultatif) : deepseek-chat par défaut. Si DeepSeek"
        echo "# le retire, mets ici l'identifiant actuel (voir platform.deepseek.com) :"
        echo "#API_MODEL=deepseek-chat" ;;
    esac
  fi
  echo
  echo "# Langue des résumés : fr (défaut) ou en"
  echo "#LANGUE_RESUMES=en"
  # Réglages avancés de l'ancienne configuration, gardés tels quels (chemins,
  # cookies, notification, jeton du serveur de liens, mot de passe de la page…).
  if [ -n "$ANCIENNE_CONFIG" ]; then
    GARDES="$(grep -E '^(VAULT|INBOX|FFMPEG_DIR|COOKIES|LANGUE_RESUMES|NOTIF_CMD|INBOX_TOKEN|PAGE_PASSWORD|PAGE_ORIGIN)=' "$ANCIENNE_CONFIG" 2>/dev/null || true)"
    if [ -n "$GARDES" ]; then
      echo
      echo "# Réglages repris de ta configuration précédente :"
      echo "$GARDES"
    fi
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

# ---------------------------------------------------------------- page locale (launchd)
PAGE_LOCALE="non"
if preparer_page && installer_page_locale; then
  PAGE_LOCALE="oui"
  ecrire_raccourci_page serveur || note "Ton raccourci Ma page est conservé."
  ok "Ta page est disponible sur http://127.0.0.1:8786/ (ce Mac uniquement)."
  note "Demander utilise ta clé API ; sans clé, la bibliothèque reste disponible."
else
  [ -n "${VAULT_EFFECTIF:-}" ] && ecrire_raccourci_page fichier || true
  note "La page locale n'a pas démarré. Ouvre vault.html : ta bibliothèque reste disponible."
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
  echo "# Lecture seule : Crush lit et cherche tes fiches (sans te demander à chaque fois)."
  echo "# Les outils qui modifient des fichiers, lancent des commandes ou vont sur internet"
  echo "# sont retirés : Crush ne peut ni écrire, ni exécuter, ni envoyer tes fiches ailleurs."
  echo "permissions allow view ls grep glob"
  echo "permissions deny bash edit multiedit write fetch download sourcegraph lsp_rename lsp_replace_symbol"
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
printf "   1. Crée le raccourci iPhone « Send to Bobine » — recette pas-à-pas sur la page du projet\n"
printf "   2. Partage une vidéo de test, puis surveille :  %s/logs/watch.log\n" "$SCRIPT_DIR"
if [ "$PAGE_LOCALE" = "oui" ]; then
  printf "   3. Ta page : http://127.0.0.1:8786/ (ce Mac uniquement)\n"
else
  printf "   3. Ta page : %s/vault.html\n" "${VAULT_EFFECTIF:-$SCRIPT_DIR}"
fi
printf "   4. Un jour, pour arrêter Bobine sans supprimer tes fichiers :  ./desinstaller.sh  (dans le dossier de ton vault)\n"
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
