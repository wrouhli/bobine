#!/bin/bash
# activer-page-web.sh — ouvre ta page Bobine sur Internet (tunnel Cloudflare dédié).
#
# Prérequis : cloudflared installé et connecté au compte (un « cloudflared tunnel
# login » a été fait une fois : il existe un certificat ~/.cloudflared/cert.pem),
# et page_server.py dans le dossier du vault.
#
# Usage :
#   ./activer-page-web.sh bobine.mon-domaine.tld [--vault ~/Bobine] [--tunnel bobine-page]
#
# Le script, sans jamais utiliser sudo :
#   1. crée un mot de passe (PAGE_PASSWORD) si nécessaire, et le note dans config.env ;
#   2. crée (ou réutilise) un tunnel Cloudflare dédié + sa route DNS ;
#   3. installe deux services systemd --user : la page et le tunnel ;
#   4. vérifie que tout répond.
# Ton tunnel ssh existant n'est jamais touché : c'est un tunnel à part.

set -u

HOTE=""; VAULT="$HOME/Bobine"; NOM_TUNNEL="bobine-page"
while [ $# -gt 0 ]; do
  case "$1" in
    --vault)  [ "$#" -ge 2 ] || { echo "Il manque le dossier après --vault."; exit 1; }; VAULT="$2"; shift 2 ;;
    --tunnel) [ "$#" -ge 2 ] || { echo "Il manque le nom après --tunnel."; exit 1; }; NOM_TUNNEL="$2"; shift 2 ;;
    -*) echo "Option inconnue : $1"; exit 1 ;;
    *)  [ -z "$HOTE" ] || { echo "Indique un seul hôte public."; exit 1; }; HOTE="$1"; shift ;;
  esac
done
if [ -z "$HOTE" ]; then
  echo "Usage : ./activer-page-web.sh bobine.mon-domaine.tld [--vault ~/Bobine] [--tunnel bobine-page]"
  exit 1
fi
VAULT="${VAULT/#\~/$HOME}"

ok()   { printf '  ✓ %s\n' "$1"; }
avis() { printf '  ⚠  %s\n' "$1"; }

echo
echo "Bobine — accès web : https://$HOTE"

# ------------------------------------------------------------ 1. prérequis
CLOUDFLARED="$(command -v cloudflared || true)"
PYTHON="$(command -v python3 || true)"
if [ -z "$CLOUDFLARED" ]; then avis "cloudflared introuvable — installe-le d'abord"; exit 1; fi
if [ -z "$PYTHON" ]; then avis "python3 introuvable"; exit 1; fi
# Un hôte uniquement : pas d'URL, chemin, identifiants ou caractères de contrôle.
if ! HOTE="$("$PYTHON" - "$HOTE" "$NOM_TUNNEL" <<'PYTHON'
import re
import sys
host, tunnel = sys.argv[1:]
labels = host.split(".")
valid = (len(host) <= 253 and len(labels) >= 2 and
         all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
             for label in labels) and
         re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", tunnel))
if not valid:
    sys.exit(1)
print(host.lower())
PYTHON
)"; then
  avis "Indique un hôte public sans https:// ni chemin, et un nom de tunnel simple."
  exit 1
fi
VAULT="$(cd "$VAULT" 2>/dev/null && pwd -P)" || { avis "Dossier du vault introuvable."; exit 1; }
UNIT_DIR="$HOME/.config/systemd/user"
YML="$HOME/.cloudflared/$NOM_TUNNEL.yml"
# Refus avant toute écriture ou modification du tunnel d'un autre vault.
if ! "$PYTHON" - "$UNIT_DIR" "$VAULT" "$YML" "$HOTE" <<'PYTHON'
import shlex
import sys
from pathlib import Path
units, vault, yml = map(Path, sys.argv[1:4])
host = sys.argv[4]
page = units / "bobine-page.service"
tunnel = units / "bobine-tunnel.service"
def command(path):
    if path.is_symlink():
        raise ValueError("lien symbolique")
    lines = [line.split("=", 1)[1].strip() for line in path.read_text().splitlines()
             if line.strip().startswith("ExecStart=")]
    if len(lines) != 1:
        raise ValueError("commande ambiguë")
    return [arg.replace("%%", "%").replace("$$", "$") for arg in shlex.split(lines[0])]
try:
    if any(ord(char) < 32 or ord(char) == 127 for char in str(vault) + str(yml)):
        raise ValueError("caractère de contrôle dans un chemin")
    if page.exists() or page.is_symlink():
        args = command(page)
        if args[1:] != [str(vault / "page_server.py"), "--vault", str(vault)]:
            raise ValueError("autre vault")
    if tunnel.exists() or tunnel.is_symlink():
        if not page.exists():
            raise ValueError("tunnel sans propriétaire connu")
        args = command(tunnel)
        if args[1:] != ["--no-autoupdate", "tunnel", "--config", str(yml), "run"]:
            raise ValueError("autre tunnel")
    if yml.is_symlink():
        raise ValueError("configuration liée")
    if yml.exists():
        content = yml.read_text()
        hosts = [line.split("hostname:", 1)[1].strip().strip('"')
                 for line in content.splitlines() if "hostname:" in line]
        if hosts != [host] or "service: http://127.0.0.1:8786" not in content:
            raise ValueError("configuration du tunnel inconnue")
except (OSError, ValueError, IndexError):
    sys.exit(1)
PYTHON
then
  avis "Un service ou tunnel existe déjà pour un autre dossier ou a été personnalisé : rien n'est remplacé."
  exit 1
fi
for unite in bobine-page.service bobine-tunnel.service; do
  if [ ! -e "$UNIT_DIR/$unite" ] && [ "$(systemctl --user show -p LoadState --value "$unite" 2>/dev/null)" = loaded ]; then
    avis "Un service existe ailleurs ($unite) : il est conservé."
    exit 1
  fi
done
if [ ! -f "$HOME/.cloudflared/cert.pem" ]; then
  avis "Pas de certificat Cloudflare (~/.cloudflared/cert.pem)."
  echo "  Lance d'abord :  cloudflared tunnel login"
  exit 1
fi
if [ ! -f "$VAULT/page_server.py" ]; then
  avis "page_server.py introuvable dans $VAULT"
  exit 1
fi
if ! systemctl --user daemon-reload 2>/dev/null; then
  avis "systemd --user n'est pas disponible ici."
  exit 1
fi
ok "prérequis en ordre (cloudflared, python3, certificat, page_server.py)"

# ------------------------------------------------------------ 2. mot de passe
CONFIG="$VAULT/config.env"
# Lecture de texte uniquement. Le secret est généré dans Python, jamais en argument.
# Le remplacement atomique garde tous les réglages sans ouvrir une fenêtre en 644.
if ! MDP_NOUVEAU="$("$PYTHON" - "$CONFIG" "https://$HOTE" <<'PYTHON'
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
config = Path(sys.argv[1])
try:
    if config.is_symlink() or (config.exists() and not stat.S_ISREG(config.stat().st_mode)):
        raise ValueError("config.env doit être un fichier ordinaire")
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    lines = text.splitlines(keepends=True)
    passwords = [line.split("=", 1)[1].strip().strip('"').strip("'") for line in lines
                 if re.match(r"^\s*PAGE_PASSWORD\s*=", line)]
    if len(passwords) > 1:
        raise ValueError("plusieurs mots de passe configurés")
    new = secrets.token_hex(16) if not passwords or not passwords[0] else ""
    kept = [line for line in lines if not re.match(r"^\s*PAGE_ORIGIN\s*=", line)
            and not (new and re.match(r"^\s*PAGE_PASSWORD\s*=", line))]
    updated = "".join(kept)
    if updated and not updated.endswith("\n"):
        updated += "\n"
    if new:
        updated += 'PAGE_PASSWORD="' + new + '"\n'
    updated += 'PAGE_ORIGIN="' + sys.argv[2] + '"\n'
    fd, temp = tempfile.mkstemp(prefix=".config-page-", dir=config.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, config)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print(new)
except (OSError, ValueError):
    print("Impossible de mettre à jour config.env en sécurité.", file=sys.stderr)
    sys.exit(1)
PYTHON
)"; then
  avis "Configuration conservée : vérifie config.env avant de réessayer."
  exit 1
fi
if [ -n "$MDP_NOUVEAU" ]; then
  ok "mot de passe créé dans config.env (lisible par toi seul)"
else
  ok "mot de passe conservé dans config.env (lisible par toi seul)"
fi
ok "origine publique enregistrée : https://$HOTE"

# ------------------------------------------------------------ 3. le tunnel
if cloudflared tunnel list 2>/dev/null | awk -v n="$NOM_TUNNEL" '$2==n {trouve=1} END {exit !trouve}'; then
  ok "tunnel « $NOM_TUNNEL » déjà présent"
else
  cloudflared tunnel create "$NOM_TUNNEL" >/dev/null && ok "tunnel « $NOM_TUNNEL » créé"
fi
UUID="$(cloudflared tunnel list 2>/dev/null | awk -v n="$NOM_TUNNEL" '$2==n {print $1; exit}')"
if [ -z "$UUID" ]; then avis "impossible de retrouver l'identifiant du tunnel"; exit 1; fi

# NB : on donne toujours l'UUID au « route dns » — le CLI peut confondre les
# tunnels quand on lui passe un nom (bug vu en vrai : CNAME vers un autre tunnel).
if cloudflared tunnel route dns --overwrite-dns "$UUID" "$HOTE" >/dev/null 2>&1; then
  ok "route DNS → $HOTE"
else
  avis "la route DNS a échoué — vérifie que le domaine est bien dans ton compte Cloudflare"
fi

# ------------------------------------------------------------ 4. les services
# Arguments distincts et échappés pour systemd, y compris espaces, % et $.
if ! "$PYTHON" - "$UNIT_DIR" "$VAULT" "$YML" "$HOTE" "$UUID" "$PYTHON" "$CLOUDFLARED" <<'PYTHON'
import json
import os
import tempfile
import sys
from pathlib import Path
units, vault, yml = map(Path, sys.argv[1:4])
host, uuid, python, cloudflared = sys.argv[4:]
def arg(value):
    value = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    return '"' + value + '"'
def write(path, text):
    if path.is_symlink():
        raise ValueError("lien symbolique")
    fd, temp = tempfile.mkstemp(prefix=".bobine-page-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
try:
    units.mkdir(parents=True, exist_ok=True)
    write(yml, "tunnel: " + json.dumps(uuid) + "\ncredentials-file: " +
          json.dumps(str(yml.parent / (uuid + ".json"))) + "\ningress:\n  - hostname: " +
          json.dumps(host) + "\n    service: http://127.0.0.1:8786\n  - service: http_status:404\n")
    page_args = [python, vault / "page_server.py", "--vault", vault]
    write(units / "bobine-page.service", "[Unit]\nDescription=Bobine : page avec mot de passe\n\n"
          "[Service]\nType=simple\nExecStart=" + " ".join(map(arg, page_args)) +
          "\nRestart=on-failure\nNoNewPrivileges=true\n\n[Install]\nWantedBy=default.target\n")
    tunnel_args = [cloudflared, "--no-autoupdate", "tunnel", "--config", yml, "run"]
    write(units / "bobine-tunnel.service", "[Unit]\nDescription=Bobine : tunnel de la page\n"
          "After=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nExecStart=" +
          " ".join(map(arg, tunnel_args)) + "\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n")
except (OSError, ValueError):
    print("Impossible d'écrire les services en sécurité.", file=sys.stderr)
    sys.exit(1)
PYTHON
then
  avis "Services non installés : vérifie les fichiers existants."
  exit 1
fi
ok "configuration du tunnel écrite ($YML)"
systemctl --user daemon-reload
systemctl --user enable --now bobine-page.service bobine-tunnel.service 2>/dev/null || true
systemctl --user restart bobine-page.service bobine-tunnel.service 2>/dev/null || true
sleep 3
ok "services installés ($UNIT_DIR)"

# ------------------------------------------------------------ 5. vérifications
if systemctl --user is-active --quiet bobine-page.service; then ok "page : active"; else avis "page : inactive"; fi
if systemctl --user is-active --quiet bobine-tunnel.service; then ok "tunnel : actif"; else avis "tunnel : inactif"; fi
CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8786/health 2>/dev/null || true)"
if [ "$CODE" = "200" ]; then ok "page locale : 200"; else avis "page locale : $CODE"; fi
CODE_PUB="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://$HOTE/" 2>/dev/null || true)"
if [ "$CODE_PUB" = "401" ]; then ok "page publique : 401 (protégée par mot de passe)"; else avis "page publique : $CODE_PUB (attendu 401 — si 404, relance le script)"; fi

echo
if [ -n "$MDP_NOUVEAU" ]; then
  echo "  ➜ TON MOT DE PASSE (note-le, le navigateur te le demandera) : $MDP_NOUVEAU"
  echo "    (il est aussi dans $CONFIG, ligne PAGE_PASSWORD — modifiable à tout moment)"
else
  echo "  ➜ Mot de passe : celui déjà présent dans $CONFIG (ligne PAGE_PASSWORD)"
fi
echo
echo "  Ouvre :  https://$HOTE"
echo "  Pour tout retirer :"
echo "    systemctl --user disable --now bobine-page.service bobine-tunnel.service"
echo "    cloudflared tunnel delete $NOM_TUNNEL"
