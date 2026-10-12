#!/bin/bash
# shellcheck shell=bash
# Bobine (Linux) : fonctions partagées de la page et du réglage « Demander ».
#
# Ce fichier n'est pas lancé directement : il est chargé (source) par
# install-linux.sh, activer-demander.sh, desactiver-demander.sh et
# ouvrir-ma-page.sh, pour que la logique du service de page n'existe qu'une fois.
#
# Variables attendues chez l'appelant :
#   SCRIPT_DIR : le dossier Bobine (code, config.env, .venv) ;
#   PY         : un Python 3 (choisir_python le trouve si besoin).
# Détails techniques (jamais montrés tels quels à l'utilisateur) : le service est
# une unité systemd --user « bobine-page.service », au même format que celle
# d'activer-page-web.sh (127.0.0.1:8786, mot de passe PAGE_PASSWORD lu dans
# config.env, jamais passé en argument). Celle créée ici porte le marqueur
# « # Créé par activer-demander.sh ». desinstaller-linux.sh reconnaît les deux.
# config.env n'est jamais exécuté (ni source, ni eval) : il est lu comme du texte.
# shellcheck disable=SC2154  # SCRIPT_DIR et PY viennent de l'appelant

# Messages : ceux de l'appelant s'ils existent déjà (couleurs d'install-linux.sh).
declare -F ok >/dev/null 2>&1 || ok() { printf '  ✓ %s\n' "$1"; }
declare -F note >/dev/null 2>&1 || note() { printf '  %s\n' "$1"; }
declare -F avis >/dev/null 2>&1 || avis() { printf '  ⚠  %s\n' "$1"; }

ADRESSE_PAGE_LOCALE="http://127.0.0.1:8786/"
UNITES_UTILISATEUR="$HOME/.config/systemd/user"
UNITE_PAGE="$UNITES_UTILISATEUR/bobine-page.service"
UNITE_TUNNEL="$UNITES_UTILISATEUR/bobine-tunnel.service"
MARQUEUR_UNITE="# Créé par activer-demander.sh"

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
# Python du dossier (.venv) si présent, sinon celui du système.
preparer_page() {
  local python_page="$PY"
  if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then python_page="$SCRIPT_DIR/.venv/bin/python"; fi
  VAULT_EFFECTIF="$(resoudre_vault_effectif)" || {
    VAULT_EFFECTIF=""
    avis "VAULT illisible ou ambigu dans config.env : la page et son service sont conservés."
    return 1
  }
  mkdir -p "$SCRIPT_DIR/logs" || return 1
  if "$python_page" "$SCRIPT_DIR/generate_page.py" --vault "$VAULT_EFFECTIF" > "$SCRIPT_DIR/logs/page-generation.log" 2>&1; then
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

port_page_libre() { [ "$(sonde_page)" = libre ]; }
page_locale_repond() { [ "$(sonde_page)" = ok ]; }

systemd_disponible() {
  command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1
}

# Même reconnaissance que desinstaller-linux.sh : arguments complets après
# décodage systemd, chemins comparés à leur chemin réel ; lien, surcharge ou
# format ambigu = pas à nous (conservé).
unite_page_appartient() {  # $1 = fichier unité
  [ -n "${PY:-}" ] && "$PY" -B - "$1" "$SCRIPT_DIR" "$HOME" <<'PYTHON'
import os
import re
import sys
from pathlib import Path
unit, vault, home = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
reel = os.path.realpath(str(vault))

def meme(arg, attendu):
    return os.path.realpath(arg) == os.path.realpath(str(attendu))

def arguments(text):
    # Sous-ensemble non ambigu : mots nus ou entièrement entre guillemets,
    # \\ et \" émis par activer-page-web.sh. Pas d'expansion shell/variable.
    words, i = [], 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        quote = text[i] if text[i] in "\"'" else None
        if quote:
            i += 1
        word = ""
        closed = not quote
        while i < len(text):
            c = text[i]
            if quote and c == quote:
                i += 1
                closed = True
                if i < len(text) and not text[i].isspace():
                    raise ValueError("guillemets ambigus")
                break
            if not quote and c.isspace():
                break
            if c == "\\":
                i += 1
                if i >= len(text) or text[i] not in ('\\', '"'):
                    raise ValueError("échappement inconnu")
                c = text[i]
            elif c in "\"'" and not quote:
                raise ValueError("guillemets dans un mot")
            word += c
            i += 1
        if not closed:
            raise ValueError("guillemets non fermés")
        # Une seule passe : %%h est un %h littéral, jamais le HOME.
        def expand(match):
            token = match.group()
            if token == "%%":
                return "%"
            if token == "$$":
                return "$"
            if token == "%h":
                return str(home)
            raise ValueError("expansion non reconnue")
        words.append(re.sub(r"%%|\$\$|%h|[%$]", expand, word))
    return words

try:
    if unit.is_symlink() or not unit.is_file() or unit.with_name(unit.name + ".d").exists():
        raise ValueError("unité non ordinaire ou surchargée")
    commands = []
    section = None
    for line in unit.read_text().splitlines():
        line = line.strip()
        if line.startswith(("#", ";")) or not line:
            continue
        if line.startswith("["):
            section = line
        elif line.startswith("ExecStart="):
            if section != "[Service]":
                raise ValueError("commande hors service")
            commands.append(line.split("=", 1)[1].strip())
    if len(commands) != 1:
        raise ValueError("commande ambiguë")
    args = arguments(commands[0])
    valid = (bool(args) and Path(args[0]).is_absolute() and
             re.fullmatch(r"python(?:3(?:\.\d+)*)?", Path(args[0]).name) is not None and
             len(args) == 4 and meme(args[1], vault / "page_server.py") and args[2] == "--vault"
             and meme(args[3], vault) and os.path.realpath(args[3]) == reel)
except (OSError, ValueError, IndexError, TypeError):
    valid = False
sys.exit(0 if valid else 1)
PYTHON
}

unite_page_marquee() { grep -qxF "$MARQUEUR_UNITE" "$UNITE_PAGE" 2>/dev/null; }

page_active() { systemctl --user is-active --quiet bobine-page.service 2>/dev/null; }

attendre_page() {  # vrai si le service tourne et que la page répond (quelques secondes au plus)
  local tentative
  for ((tentative=0; tentative<10; tentative++)); do
    if page_active && page_locale_repond; then return 0; fi
    sleep 0.5
  done
  return 1
}

# Unité au même format qu'activer-page-web.sh : arguments distincts et échappés
# pour systemd (espaces, %, $ compris), écriture atomique, jamais via un lien.
ecrire_unite_page() {  # $1 = dossier réel, $2 = Python absolu
  "$PY" -B - "$UNITE_PAGE" "$1" "$2" "$MARQUEUR_UNITE" <<'PYTHON'
import os
import sys
import tempfile
from pathlib import Path
unit, vault, python, marqueur = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
def arg(value):
    value = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    return '"' + value + '"'
try:
    if unit.is_symlink() or unit.exists():
        raise ValueError("unité déjà présente")
    unit.parent.mkdir(parents=True, exist_ok=True)
    page_args = [python, vault / "page_server.py", "--vault", vault]
    texte = ("[Unit]\nDescription=Bobine : page locale avec mot de passe (Demander)\n" + marqueur + "\n\n"
             "[Service]\nType=simple\nExecStart=" + " ".join(map(arg, page_args)) +
             "\nRestart=on-failure\nNoNewPrivileges=true\n\n[Install]\nWantedBy=default.target\n")
    fd, temp = tempfile.mkstemp(prefix=".bobine-page-", dir=unit.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(texte)
        os.replace(temp, unit)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
except (OSError, ValueError):
    sys.exit(1)
PYTHON
}

# 0 = la page tourne ; 1 = rien de démarré (message déjà affiché).
installer_service_page() {
  local reel python_page cree=non
  reel="$(cd "$SCRIPT_DIR" && pwd -P)" || return 1
  if [ ! -f "$reel/page_server.py" ]; then
    avis "page_server.py est introuvable dans ce dossier : relance l'installation de Bobine."
    return 1
  fi
  if ! systemd_disponible; then
    avis "Ce serveur ne permet pas de lancer ta page en arrière-plan : rien n'a été installé."
    note "Tu peux la lancer à la main :  cd $(printf '%q' "$reel") && python3 page_server.py --vault ."
    ecrire_demander oui mot-de-passe >/dev/null || true
    return 1
  fi
  if [ -e "$UNITE_PAGE" ] || [ -L "$UNITE_PAGE" ]; then
    if ! unite_page_appartient "$UNITE_PAGE"; then
      avis "Une page Bobine existe pour un autre dossier ou a été personnalisée : elle est conservée."
      return 1
    fi
    ecrire_demander oui mot-de-passe || return 1
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart bobine-page.service 2>/dev/null || true
  else
    if [ "$(systemctl --user show -p LoadState --value bobine-page.service 2>/dev/null)" = loaded ]; then
      avis "Une page Bobine est déjà installée ailleurs sur ce serveur : elle est conservée."
      return 1
    fi
    if [ -e "$UNITE_TUNNEL" ] || [ -L "$UNITE_TUNNEL" ]; then
      avis "Un accès web Bobine existe déjà sans page reconnue : rien n'est installé."
      return 1
    fi
    if ! port_page_libre; then
      avis "Une autre application utilise déjà l'adresse de ta page (127.0.0.1:8786) : rien n'est remplacé."
      return 1
    fi
    python_page="$reel/.venv/bin/python"
    if [ ! -x "$python_page" ]; then python_page="$(command -v python3 || true)"; fi
    case "$python_page" in
      /*) ;;
      *) avis "Python est introuvable : relance l'installation de Bobine."; return 1 ;;
    esac
    ecrire_demander oui mot-de-passe || return 1
    if ! ecrire_unite_page "$reel" "$python_page"; then
      avis "Le service de ta page n'a pas pu être écrit : rien n'est installé."
      return 1
    fi
    cree=oui
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable --now bobine-page.service 2>/dev/null || true
  fi
  if attendre_page; then return 0; fi
  # Un service qui ne démarre pas n'est pas laissé en boucle.
  if [ "$cree" = oui ]; then
    systemctl --user disable --now bobine-page.service 2>/dev/null || true
    rm -f "$UNITE_PAGE"
    systemctl --user daemon-reload 2>/dev/null || true
  fi
  avis "Ta page n'a pas démarré. Pour comprendre :  journalctl --user -u bobine-page -n 20"
  return 1
}

annoncer_adresse() {
  local origine
  origine="$(lire_reglage PAGE_ORIGIN 2>/dev/null)" || origine=""
  if [ -n "$origine" ]; then
    note "Ta page : $origine"
  else
    note "Sur ce serveur : $ADRESSE_PAGE_LOCALE"
    note "Depuis ton ordinateur :  ssh -L 8786:127.0.0.1:8786 $(id -un 2>/dev/null || echo toi)@ton-serveur"
    note "puis ouvre $ADRESSE_PAGE_LOCALE dans ton navigateur."
  fi
  note "Mot de passe : dans $SCRIPT_DIR/config.env, ligne PAGE_PASSWORD."
}

# ------------------------------------------------------------ Demander
# Code retour : 0 = actif ; 1 = réglage écrit mais page non démarrée ; 2 = refusé.
activer_demander() {  # $1 = « page-prete » si la page vient d'être générée
  NOUVEAU_MOT_DE_PASSE=""
  ecrire_demander oui || return 2
  if [ "${1:-}" != page-prete ]; then
    preparer_page || note "La page précédente reste disponible si elle existe."
  fi
  installer_service_page
}

# Code retour : 0 = fait ; 1 = fait, mais une page étrangère est conservée ; 2 = refusé.
# Aucune donnée n'est supprimée. Unité créée par activer-demander.sh et sans tunnel :
# arrêtée et retirée. Page web publique (activer-page-web.sh) : redémarrée, elle
# reste lisible, sans chat ni profil modifiable.
desactiver_demander() {
  ecrire_demander non || return 2
  VAULT_EFFECTIF="$(resoudre_vault_effectif)" || VAULT_EFFECTIF=""
  if [ -e "$UNITE_PAGE" ] || [ -L "$UNITE_PAGE" ]; then
    if ! unite_page_appartient "$UNITE_PAGE"; then
      avis "Une page Bobine d'un autre dossier (ou personnalisée) existe : elle est conservée."
      return 1
    fi
    if unite_page_marquee && [ ! -e "$UNITE_TUNNEL" ] && [ ! -L "$UNITE_TUNNEL" ]; then
      systemctl --user disable --now bobine-page.service 2>/dev/null || true
      rm -f "$UNITE_PAGE"
      systemctl --user daemon-reload 2>/dev/null || true
      ok "Le service de ta page est arrêté."
    else
      systemctl --user restart bobine-page.service 2>/dev/null || true
      ok "Ta page web reste en ligne, sans chat ni profil modifiable."
    fi
  fi
  return 0
}

annoncer_activation() {  # $1 = code retour d'activer_demander
  case "$1" in
    0)
      ok "Demander est activé."
      annoncer_adresse
      if [ -n "${NOUVEAU_MOT_DE_PASSE:-}" ]; then
        note "Un mot de passe vient d'être créé pour ta page (config.env, ligne PAGE_PASSWORD)."
      fi
      if ! cle_api_configuree; then
        note "Pas encore de clé API : le chat te proposera d'en ajouter une (dans config.env)."
        note "La modification de ton profil fonctionne déjà sans clé."
      fi ;;
    1)
      avis "Demander est activé, mais ta page n'a pas démarré."
      note "Ta bibliothèque reste lisible : $(page_fichier)"
      note "Pour réessayer :  ./activer-demander.sh" ;;
    *)
      note "Demander n'a pas été modifié." ;;
  esac
}

annoncer_desactivation() {  # $1 = code retour de desactiver_demander
  case "$1" in
    0|1)
      ok "Demander est désactivé. Aucune donnée n'a été supprimée."
      note "Ta page lisible sans Demander : $(page_fichier)"
      note "Pour le réactiver :  ./activer-demander.sh" ;;
    *)
      note "Demander n'a pas été modifié." ;;
  esac
}
