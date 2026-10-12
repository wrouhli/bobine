#!/bin/bash
# shellcheck shell=bash
# Bobine (macOS) : fonctions partagées de la page locale et du réglage « Demander ».
#
# Ce fichier n'est pas lancé directement : il est chargé (source) par install.sh,
# activer-demander.sh, desactiver-demander.sh et ouvrir-ma-page.sh, pour que la
# logique du service de page et du raccourci « Ma page » n'existe qu'une fois.
#
# Variables attendues chez l'appelant :
#   SCRIPT_DIR : le dossier Bobine (code, config.env, .venv) ;
#   PY         : un Python 3 (choisir_python le trouve si besoin).
# Détails techniques (jamais montrés tels quels à l'utilisateur) : le service est
# un agent launchd « com.bobine.page » qui écoute sur 127.0.0.1:8786 (--local).
# config.env n'est jamais exécuté (ni source, ni eval) : il est lu comme du texte.
# shellcheck disable=SC2154  # SCRIPT_DIR et PY viennent de l'appelant

# Messages : ceux de l'appelant s'ils existent déjà (couleurs d'install.sh).
declare -F ok >/dev/null 2>&1 || ok() { printf '  ✓ %s\n' "$1"; }
declare -F note >/dev/null 2>&1 || note() { printf '  %s\n' "$1"; }
declare -F avis >/dev/null 2>&1 || avis() { printf '  ⚠  %s\n' "$1"; }

ADRESSE_PAGE_LOCALE="http://127.0.0.1:8786/"
PAGE_PLIST="$HOME/Library/LaunchAgents/com.bobine.page.plist"
# Marqueur de « Ma page.app » : un fichier texte dans le paquet, au contenu exact.
# Un « Ma page.app » sans ce fichier (ou avec un autre contenu) n'est pas à nous :
# il n'est jamais modifié ni remplacé.
MARQUEUR_APP="Contents/Resources/bobine-ma-page.txt"
MARQUEUR_APP_TEXTE="Bobine : raccourci Ma page (version 1)"

choisir_python() {  # PY : le Python du dossier si présent, sinon celui du système
  local candidat
  if [ -n "${PY:-}" ]; then return 0; fi
  if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then PY="$SCRIPT_DIR/.venv/bin/python"; return 0; fi
  for candidat in python3 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidat" >/dev/null 2>&1; then PY="$candidat"; return 0; fi
  done
  return 1
}

# ------------------------------------------------------------ réglages (texte)
lire_reglage() {  # $1 = clé, $2 = fichier (défaut : config.env) ; même lecture que charger_config
  [ -n "${PY:-}" ] || return 1
  "$PY" -B - "$1" "${2:-$SCRIPT_DIR/config.env}" <<'PYTHON'
import sys
from pathlib import Path
cle, chemin = sys.argv[1], Path(sys.argv[2])
valeur = ""
try:
    if chemin.is_file():
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            nom, texte = ligne.split("=", 1)
            texte = texte.strip().strip('"').strip("'")
            if nom.strip() == cle and texte:
                valeur = texte
except (OSError, ValueError):
    sys.exit(1)
print(valeur)
PYTHON
}

lire_demander() {  # affiche « oui » ou « non » ; réglage absent = oui (compatibilité)
  local valeur
  valeur="$(lire_reglage DEMANDER "${1:-}" 2>/dev/null)" || valeur=""
  case "$valeur" in
    # Mêmes valeurs que page_server.py (VALEURS_NON).
    [Nn][Oo][Nn]|[Nn][Oo]|[Nn]|[Ff][Aa][Ll][Ss][Ee]|0|[Oo][Ff][Ff]) echo non ;;
    *) echo oui ;;
  esac
}

cle_api_configuree() {
  local cle
  for cle in DEEPSEEK_API_KEY OPENAI_API_KEY OPENROUTER_API_KEY GEMINI_API_KEY API_KEY; do
    if [ -n "$(lire_reglage "$cle" 2>/dev/null)" ]; then return 0; fi
  done
  return 1
}

# Remplacement atomique de config.env : fichier temporaire dans le même dossier,
# fsync, os.replace, droits 600. Toutes les autres lignes (commentaires compris)
# sont gardées ; les doublons DEMANDER= disparaissent. Un lien symbolique ou un
# fichier non ordinaire est refusé sans rien modifier.
# $2 = « mot-de-passe » : garantit aussi un PAGE_PASSWORD (édition Linux) ; un
# nouveau mot de passe est créé dans Python et seulement affiché sur la sortie.
ecrire_demander() {
  local sortie
  case "$1" in oui|non) ;; *) return 1 ;; esac
  [ -n "${PY:-}" ] || return 1
  sortie="$("$PY" -B - "$SCRIPT_DIR/config.env" "$1" "${2:-}" <<'PYTHON'
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
config, valeur, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
try:
    if config.is_symlink() or (config.exists() and not stat.S_ISREG(config.stat().st_mode)):
        raise ValueError("config.env doit être un fichier ordinaire")
    ancien = config.read_text(encoding="utf-8") if config.exists() else None
    reglage = re.compile(r"^\s*DEMANDER\s*=")
    lignes, place = [], False
    for ligne in (ancien or "").splitlines(keepends=True):
        if reglage.match(ligne):
            if not place:
                lignes.append("DEMANDER=" + valeur + "\n")
                place = True
            continue
        lignes.append(ligne)
    if lignes and not lignes[-1].endswith("\n"):
        lignes[-1] += "\n"
    if not place:
        lignes.append("# Demander (questions à l'IA et profil modifiable depuis ta page) : oui ou non.\n")
        lignes.append("DEMANDER=" + valeur + "\n")
    nouveau = ""
    if mode == "mot-de-passe":
        motif = re.compile(r"^\s*PAGE_PASSWORD\s*=")
        actuels = [ligne.split("=", 1)[1].strip().strip('"').strip("'")
                   for ligne in lignes if motif.match(ligne)]
        if len(actuels) > 1:
            raise ValueError("plusieurs mots de passe configurés")
        if not actuels or not actuels[0]:
            nouveau = secrets.token_hex(16)
            lignes = [ligne for ligne in lignes if not motif.match(ligne)]
            lignes.append('PAGE_PASSWORD="' + nouveau + '"\n')
    texte = "".join(lignes)
    if texte == ancien and stat.S_IMODE(config.stat().st_mode) == 0o600:
        sys.exit(0)
    fd, temp = tempfile.mkstemp(prefix=".config-demander-", dir=config.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as flux:
            os.fchmod(flux.fileno(), 0o600)
            flux.write(texte)
            flux.flush()
            os.fsync(flux.fileno())
        os.replace(temp, config)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    try:
        dossier = os.open(config.parent, os.O_RDONLY)
        try:
            os.fsync(dossier)
        finally:
            os.close(dossier)
    except OSError:
        pass
    print(nouveau)
except (OSError, ValueError):
    sys.exit(1)
PYTHON
)" || {
    avis "Impossible de modifier config.env en sécurité (lien, dossier ou fichier protégé) : rien n'a été modifié."
    return 1
  }
  # shellcheck disable=SC2034  # lu par l'édition Linux (mot de passe créé)
  NOUVEAU_MOT_DE_PASSE="$sortie"
}

# ------------------------------------------------------------ dossier de données
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
    VAULT_EFFECTIF=""
    avis "VAULT illisible ou ambigu dans config.env : la page et son service sont conservés."
    return 1
  }
  mkdir -p "$SCRIPT_DIR/logs" || return 1
  if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/generate_page.py" --vault "$VAULT_EFFECTIF" > "$SCRIPT_DIR/logs/page-generation.log" 2>&1; then
    ok "Page régénérée localement (sans appel d'IA)."
  else
    avis "La génération de la page a échoué : détails dans logs/page-generation.log."
    return 1
  fi
}

page_fichier() {  # la page lisible sans serveur (vault.html du dossier de données)
  if [ -n "${VAULT_EFFECTIF:-}" ] && [ -f "$VAULT_EFFECTIF/vault.html" ]; then
    printf '%s' "$VAULT_EFFECTIF/vault.html"
  else
    printf '%s' "$SCRIPT_DIR/vault.html"
  fi
}

# ------------------------------------------------------------ raccourci « Ma page »
# Repli « Ma page.webloc » (si « Ma page.app » ne peut pas être créé). Un raccourci
# personnel (autre adresse, contenu illisible ou lien symbolique) n'est jamais
# remplacé ni retiré. $1 = serveur | fichier | retirer.
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
    if sys.argv[2] == "retirer" and not shortcut.exists():
        sys.exit(0)
    if shortcut.exists():
        with shortcut.open("rb") as stream:
            old = plistlib.load(stream)
        if old not in ({"URL": fallback}, {"URL": legacy}, {"URL": local}):
            sys.exit(1)
        if sys.argv[2] == "retirer":
            shortcut.unlink()
            sys.exit(0)
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

app_ma_page_est_a_nous() {
  local app="$SCRIPT_DIR/Ma page.app"
  [ -d "$app" ] && [ ! -L "$app" ] && [ -f "$app/$MARQUEUR_APP" ] && [ ! -L "$app/$MARQUEUR_APP" ] &&
    [ "$(head -c 200 "$app/$MARQUEUR_APP")" = "$MARQUEUR_APP_TEXTE" ]
}

# « Ma page.app » : petite application AppleScript, relocalisable (elle calcule
# son propre dossier) qui lance ouvrir-ma-page.sh sans ouvrir de Terminal.
# Vrai si l'application de ce dossier est la nôtre (déjà là ou créée à l'instant).
# Outils macOS désignables (tests uniquement) : sur un vrai Mac, retirer un faux
# osacompile du PATH ferait retomber sur /usr/bin/osacompile. Défaut : le vrai.
OSACOMPILE="${BOBINE_OSACOMPILE:-osacompile}"
CODESIGN="${BOBINE_CODESIGN:-codesign}"

creer_app_ma_page() {
  local app="$SCRIPT_DIR/Ma page.app" temp
  if [ -e "$app" ] || [ -L "$app" ]; then
    if app_ma_page_est_a_nous; then return 0; fi
    note "Ton « Ma page » personnel est conservé."
    return 1
  fi
  command -v "$OSACOMPILE" >/dev/null 2>&1 || return 1
  mkdir -p "$SCRIPT_DIR/logs" || return 1
  temp="$(mktemp -d "$SCRIPT_DIR/.ma-page-XXXXXX")" || return 1
  # Le marqueur est ajouté avant la signature locale (codesign ad hoc) pour que
  # le paquet reste cohérent ; sans codesign, l'application fonctionne aussi.
  if "$OSACOMPILE" -o "$temp/Ma page.app" \
       -e '-- Bobine : raccourci Ma page (ouvre ta page, avec Demander si active)' \
       -e 'try' \
       -e '	set dossier to do shell script "/usr/bin/dirname " & quoted form of (POSIX path of (path to me))' \
       -e '	do shell script "/bin/bash " & quoted form of (dossier & "/ouvrir-ma-page.sh") & " >/dev/null 2>&1"' \
       -e 'end try' >> "$SCRIPT_DIR/logs/raccourci.log" 2>&1 &&
     [ -d "$temp/Ma page.app/Contents/Resources" ] &&
     printf '%s\n' "$MARQUEUR_APP_TEXTE" > "$temp/Ma page.app/$MARQUEUR_APP"; then
    if command -v "$CODESIGN" >/dev/null 2>&1; then
      "$CODESIGN" --force --sign - "$temp/Ma page.app" >> "$SCRIPT_DIR/logs/raccourci.log" 2>&1 || true
    fi
    if [ ! -e "$app" ] && [ ! -L "$app" ] && mv "$temp/Ma page.app" "$app"; then
      rm -rf "$temp"
      return 0
    fi
  fi
  rm -rf "$temp"
  return 1
}

# $1 = serveur | fichier : ne sert qu'au repli .webloc (l'application, elle,
# choisit au moment du double-clic). L'ancien « Ma page.webloc » n'est retiré que
# s'il est à nous (adresse connue) ; un raccourci personnel reste en place.
installer_raccourci() {
  if creer_app_ma_page; then
    ecrire_raccourci_page retirer >/dev/null 2>&1 || true
    return 0
  fi
  ecrire_raccourci_page "$1" || note "Ton raccourci « Ma page » personnel est conservé."
}

# ------------------------------------------------------------ service de la page
# Sonde directe 127.0.0.1:8786 : ni proxy (--noproxy, -q ignore ~/.curlrc), ni LAN.
# Affiche « ok » (la page répond), « libre » (personne n'écoute) ou « occupe ».
sonde_page() {
  local sortie rc code corps
  if command -v curl >/dev/null 2>&1; then
    sortie="$(curl -q -s --noproxy '*' --max-time 1 -w '\n%{http_code}' http://127.0.0.1:8786/health 2>/dev/null)"
    rc=$?
    if [ "$rc" -eq 7 ]; then echo libre; return 0; fi
    code="${sortie##*$'\n'}"
    corps="${sortie%$'\n'*}"
    corps="${corps//[[:space:]]/}"
    if [ "$rc" -eq 0 ] && [ "$code" = 200 ] && [ "$corps" = ok ]; then echo ok; else echo occupe; fi
    return 0
  fi
  "$PY" - <<'PYTHON'
import http.client
connection = http.client.HTTPConnection("127.0.0.1", 8786, timeout=0.5)
try:
    connection.request("GET", "/health")
    response = connection.getresponse()
    print("ok" if response.status == 200 and response.read(16).strip() == b"ok" else "occupe")
except ConnectionRefusedError:
    print("libre")
except (OSError, http.client.HTTPException):
    print("occupe")
finally:
    connection.close()
PYTHON
}

port_page_libre() { [ "$(sonde_page)" = libre ]; }
page_locale_repond() { [ "$(sonde_page)" = ok ]; }

# La page est un service distinct du réveil. Propriété exacte : même étiquette et
# mêmes arguments, chaque chemin comparé à son chemin réel (comme desinstaller.sh).
page_plist_appartient() {
  [ ! -L "$1" ] && [ -n "${VAULT_EFFECTIF:-}" ] && "$PY" -B - "$1" "$SCRIPT_DIR" "$VAULT_EFFECTIF" <<'PYTHON'
import os
import plistlib
from xml.parsers.expat import ExpatError
import sys
from pathlib import Path
try:
    with open(sys.argv[1], "rb") as stream:
        data = plistlib.load(stream)
    code = Path(sys.argv[2])
    expected = [str(code / ".venv/bin/python"), str(code / "page_server.py"),
                "--vault", sys.argv[3], "--local"]
    args = data.get("ProgramArguments")
    meme = (isinstance(args, list) and len(args) == 5 and all(isinstance(a, str) for a in args)
            and args[2] == "--vault" and args[4] == "--local"
            and all(os.path.realpath(args[i]) == os.path.realpath(expected[i]) for i in (0, 1, 3)))
    valid = data.get("Label") == "com.bobine.page" and meme
except (OSError, ValueError, TypeError, AttributeError, ExpatError):
    valid = False
sys.exit(0 if valid else 1)
PYTHON
}

installer_page_locale() {
  local plist="$PAGE_PLIST"
  local service existant=non etat tentative
  service="gui/$(id -u)/com.bobine.page"
  [ -x "$SCRIPT_DIR/.venv/bin/python" ] && [ -f "$SCRIPT_DIR/page_server.py" ] &&
    [ -f "$SCRIPT_DIR/demander.py" ] || return 1
  if [ -e "$plist" ] || [ -L "$plist" ]; then
    if ! page_plist_appartient "$plist"; then
      avis "Une page Bobine existe pour un autre dossier ou a été personnalisée : elle est conservée."
      return 1
    fi
    existant=oui
  elif launchctl print "$service" >/dev/null 2>&1; then
    avis "Une page Bobine est déjà lancée sans fichier reconnu : elle est conservée."
    return 1
  fi
  if [ "$existant" = oui ]; then
    launchctl bootout "$service" 2>/dev/null || true
  fi
  if ! port_page_libre; then
    avis "Une autre application utilise déjà l'adresse de ta page (127.0.0.1:8786) : rien n'est remplacé."
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

retirer_page_locale() {  # 0 = retiré ou absent ; 1 = service d'un autre dossier conservé
  if [ -e "$PAGE_PLIST" ] || [ -L "$PAGE_PLIST" ]; then
    if page_plist_appartient "$PAGE_PLIST"; then
      launchctl bootout "gui/$(id -u)/com.bobine.page" 2>/dev/null || launchctl remove com.bobine.page 2>/dev/null || true
      rm -f "$PAGE_PLIST"
      ok "Le service de ta page est arrêté."
      return 0
    fi
    avis "Une page Bobine d'un autre dossier (ou personnalisée) existe : elle est conservée."
    return 1
  fi
  return 0
}

# Vrai si la page locale de CE dossier répond, en la (re)démarrant au besoin.
demarrer_page_locale() {
  local service tentative
  [ -f "$PAGE_PLIST" ] && page_plist_appartient "$PAGE_PLIST" || return 1
  if page_locale_repond; then return 0; fi
  service="gui/$(id -u)/com.bobine.page"
  if launchctl print "$service" >/dev/null 2>&1; then
    launchctl kickstart "$service" >/dev/null 2>&1 || true
  else
    launchctl bootstrap "gui/$(id -u)" "$PAGE_PLIST" >/dev/null 2>&1 || true
  fi
  for ((tentative=0; tentative<12; tentative++)); do
    if page_locale_repond; then return 0; fi
    sleep 0.5
  done
  return 1
}

# ------------------------------------------------------------ Demander
# Code retour : 0 = actif ; 1 = réglage écrit mais page non démarrée ; 2 = refusé.
activer_demander() {  # $1 = « page-prete » si la page vient d'être générée
  local prete=non
  ecrire_demander oui || return 2
  if [ "${1:-}" = page-prete ] && [ -n "${VAULT_EFFECTIF:-}" ]; then
    prete=oui
  elif preparer_page; then
    prete=oui
  fi
  if [ "$prete" = oui ] && installer_page_locale; then
    installer_raccourci serveur
    return 0
  fi
  if [ -n "${VAULT_EFFECTIF:-}" ]; then installer_raccourci fichier; fi
  return 1
}

# Code retour : 0 = fait ; 1 = fait, mais un service étranger est conservé ; 2 = refusé.
# Aucune donnée n'est supprimée : seul le service de CE dossier est arrêté.
desactiver_demander() {
  local rc=0
  ecrire_demander non || return 2
  VAULT_EFFECTIF="$(resoudre_vault_effectif)" || VAULT_EFFECTIF=""
  retirer_page_locale || rc=1
  if [ -n "$VAULT_EFFECTIF" ]; then installer_raccourci fichier; fi
  return "$rc"
}

annoncer_activation() {  # $1 = code retour d'activer_demander
  case "$1" in
    0)
      ok "Demander est activé. Ouvre « Ma page »."
      note "Ta page s'ouvre sur ce Mac uniquement : $ADRESSE_PAGE_LOCALE"
      if ! cle_api_configuree; then
        note "Pas encore de clé API : le chat te proposera d'en ajouter une (dans config.env)."
        note "La modification de ton profil fonctionne déjà sans clé."
      fi ;;
    1)
      avis "Demander est activé, mais ta page locale n'a pas démarré."
      note "« Ma page » ouvre ta bibliothèque, sans Demander. Pour réessayer : double-clique « Activer Demander »." ;;
    *)
      note "Demander n'a pas été modifié." ;;
  esac
}

annoncer_desactivation() {  # $1 = code retour de desactiver_demander
  case "$1" in
    0|1)
      ok "Demander est désactivé. « Ma page » ouvre ta bibliothèque, sans Demander."
      note "Aucune donnée n'a été supprimée. Pour le réactiver : double-clique « Activer Demander »." ;;
    *)
      note "Demander n'a pas été modifié." ;;
  esac
}
