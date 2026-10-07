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
    --vault)  VAULT="$2"; shift 2 ;;
    --tunnel) NOM_TUNNEL="$2"; shift 2 ;;
    -*) echo "Option inconnue : $1"; exit 1 ;;
    *)  HOTE="$1"; shift ;;
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
MDP_NOUVEAU=""
if grep -q '^PAGE_PASSWORD=' "$CONFIG" 2>/dev/null; then
  ok "mot de passe déjà présent dans config.env"
else
  MDP="$(openssl rand -hex 16 2>/dev/null || head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  printf 'PAGE_PASSWORD="%s"\n' "$MDP" >> "$CONFIG"
  MDP_NOUVEAU="$MDP"
  ok "mot de passe créé et ajouté à config.env"
fi

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

YML="$HOME/.cloudflared/$NOM_TUNNEL.yml"
printf 'tunnel: %s\ncredentials-file: %s/.cloudflared/%s.json\n' "$UUID" "$HOME" "$UUID" > "$YML"
printf 'ingress:\n  - hostname: %s\n    service: http://127.0.0.1:8786\n  - service: http_status:404\n' "$HOTE" >> "$YML"
ok "configuration du tunnel écrite ($YML)"

# ------------------------------------------------------------ 4. les services
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/bobine-page.service" <<EOF
[Unit]
Description=Bobine — sert la page (vault.html + graph.html, mot de passe)

[Service]
Type=simple
ExecStart=$PYTHON $VAULT/page_server.py --vault $VAULT
Restart=on-failure
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
cat > "$UNIT_DIR/bobine-tunnel.service" <<EOF
[Unit]
Description=Bobine — tunnel Cloudflare (page à distance)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$CLOUDFLARED --no-autoupdate tunnel --config $YML run
Restart=on-failure

[Install]
WantedBy=default.target
EOF
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
