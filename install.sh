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

# ------------------------------------- dépendances et réveils (même code Mac et Linux)
# Ce bloc est identique, octet pour octet, dans install.sh et linux/install-linux.sh
# (vérifié par tests/test_installation.py). Les détails techniques vont dans
# logs/install.log ; les messages affichés restent simples.

# Installe requirements.txt dans .venv. L'appelant redirige tout vers
# logs/install.log. Méthode, dans cet ordre :
#   a) .venv/bin/pip (cas habituel) ;
#   b) .venv/bin/python -m pip (pip présent sans son raccourci) ;
#   c) uv pip, si uv est installé (un environnement créé par uv n'a pas de pip) ;
#   d) python -m ensurepip pour ajouter pip, puis b).
# ensurepip n'a pas d'option -q : sa sortie va simplement dans le journal.
# La méthode retenue est notée en tête du journal.
installer_dependances() {
  local py=.venv/bin/python rc
  if [ -x .venv/bin/pip ]; then
    echo "Bobine : installation avec .venv/bin/pip"
    .venv/bin/pip install --upgrade pip -q &&
      .venv/bin/pip install -q -r requirements.txt
  elif "$py" -m pip --version >/dev/null 2>&1; then
    echo "Bobine : installation avec .venv/bin/python -m pip"
    "$py" -m pip install --upgrade pip -q &&
      "$py" -m pip install -q -r requirements.txt
  elif command -v uv >/dev/null 2>&1; then
    echo "Bobine : pas de pip dans .venv, installation avec uv pip ($(command -v uv))"
    uv pip install --python "$py" -q -r requirements.txt
  else
    echo "Bobine : ni pip ni uv, ajout de pip avec python -m ensurepip puis python -m pip"
    "$py" -m ensurepip --upgrade &&
      "$py" -m pip install --upgrade pip -q &&
      "$py" -m pip install -q -r requirements.txt
  fi
  rc=$?
  if [ "$rc" -ne 0 ]; then echo "Bobine : échec de l'installation des dépendances (code $rc)"; fi
  return "$rc"
}

# Lecture des réveils, en Python (bibliothèque standard seulement). Un réveil est
# un fichier .plist sur Mac (clés ProgramArguments et Label) ou une unité
# .service sous Linux (lignes ExecStart). Un lien symbolique ou un fichier
# illisible n'est jamais reconnu comme relevant ce dossier.
#   lire_reveils examiner FICHIER SCRIPT
#     code 0 si FICHIER lance SCRIPT (même chemin réel), 1 sinon ; dans ce cas,
#     affiche le dossier relevé quand il se lit.
#   lire_reveils anciens DOSSIER SCRIPT EXCLU...
#     liste « fichier<tabulation>nom » des réveils de DOSSIER (même extension que
#     le premier EXCLU, sans les EXCLUS) qui lancent SCRIPT ; nom = Label sur Mac,
#     nom de l'unité sans .service sous Linux.
#   lire_reveils declenche FICHIER UNITE
#     code 0 si le .timer ou le .path FICHIER (fichier ordinaire) déclenche UNITE.
lire_reveils() {
  "${PY:-python3}" - "$@" <<'PYTHON'
import os
import plistlib
import re
import shlex
import sys


def ordinaire(fichier):
    return not os.path.islink(fichier) and os.path.isfile(fichier)


def lire(fichier):
    """(mots, commandes, nom) d'un réveil, ou None s'il est illisible."""
    if not ordinaire(fichier):
        return None
    try:
        if fichier.endswith(".plist"):
            with open(fichier, "rb") as f:
                donnees = plistlib.load(f)
            mots = donnees.get("ProgramArguments") if isinstance(donnees, dict) else None
            if not isinstance(mots, list) or not all(isinstance(m, str) for m in mots):
                return None
            nom = donnees.get("Label")
            return mots, [], nom if isinstance(nom, str) else ""
        home = os.path.expanduser("~")
        mots, commandes = [], []
        with open(fichier, encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne.startswith("ExecStart="):
                    continue
                commande = re.sub(r"%%|%h", lambda m: "%" if m.group() == "%%" else home,
                                  ligne.split("=", 1)[1].strip())
                try:
                    morceaux = shlex.split(commande)
                except ValueError:
                    morceaux = commande.split()
                if morceaux:
                    morceaux[0] = morceaux[0].lstrip("-@:+!|")
                mots += morceaux
                commandes.append(commande)
        return mots, commandes, os.path.basename(fichier).rsplit(".", 1)[0]
    except Exception:
        return None


def lance(lu, script):
    """Le réveil lu lance-t-il script ? Chemin réel identique, ou chemin cité
    tel quel dans une commande (entre espaces ou guillemets : un chemin avec
    des espaces écrit sans guillemets reste reconnu, sans confondre
    /x/Bobine et /x/Bobine-autre)."""
    mots, commandes = lu[0], lu[1]
    reel = os.path.realpath(script)
    if any(os.path.isabs(m) and os.path.realpath(m) == reel for m in mots):
        return True
    for commande in commandes:
        for chemin in {os.path.abspath(script), reel}:
            debut = commande.find(chemin)
            while debut >= 0:
                fin = debut + len(chemin)
                if ((debut == 0 or commande[debut - 1] in " \t\"'")
                        and (fin == len(commande) or commande[fin] in " \t\"';")):
                    return True
                debut = commande.find(chemin, debut + 1)
    return False


mode = sys.argv[1]
if mode == "examiner":
    fichier, script = sys.argv[2], sys.argv[3]
    lu = lire(fichier)
    if lu and lance(lu, script):
        sys.exit(0)
    if lu:
        for mot in lu[0]:
            if os.path.isabs(mot) and os.path.basename(mot) == os.path.basename(script):
                print(os.path.dirname(mot))
                break
    sys.exit(1)
elif mode == "anciens":
    dossier, script, exclus = sys.argv[2], sys.argv[3], sys.argv[4:]
    extension = os.path.splitext(exclus[0])[1]
    try:
        noms = sorted(os.listdir(dossier))
    except OSError:
        noms = []
    for nom in noms:
        if not nom.endswith(extension) or nom in exclus or "\t" in nom or "\n" in nom:
            continue
        fichier = os.path.join(dossier, nom)
        lu = lire(fichier)
        if lu and lu[2] and "\t" not in lu[2] and "\n" not in lu[2] and lance(lu, script):
            print(fichier + "\t" + lu[2])
elif mode == "declenche":
    fichier, unite = sys.argv[2], sys.argv[3]
    if not ordinaire(fichier):
        sys.exit(1)
    try:
        with open(fichier, encoding="utf-8") as f:
            lignes = [ligne.strip() for ligne in f]
    except Exception:
        sys.exit(1)
    cibles = [ligne.split("=", 1)[1].strip() for ligne in lignes if ligne.startswith("Unit=")]
    defaut = os.path.basename(fichier).rsplit(".", 1)[0] + ".service"
    sys.exit(0 if set(cibles or [defaut]) == {unite} else 1)
else:
    sys.exit(2)
PYTHON
}

# Avant d'écrire le réveil de Bobine : s'il existe déjà et relève un AUTRE dossier
# (ou s'il ne se lit pas, ou si c'est un lien symbolique), on demande avant de le
# remplacer. Le même dossier : remplacement sans question.
# Code 0 : on peut écrire le réveil ; 1 : on n'y touche pas.
reveil_libre() {  # $1 = fichier du réveil de Bobine, $2 = script relevé par ce dossier
  local autre
  if [ ! -e "$1" ] && [ ! -L "$1" ]; then return 0; fi
  if autre="$(lire_reveils examiner "$1" "$2" 2>/dev/null)"; then return 0; fi
  if [ -z "$autre" ]; then autre="dossier inconnu"; else autre="$(affiche "$autre")"; fi
  avis "Un réveil existe déjà pour un autre dossier Bobine ($autre)."
  if confirmer "Le remplacer par celui de ce dossier ?" "n"; then
    return 0
  fi
  note "D'accord, on n'y touche pas : ce dossier n'aura pas de réveil automatique."
  note "Tu pourras relancer l'installation plus tard pour changer d'avis."
  return 1
}

# Le dossier de sauvegarde de ce passage : celui de la mise à jour s'il est déjà
# choisi, sinon un nouveau (horodaté, rendu unique au besoin). Jamais supprimé.
dossier_anciens_reveils() {
  local horodatage n=1
  if [ -z "${SAUVEGARDE:-}" ]; then
    horodatage="$(date '+%Y%m%d-%H%M')"
    SAUVEGARDE="$SCRIPT_DIR/.bobine-sauvegarde-$horodatage"
    while [ -e "$SAUVEGARDE" ] || [ -L "$SAUVEGARDE" ]; do
      n=$((n + 1)); SAUVEGARDE="$SCRIPT_DIR/.bobine-sauvegarde-$horodatage-$n"
    done
  fi
  mkdir -p "$SAUVEGARDE/anciens-reveils" 2>/dev/null
}

ranger_fichier_reveil() {  # $1 = fichier mis de côté dans anciens-reveils/ (jamais écrasé)
  local destination="$SAUVEGARDE/anciens-reveils/${1##*/}"
  [ ! -e "$destination" ] && [ ! -L "$destination" ] && mv "$1" "$destination"
}

# Anciens réveils d'un autre nom qui relèvent CE dossier (d'anciennes installations
# en ont un, par exemple com.wahid.vaultwatch) : avec celui de Bobine, ce dossier
# serait relevé deux fois. Pour chacun, on propose de le remplacer ; son fichier
# est rangé dans le dossier de sauvegarde (retirer_ancien_reveil, propre à chaque
# édition). Un réveil qui relève un autre dossier n'est jamais touché.
ranger_anciens_reveils() {  # $1 = dossier des réveils, $2 = script de ce dossier, $3... = réveils de Bobine
  local liste fichier nom
  liste="$(lire_reveils anciens "$@" 2>/dev/null)" || liste=""
  [ -n "$liste" ] || return 0
  # Lecture sur le descripteur 3 : les réponses, elles, viennent du clavier.
  while IFS=$'\t' read -r fichier nom <&3; do
    [ -n "$fichier" ] || continue
    avis "Un ancien réveil ($nom) relève déjà ce dossier."
    if confirmer "Le remplacer par celui de Bobine ?" "o"; then
      retirer_ancien_reveil "$fichier" "$nom"
    else
      note "D'accord, il est gardé : deux réveils relèveront ce dossier."
    fi
  done 3<<<"$liste"
}
# ---------------------------------------------- fin du code commun Mac et Linux

# Mac : arrêter un ancien réveil (par son étiquette, lue dans le fichier) puis
# ranger son fichier dans le dossier de sauvegarde.
retirer_ancien_reveil() {  # $1 = fichier .plist, $2 = son étiquette (Label)
  launchctl bootout "gui/$(id -u)/$2" 2>/dev/null || true
  if dossier_anciens_reveils && ranger_fichier_reveil "$1"; then
    ok "Ancien réveil ($2) arrêté, gardé dans ${SAUVEGARDE##*/}/anciens-reveils/"
  else
    avis "L'ancien réveil ($2) est arrêté, mais son fichier n'a pas pu être rangé : il reviendra au prochain redémarrage."
  fi
}

# Page locale, raccourci « Ma page » et réglage « Demander » : logique partagée
# avec activer-demander.sh, desactiver-demander.sh et ouvrir-ma-page.sh.
if [ ! -f "$DEPOT/page-locale.sh" ]; then
  avis "Il manque le fichier page-locale.sh : télécharge à nouveau Bobine."
  exit 1
fi
# shellcheck source=page-locale.sh
. "$DEPOT/page-locale.sh"

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
    if [ -f "$CIBLE/config.env" ] || [ -d "$CIBLE/.venv" ]; then
      # Un Bobine déjà installé ailleurs : on propose de le mettre à jour.
      # Seuls les fichiers programme changent ; fiches, réglages et pages restent intacts.
      if confirmer "Ce dossier contient déjà un Bobine. Le mettre à jour en gardant tes fiches et tes réglages ?" "o"; then
        GARDE="maj"
        break
      fi
      note "D'accord, on n'y touche pas."
      REP="$(question "Emplacement de ton vault" "$(affiche "$DEFAUT_CIBLE")")"
      CIBLE=""; continue
    fi
    avis "Ce dossier contient déjà des fichiers. Choisis un dossier vide pour les protéger."
    REP="$(question "Emplacement de ton vault" "$(affiche "$DEFAUT_CIBLE")")"
    CIBLE=""; continue
  fi
done

# Copie d'un fichier programme du dépôt vers le vault. Installation neuve : copie
# simple. Mise à jour : un fichier identique est laissé tel quel, un fichier
# différent est d'abord mis de côté dans le dossier de sauvegarde, un lien
# symbolique ou un dossier du même nom n'est jamais écrasé.
SAUVEGARDE=""; REMPLACES=0; AJOUTES=0; SAUVES=0
identiques() {  # $1 et $2 ont-ils exactement le même contenu ?
  if command -v cmp >/dev/null 2>&1; then cmp -s "$1" "$2"; return; fi
  "${PY:-python3}" -c 'import sys; sys.exit(open(sys.argv[1], "rb").read() != open(sys.argv[2], "rb").read())' "$1" "$2" 2>/dev/null
}
installer_fichier() {  # $1 = chemin relatif au dépôt
  local source="$DEPOT/$1" destination="$CIBLE/$1"
  [ -f "$source" ] || return 0
  if [ "$GARDE" = "maj" ]; then
    if [ -L "$destination" ]; then
      avis "« $1 » est un lien symbolique chez toi : gardé tel quel, pas mis à jour."
      return 0
    fi
    if [ -d "$destination" ]; then
      avis "« $1 » est un dossier chez toi : gardé tel quel, pas mis à jour."
      return 0
    fi
    if [ -f "$destination" ]; then
      if identiques "$source" "$destination"; then return 0; fi
      if ! mkdir -p "$(dirname "$SAUVEGARDE/$1")" || ! cp -p "$destination" "$SAUVEGARDE/$1"; then
        avis "Impossible de sauvegarder « $1 » : il est gardé tel quel, pas mis à jour."
        return 0
      fi
      SAUVES=$((SAUVES + 1))
      if cp "$source" "$destination"; then REMPLACES=$((REMPLACES + 1)); fi
    else
      mkdir -p "$(dirname "$destination")" 2>/dev/null
      if cp "$source" "$destination"; then AJOUTES=$((AJOUTES + 1)); fi
    fi
  else
    mkdir -p "$(dirname "$destination")" 2>/dev/null
    cp "$source" "$destination"
  fi
  if [ -x "$source" ]; then chmod +x "$destination" 2>/dev/null || true; fi
}

if [ "$GARDE" = "reinstall" ]; then
  ok "Réinstallation dans ton dossier Bobine : $(affiche "$CIBLE")"
elif [ "$GARDE" = "oui" ]; then
  ok "D'accord — ce dossier devient ton dossier Bobine (il ne sera pas supprimé)."
else
  if [ "$GARDE" = "maj" ]; then
    # Un dossier de sauvegarde par mise à jour, horodaté ; un suffixe le rend unique
    # si deux mises à jour tombent dans la même minute.
    HORODATAGE="$(date '+%Y%m%d-%H%M')"
    SAUVEGARDE="$CIBLE/.bobine-sauvegarde-$HORODATAGE"
    n=1
    while [ -e "$SAUVEGARDE" ] || [ -L "$SAUVEGARDE" ]; do
      n=$((n + 1)); SAUVEGARDE="$CIBLE/.bobine-sauvegarde-$HORODATAGE-$n"
    done
    # Le nom du vault : si tu as gardé la proposition, on reprend celui de ta configuration.
    ANCIEN_NOM="$(grep -m1 '^NOM=' "$CIBLE/config.env" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)"
    if [ -n "${ANCIEN_NOM:-}" ] && [ "$NOM_VAULT" = "${NOM_DEFAUT:-$NOM_VAULT}" ] && [ "$ANCIEN_NOM" != "$NOM_VAULT" ]; then
      NOM_VAULT="$ANCIEN_NOM"
      ok "Nom repris de ta configuration : $NOM_VAULT"
    fi
  fi
  for f in ingest.py enrichir.py generate_page.py graphe.py filtre.py page_server.py demander.py watch.sh install.sh \
           desinstaller.sh page-locale.sh activer-demander.sh desactiver-demander.sh ouvrir-ma-page.sh \
           requirements.txt config.example.env filtres.exemple.yaml \
           LICENSE; do
    installer_fichier "$f"
  done
  if [ -d "$DEPOT/exemples" ]; then
    while IFS= read -r chemin; do
      installer_fichier "${chemin#"$DEPOT"/}"
    done < <(find "$DEPOT/exemples" -type f 2>/dev/null)
  fi
  installer_fichier "👉 2. Installer Bobine.command"
  # .gitignore : fourni à l'installation ; un .gitignore déjà présent est à toi, on n'y touche pas.
  if [ -f "$DEPOT/.gitignore" ] && [ ! -e "$CIBLE/.gitignore" ] && [ ! -L "$CIBLE/.gitignore" ]; then
    cp "$DEPOT/.gitignore" "$CIBLE/.gitignore"
  fi
  if [ "$GARDE" = "maj" ]; then
    if [ "$REMPLACES" -eq 0 ] && [ "$AJOUTES" -eq 0 ]; then
      ok "Ton dossier Bobine est déjà à jour : $(affiche "$CIBLE")"
    else
      BILAN=""
      if [ "$REMPLACES" -eq 1 ]; then BILAN="1 fichier remplacé"; fi
      if [ "$REMPLACES" -gt 1 ]; then BILAN="$REMPLACES fichiers remplacés"; fi
      if [ "$AJOUTES" -eq 1 ]; then BILAN="${BILAN:+$BILAN, }1 fichier ajouté"; fi
      if [ "$AJOUTES" -gt 1 ]; then BILAN="${BILAN:+$BILAN, }$AJOUTES fichiers ajoutés"; fi
      if [ "$SAUVES" -gt 0 ]; then
        BILAN="$BILAN, anciens fichiers gardés dans ${SAUVEGARDE##*/}/"
      fi
      ok "Mise à jour de ton dossier Bobine : $BILAN"
    fi
    note "Tes fiches, tes réglages et tes pages n'ont pas bougé."
  else
    ok "Fichiers installés dans : $(affiche "$CIBLE")"
  fi
fi
cd "$CIBLE" || exit 1
SCRIPT_DIR="$(pwd)"
chmod 755 activer-demander.sh desactiver-demander.sh ouvrir-ma-page.sh 2>/dev/null || true

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
# Double-clic pour activer ou désactiver Demander, à tout moment. Créés ici, comme
# le précédent ; un fichier déjà présent (personnalisé ou lien) n'est jamais écrasé.
for commande in "Activer Demander:activer-demander.sh" "Désactiver Demander:desactiver-demander.sh"; do
  fichier="${commande%%:*}.command"
  if [ ! -e "$fichier" ] && [ ! -L "$fichier" ]; then
    printf '#!/bin/bash\ncd "$(dirname "$0")" || exit 1\nexec bash ./%s\n' "${commande#*:}" > "$fichier"
    chmod +x "$fichier"
  fi
done

# Un petit README pour le vault — le guide complet reste sur la page du projet.
if [ ! -f "README.md" ]; then
  cat > "README.md" <<EOF
# 🎞️ $NOM_VAULT

Ton vault, chez toi : chaque vidéo partagée depuis ton iPhone devient une fiche
ici — téléchargée, transcrite et résumée automatiquement.

## Au quotidien

- **Partager** : Instagram, TikTok ou YouTube → Partager → le raccourci « Send to Bobine ».
- **La page** : double-clique « Ma page » (recherche, pastilles de thèmes, fiches).
- **Demander** : double-clique « Activer Demander » ou « Désactiver Demander » (questions à l'IA depuis ta page).
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

# Raccourci « Ma page » dès maintenant : il ouvre la page fichier tant que
# Demander n'est pas activé. Un raccourci personnel n'est jamais remplacé.
installer_raccourci fichier

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
    GARDES="$(grep -E '^(VAULT|INBOX|FFMPEG_DIR|COOKIES|LANGUE_RESUMES|NOTIF_CMD|INBOX_TOKEN|PAGE_PASSWORD|PAGE_ORIGIN|DEMANDER)=' "$ANCIENNE_CONFIG" 2>/dev/null || true)"
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
# Bobine n'en fait tourner qu'un à la fois : celui d'un autre dossier n'est
# remplacé qu'avec ton accord (reveil_libre). Les anciens réveils d'un autre nom
# qui relèvent CE dossier sont proposés au remplacement (ranger_anciens_reveils).
PLIST="$HOME/Library/LaunchAgents/com.bobine.watch.plist"
if [ "$REVEIL" = "oui" ] && ! reveil_libre "$PLIST" "$SCRIPT_DIR/watch.sh"; then
  REVEIL="non"
elif [ "$REVEIL" = "oui" ]; then
  ranger_anciens_reveils "$HOME/Library/LaunchAgents" "$SCRIPT_DIR/watch.sh" \
    com.bobine.watch.plist com.bobine.page.plist
  mkdir -p "$HOME/Library/LaunchAgents"
  # Un lien symbolique est remplacé par un vrai fichier : sa cible n'est jamais réécrite.
  if [ -L "$PLIST" ]; then rm -f "$PLIST"; fi
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
  # En arrière-plan, pour afficher l'attente ; méthode et détails : logs/install.log.
  ( installer_dependances ) > logs/install.log 2>&1 &
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

# ---------------------------------------------------------------- génération locale
PAGE_PRETE="non"
if preparer_page; then
  PAGE_PRETE="oui"
else
  note "La page précédente reste disponible si elle existe."
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

# ---------------------------------------------------------------- 8. Demander
# Dernière question : rien n'est imposé. Le défaut reprend l'ancien choix.
etape "Pour finir : Demander"
note "Demander : pose des questions à l'IA sur tes vidéos et modifie ton profil, depuis ta page."
note "Tu pourras changer d'avis à tout moment (double-clic sur « Activer Demander » ou « Désactiver Demander »)."
DEFAUT_DEMANDER="o"
DEMANDER_ACTIF="non"
if [ "$(lire_demander)" = non ]; then DEFAUT_DEMANDER="n"; fi
if confirmer "Activer Demander (poser des questions à l'IA depuis ta page) ?" "$DEFAUT_DEMANDER"; then
  if [ "${PAGE_PRETE:-non}" = oui ]; then activer_demander page-prete; else activer_demander; fi
  rc_demander=$?
  annoncer_activation "$rc_demander"
  if [ "$rc_demander" -eq 0 ]; then DEMANDER_ACTIF="oui"; fi
  case "$rc_demander" in
    0) DEMANDER_ETAT="oui" ;;
    1) DEMANDER_ETAT="oui (ta page locale n'a pas démarré : double-clique « Activer Demander » pour réessayer)" ;;
    *) DEMANDER_ETAT="non modifié (config.env n'a pas pu être mis à jour)" ;;
  esac
else
  desactiver_demander
  rc_demander=$?
  if [ "$rc_demander" -eq 2 ]; then
    DEMANDER_ETAT="non modifié (config.env n'a pas pu être mis à jour)"
  else
    DEMANDER_ETAT="non"
    ok "D'accord : Demander n'est pas activé. « Ma page » ouvre ta bibliothèque."
    note "Pour l'activer plus tard : double-clique « Activer Demander » dans ton dossier Bobine."
  fi
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
printf "   Demander        : %s\n" "$DEMANDER_ETAT"
echo
printf "   ${GRAS}Et maintenant ?${FIN}\n"
printf "   1. Crée le raccourci iPhone « Send to Bobine » — recette pas-à-pas sur la page du projet\n"
printf "   2. Partage une vidéo de test, puis surveille :  %s/logs/watch.log\n" "$SCRIPT_DIR"
if [ "${DEMANDER_ACTIF:-non}" = oui ]; then
  printf "   3. Ta page : double-clique « Ma page » (http://127.0.0.1:8786/, ce Mac uniquement)\n"
else
  printf "   3. Ta page : double-clique « Ma page » (%s/vault.html)\n" "${VAULT_EFFECTIF:-$SCRIPT_DIR}"
fi
printf "   4. Un jour, pour arrêter Bobine sans supprimer tes fichiers :  ./desinstaller.sh  (dans le dossier de ton vault)\n"
if [ "$SYNC" = "oui" ]; then
  printf "      (sur l'iPhone : Fichiers → iCloud Drive → %s → vault.html)\n" "$NOM_VAULT"
fi
if [ -z "$GARDE" ] || [ "$GARDE" = "maj" ]; then
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
