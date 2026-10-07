#!/usr/bin/env python3
"""inbox_server.py — reçois des liens par HTTP et dépose-les dans inbox.txt.

Pensé pour un serveur : depuis ton téléphone, un raccourci, ou n'importe où,
tu envoies un lien par une requête POST — il atterrit dans la boîte de
réception de Bobine, que le réveil lit toutes les 15 minutes.

    curl -X POST -H "Authorization: Bearer MONJETON" \\
         -d 'https://www.instagram.com/reel/Cxyz123AbCd/' http://127.0.0.1:8785/push

Le jeton : donne-le avec --token, ou mets INBOX_TOKEN=… dans config.env.
Par défaut, le serveur écoute sur 127.0.0.1 (visible de la machine seule).
Pour l'utiliser à distance, passe par ton tunnel/proxy habituel (Cloudflare
Tunnel, Caddy, Tailscale…) — n'expose jamais ce port en clair sur internet.

Routes :
    GET  /            petite page d'info (sans secret)
    GET  /health      ok
    POST /push        corps = texte ; les liens Instagram/TikTok/YouTube sont
                      extraits et ajoutés à inbox.txt (jeton requis)

Usage :
    python3 inbox_server.py --vault ~/Bobine --token … [--port 8785] [--bind 127.0.0.1]
"""

import argparse
import hmac
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest import MOTIF_LIEN  # même motif que l'ingestion : une seule source

TAILLE_MAX_CORPS = 16 * 1024   # 16 Ko : largement assez pour quelques liens


def extraire_texte(corps):
    """Texte utile d'un corps de requête : si c'est du JSON (les Raccourcis iOS
    en envoient, avec les « / » échappés), on prend les chaînes qu'il contient ;
    sinon le corps tel quel."""
    texte = corps.strip()
    if not texte.startswith(("{", "[")):
        return corps
    try:
        donnees = json.loads(texte)
    except (ValueError, RecursionError):
        return corps

    def collecter(element, morceaux):
        if isinstance(element, str):
            morceaux.append(element)
        elif isinstance(element, dict):
            for valeur in element.values():
                collecter(valeur, morceaux)
        elif isinstance(element, list):
            for item in element:
                collecter(item, morceaux)
        return morceaux

    return "\n".join(collecter(donnees, []))


def liens_du_corps(corps):
    """Extrait les liens reconnus d'un corps de requête (brut ou JSON, dédoublonné)."""
    liens, vus = [], set()
    for lien in MOTIF_LIEN.findall(extraire_texte(corps)):
        lien = lien.rstrip(".,;")
        if lien not in vus:
            vus.add(lien)
            liens.append(lien)
    return liens


def ajouter_a_la_boite(inbox, liens):
    """Ajoute les liens à la boîte (en ajout seul). Retourne le nombre écrit."""
    if not liens:
        return 0
    inbox = Path(inbox)
    inbox.parent.mkdir(parents=True, exist_ok=True)
    with inbox.open("a", encoding="utf-8") as f:
        for lien in liens:
            f.write(lien + "\n")
    return len(liens)


class BoiteHandler(BaseHTTPRequestHandler):
    server_version = "bobine-inbox/0.1"

    def _repondre(self, code, texte):
        corps = (texte + "\n").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _jeton(self, chemin, requete):
        """Jeton accepté : « Authorization: Bearer … », « /push/JETON » ou « ?token=… »."""
        entete = self.headers.get("Authorization", "")
        if entete.startswith("Bearer "):
            return entete[len("Bearer "):].strip()
        if chemin.startswith("/push/"):
            return unquote(chemin[len("/push/"):])
        for morceau in requete.split("&"):
            nom, _, valeur = morceau.partition("=")
            if nom == "token":
                return unquote(valeur)
        return ""

    def do_GET(self):
        chemin = urlsplit(self.path).path
        if chemin in ("/", "/index.html"):
            self._repondre(200, "Bobine — boîte à liens.\n"
                                "Dépose un lien :  POST /push  (jeton requis)")
        elif chemin == "/health":
            self._repondre(200, "ok")
        else:
            self._repondre(404, "inconnu")

    def do_POST(self):
        morceaux = urlsplit(self.path)
        chemin = morceaux.path
        if chemin != "/push" and not chemin.startswith("/push/"):
            self._repondre(404, "inconnu — utilise POST /push")
            return

        jeton = self._jeton(chemin, morceaux.query)
        if not jeton or not hmac.compare_digest(jeton.encode(), self.server.jeton.encode()):
            self._repondre(401, "jeton manquant ou invalide")
            return

        try:
            taille = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            taille = 0
        if taille <= 0 or taille > TAILLE_MAX_CORPS:
            print("POST /push — refusé : corps absent ou trop grand (Content-Length: %s)" % (self.headers.get("Content-Length"),), flush=True)
            self._repondre(400, "corps vide ou trop grand")
            return

        corps = self.rfile.read(taille).decode("utf-8", errors="ignore")
        liens = liens_du_corps(corps)
        if not liens:
            print("POST /push — refusé : aucun lien reconnu dans %d octets reçus : %r" % (len(corps), corps[:120]), flush=True)
            self._repondre(400, "aucun lien Instagram/TikTok/YouTube reconnu")
            return

        nombre = ajouter_a_la_boite(self.server.inbox, liens)
        print("%s — %d lien(s) ajouté(s) à %s" % (self.client_address[0], nombre, self.server.inbox), flush=True)
        self._repondre(202, "%d lien(s) ajouté(s) à la boîte" % nombre)


def jeton_de_config(vault, script):
    """Lit INBOX_TOKEN dans config.env (vault, puis dossier du script)."""
    for dossier in (vault, script):
        fichier = Path(dossier) / "config.env"
        if not fichier.is_file():
            continue
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne.startswith("INBOX_TOKEN="):
                return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main():
    ap = argparse.ArgumentParser(description="Bobine — boîte à liens par HTTP.")
    ap.add_argument("--vault", default=str(Path(__file__).resolve().parent),
                    help="dossier du vault (défaut : le dossier de ce script)")
    ap.add_argument("--inbox", default=None,
                    help="fichier boîte (défaut : VAULT/inbox.txt)")
    ap.add_argument("--token", default=None,
                    help="jeton attendu (défaut : INBOX_TOKEN de config.env)")
    ap.add_argument("--port", type=int, default=8785)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    inbox = Path(args.inbox).expanduser() if args.inbox else vault / "inbox.txt"

    jeton = args.token or jeton_de_config(vault, Path(__file__).resolve().parent)
    if not jeton:
        print("Il faut un jeton : --token MONJETON, ou INBOX_TOKEN=… dans config.env.")
        print("Pour en fabriquer un :  openssl rand -hex 16")
        return 1

    serveur = ThreadingHTTPServer((args.bind, args.port), BoiteHandler)
    serveur.jeton = jeton
    serveur.inbox = inbox
    print("Bobine — boîte à liens : POST http://%s:%d/push  →  %s" % (args.bind, args.port, inbox))
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
